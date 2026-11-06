/* All historical scans/text remain in the authenticated practice database. */
(() => {
  const $ = id => document.getElementById(id);
  const panel = $('history-panel'), form = $('history-form');
  const request = window.internalAgenda.request;
  let busy = false, loading = false, dirty = false, record = null, documents = {}, opener = null, pdfUrl = null;
  const editableKeys = ['patient_name','national_number','examined_on','examination','transfer_status','report_text','report_date','radiologist'];
  const fingerprint = () => JSON.stringify([...editableKeys.map(key=>form.elements[key].value), form.elements.report_reviewed.checked]);
  const hasFiles = () => [...panel.querySelectorAll('[data-history-file]')].some(input=>input.files.length);
  function readiness() {
    const ready = Boolean(documents.request && (documents.report || (form.elements.report_reviewed.checked && form.elements.report_text.value.trim())));
    [...form.elements.transfer_status.options].forEach(option=>{ option.disabled = option.value !== 'todo' && !ready; });
    if (!ready) form.elements.transfer_status.value = 'todo';
  }
  function setBusy(value, isLoading = false) {
    busy = value; loading = isLoading; panel.setAttribute('aria-busy',String(value));
    panel.querySelectorAll('button').forEach(button=>{ button.disabled = value; });
    form.querySelectorAll('input:not([type=hidden]),textarea,select').forEach(input=>{ input.disabled = isLoading; });
    panel.querySelectorAll('[data-history-file]').forEach(input=>{ input.disabled = value || isLoading; });
    readiness();
  }
  function clearPdf() {
    $('history-pdf-preview').removeAttribute('src'); $('history-pdf-download').removeAttribute('href');
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = null; $('history-pdf-output').hidden = true;
  }
  function paintDocuments(value) {
    documents = value || {};
    panel.querySelectorAll('[data-history-kind]').forEach(section=>{
      const file = documents[section.dataset.historyKind];
      section.querySelector('[data-history-upload]').hidden = Boolean(file);
      section.querySelector('[data-history-existing]').hidden = !file;
      if (file) {
        section.querySelector('[data-history-filename]').textContent = file.filename;
        section.querySelector('[data-history-download]').href = file.download_url;
      }
    });
    readiness();
  }
  function showText(edit = false) {
    const text = form.elements.report_text.value;
    const readonly = Boolean(text.trim()) && !edit;
    $('history-text-editor').hidden = readonly;
    $('history-readonly-text').hidden = !readonly;
    $('history-readonly-text').textContent = text;
    $('history-edit-text').hidden = !readonly;
  }
  function populate(value) {
    form.elements.dossier_id.value = value.id;
    form.elements.revision.value = value.revision;
    editableKeys.forEach(key=>{ form.elements[key].value = value[key] || ''; });
    form.elements.report_reviewed.checked = value.report_reviewed;
    form.elements.report_date.required = Boolean(value.report_text?.trim());
    $('history-title').textContent = value.patient_name;
    paintDocuments(value.documents); showText();
  }
  async function loadList() {
    $('history-list-status').textContent = 'Chargement de XIMEO-RIZIV…';
    try {
      const result = await request(panel.dataset.endpoint);
      $('history-patients').innerHTML = result.html;
      $('history-list-status').textContent = result.total + ' dossier(s), classés par date d’examen.';
    } catch (error) { $('history-list-status').textContent = error.message; }
  }
  async function refreshLists() {
    await loadList();
    if (!$('riziv-list').hidden) await window.internalAgenda.refreshRiziv();
  }
  function close() {
    if (panel.hidden) return true;
    if (busy) return false;
    if ((dirty || hasFiles()) && !confirm('Des modifications ou scans ne sont pas enregistrés. Fermer quand même ?')) return false;
    clearPdf(); form.reset(); panel.querySelectorAll('[data-history-file]').forEach(input=>{input.value='';});
    dirty=false; record=null; documents={}; panel.hidden=true;
    document.body.classList.remove('report-panel-open'); opener?.focus(); return true;
  }
  window.internalHistory = {close,loadList};
  async function open(button) {
    if (!close() || (window.internalReporting && !window.internalReporting.close())) return;
    opener=button; record=null; dirty=false; documents={}; loading=false; form.reset(); clearPdf();
    form.elements.report_date.required=false;
    form.elements.creation_key.value = crypto.randomUUID(); form.elements.revision.value='0';
    form.elements.dossier_id.value='';
    panel.querySelectorAll('[data-history-file]').forEach(input=>{input.value='';});
    $('history-title').textContent='Ajouter un ancien dossier';
    $('history-error').textContent=''; $('history-status').textContent='Nouveau dossier · pas encore enregistré.';
    paintDocuments({}); showText(true); panel.hidden=false; document.body.classList.add('report-panel-open');
    setBusy(false);
    const id=button.dataset.historyId;
    if (id) {
      setBusy(true,true); $('history-status').textContent='Chargement du dossier…';
      try {
        const result=await request(panel.dataset.endpoint+'/'+id);
        record=result.dossier; populate(record);
        $('history-status').textContent='Enregistré · '+new Date(record.updated_at).toLocaleString('fr-BE');
      } catch(error) {
        $('history-error').textContent=error.message;
        $('history-status').textContent='Dossier non chargé. Fermez puis réessayez.';
        loading=true;
      } finally {
        const failed=!record; setBusy(false,failed);
        if(failed) panel.querySelectorAll('button:not(#history-close)').forEach(b=>{b.disabled=true;});
      }
    }
    if (!loading && button.dataset.historySection) {
      $(button.dataset.historySection==='documents'?'history-documents':'history-text-section').scrollIntoView({block:'start'});
    }
    if(!id) form.elements.patient_name.focus();
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-history-new], [data-history-id]');
    if(button) open(button);
  });
  $('history-close').addEventListener('click',close);
  $('history-refresh').addEventListener('click',loadList);
  $('history-edit-text').addEventListener('click',()=>{ showText(true); form.elements.report_text.focus(); });
  form.addEventListener('input',event=>{
    dirty=true;
    if(['report_text','report_date','radiologist'].includes(event.target.name)) form.elements.report_reviewed.checked=false;
    form.elements.report_date.required=Boolean(form.elements.report_text.value.trim());
    readiness(); $('history-status').textContent='Modifications non enregistrées · Ctrl+S pour enregistrer.';
  });
  async function save() {
    if(busy || loading || !form.reportValidity()) return false;
    const snapshot=fingerprint(), data=new FormData(form);
    setBusy(true); $('history-error').textContent=''; $('history-status').textContent='Enregistrement…';
    try {
      const result=await request(panel.dataset.endpoint,{method:'POST',body:data});
      record=result.dossier;
      form.elements.dossier_id.value=record.id; form.elements.revision.value=record.revision;
      dirty=fingerprint()!==snapshot;
      paintDocuments(record.documents);
      if(!dirty) { populate(record); showText(); }
      $('history-status').textContent=dirty?'Version envoyée enregistrée. Dernières modifications encore à enregistrer.':'Dossier et texte enregistrés · '+new Date(record.updated_at).toLocaleString('fr-BE');
      refreshLists(); return true;
    } catch(error) {
      $('history-error').textContent=error.message;
      $('history-status').textContent='Enregistrement non confirmé · vos champs et votre texte restent ici.'; return false;
    } finally { setBusy(false); }
  }
  form.addEventListener('submit',event=>{ event.preventDefault(); save(); });
  $('history-copy').addEventListener('click',async()=>{
    const text=form.elements.report_text.value;
    if(!text.trim()) { $('history-error').textContent='Collez d’abord le texte du compte rendu.'; return; }
    try { await navigator.clipboard.writeText(text); $('history-status').textContent='Texte copié : collez-le dans votre autre logiciel.'; }
    catch { showText(true); form.elements.report_text.focus(); form.elements.report_text.select(); $('history-status').textContent='Texte sélectionné : utilisez Ctrl+C.'; }
  });
  async function upload(kind) {
    if(busy || loading) return;
    const input=panel.querySelector('[data-history-file="'+kind+'"]'), file=input.files[0];
    if(!file || file.size>10*1024*1024 || !/\.pdf$/i.test(file.name)) { $('history-error').textContent='Choisissez un scan PDF de 10 Mo maximum.'; return; }
    if((dirty || !record) && !await save()) return;
    if(dirty) return;
    const data=new FormData(); data.set('csrf_token',form.elements.csrf_token.value); data.set('file',file);
    setBusy(true); $('history-status').textContent='Enregistrement du scan…'; $('history-error').textContent='';
    try {
      const result=await request(panel.dataset.endpoint+'/'+record.id+'/documents/'+kind,{method:'POST',body:data});
      paintDocuments(result.dossier.documents); input.value='';
      $('history-status').textContent='Scan original enregistré. Il restera séparé du texte.'; refreshLists();
    } catch(error) { $('history-error').textContent=error.message; }
    finally { setBusy(false); }
  }
  panel.querySelectorAll('button[data-history-upload]').forEach(button=>button.addEventListener('click',()=>upload(button.dataset.historyUpload)));
  panel.querySelectorAll('[data-history-view]').forEach(button=>button.addEventListener('click',()=>{
    const file=documents[button.dataset.historyView]; if(!file) return;
    clearPdf(); $('history-pdf-preview').src=file.view_url; $('history-pdf-download').href=file.download_url;
    $('history-pdf-title').textContent='Scan original · '+file.filename; $('history-pdf-output').hidden=false;
    $('history-pdf-output').scrollIntoView({block:'start'});
  }));
  $('history-pdf').addEventListener('click',async()=>{
    if(busy || loading) return;
    if(!form.elements.report_text.value.trim() || !form.elements.report_reviewed.checked) {
      $('history-error').textContent='Collez le texte, relisez-le puis cochez la confirmation de relecture avant de créer le PDF.'; showText(true); return;
    }
    if((dirty || !record) && !await save()) return;
    if(dirty) return;
    const version=fingerprint(); setBusy(true);
    try {
      const result=await request(record.pdf_url,{},'pdf');
      if(version!==fingerprint()) { $('history-error').textContent='Le texte a changé pendant la préparation. Enregistrez et regénérez le PDF.'; return; }
      clearPdf(); pdfUrl=URL.createObjectURL(result.blob);
      $('history-pdf-preview').src=pdfUrl; $('history-pdf-download').href=pdfUrl;
      $('history-pdf-download').download='compte-rendu-historique-'+record.id+'.pdf';
      $('history-pdf-title').textContent='Compte rendu issu du texte relu et enregistré'; $('history-pdf-output').hidden=false;
      $('history-pdf-output').scrollIntoView({block:'start'});
    } catch(error) { $('history-error').textContent=error.message; }
    finally { setBusy(false); }
  });
  $('history-print').addEventListener('click',()=>{
    try { $('history-pdf-preview').contentWindow.focus(); $('history-pdf-preview').contentWindow.print(); }
    catch { window.open($('history-pdf-preview').src,'_blank','noopener'); }
  });
  $('history-pdf-close').addEventListener('click',clearPdf);
  panel.addEventListener('keydown',event=>{
    if(event.key==='Escape') close();
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s') {event.preventDefault();save();}
  });
  window.addEventListener('beforeunload',event=>{if(dirty||hasFiles()){event.preventDefault();event.returnValue='';}});
})();
