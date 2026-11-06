/* Manual internal administrative coding. No tariff or automatic code selection. */
(() => {
  const descriptions = new Map([...document.querySelectorAll('#internal-billing-options option')].map(option=>[option.value,option.label]));
  function paint(form) {
    const field=form.elements.billing_code;
    if(!field) return;
    const target=form.querySelector('[data-billing-description]');
    target.textContent=descriptions.get(field.value) || (field.value ? 'Sélectionnez un code de la liste.' : 'Choisissez la prestation correspondant à l’examen réalisé.');
    form.querySelector('[data-copy-status]').textContent='';
  }
  window.internalBilling={paint};
  document.addEventListener('input',event=>{if(event.target.name==='billing_code') paint(event.target.form);});
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-copy-field]'); if(!button) return;
    const form=button.closest('form'), field=form.elements[button.dataset.copyField];
    const status=form.querySelector('[data-copy-status]');
    if(!field.value.trim()) {status.textContent='Complétez d’abord ce champ.';return;}
    if(button.dataset.copyField==='billing_code'&&!descriptions.has(field.value)) {status.textContent='Choisissez d’abord un code de la liste.';return;}
    try {await navigator.clipboard.writeText(field.value);status.textContent=button.dataset.copyField==='billing_code'?'Code copié.':'N° dossier copié.';}
    catch {field.focus();field.select();status.textContent='Champ sélectionné : utilisez Ctrl+C.';}
  });
})();
