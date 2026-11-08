/* Pointer-based drag/drop (mouse, iPad touch, pen) plus a keyboard/tap fallback. */
(() => {
  const $=id=>document.getElementById(id), dialog=$('move-appointment-dialog');
  const agenda=window.internalAgenda;
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
    pending={source,target:cell.dataset.start,token:crypto.randomUUID(),attempted:false};
    $('move-patient-name').textContent=source.name;
    $('move-from-time').textContent=stampLabel(source.start);
    $('move-to-time').textContent=stampLabel(pending.target);
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
    body.set('expected_start',source.start);body.set('expected_key',source.key);body.set('target_start',operation.target);
    dialog.querySelectorAll('button').forEach(e=>{e.disabled=true;});
    $('move-confirm-error').textContent='Déplacement en cours…';
    let saved=false;
    try {
      await agenda.request(dialog.dataset.endpoint,{method:'POST',body});saved=true;
      await agenda.refreshCalendar(operation.target.slice(0,10));
      pending=null;dialog.hidden=true;document.body.classList.remove('appointment-modal-open');
      notify('Rendez-vous déplacé au '+stampLabel(operation.target)+'. Toutes les données ont été conservées.');
    } catch(error) {
      if(saved) {pending=null;dialog.hidden=true;document.body.classList.remove('appointment-modal-open');notify('Le rendez-vous a été déplacé. '+error.message,true);}
      else $('move-confirm-error').textContent=error.message;
    } finally {busy=false;dialog.querySelectorAll('button').forEach(e=>{e.disabled=false;});}
  }
  $('confirm-appointment-move').addEventListener('click',confirmMove);
  dialog.querySelectorAll('[data-cancel-move]').forEach(e=>e.addEventListener('click',cancel));

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
    const cell=document.elementFromPoint(x,y)?.closest('.appointment-slot-cell');
    preview(source,cell);
    gesture.frame=requestAnimationFrame(animate);
  }
  document.addEventListener('pointerdown',event=>{
    const card=event.target.closest('[data-move-card]');
    if(!card||busy||pending||agenda.availabilityIsBusy()||event.button!==0) return;
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
    const cell=document.elementFromPoint(event.clientX,event.clientY)?.closest('.appointment-slot-cell');
    const previous=endGesture();
    if(previous.active) {ignoreClickUntil=performance.now()+500;event.preventDefault();propose(previous.source,cell);}
  });
  document.addEventListener('pointercancel',()=>{endGesture();});
  window.addEventListener('blur',()=>{endGesture();});
  document.addEventListener('dragstart',event=>{if(event.target.closest('[data-move-card]')) event.preventDefault();});
  document.addEventListener('click',event=>{
    if(performance.now()<ignoreClickUntil&&event.target.closest('.appointment-calendar-grid')) {event.preventDefault();event.stopImmediatePropagation();return;}
    const handle=event.target.closest('[data-move-handle]');
    if(handle) {
      event.preventDefault();event.stopImmediatePropagation();
      if(busy||pending||agenda.availabilityIsBusy()) return;
      clearPick();picked=sourceOf(handle.closest('[data-move-card]'));highlightSource(picked);
      document.body.classList.add('appointment-picking');
      notify('Choisissez une case libre pour '+picked.name+', ou appuyez sur Échap pour annuler.');return;
    }
    const cell=event.target.closest('.appointment-slot-cell');
    if(picked&&cell) {event.preventDefault();event.stopImmediatePropagation();propose(picked,cell);}
  },true);
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape') {endGesture();cancel();clearPick();}
    if(event.key==='Tab'&&!dialog.hidden) {
      const buttons=[...dialog.querySelectorAll('button:not([disabled])')];
      const index=buttons.indexOf(document.activeElement);
      if(buttons.length&&((event.shiftKey&&index<=0)||(!event.shiftKey&&index===buttons.length-1))) {
        event.preventDefault();buttons[event.shiftKey?buttons.length-1:0].focus();
      }
    }
  });
})();
