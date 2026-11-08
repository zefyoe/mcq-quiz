/* Internal-only interactions. No patient data is written to browser storage. */
(() => {
  const script = document.currentScript;
  async function request(url, options = {}, format = 'json') {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store',
        headers: {'X-Requested-With': 'XMLHttpRequest', ...options.headers}});
      if (response.redirected || response.status === 401 || response.status === 403) {
        throw new Error('Votre session a expiré ou l’accès est refusé. Gardez ce panneau ouvert et reconnectez-vous dans un autre onglet.');
      }
      if (format === 'pdf' && response.ok && response.headers.get('Content-Type')?.includes('application/pdf')) {
        return {blob: await response.blob(), disposition: response.headers.get('Content-Disposition')};
      }
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.ok === false || result.error) {
        throw new Error(result.error || 'Action non confirmée. Vos données restent dans le panneau. Réessayez.');
      }
      if (!response.headers.get('Content-Type')?.includes('application/json') || format === 'pdf') {
        throw new Error('Réponse inattendue. Vérifiez votre session puis réessayez.');
      }
      return result;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Le serveur met trop de temps à répondre. Votre texte reste ici. Réessayez : aucun doublon de compte rendu ne sera créé.');
      if (error instanceof TypeError) throw new Error('Connexion interrompue. Vos données restent ici. Vérifiez le réseau puis réessayez.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  window.internalAgenda = {request};
  const feedback = document.getElementById('availability-feedback');
  function notify(message) { feedback.hidden = false; feedback.textContent = message; }
  function updateSlot(start, isOpen) {
    const cell = [...document.querySelectorAll('.appointment-slot-cell[data-start]')].find(e => e.dataset.start === start);
    const form = cell?.querySelector('.appointment-slot-toggle');
    if (!form) return; // Occupied slots never get replaced.
    const current = cell.querySelector('[data-slot], .appointment-slot-blocked');
    const replacement = document.createElement(isOpen ? 'button' : 'div');
    replacement.className = 'appointment-slot ' + (isOpen ? 'appointment-slot-available' : 'appointment-slot-blocked');
    if (isOpen) {
      replacement.type = 'button'; replacement.dataset.slot = start;
      replacement.dataset.slotLabel = new Date(start).toLocaleString('fr-BE', {dateStyle:'full', timeStyle:'short'});
      const label = document.createElement('span'); label.textContent = 'Libre';
      const clock = document.createElement('small'); clock.textContent = start.slice(11,16);
      replacement.append(label, clock);
    } else replacement.textContent = 'Fermé par le cabinet';
    current?.replaceWith(replacement);
    cell.classList.toggle('is-open', isOpen);
    form.elements.is_open.value = isOpen ? '0' : '1';
    form.querySelector('button').textContent = isOpen ? 'Fermer' : 'Ouvrir';
    const counter = document.querySelector('[data-available-count]');
    if (counter) counter.textContent = document.querySelectorAll('.appointment-slot-cell [data-slot]').length;
  }
  let availabilityBusy = false;
  const hoursDialog = document.getElementById('day-hours-dialog');
  const hoursForm = document.getElementById('day-hours-form');
  const gridContainer = document.getElementById('internal-calendar-grid');
  async function refreshCalendar(day) {
    if(day && !gridContainer.querySelector('[data-day-action][data-day="'+day+'"]')) {
      window.location.assign('/admin/appointments?date='+encodeURIComponent(day));
      return;
    }
    try {
      const result = await request(gridContainer.dataset.endpoint);
      gridContainer.innerHTML = result.html;
      const counter=document.querySelector('[data-available-count]');
      if(counter) counter.textContent=result.available_count;
    } catch(error) {
      throw new Error('Les horaires sont enregistrés, mais l’affichage n’a pas pu être actualisé. Actualisez l’agenda pour voir les changements. '+error.message);
    }
  }
  function closeHours() {
    hoursDialog.hidden=true; document.body.classList.remove('appointment-modal-open');
  }
  function openHours(button) {
    if(availabilityBusy) return;
    closeDayMenus();
    closeBooking();
    hoursForm.elements.day.value=button.dataset.dayHours;
    hoursForm.elements.start_time.value=button.dataset.startTime || '18:30';
    hoursForm.elements.end_time.value=button.dataset.endTime || '20:10';
    hoursForm.elements.action.value='replace';
    document.getElementById('day-hours-error').textContent='';
    hoursDialog.hidden=false; document.body.classList.add('appointment-modal-open');
    hoursForm.elements.start_time.focus();
  }
  async function saveHours(action=null) {
    if(availabilityBusy) return;
    if(!action && !hoursForm.reportValidity()) return;
    if(!hoursForm.elements.day.reportValidity()) return;
    const body=new FormData(hoursForm); body.set('csrf_token',script.dataset.csrf);
    if(action) {body.set('action',action);body.delete('start_time');body.delete('end_time');}
    const day=body.get('day');
    availabilityBusy=true;
    const controls=[...hoursDialog.querySelectorAll('button,input,select')];
    controls.forEach(item=>{item.disabled=true;});
    document.getElementById('day-hours-error').textContent='';
    let saved=false;
    try {
      const result=await request(script.dataset.dayEndpoint,{method:'POST',body});
      saved=true;
      await refreshCalendar(day);
      notify('Horaires du '+new Date(day+'T12:00:00').toLocaleDateString('fr-BE')+' enregistrés. L’agenda public suit ces disponibilités. '+result.protected_count+' créneau(x) occupé(s) conservé(s).');
      closeHours();
    } catch(error) {document.getElementById('day-hours-error').textContent=error.message;if(saved) notify(error.message);}
    finally {availabilityBusy=false;controls.forEach(item=>{item.disabled=false;});}
  }
  hoursForm.addEventListener('submit',event=>{event.preventDefault();saveHours();});
  hoursDialog.querySelectorAll('[data-close-day-hours]').forEach(button=>button.addEventListener('click',()=>{if(!availabilityBusy) closeHours();}));
  hoursDialog.querySelectorAll('[data-hours-action]').forEach(button=>button.addEventListener('click',()=>saveHours(button.dataset.hoursAction)));
  function closeDayMenus(except = null) {
    document.querySelectorAll('.day-menu[open]').forEach(menu => {
      if (menu !== except) menu.removeAttribute('open');
    });
  }
  const riziv = document.getElementById('riziv-list');
  let rizivLoading = null;
  async function loadRiziv() {
    if (rizivLoading) return rizivLoading;
    const status = document.getElementById('riziv-status');
    document.getElementById('riziv-refresh').disabled = true;
    document.getElementById('riziv-print').disabled = true;
    status.textContent = 'Chargement de tous les patients…';
    rizivLoading = (async () => {
      try {
        const result = await request(riziv.dataset.endpoint);
        // HTML is rendered by our authenticated, same-origin Jinja template;
        // all patient-supplied values are escaped on the server.
        document.getElementById('riziv-patients').innerHTML = result.html;
        document.getElementById('riziv-total').textContent = result.total;
        document.getElementById('riziv-print').disabled = false;
        status.textContent = result.total ? 'Liste complète · ordre chronologique.' : 'Aucun patient enregistré.';
        document.dispatchEvent(new Event('internal-patient-list-updated'));
      } catch (error) { status.textContent = error.message + ' Cliquez sur Actualiser pour réessayer.'; }
      finally { document.getElementById('riziv-refresh').disabled = false; rizivLoading = null; }
    })();
    return rizivLoading;
  }
  window.internalAgenda.refreshRiziv = loadRiziv;
  document.getElementById('riziv-refresh').addEventListener('click', loadRiziv);
  document.getElementById('riziv-print').addEventListener('click', () => window.print());
  window.addEventListener('beforeprint', () => {
    document.body.classList.toggle('printing-riziv', !riziv.hidden);
  });
  window.addEventListener('afterprint', () => document.body.classList.remove('printing-riziv'));
  // Native exclusive details groups, with a fallback for older browsers and
  // assistive-technology toggles. Clicking outside also dismisses the menu.
  document.addEventListener('toggle', event => {
    if (event.target.matches?.('.day-menu') && event.target.open) closeDayMenus(event.target);
  }, true);
  document.addEventListener('click', async event => {
    closeDayMenus(event.target.closest('.day-menu'));
    const hoursButton=event.target.closest('[data-day-hours]');
    if(hoursButton) openHours(hoursButton);
    const view = event.target.closest('[data-agenda-view]');
    if (view) {
      const patients = view.dataset.agendaView === 'patients';
      const allPatients = view.dataset.agendaView === 'riziv';
      const history = view.dataset.agendaView === 'history';
      document.getElementById('patient-list').hidden = !patients;
      document.getElementById('internal-calendar').hidden = patients || allPatients || history;
      riziv.hidden = !allPatients;
      document.getElementById('history-list').hidden = !history;
      document.body.classList.toggle('riziv-view-active', allPatients);
      document.body.classList.toggle('history-view-active', history);
      document.querySelectorAll('[data-agenda-view]').forEach(b => b.setAttribute('aria-pressed', String(b === view)));
      document.dispatchEvent(new Event('internal-patient-list-updated'));
      if (allPatients) await loadRiziv();
      if (history) await window.internalHistory?.loadList();
    }
    const button = event.target.closest('[data-day-action]');
    if (!button || availabilityBusy) return;
    const open = button.dataset.dayAction === 'open', day = button.dataset.day;
    const label = new Date(day+'T12:00:00').toLocaleDateString('fr-BE');
    // Reversible and limited to unoccupied slots: one click, no blocking dialog.
    availabilityBusy = true;
    const controls = [...document.querySelectorAll('[data-day-action]:not([data-past-day]), .appointment-slot-toggle button')];
    controls.forEach(b => { b.disabled = true; });
    const body = new FormData(); body.set('csrf_token', script.dataset.csrf);
    body.set('day', day); body.set('action', open ? 'open' : 'close');
    notify('Mise à jour de la journée…');
    try {
      const result = await request(script.dataset.dayEndpoint, {method:'POST', body});
      await refreshCalendar(day);
      notify(label + ' · ' + result.changed_slots.length + ' créneau(x) ' + (open ? 'ouvert(s).' : 'fermé(s).') +
        ' L’agenda public suit ces disponibilités. Les rendez-vous existants sont conservés.');
      button.closest('details')?.removeAttribute('open');
    } catch (error) { notify(error.message); }
    finally { availabilityBusy = false; controls.forEach(b => { b.disabled = false; }); }
  });
  // A slot toggle only updates the server-confirmed timestamp.
  document.addEventListener('submit', async event => {
    const form = event.target.closest('.appointment-slot-toggle');
    if (!form) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (availabilityBusy) return;
    availabilityBusy = true;
    const buttons = [...document.querySelectorAll('[data-day-action]:not([data-past-day]), .appointment-slot-toggle button')];
    buttons.forEach(b => { b.disabled = true; });
    const body = new FormData(form);
    try {
      const result = await request(form.action, {method:'POST', body});
      await refreshCalendar();
      notify('Créneau de ' + result.starts_at.slice(11,16) + (result.is_open ? ' ouvert.' : ' fermé.'));
    } catch (error) { notify(error.message); }
    finally { availabilityBusy = false; buttons.forEach(b => { b.disabled = false; }); }
  }, true);
  const booking = document.getElementById('appointment-modal');
  function closeBooking() { booking.hidden = true; document.body.classList.remove('appointment-modal-open'); }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-slot]');
    if (!button || !button.closest('#internal-calendar-grid')) return;
    document.getElementById('appointment-slot-start').value = button.dataset.slot;
    document.getElementById('appointment-selected-slot').textContent = button.dataset.slotLabel;
    booking.hidden = false; document.body.classList.add('appointment-modal-open');
    booking.querySelector('[name=patient_name]').focus();
  });
  document.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', closeBooking));
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    closeDayMenus();
    if (!booking.hidden) closeBooking();
    if (!hoursDialog.hidden && !availabilityBusy) closeHours();
  });
  const uploads = [...booking.querySelectorAll('[data-prescription-input]')];
  uploads.forEach(input => input.addEventListener('change', () => {
    if (!input.files.length) return;
    uploads.filter(other => other !== input).forEach(other => { other.value = ''; });
    const status = booking.querySelector('[data-upload-status="' + (input.id.includes('photo') ? 'photo' : 'file') + '"]');
    if (status) status.textContent = input.files[0].name;
  }));
})();
