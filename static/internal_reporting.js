(() => {
  const modal = document.getElementById('report-modal');
  const form = document.getElementById('report-form');
  const output = document.getElementById('report-output');
  const preview = document.getElementById('report-preview');
  const errorBox = document.getElementById('report-error');
  const download = document.getElementById('report-download');
  const printButton = document.getElementById('report-print');
  const saveStatus = document.getElementById('report-save-status');
  let pdfUrl = null, opener = null, busy = false, dirty = false;
  function setBusy(value) {
    busy = value;
    form.querySelectorAll('input:not([type=hidden]),textarea,button').forEach(control => { control.disabled = value; });
    document.getElementById('report-close').disabled = value;
    document.getElementById('report-save-preview').disabled = value;
  }
  function savedStatus(timestamp) {
    saveStatus.textContent = 'Compte rendu enregistré · ' + new Date(timestamp).toLocaleString('fr-BE');
  }
  preview.addEventListener('load', () => { printButton.disabled = false; });
  function discardPdf() {
    preview.removeAttribute('src'); download.removeAttribute('href');
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = null; output.hidden = true;
  }
  function close() {
    if (busy) return;
    if (dirty && !window.confirm('Fermer sans enregistrer les dernières modifications ?')) return;
    discardPdf(); form.reset(); dirty = false; errorBox.textContent = '';
    modal.hidden = true; document.body.classList.remove('appointment-modal-open');
    opener?.focus();
  }
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-report-patient]');
    if (!button || busy) return;
    opener = button; discardPdf(); form.reset(); dirty = false;
    form.elements.appointment_id.value = button.dataset.reportAppointment;
    form.elements.reservation_start.value = button.dataset.reportReservation;
    document.getElementById('report-patient-summary').textContent = button.dataset.reportPatient + ' · ' + button.dataset.reportExam + ' · ' + button.dataset.reportDate;
    errorBox.textContent = ''; form.hidden = false; modal.hidden = false;
    document.body.classList.add('appointment-modal-open');
    saveStatus.textContent = 'Chargement du compte rendu…';
    const query = new URLSearchParams({appointment_id:form.elements.appointment_id.value, reservation_start:form.elements.reservation_start.value});
    setBusy(true);
    let loaded = false;
    try {
      const response = await fetch(modal.dataset.storageEndpoint + '?' + query, {cache:'no-store'});
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Le compte rendu n’a pas pu être chargé. Fermez puis rouvrez le patient.');
      const result = await response.json();
      if (result.report) {
        form.elements.report_text.value = result.report.report_text;
        form.elements.report_date.value = result.report.report_date;
        form.elements.radiologist.value = result.report.radiologist;
        form.elements.revision.value = result.report.revision;
        savedStatus(result.report.updated_at);
      } else saveStatus.textContent = 'Nouveau compte rendu · pas encore enregistré.';
      loaded = true;
    } catch (error) { saveStatus.textContent = ''; errorBox.textContent = error.message; }
    finally {
      setBusy(false);
      if (!loaded) form.querySelectorAll('input:not([type=hidden]),textarea,button').forEach(control => { control.disabled = true; });
      else form.elements.report_text.focus();
    }
  });
  form.addEventListener('input', () => { dirty = true; saveStatus.textContent = 'Modifications non enregistrées.'; });
  async function saveReport() {
    if (busy || !form.reportValidity()) return;
    const data = new FormData(form);
    setBusy(true); errorBox.textContent = ''; saveStatus.textContent = 'Enregistrement…';
    try {
      const response = await fetch(modal.dataset.storageEndpoint, {method:'POST', body:data});
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) throw new Error(result.error || 'Le compte rendu n’a pas pu être enregistré. Votre texte reste dans cette fenêtre.');
      form.elements.revision.value = result.revision;
      dirty = false; savedStatus(result.updated_at);
    } catch (error) { saveStatus.textContent = 'Non enregistré.'; errorBox.textContent = error.message; }
    finally { setBusy(false); }
  }
  document.getElementById('report-save').addEventListener('click', saveReport);
  document.getElementById('report-save-preview').addEventListener('click', saveReport);
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    const data = new FormData(form);
    setBusy(true); errorBox.textContent = '';
    try {
      const response = await fetch(modal.dataset.endpoint, {method:'POST', body:data});
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/pdf')) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.error || 'Le PDF n’a pas pu être généré. Vérifiez votre connexion et votre session.');
      }
      const blob = await response.blob(); discardPdf(); pdfUrl = URL.createObjectURL(blob);
      const filename = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/);
      download.download = filename ? filename[1] : 'compte-rendu-radiologique.pdf';
      printButton.disabled = true; preview.src = pdfUrl; download.href = pdfUrl; output.hidden = false; form.hidden = true;
      window.setTimeout(() => { if (pdfUrl) printButton.disabled = false; }, 1200);
      document.getElementById('report-preview-status').textContent = 'PDF prêt. Vous pouvez l’imprimer et le télécharger.';
      download.focus();
    } catch (error) { errorBox.textContent = error.message; }
    finally { setBusy(false); }
  });
  document.getElementById('report-close').addEventListener('click', close);
  document.getElementById('report-edit').addEventListener('click', () => {
    discardPdf(); form.hidden = false; form.elements.report_text.focus();
  });
  printButton.addEventListener('click', () => {
    if (!pdfUrl) return;
    const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    if (ios) { window.open(pdfUrl, '_blank', 'noopener'); return; }
    try { preview.contentWindow.focus(); preview.contentWindow.print(); }
    catch { window.open(pdfUrl, '_blank', 'noopener'); }
  });
  modal.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key !== 'Tab') return;
    const fields = [...modal.querySelectorAll('button,input:not([type=hidden]),textarea,a[href],iframe')]
      .filter(el => !el.disabled && el.getClientRects().length);
    const first = fields[0], last = fields[fields.length-1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  window.addEventListener('pagehide', () => {
    discardPdf(); form.reset(); form.hidden = false; dirty = false; modal.hidden = true;
    document.body.classList.remove('appointment-modal-open');
  });
})();
