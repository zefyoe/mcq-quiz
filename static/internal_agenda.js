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
  document.addEventListener('click', async event => {
    const view = event.target.closest('[data-agenda-view]');
    if (view) {
      const patients = view.dataset.agendaView === 'patients';
      document.getElementById('patient-list').hidden = !patients;
      document.getElementById('internal-calendar').hidden = patients;
      document.querySelectorAll('[data-agenda-view]').forEach(b => b.setAttribute('aria-pressed', String(b === view)));
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
    body.set('day', day); body.set('is_open', open ? '1' : '0');
    notify('Mise à jour de la journée…');
    try {
      const result = await request(script.dataset.dayEndpoint, {method:'POST', body});
      result.changed_slots.forEach(start => updateSlot(start, result.is_open));
      notify(label + ' · ' + result.changed_slots.length + ' créneau(x) ' + (open ? 'ouvert(s).' : 'fermé(s).') +
        ' Les rendez-vous existants sont conservés.' + (open && !result.changed_slots.length ? ' Aucun autre créneau prévu à ouvrir.' : ''));
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
      updateSlot(result.starts_at, result.is_open);
      notify('Créneau de ' + result.starts_at.slice(11,16) + (result.is_open ? ' ouvert.' : ' fermé.'));
    } catch (error) { notify(error.message); }
    finally { availabilityBusy = false; buttons.forEach(b => { b.disabled = false; }); }
  }, true);
  const booking = document.getElementById('appointment-modal');
  function closeBooking() { booking.hidden = true; document.body.classList.remove('appointment-modal-open'); }
  document.querySelector('.appointment-calendar-grid').addEventListener('click', event => {
    const button = event.target.closest('[data-slot]');
    if (!button) return;
    document.getElementById('appointment-slot-start').value = button.dataset.slot;
    document.getElementById('appointment-selected-slot').textContent = button.dataset.slotLabel;
    booking.hidden = false; document.body.classList.add('appointment-modal-open');
    booking.querySelector('[name=patient_name]').focus();
  });
  document.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', closeBooking));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !booking.hidden) closeBooking(); });
  const uploads = [...booking.querySelectorAll('[data-prescription-input]')];
  uploads.forEach(input => input.addEventListener('change', () => {
    if (!input.files.length) return;
    uploads.filter(other => other !== input).forEach(other => { other.value = ''; });
    const status = booking.querySelector('[data-upload-status="' + (input.id.includes('photo') ? 'photo' : 'file') + '"]');
    if (status) status.textContent = input.files[0].name;
  }));
})();
