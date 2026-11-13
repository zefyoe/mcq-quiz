/* Internal shortcuts reflect every free slot; public release rules stay server-side. */
(() => {
  const calendar = document.getElementById('internal-calendar-grid');
  const target = document.getElementById('internal-quick-slots');
  if (!calendar || !target) return;
  let expanded = false;
  function render() {
    const slots = [...calendar.querySelectorAll('button[data-slot]:not(:disabled)')]
      .sort((a, b) => a.dataset.slot.localeCompare(b.dataset.slot));
    const content = document.createDocumentFragment();
    if (!slots.length) {
      const empty = document.createElement('p');
      empty.className = 'agenda-quick-empty';
      empty.textContent = 'Aucun créneau libre cette semaine.';
      content.append(empty);
    }
    let previousDay;
    for (const slot of slots.slice(0, expanded ? slots.length : 6)) {
      const day = slot.dataset.slot.slice(0, 10);
      if (day !== previousDay) {
        const heading = document.createElement('p');
        heading.className = 'agenda-quick-date';
        heading.textContent = new Date(day + 'T12:00:00').toLocaleDateString('fr-BE', {weekday: 'long', day: 'numeric', month: 'short'});
        content.append(heading);
        previousDay = day;
      }
      const choice = document.createElement('button');
      choice.type = 'button';
      choice.className = 'agenda-internal-choice';
      choice.textContent = slot.dataset.slot.slice(11, 16);
      choice.setAttribute('aria-label', 'Planifier le ' + slot.dataset.slotLabel);
      choice.addEventListener('click', () => { if (slot.isConnected && !slot.disabled) slot.click(); });
      content.append(choice);
    }
    if (slots.length > 6) {
      const more = document.createElement('button');
      more.type = 'button';
      more.className = 'agenda-quick-more';
      more.textContent = expanded ? 'Réduire' : 'Tous les créneaux';
      more.setAttribute('aria-expanded', String(expanded));
      more.addEventListener('click', () => { expanded = !expanded; render(); target.querySelector('.agenda-quick-more')?.focus(); });
      content.append(more);
    }
    target.replaceChildren(content);
  }
  new MutationObserver(render).observe(calendar, {childList: true, subtree: true});
  render();
})();
