/* Private billing UI. No patient, bank or invoice data is stored in the browser. */
(() => {
  const script=document.currentScript, base=script.dataset.endpoint, csrf=script.dataset.csrf;
  const $=id=>document.getElementById(id), editor=$('invoice-editor'), form=$('invoice-form');
  const settingsDialog=$('invoice-settings-dialog'), settingsForm=$('invoice-settings-form');
  const preview=$('invoice-pdf-preview');
  const searchSheet=$('invoice-patient-sheet');
  const steps=['patient','exam','amounts'];let currentStep='patient';
  let invoice=null, dirty=false, busy=false, settingsRevision=0, gmailReady=false, attempt=null, missingSettings=[];
  let listChanged=false;
  let settingsDirty=false,settingsSaving=false;
  const currency=cents=>new Intl.NumberFormat('fr-BE',{style:'currency',currency:'EUR'}).format(cents/100);
  const cents=value=>Math.round(Number(String(value).replace(',','.'))*100);
  function feedback(message,error=false){$('invoice-feedback').textContent=message;$('invoice-feedback').classList.toggle('is-error',error);}
  async function request(url,body=null,signal=null) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
    const abort=()=>controller.abort();
    if(signal){signal.addEventListener('abort',abort,{once:true});if(signal.aborted)controller.abort();}
    try {
      const response=await fetch(url,{method:body?'POST':'GET',body,cache:'no-store',signal:controller.signal,headers:{'X-Requested-With':'XMLHttpRequest'}});
      if(response.redirected || [401,403].includes(response.status))throw new Error('Votre session a expiré. Gardez ce formulaire ouvert et reconnectez-vous dans un autre onglet.');
      const result=await response.json().catch(()=>({}));
      if(!response.ok || result.ok===false || result.error)throw new Error(result.error || 'Action non confirmée. Vos saisies restent dans le formulaire.');
      return result;
    }catch(error){if(error.name==='AbortError')throw new Error('Réponse trop lente. Vos saisies restent ici. Rechargez la facture avant de réessayer une émission ou un envoi.');throw error;}
    finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
  }
  function body(fields={}){const result=new FormData();result.set('csrf_token',csrf);for(const [key,value] of Object.entries(fields))result.set(key,value??'');return result;}
  function amounts(){const patient=cents(form.elements.patient_amount.value),ticket=cents(form.elements.ticket_amount.value),insurance=cents(form.elements.insurance_amount.value);
    $('invoice-supplement').textContent=currency(patient-ticket);$('invoice-total').textContent=currency(patient+insurance);
    $('invoice-supplement-check').hidden=patient<=ticket;
  }
  function selectStep(step,focus=false){
    currentStep=step;
    form.querySelectorAll('[data-invoice-step]').forEach(panel=>{panel.hidden=panel.dataset.invoiceStep!==step;});
    $('invoice-step-tabs').querySelectorAll('button').forEach(button=>{if(button.dataset.invoiceStepTab===step)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');});
    $('invoice-next').hidden=step==='amounts';$('invoice-issue').hidden=invoice?.state==='issued'||step!=='amounts';
    if(focus)form.querySelector('[data-invoice-step="'+step+'"] input, [data-invoice-step="'+step+'"] select')?.focus();
  }
  $('invoice-step-tabs').addEventListener('click',event=>{const tab=event.target.closest('[data-invoice-step-tab]');if(tab&&!busy)selectStep(tab.dataset.invoiceStepTab,true);});
  $('invoice-next').addEventListener('click',()=>{if(!busy)selectStep(steps[Math.min(2,steps.indexOf(currentStep)+1)],true);});
  function state() {
    const issued=invoice.state==='issued';
    $('invoice-title').textContent=invoice.number || invoice.data.patient_name || 'Nouvelle facture';
    $('invoice-document-meta').textContent=issued?'Émise le '+invoice.invoice_date+' · Échéance '+invoice.due_date:'Brouillon';
    $('invoice-fields').disabled=issued;
    $('invoice-save').hidden=issued;$('invoice-issue').hidden=issued;$('invoice-adapt-amounts').hidden=issued;
    $('invoice-mail-panel').hidden=!issued;$('invoice-payment-panel').hidden=!issued;
    $('invoice-settings-note').hidden=issued || !missingSettings.length;
    form.querySelector('.invoice-issue-checks').hidden=issued;
    form.querySelector('.invoice-reference').hidden=issued;
    form.hidden=issued;$('invoice-step-tabs').hidden=issued;$('invoice-issued-summary').hidden=!issued;
    $('invoice-summary-name').textContent=invoice.data.patient_name;
    $('invoice-summary-amount').textContent=currency(invoice.data.patient_cents);
    $('invoice-summary-exam').textContent=invoice.data.examination;
    selectStep(currentStep);
    $('invoice-email-status').textContent=invoice.email_state==='sent'?'Dernier envoi confié à Gmail : '+invoice.last_recipient:
      ['sending','uncertain'].includes(invoice.email_state)?'Envoi en cours ou non confirmé. Vérifiez Gmail avant tout nouvel essai.':gmailReady?'Gmail connecté.':'Connectez Gmail depuis l’agenda pour activer l’envoi.';
    $('invoice-send').disabled=!gmailReady || ['sending','uncertain'].includes(invoice.email_state);
    $('invoice-send').textContent=invoice.email_state==='sent'?'Renvoyer la facture PDF':'Envoyer la facture PDF';
    $('invoice-resend-check').hidden=invoice.email_state!=='sent';
    $('invoice-mail-form').elements.resend_confirmed.required=invoice.email_state==='sent';
    $('invoice-reset-delivery').hidden=!['sending','uncertain'].includes(invoice.email_state);
    $('invoice-payment-form').elements.paid_on.value=invoice.paid_on;
    $('invoice-download').href=invoice.pdf_url+'?download=1';
    if($('invoice-open-pdf'))$('invoice-open-pdf').href=invoice.pdf_url;
    amounts();
  }
  async function open(id) {
    if(busy)return;
    const result=await request(base+'/'+encodeURIComponent(id));
    invoice=result.invoice;gmailReady=result.gmail_ready;missingSettings=result.missing||[];attempt=null;currentStep='patient';
    editor.classList.remove('has-preview');editor.querySelector('.invoice-preview-column').hidden=true;
    form.reset();
    for(const [name,value] of Object.entries(invoice.data))if(form.elements.namedItem(name))form.elements.namedItem(name).value=value??'';
    for(const name of ['patient','insurance','ticket']){form.elements[name+'_amount'].value=(invoice.data[name+'_cents']/100).toFixed(2);form.elements[name+'_amount'].readOnly=true;}
    $('invoice-mail-form').reset();$('invoice-mail-form').elements.recipient.value=invoice.last_recipient || invoice.data.patient_email || '';
    $('invoice-pdf-actions').hidden=true;preview.hidden=true;preview.removeAttribute('src');$('invoice-preview-empty').hidden=false;
    $('invoice-unsaved').hidden=true;dirty=false;feedback('');state();
    if(!editor.open)editor.showModal();
    if(invoice.state==='issued')showPdf();
    if(invoice.state==='draft')form.elements.patient_name.focus();
  }
  function close(force=false){if(busy)return;if(dirty&&!force){$('invoice-unsaved').hidden=false;return;}editor.close();invoice=null;dirty=false;preview.removeAttribute('src');if(listChanged && document.body.classList.contains('invoice-page'))location.reload();}
  editor.addEventListener('cancel',event=>{event.preventDefault();close();});
  document.querySelector('[data-invoice-close]').addEventListener('click',()=>close());
  $('invoice-discard-close').addEventListener('click',()=>close(true));$('invoice-keep-editing').addEventListener('click',()=>{$('invoice-unsaved').hidden=true;});
  form.addEventListener('input',event=>{dirty=true;
    if(!['performed','verified','supplement_confirmed'].includes(event.target.name)){form.elements.verified.checked=false;form.elements.supplement_confirmed.checked=false;}
    feedback('Modifications non enregistrées.');amounts();});
  form.addEventListener('change',()=>{dirty=true;});
  $('invoice-adapt-amounts').addEventListener('click',()=>{for(const name of ['patient','ticket','insurance'])form.elements[name+'_amount'].readOnly=false;form.elements.patient_amount.focus();});
  form.elements.billing_code.addEventListener('change',()=>run(async()=>{
    if(!form.elements.billing_code.value)return;
    const result=await request(base+'/tariff/'+encodeURIComponent(form.elements.billing_code.value));
    form.elements.examination.value=result.label;
    form.elements.ticket_amount.value=(result.ticket_cents/100).toFixed(2);
    form.elements.insurance_amount.value=(result.insurance_cents/100).toFixed(2);
    form.elements.verified.checked=false;form.elements.supplement_confirmed.checked=false;
    dirty=true;amounts();feedback('Référence 2026 chargée pour ce code. Vérifiez les tarifs applicables avant émission.');
  }));
  async function save() {
    if(invoice.state!=='draft')return;
    const data=new FormData(form);data.set('csrf_token',csrf);data.set('revision',invoice.revision);
    const result=await request(base+'/'+invoice.id,data);invoice=result.invoice;dirty=false;listChanged=true;state();feedback('Brouillon enregistré.');
  }
  async function run(action){if(busy)return;busy=true;editor.setAttribute('aria-busy','true');editor.querySelector('.invoice-editor-grid').inert=true;for(const id of ['invoice-save','invoice-issue','invoice-preview-button'])$(id).disabled=true;
    try{await action();}catch(error){feedback(error.message,true);}finally{busy=false;editor.removeAttribute('aria-busy');editor.querySelector('.invoice-editor-grid').inert=false;for(const id of ['invoice-save','invoice-issue','invoice-preview-button'])$(id).disabled=false;}
  }
  form.addEventListener('submit',event=>{event.preventDefault();run(save);});
  preview.addEventListener('load',()=>{$('invoice-print').disabled=false;});
  function showPdf(){editor.classList.add('has-preview');editor.querySelector('.invoice-preview-column').hidden=false;$('invoice-print').disabled=true;preview.src=invoice.pdf_url+'?v='+invoice.revision;preview.hidden=false;$('invoice-preview-empty').hidden=true;$('invoice-pdf-actions').hidden=false;}
  $('invoice-preview-button').addEventListener('click',()=>run(async()=>{if(invoice.state==='draft')await save();showPdf();}));
  $('invoice-print').addEventListener('click',()=>{try{preview.contentWindow.focus();preview.contentWindow.print();}catch(error){window.open(invoice.pdf_url,'_blank','noopener');}});
  $('invoice-issue').addEventListener('click',()=>{const invalid=form.querySelector('input:invalid,select:invalid,textarea:invalid');if(invalid){selectStep(invalid.closest('[data-invoice-step]').dataset.invoiceStep);const disclosure=invalid.closest('details');if(disclosure)disclosure.open=true;invalid.reportValidity();return;}run(async()=>{
    const checks={performed:form.elements.performed.checked?'1':'0',verified:form.elements.verified.checked?'1':'0',supplement_confirmed:form.elements.supplement_confirmed.checked?'1':'0'};
    await save();const result=await request(base+'/'+invoice.id+'/issue',body({...checks,revision:invoice.revision}));
    invoice=result.invoice;listChanged=true;dirty=false;state();showPdf();feedback('Facture émise : '+invoice.number+'. Le document est figé.');
  });});
  $('invoice-mail-form').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
    $('invoice-send').disabled=true;attempt??=crypto.randomUUID();
    try{
      const result=await request(base+'/'+invoice.id+'/email',body({recipient:event.target.elements.recipient.value,patient_agreement:event.target.elements.patient_agreement.checked?'1':'0',resend_confirmed:event.target.elements.resend_confirmed.checked?'1':'0',delivery_token:attempt}));
      invoice=result.invoice;attempt=null;state();event.target.elements.patient_agreement.checked=false;event.target.elements.resend_confirmed.checked=false;listChanged=true;feedback(result.message);
    }catch(error){
      try{const result=await request(base+'/'+invoice.id);invoice=result.invoice;state();}catch(ignored){}
      throw error;
    }finally{if(invoice.email_state!=='sending'&&invoice.email_state!=='uncertain')$('invoice-send').disabled=!gmailReady;}
  });});
  $('invoice-reset-delivery').addEventListener('click',()=>run(async()=>{const result=await request(base+'/'+invoice.id+'/delivery/reset',body({verified_not_sent:'1'}));invoice=result.invoice;attempt=null;state();feedback('Envoi réactivé après votre vérification.');}));
  $('invoice-payment-form').addEventListener('submit',event=>{event.preventDefault();run(async()=>{const result=await request(base+'/'+invoice.id+'/payment',body({paid_on:event.target.elements.paid_on.value,revision:invoice.revision}));invoice=result.invoice;listChanged=true;state();feedback(invoice.paid_on?'Paiement patient enregistré.':'Marquage du paiement retiré.');});});
  async function openSettings(){const result=await request(base+'/settings');settingsForm.reset();settingsRevision=result.revision;
    for(const [name,value]of Object.entries(result.settings))if(settingsForm.elements.namedItem(name))settingsForm.elements.namedItem(name).value=value??'';
    settingsForm.elements.default_patient_amount.value=(result.settings.default_patient_cents/100).toFixed(2);
    settingsDirty=false;$('invoice-settings-discard').hidden=true;
    $('invoice-settings-feedback').textContent='';settingsDialog.showModal();
  }
  settingsForm.addEventListener('input',()=>{settingsDirty=true;});
  function closeSettings(){if(settingsSaving)return;if(settingsDirty){$('invoice-settings-feedback').textContent='Vos modifications ne sont pas enregistrées.';$('invoice-settings-discard').hidden=false;return;}settingsDialog.close();}
  $('invoice-settings-close').addEventListener('click',closeSettings);
  settingsDialog.addEventListener('cancel',event=>{event.preventDefault();closeSettings();});
  $('invoice-settings-discard').addEventListener('click',()=>{settingsDirty=false;settingsDialog.close();});
  settingsForm.addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;settingsSaving=true;settingsForm.inert=true;
    try{const data=new FormData(settingsForm);data.set('csrf_token',csrf);data.set('revision',settingsRevision);const result=await request(base+'/settings',data);settingsRevision=result.revision;
      if(invoice?.state==='draft'){if(!form.elements.doctor_name.value)form.elements.doctor_name.value=result.settings.doctor_name;if(!form.elements.doctor_inami.value)form.elements.doctor_inami.value=result.settings.doctor_inami;dirty=true;}
      missingSettings=result.missing;settingsDirty=false;$('invoice-settings-discard').hidden=true;if(invoice)state();
      $('invoice-settings-feedback').textContent=result.missing.length?'Coordonnées enregistrées. Certains champs restent à compléter.':'Coordonnées et IBAN enregistrés.';
    }catch(error){$('invoice-settings-feedback').textContent=error.message;}finally{button.disabled=false;settingsSaving=false;settingsForm.inert=false;}
  });
  document.addEventListener('click',async event=>{
    const settings=event.target.closest('[data-invoice-settings]');
    const existing=event.target.closest('[data-invoice-open]');
    const create=event.target.closest('[data-invoice-create], [data-invoice-current-patient]');
    if(!settings&&!existing&&!create)return;
    event.preventDefault();const clicked=settings||existing||create;clicked.disabled=true;
    try{
      if(settings){await openSettings();return;}
      if(existing){searchSheet?.close();await open(existing.dataset.invoiceOpen);return;}
      let fields={appointment_id:create.dataset.invoiceAppointment,reservation_start:create.dataset.invoiceReservation,historical_id:create.dataset.invoiceHistorical};
      if(create.hasAttribute('data-invoice-current-patient')){const context=$('report-form');fields={appointment_id:context.elements.appointment_id.value,reservation_start:context.elements.reservation_start.value};}
      const result=await request(base,body(fields));listChanged=true;
      searchSheet?.close();
      if(!$('report-modal')?.hidden)$('report-close')?.click();
      await open(result.invoice.id);
    }catch(error){if(editor.open)feedback(error.message,true);else{let box=$('invoice-list-feedback')||$('availability-feedback');if(box){box.hidden=false;box.textContent=error.message;}}}
    finally{clicked.disabled=false;}
  });
  window.addEventListener('beforeunload',event=>{if(editor.open&&dirty){event.preventDefault();event.returnValue='';}});
  const patientSearch=$('invoice-patient-search-form');
  if(patientSearch){
    const query=$('invoice-patient-query'),results=$('invoice-patient-results'),status=$('invoice-search-status');
    const empty=$('invoice-search-empty');
    let timer=null,controller=null,generation=0;
    const reset=()=>{clearTimeout(timer);controller?.abort();controller=null;generation++;results.replaceChildren();results.hidden=true;results.removeAttribute('aria-busy');};
    async function search(){
      reset();const term=query.value.trim().replace(/\s+/g,' '),current=generation;
      empty.hidden=term.length>=2;
      if(term.length<2){status.textContent='';return;}
      controller=new AbortController();status.textContent='Recherche…';results.setAttribute('aria-busy','true');
      try{
        const data=await request(base+'/patients/search',body({q:term}),controller.signal);
        if(current!==generation)return;
        for(const patient of data.patients){
          const row=document.createElement('li'),identity=document.createElement('div');
          const name=document.createElement('strong'),details=document.createElement('span'),exam=document.createElement('p');
          name.textContent=patient.patient_name;
          const date=new Date(patient.starts_at.length===10?patient.starts_at+'T12:00':patient.starts_at);
          const options={day:'2-digit',month:'2-digit',year:'numeric'};
          if(patient.starts_at.length>10)Object.assign(options,{hour:'2-digit',minute:'2-digit'});
          details.textContent=patient.kind+' · '+new Intl.DateTimeFormat('fr-BE',options).format(date);
          exam.textContent=patient.examination;identity.append(name,details,exam);
          const button=document.createElement('button');button.type='button';button.className='invoice-search-result';
          if(patient.invoice_id){button.dataset.invoiceOpen=patient.invoice_id;}
          else{
            button.dataset.invoiceCreate='';
            if(patient.appointment_id)button.dataset.invoiceAppointment=patient.appointment_id;
            if(patient.historical_id)button.dataset.invoiceHistorical=patient.historical_id;
            if(patient.reservation_start)button.dataset.invoiceReservation=patient.reservation_start;
          }
          const avatar=document.createElement('span');avatar.className='invoice-avatar';avatar.setAttribute('aria-hidden','true');avatar.textContent=patient.patient_name.trim().split(/\s+/).slice(0,2).map(word=>word[0]).join('');
          button.append(avatar,identity);row.append(button);results.append(row);
        }
        results.hidden=!data.patients.length;
        status.textContent=data.patients.length?data.patients.length+' résultat(s)'+(data.limited?' · Précisez le nom':''):'Aucun patient trouvé';
      }catch(error){if(current===generation)status.textContent=error.message;}
      finally{if(current===generation){results.removeAttribute('aria-busy');controller=null;}}
    }
    query.addEventListener('input',()=>{reset();empty.hidden=query.value.trim().length>=2;status.textContent=query.value.trim().length<2?'':'Recherche…';timer=setTimeout(search,300);});
    patientSearch.addEventListener('submit',event=>{event.preventDefault();search();});
    document.addEventListener('click',event=>{if(event.target.closest('[data-invoice-new]')){reset();query.value='';status.textContent='';empty.hidden=false;searchSheet.showModal();query.focus();}});
    $('invoice-search-close').addEventListener('click',()=>searchSheet.close());
    searchSheet.addEventListener('close',reset);
    window.addEventListener('pagehide',reset);
  }
  const workspace=$('invoice-list-workspace');
  if(workspace){let filterController=null,filterVersion=0;
    document.addEventListener('click',async event=>{const link=event.target.closest('[data-invoice-list-url]');if(!link||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();
      filterController?.abort();filterController=new AbortController();const version=++filterVersion;
      workspace.classList.add('is-loading');workspace.setAttribute('aria-busy','true');
      try{const target=new URL(link.href);target.searchParams.set('fragment','1');const result=await request(target.href,null,filterController.signal);if(version!==filterVersion)return;workspace.innerHTML=result.html;target.searchParams.delete('fragment');history.replaceState(null,'',target.href);$('invoice-list-feedback').textContent='';}
      catch(error){if(version===filterVersion)$('invoice-list-feedback').textContent=error.message;}
      finally{if(version===filterVersion){workspace.classList.remove('is-loading');workspace.removeAttribute('aria-busy');}}
    });
  }
  if(location.hash==='#settings')openSettings().catch(error=>{$('invoice-list-feedback').textContent=error.message;});
})();
