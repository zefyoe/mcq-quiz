/* Pointer-based drag/drop (mouse, iPad touch, pen) plus a keyboard/tap fallback. */
(() => {
  const $=id=>document.getElementById(id), dialog=$('move-appointment-dialog');
  const agenda=window.internalAgenda, trashDrop=$('appointment-trash-drop'), trashDialog=$('appointment-trash-dialog');
  let gesture=null, picked=null, pending=null, busy=false, ignoreClickUntil=0;
  const stampLabel=stamp=>new Date(stamp).toLocaleString('fr-BE',{dateStyle:'full',timeStyle:'short'});
  function notify(message,error=false) {
    const target=$('availability-feedback');target.hidden=false;target.textContent=message;
    target.classList.toggle('move-feedback-error',error);
  }
  function sourceOf(card) {
    return {kind:card.dataset.moveKind,id:card.dataset.moveId,start:card.dataset.moveStart,
      key:card.dataset.moveKey,name:card.dataset.moveName,duration:Number(card.dataset.moveDuration)||10};
  }
  function clearHighlights() {
    document.querySelectorAll('.move-target-valid,.move-target-invalid,.move-source').forEach(e=>e.classList.remove('move-target-valid','move-target-invalid','move-source'));
    document.body.classList.remove('appointment-picking');
    trashDrop.classList.remove('is-target');
  }
  function clearPick() {picked=null;clearHighlights();}
  function highlightSource(source) {
    document.querySelectorAll('[data-move-card]').forEach(card=>card.classList.toggle('move-source',card.dataset.moveKey===source.key));
  }
  function addMinutes(stamp,offset) {
    const minute=Number(stamp.slice(11,13))*60+Number(stamp.slice(14,16))+offset;
    return stamp.slice(0,11)+String(Math.floor(minute/60)).padStart(2,'0')+':'+String(minute%60).padStart(2,'0');
  }
  function validate(source,cell) {
    if(!cell?.dataset.start) return 'Déposez le rendez-vous sur une case marquée « Libre ».';
    for(let offset=0;offset<source.duration;offset+=10) {
      const stamp=addMinutes(cell.dataset.start,offset);
      const part=document.querySelector('.appointment-slot-cell[data-start="'+stamp+'"]');
      if(!part) return 'La durée du rendez-vous dépasse les créneaux visibles ou ouverts.';
      if(part.dataset.dropState==='occupied') return 'Ce créneau est déjà occupé. Choisissez une case libre.';
      if(part.dataset.dropState!=='free') return 'Ce créneau est fermé ou passé. Choisissez une case libre.';
    }
    return '';
  }
  function preview(source,cell) {
    document.querySelectorAll('.move-target-valid,.move-target-invalid').forEach(e=>e.classList.remove('move-target-valid','move-target-invalid'));
    const error=validate(source,cell);
    cell?.classList.add(error?'move-target-invalid':'move-target-valid');
    return error;
  }
  function cancel() {
    if(busy) return;
    const attempted=pending?.attempted;
    pending=null;dialog.hidden=true;document.body.classList.remove('appointment-modal-open');clearPick();
    if(attempted) agenda.refreshCalendar().catch(error=>notify(error.message,true));
  }
  function propose(source,cell) {
    const error=validate(source,cell);
    clearPick();
    if(error) {notify(error,true);return;}
    if(agenda.availabilityIsBusy()) {notify('Attendez la fin de la modification des horaires.',true);return;}
    if(window.internalReporting&&!window.internalReporting.close()) return;
    if(window.internalHistory&&!window.internalHistory.close()) return;
    pending={source,target:cell.dataset.start,mode:'move',token:crypto.randomUUID(),attempted:false};
    $('move-appointment-title').textContent='Déplacer le rendez-vous ?';
    $('confirm-appointment-move').textContent='Oui, déplacer';
    $('confirm-appointment-move').classList.remove('trash-confirm-button');
    $('move-to-time').closest('div').hidden=false;
    $('move-confirm-description').textContent='Le patient, l’examen, le statut, la demande et le compte rendu sont conservés. L’ancien créneau est libéré après confirmation.';
    $('move-patient-name').textContent=source.name;
    $('move-from-time').textContent=stampLabel(source.start);
    $('move-to-time').textContent=stampLabel(pending.target);
    $('move-confirm-error').textContent='';
    dialog.hidden=false;document.body.classList.add('appointment-modal-open');
    dialog.querySelector('button[data-cancel-move]').focus();
  }
  function proposeTrash(source) {
    clearPick();
    if(agenda.availabilityIsBusy()) {notify('Attendez la fin de la modification des horaires.',true);return;}
    if(window.internalReporting&&!window.internalReporting.close()) return;
    if(window.internalHistory&&!window.internalHistory.close()) return;
    pending={source,mode:'trash',token:crypto.randomUUID(),attempted:false};
    $('move-appointment-title').textContent='Retirer ce rendez-vous de l’agenda ?';
    $('confirm-appointment-move').textContent='Oui, mettre à la corbeille';
    $('confirm-appointment-move').classList.add('trash-confirm-button');
    $('move-patient-name').textContent=source.name;
    $('move-from-time').textContent=stampLabel(source.start);
    $('move-to-time').closest('div').hidden=true;
    $('move-confirm-description').textContent='Le créneau sera libéré. Les données du patient, la demande et le compte rendu seront conservés dans la corbeille. Vous pourrez rétablir le rendez-vous.';
    $('move-confirm-error').textContent='';
    dialog.hidden=false;document.body.classList.add('appointment-modal-open');
    dialog.querySelector('button[data-cancel-move]').focus();
  }
  async function confirmMove() {
    if(busy||!pending) return;
    busy=true;pending.attempted=true;
    const operation=pending, source=operation.source, body=new FormData();
    body.set('csrf_token',dialog.dataset.csrf);body.set('move_token',operation.token);
    body.set('appointment_id',source.id);body.set('reservation_start',source.kind==='reservation'?source.start:'');
    body.set('expected_start',source.start);body.set('expected_key',source.key);
    if(operation.mode==='move') body.set('target_start',operation.target);
    dialog.querySelectorAll('button').forEach(e=>{e.disabled=true;});
    const trash=operation.mode==='trash';
    $('move-confirm-error').textContent=trash?'Retrait en cours…':'Déplacement en cours…';
    let saved=false;
    try {
      await agenda.request(trash?dialog.dataset.trashEndpoint:dialog.dataset.endpoint,{method:'POST',body});saved=true;
      await agenda.refreshCalendar((operation.target||source.start).slice(0,10));
      pending=null;dialog.hidden=true;document.body.classList.remove('appointment-modal-open');
      notify(trash?'Rendez-vous retiré de l’agenda. Le créneau est libre. Les données restent dans la corbeille.':'Rendez-vous déplacé au '+stampLabel(operation.target)+'. L’ancien créneau est libéré. Toutes les données ont été conservées.');
    } catch(error) {
      if(saved) {pending=null;dialog.hidden=true;document.body.classList.remove('appointment-modal-open');notify((trash?'Le rendez-vous est dans la corbeille. ':'Le rendez-vous a été déplacé. ')+error.message,true);}
      else $('move-confirm-error').textContent=error.message;
    } finally {busy=false;dialog.querySelectorAll('button').forEach(e=>{e.disabled=false;});}
  }
  $('confirm-appointment-move').addEventListener('click',confirmMove);
  dialog.querySelectorAll('[data-cancel-move]').forEach(e=>e.addEventListener('click',cancel));

  async function loadTrash() {
    $('appointment-trash-status').textContent='Chargement…';
    $('appointment-trash-items').replaceChildren();
    try {
      const result=await agenda.request(dialog.dataset.trashEndpoint);
      $('appointment-trash-status').textContent=result.items.length?result.items.length+' rendez-vous dans la corbeille.':'La corbeille est vide.';
      result.items.forEach(item=>{
        const row=document.createElement('div'), info=document.createElement('div'), name=document.createElement('strong'), date=document.createElement('small'), button=document.createElement('button');
        row.className='appointment-trash-row';name.textContent=item.patient_name;date.textContent=stampLabel(item.starts_at);
        info.append(name,date);button.type='button';button.textContent='Rétablir';button.dataset.restoreTrash=item.token;
        row.append(info,button);$('appointment-trash-items').append(row);
      });
    } catch(error) {$('appointment-trash-status').textContent=error.message;}
  }
  $('open-appointment-trash').addEventListener('click',()=>{
    if(busy||pending||agenda.availabilityIsBusy()) return;
    if(window.internalReporting&&!window.internalReporting.close()) return;
    if(window.internalHistory&&!window.internalHistory.close()) return;
    clearPick();trashDialog.hidden=false;document.body.classList.add('appointment-modal-open');
    trashDialog.querySelector('button[data-close-trash]').focus();loadTrash();
  });
  function closeTrash() {if(busy) return;trashDialog.hidden=true;document.body.classList.remove('appointment-modal-open');}
  trashDialog.querySelectorAll('[data-close-trash]').forEach(button=>button.addEventListener('click',closeTrash));
  trashDialog.addEventListener('click',async event=>{
    const button=event.target.closest('[data-restore-trash]');
    if(!button||busy) return;
    busy=true;trashDialog.querySelectorAll('button').forEach(b=>{b.disabled=true;});
    const body=new FormData();body.set('csrf_token',dialog.dataset.csrf);
    let saved=false;
    try {
      await agenda.request(dialog.dataset.trashEndpoint+'/'+encodeURIComponent(button.dataset.restoreTrash)+'/restore',{method:'POST',body});saved=true;
      await agenda.refreshCalendar();await loadTrash();
      $('appointment-trash-status').textContent='Rendez-vous rétabli à son horaire initial.';
    } catch(error) {$('appointment-trash-status').textContent=(saved?'Le rendez-vous est rétabli. ':'')+error.message;}
    finally {busy=false;trashDialog.querySelectorAll('button').forEach(b=>{b.disabled=false;});}
  });

  function endGesture() {
    const previous=gesture;if(!previous) return null;
    gesture=null;cancelAnimationFrame(previous.frame);previous.ghost?.remove();
    try {previous.capture.releasePointerCapture(previous.id);} catch {}
    document.body.classList.remove('appointment-dragging');clearHighlights();
    return previous;
  }
  function animate() {
    if(!gesture?.active) return;
    const {x,y,source,ghost}=gesture;
    ghost.style.left=Math.max(4,Math.min(x+14,innerWidth-210))+'px';ghost.style.top=Math.max(4,Math.min(y+12,innerHeight-100))+'px';
    const scroll=document.querySelector('.appointment-calendar-scroll'), box=scroll.getBoundingClientRect();
    if(x>=box.left-30&&x<=box.right+30&&y>=box.top-30&&y<=box.bottom+30) {
      const dx=x<box.left+35?-12:x>box.right-35?12:0;
      const dy=y<box.top+35?-12:y>box.bottom-35?12:0;
      if(dx||dy) scroll.scrollBy(dx,dy);
    }
    if(y<35) window.scrollBy(0,-10);else if(y>innerHeight-35) window.scrollBy(0,10);
    const hit=document.elementFromPoint(x,y), overTrash=Boolean(hit?.closest('#appointment-trash-drop'));
    trashDrop.classList.toggle('is-target',overTrash);
    const cell=hit?.closest('.appointment-slot-cell');
    preview(source,cell);
    gesture.frame=requestAnimationFrame(animate);
  }
  document.addEventListener('pointerdown',event=>{
    const card=event.target.closest('[data-move-card]');
    if(!card||busy||pending||!trashDialog.hidden||agenda.availabilityIsBusy()||event.button!==0) return;
    const handle=event.target.closest('[data-move-handle]');
    if(picked&&!handle) return;
    if(!handle&&(event.pointerType!=='mouse'||event.target.closest('button,a,input,select,summary,details'))) return;
    clearPick();
    gesture={id:event.pointerId,capture:handle||card,source:sourceOf(card),initialX:event.clientX,initialY:event.clientY,x:event.clientX,y:event.clientY,active:false,frame:0};
    try {gesture.capture.setPointerCapture(event.pointerId);} catch {}
  });
  document.addEventListener('pointermove',event=>{
    if(!gesture||gesture.id!==event.pointerId) return;
    gesture.x=event.clientX;gesture.y=event.clientY;
    if(!gesture.active&&Math.hypot(gesture.x-gesture.initialX,gesture.y-gesture.initialY)>7) {
      gesture.active=true;
      const ghost=document.createElement('div');ghost.className='appointment-drag-ghost';ghost.setAttribute('aria-hidden','true');
      ghost.textContent=gesture.source.name+' · '+gesture.source.duration+' min';document.body.append(ghost);gesture.ghost=ghost;
      document.body.classList.add('appointment-dragging');highlightSource(gesture.source);animate();
    }
    if(gesture.active) event.preventDefault();
  },{passive:false});
  document.addEventListener('pointerup',event=>{
    if(!gesture||gesture.id!==event.pointerId) return;
    const hit=document.elementFromPoint(event.clientX,event.clientY), cell=hit?.closest('.appointment-slot-cell'), overTrash=Boolean(hit?.closest('#appointment-trash-drop'));
    const previous=endGesture();
    if(previous.active) {ignoreClickUntil=performance.now()+500;event.preventDefault();if(overTrash) proposeTrash(previous.source);else propose(previous.source,cell);}
  });
  document.addEventListener('pointercancel',()=>{endGesture();});
  window.addEventListener('blur',()=>{endGesture();});
  document.addEventListener('dragstart',event=>{if(event.target.closest('[data-move-card]')) event.preventDefault();});
  document.addEventListener('click',event=>{
    if(event.target.closest('#appointment-trash-drop')&&picked) {event.preventDefault();event.stopImmediatePropagation();proposeTrash(picked);return;}
    if(performance.now()<ignoreClickUntil&&event.target.closest('.appointment-calendar-grid')) {event.preventDefault();event.stopImmediatePropagation();return;}
    const handle=event.target.closest('[data-move-handle]');
    if(handle) {
      event.preventDefault();event.stopImmediatePropagation();
      if(busy||pending||!trashDialog.hidden||agenda.availabilityIsBusy()) return;
      clearPick();picked=sourceOf(handle.closest('[data-move-card]'));highlightSource(picked);
      document.body.classList.add('appointment-picking');
      notify('Choisissez une case libre pour '+picked.name+', ou appuyez sur Échap pour annuler.');return;
    }
    const cell=event.target.closest('.appointment-slot-cell');
    if(picked&&cell) {event.preventDefault();event.stopImmediatePropagation();propose(picked,cell);}
  },true);
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape') {endGesture();cancel();closeTrash();clearPick();}
    const modal=!dialog.hidden?dialog:!trashDialog.hidden?trashDialog:null;
    if(event.key==='Tab'&&modal) {
      const buttons=[...modal.querySelectorAll('button:not([disabled])')];
      const index=buttons.indexOf(document.activeElement);
      if(buttons.length&&((event.shiftKey&&index<=0)||(!event.shiftKey&&index===buttons.length-1))) {
        event.preventDefault();buttons[event.shiftKey?buttons.length-1:0].focus();
      }
    }
  });
})();
