(() => {
  const modal = document.getElementById('report-modal');
  const form = document.getElementById('report-form');
  const output = document.getElementById('report-output');
  const preview = document.getElementById('report-preview');
  const errorBox = document.getElementById('report-error');
  const download = document.getElementById('report-download');
  const printButton = document.getElementById('report-print');
  let pdfUrl = null, opener = null, busy = false, dirty = false;
  preview.addEventListener('load', () => { printButton.disabled = false; });
  function discardPdf() {
    preview.removeAttribute('src'); download.removeAttribute('href');
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = null; output.hidden = true;
  }
  function close() {
    if (busy) return;
    if (dirty && !window.confirm('Fermer et effacer ce compte rendu ? Vérifiez que vous avez téléchargé le PDF.')) return;
    discardPdf(); form.reset(); dirty = false; errorBox.textContent = '';
    modal.hidden = true; document.body.classList.remove('appointment-modal-open');
    opener?.focus();
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-report-patient]');
    if (!button) return;
    opener = button; discardPdf(); form.reset(); dirty = false;
    form.elements.appointment_id.value = button.dataset.reportAppointment;
    form.elements.reservation_start.value = button.dataset.reportReservation;
    document.getElementById('report-patient-summary').textContent = button.dataset.reportPatient + ' · ' + button.dataset.reportExam + ' · ' + button.dataset.reportDate;
    errorBox.textContent = ''; form.hidden = false; modal.hidden = false;
    document.body.classList.add('appointment-modal-open'); form.elements.report_text.focus();
  });
  form.addEventListener('input', () => { dirty = true; });
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    busy = true; errorBox.textContent = '';
    const button = form.querySelector('[type=submit]'); button.disabled = true;
    document.getElementById('report-close').disabled = true;
    try {
      const response = await fetch(modal.dataset.endpoint, {method:'POST', body:new FormData(form)});
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
    finally { busy = false; button.disabled = false; document.getElementById('report-close').disabled = false; }
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
