(() => {
  const panel = document.getElementById('report-modal');
  const form = document.getElementById('report-form');
  const byId = id => document.getElementById(id);
  const request = window.internalAgenda.request;
  const emailForm = byId('report-email-form'), detailsForm = byId('patient-details-form');
  const uploadForm = byId('patient-request-form');
  let busy = false, loaded = false, dirty = false, identityDirty = false, requestDirty = false;
  let savedReport = null, prescription = null, pdfUrl = null, opener = null;
  let emailEnabled = false, emailAttempt = null;
  const fingerprint = () => JSON.stringify([form.elements.report_text.value, form.elements.report_date.value, form.elements.radiologist.value]);
  const context = () => new URLSearchParams({appointment_id: form.elements.appointment_id.value,
    reservation_start: form.elements.reservation_start.value});
  function contextData() {
    const body = new FormData();
    for (const [key,value] of context()) body.set(key,value);
    body.set('csrf_token', form.elements.csrf_token.value);
    return body;
  }
  function patientRows() {
    const allPatients = byId('riziv-list');
    const history = byId('history-list');
    const selector = allPatients && !allPatients.hidden ? '#riziv-list' : history && !history.hidden ? '#history-list' : '#patient-list';
    return [...document.querySelectorAll(selector + ' [data-patient-row]')];
  }
  function matchingRows() {
    return [...document.querySelectorAll('[data-patient-row]')].filter(row =>
      row.dataset.appointment === form.elements.appointment_id.value && row.dataset.reservation === form.elements.reservation_start.value);
  }
  function currentRow() { return patientRows().find(row =>
    row.dataset.appointment === form.elements.appointment_id.value && row.dataset.reservation === form.elements.reservation_start.value); }
  function navigation() {
    const rows = patientRows(), index = rows.indexOf(currentRow());
    byId('patient-previous').disabled = busy || index <= 0;
    byId('patient-next').disabled = busy || index < 0 || index >= rows.length - 1;
  }
  function setBusy(value, loading = false) {
    busy = value;
    panel.setAttribute('aria-busy', String(value));
    panel.querySelectorAll('button').forEach(button => { button.disabled = value; });
    panel.querySelectorAll('form input:not([type=hidden]),form textarea').forEach(input => { input.disabled = loading; });
    byId('report-email-fields').disabled = value || !emailEnabled;
    navigation();
  }
  function discardPdf() {
    byId('report-preview').removeAttribute('src'); byId('report-download').removeAttribute('href');
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = null; byId('report-output').hidden = true;
  }
  function showText() {
    byId('report-output').hidden = true;
    byId('report-readonly').hidden = !savedReport || dirty;
    form.hidden = Boolean(savedReport) && !dirty;
    byId('report-cancel-edit').hidden = !savedReport;
  }
  function paintSaved() {
    if (!savedReport) return;
    byId('report-readonly-text').textContent = savedReport.report_text;
    byId('report-readonly-meta').textContent = savedReport.report_date + (savedReport.radiologist ? ' · ' + savedReport.radiologist : '');
    byId('patient-report-tab').textContent = 'Voir le compte rendu';
  }
  function rowButton(label, action, row = currentRow()) {
    const base = row?.querySelector('[data-report-patient]');
    if (!base) return null;
    const button = base.cloneNode(true); button.textContent = label;
    button.dataset.reportAction = action; return button;
  }
  function updateRowReport() {
    matchingRows().forEach(row => {
      const cell = row.querySelector('[data-report-actions]');
      if (cell) cell.replaceChildren(rowButton('Voir le compte rendu', 'report', row), rowButton('Modifier', 'edit', row));
    });
  }
  function paintPrescription(value) {
    prescription = value;
    byId('patient-request-tab').textContent = value ? 'Voir la demande' : 'Scanner / importer la demande';
    uploadForm.hidden = Boolean(value); byId('patient-request-existing').hidden = !value;
    const frame = byId('patient-request-preview');
    if (value) {
      byId('patient-request-name').textContent = value.filename;
      byId('patient-request-download').href = value.download_url;
      // Load the document only when its tab is opened.
      if (!byId('patient-request').hidden) frame.src = value.view_url;
      matchingRows().forEach(row => {
        const cell = row.querySelector('[data-request-actions]');
        if (!cell) return;
        const link = document.createElement('a'); link.textContent = 'Télécharger la demande'; link.href = value.download_url;
        cell.replaceChildren(rowButton('Voir la demande', 'request', row), link);
      });
    } else frame.removeAttribute('src');
  }
  function selectTab(tab) {
    byId('patient-request').hidden = tab !== 'request';
    byId('patient-report').hidden = tab === 'request';
    byId('patient-request-tab').setAttribute('aria-pressed', String(tab === 'request'));
    byId('patient-report-tab').setAttribute('aria-pressed', String(tab !== 'request'));
    if (tab === 'request' && prescription) byId('patient-request-preview').src = prescription.view_url;
  }
  function mayLeave() {
    return !(dirty || identityDirty || requestDirty) || confirm('Des modifications ne sont pas enregistrées. Quitter ce patient sans les enregistrer ?');
  }
  async function openPatient(button) {
    if (busy || !mayLeave()) return;
    if (window.internalHistory && !window.internalHistory.close()) return;
    opener = button; loaded = false; savedReport = null; dirty = false; identityDirty = false; requestDirty = false;
    emailEnabled = false; emailAttempt = null; prescription = null;
    discardPdf(); form.reset(); detailsForm.reset(); uploadForm.reset(); emailForm.reset();
    byId('patient-request-preview').removeAttribute('src');
    paintPrescription(null);
    byId('report-readonly-text').textContent = '';
    ['report-error','report-save-status','patient-details-status','patient-request-status','report-email-status'].forEach(id => { byId(id).textContent = ''; });
    byId('report-email-panel').open = false;
    byId('report-retry').hidden = true;
    form.elements.appointment_id.value = button.dataset.reportAppointment || '';
    form.elements.reservation_start.value = button.dataset.reportReservation || '';
    byId('report-patient-summary').textContent = button.dataset.reportPatient + ' · ' + button.dataset.reportExam + ' · ' + button.dataset.reportDate;
    byId('report-title').textContent = button.dataset.reportPatient;
    panel.hidden = false; document.body.classList.add('report-panel-open');
    byId('report-readonly').hidden = true; form.hidden = true;
    byId('patient-report-tab').textContent = 'Créer un compte rendu';
    selectTab(button.dataset.reportAction === 'request' ? 'request' : 'report');
    byId('report-save-status').textContent = 'Chargement du dossier…';
    setBusy(true, true);
    try {
      const query = '?' + context();
      const [result, patient] = await Promise.all([request(panel.dataset.storageEndpoint + query), request(panel.dataset.patientEndpoint + query)]);
      emailEnabled = result.email_enabled === true;
      byId('report-email-setup').hidden = emailEnabled;
      savedReport = result.report;
      if (savedReport) {
        form.elements.report_text.value = savedReport.report_text;
        form.elements.report_date.value = savedReport.report_date;
        form.elements.radiologist.value = savedReport.radiologist;
        form.elements.revision.value = savedReport.revision;
        paintSaved();
        byId('report-save-status').textContent = 'Enregistré · ' + new Date(savedReport.updated_at).toLocaleString('fr-BE');
      } else byId('report-save-status').textContent = 'Nouveau compte rendu · pas encore enregistré.';
      detailsForm.elements.national_number.value = patient.national_number;
      detailsForm.elements.billing_code.value = patient.billing_code || '';
      window.internalBilling.paint(detailsForm);
      paintPrescription(patient.prescription);
      loaded = true; showText();
    } catch (error) {
      byId('report-error').textContent = error.message; byId('report-save-status').textContent = '';
      byId('report-retry').hidden = false;
    } finally {
      setBusy(false);
      if (!loaded) panel.querySelectorAll('form button,form input,form textarea').forEach(e => { e.disabled = true; });
    }
    if (loaded && button.dataset.reportAction === 'edit') startEdit();
    if (loaded && button.dataset.reportAction === 'identity') detailsForm.elements.national_number.focus();
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-report-patient]');
    if (button) openPatient(button);
  });
  byId('report-retry').addEventListener('click', () => openPatient(opener));
  function close() {
    if (panel.hidden) return true;
    if (busy || !mayLeave()) return false;
    discardPdf(); byId('patient-request-preview').removeAttribute('src');
    form.reset(); detailsForm.reset(); uploadForm.reset(); emailForm.reset();
    savedReport = null; dirty = false; identityDirty = false; requestDirty = false; loaded = false;
    panel.hidden = true; document.body.classList.remove('report-panel-open'); opener?.focus();
    return true;
  }
  window.internalReporting = {close};
  byId('report-close').addEventListener('click', close);
  byId('patient-request-tab').addEventListener('click', () => selectTab('request'));
  byId('patient-report-tab').addEventListener('click', () => selectTab('report'));
  function startEdit() {
    if (!loaded || busy) return;
    discardPdf(); byId('report-readonly').hidden = true; form.hidden = false;
    byId('report-cancel-edit').hidden = !savedReport;
    form.elements.report_text.focus();
  }
  byId('report-start-edit').addEventListener('click', startEdit);
  byId('report-cancel-edit').addEventListener('click', () => {
    if (!savedReport || !mayLeave()) return;
    for (const key of ['report_text','report_date','radiologist','revision']) form.elements[key].value = savedReport[key];
    dirty = false; discardPdf(); showText();
    byId('report-save-status').textContent = 'Version enregistrée affichée.';
  });
  form.addEventListener('input', () => {
    dirty = true; byId('report-save-status').textContent = 'Modifications non enregistrées · Ctrl+S pour enregistrer.';
  });
  async function saveReport() {
    if (busy || !loaded || !form.reportValidity()) return false;
    const data = new FormData(form), version = fingerprint();
    setBusy(true); byId('report-error').textContent = ''; byId('report-save-status').textContent = 'Enregistrement…';
    try {
      const result = await request(panel.dataset.storageEndpoint, {method:'POST', body:data});
      form.elements.revision.value = result.revision;
      savedReport = {report_text:data.get('report_text').trim(), report_date:data.get('report_date'),
        radiologist:data.get('radiologist').trim(), revision:result.revision, updated_at:result.updated_at};
      dirty = fingerprint() !== version; paintSaved(); updateRowReport();
      byId('report-save-status').textContent = dirty ? 'Version envoyée enregistrée. Vos dernières modifications restent à enregistrer.' :
        'Enregistré · ' + new Date(result.updated_at).toLocaleString('fr-BE');
      if (!dirty) showText();
      return true;
    } catch (error) {
      byId('report-save-status').textContent = 'Enregistrement non confirmé · texte conservé ici.';
      byId('report-error').textContent = error.message; return false;
    } finally { setBusy(false); }
  }
  byId('report-save').addEventListener('click', saveReport);
  async function generatePdf(event) {
    event?.preventDefault();
    if (busy || !loaded || !form.reportValidity()) return;
    if ((dirty || !savedReport) && !await saveReport()) return;
    if (dirty) return; // Edits made while saving must not silently produce an older PDF.
    const data = new FormData(form), version = fingerprint();
    setBusy(true); byId('report-error').textContent = '';
    try {
      const result = await request(panel.dataset.endpoint, {method:'POST', body:data}, 'pdf');
      if (version !== fingerprint()) { byId('report-error').textContent = 'Texte modifié pendant la préparation. Enregistrez puis regénérez le PDF.'; return; }
      discardPdf(); pdfUrl = URL.createObjectURL(result.blob);
      byId('report-preview').src = pdfUrl; byId('report-download').href = pdfUrl;
      const filename = result.disposition?.match(/filename="([^"]+)"/);
      byId('report-download').download = filename ? filename[1] : 'compte-rendu-radiologique.pdf';
      byId('report-output').hidden = false; byId('report-readonly').hidden = true; form.hidden = true;
      byId('report-preview-status').textContent = 'PDF prêt · compte rendu enregistré.';
    } catch (error) { byId('report-error').textContent = error.message; }
    finally { setBusy(false); }
  }
  form.addEventListener('submit', generatePdf); byId('report-view-pdf').addEventListener('click', generatePdf);
  byId('report-back').addEventListener('click', () => { discardPdf(); showText(); });
  byId('report-print').addEventListener('click', () => {
    if (!pdfUrl) return;
    try { byId('report-preview').contentWindow.focus(); byId('report-preview').contentWindow.print(); }
    catch { window.open(pdfUrl, '_blank', 'noopener'); }
  });
  byId('report-copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(savedReport.report_text); byId('report-save-status').textContent = 'Texte copié. Collez-le dans votre autre logiciel.'; }
    catch { getSelection().selectAllChildren(byId('report-readonly-text')); byId('report-save-status').textContent = 'Texte sélectionné : utilisez Ctrl+C pour le copier.'; }
  });
  detailsForm.addEventListener('input', () => { identityDirty = true; byId('patient-details-status').textContent = 'Dossier / code non enregistré.'; });
  detailsForm.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !loaded) return;
    const data = contextData(), sentValue = detailsForm.elements.national_number.value;
    const sentCode = detailsForm.elements.billing_code.value;
    data.set('billing_code',sentCode);
    data.set('national_number', sentValue); setBusy(true);
    try {
      const result = await request(panel.dataset.patientEndpoint, {method:'POST', body:data});
      identityDirty = detailsForm.elements.national_number.value !== sentValue || detailsForm.elements.billing_code.value !== sentCode;
      if (!identityDirty) detailsForm.elements.national_number.value = result.national_number;
      if (!identityDirty) detailsForm.elements.billing_code.value = result.billing_code;
      window.internalBilling.paint(detailsForm);
      matchingRows().forEach(row => {
        const cell = row.querySelector('[data-national-number]');
        if (cell) cell.textContent = result.national_number || 'Non renseigné';
        const codeCell = row.querySelector('[data-billing-code]');
        if (codeCell) codeCell.textContent = result.billing_code || 'À choisir';
      });
      byId('patient-details-status').textContent = identityDirty ? 'Version envoyée enregistrée. Dernières modifications non enregistrées.' : 'Dossier et code enregistrés.';
    } catch (error) { byId('patient-details-status').textContent = error.message; }
    finally { setBusy(false); }
  });
  uploadForm.addEventListener('change', () => { requestDirty = Boolean(uploadForm.elements.prescription_file.files.length); });
  uploadForm.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !loaded || prescription) return;
    const file = uploadForm.elements.prescription_file.files[0];
    if (!file || file.size > 10*1024*1024 || !/\.pdf$/i.test(file.name)) {
      byId('patient-request-status').textContent = 'Choisissez un PDF de 10 Mo maximum.'; return;
    }
    const data = contextData(); data.set('prescription_file', file);
    setBusy(true); byId('patient-request-status').textContent = 'Enregistrement de la demande…';
    try {
      const result = await request(panel.dataset.prescriptionEndpoint, {method:'POST', body:data});
      paintPrescription(result.prescription); uploadForm.reset(); requestDirty = false;
      byId('patient-request-status').textContent = 'Demande enregistrée dans le dossier.';
    } catch (error) { byId('patient-request-status').textContent = error.message; }
    finally { setBusy(false); }
  });
  emailForm.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !loaded || !emailEnabled || !form.reportValidity()) return;
    const recipient = emailForm.elements.recipient.value.trim();
    if ((dirty || !savedReport) && !await saveReport()) return;
    if (dirty) return;
    const signature = form.elements.revision.value + ':' + recipient;
    if (!emailAttempt || emailAttempt.signature !== signature) emailAttempt = {signature, token:crypto.randomUUID()};
    const data = new FormData(form); data.set('recipient',recipient); data.set('email_attempt',emailAttempt.token);
    setBusy(true); byId('report-email-status').textContent = 'Envoi en cours…';
    try {
      const result = await request(panel.dataset.emailEndpoint, {method:'POST',body:data});
      byId('report-email-status').textContent = result.message; emailAttempt = null;
    } catch (error) { byId('report-email-status').textContent = error.message + ' Vérifiez les messages envoyés avant de réessayer.'; }
    finally { setBusy(false); }
  });
  function movePatient(offset) {
    const rows = patientRows(), index = rows.indexOf(currentRow());
    const target = rows[index + offset]?.querySelector('[data-report-patient]');
    if (index >= 0 && target) openPatient(target);
  }
  byId('patient-previous').addEventListener('click', () => movePatient(-1));
  byId('patient-next').addEventListener('click', () => movePatient(1));
  document.addEventListener('internal-patient-list-updated', navigation);
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') close();
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveReport(); }
  });
  window.addEventListener('beforeunload', event => { if (dirty || identityDirty || requestDirty) { event.preventDefault(); event.returnValue = ''; } });
})();
