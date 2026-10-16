/* Intake keeps unsaved fields in the page; private photos only go to this instance. */
(() => {
  const form = document.querySelector('#asset-form');
  if (!form) return;
  const token = form.querySelector('[name=csrfmiddlewaretoken]').value;
  const fields = Object.fromEntries(['category', 'brand', 'model', 'name', 'serial', 'interval_days'].map(name => [name, form.elements[name]]));
  const dialog = document.querySelector('#reference-dialog');
  const referenceForm = document.querySelector('#reference-form');
  const error = document.querySelector('#reference-error');
  const suggestions = document.querySelector('#reference-suggestions');
  let kind = '';
  let origin = null;
  let modelLoad = 0;
  const status = document.querySelector('#assistance-status');

  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', ...options });
    let data;
    try { data = await response.json(); } catch { throw new Error('La session a expiré ou le serveur est indisponible. Réessayez.'); }
    return { response, data };
  }
  function choose(option) {
    const select = fields[kind];
    const previous = select.value;
    if (![...select.options].some(item => item.value === option.value)) select.add(new Option(option.label, option.value));
    select.value = option.value;
    if (kind !== 'brand' || previous !== option.value) select.dispatchEvent(new Event('change', { bubbles: true }));
    dialog.close();
    origin?.focus();
  }
  document.querySelectorAll('[data-add-reference]').forEach(button => button.addEventListener('click', () => {
    kind = button.dataset.addReference;
    if (kind === 'model' && !fields.brand.value) {
      status.textContent = 'Choisissez ou ajoutez d’abord la marque.';
      fields.brand.focus();
      return;
    }
    origin = button;
    referenceForm.reset();
    error.textContent = '';
    suggestions.replaceChildren();
    document.querySelector('#reference-title').textContent = { category: 'Ajouter une catégorie', brand: 'Ajouter une marque', model: 'Ajouter un modèle' }[kind];
    document.querySelector('#reference-name').maxLength = kind === 'category' ? 120 : 100;
    dialog.showModal();
    document.querySelector('#reference-name').focus();
  }));
  document.querySelector('#reference-cancel').addEventListener('click', () => { dialog.close(); origin?.focus(); });
  async function saveReference(confirmDistinct = false) {
    const button = referenceForm.querySelector('[type=submit]');
    button.disabled = true;
    try {
      const body = new FormData(referenceForm);
      body.set('name', document.querySelector('#reference-name').value);
      body.set('brand', fields.brand.value);
      if (confirmDistinct) body.set('confirm_distinct', '1');
      const { response, data } = await jsonRequest(`${form.dataset.referenceBase}${kind}/`, { method: 'POST', headers: { 'X-CSRFToken': token }, body });
      if (response.ok) { choose(data); return; }
      error.textContent = data.error;
      suggestions.replaceChildren();
      (data.suggestions || []).forEach(option => {
        const use = document.createElement('button');
        use.type = 'button'; use.className = 'secondary'; use.textContent = `Utiliser ${option.label}`;
        use.addEventListener('click', () => choose(option)); suggestions.append(use);
      });
      if (data.suggestions?.length) {
        const create = document.createElement('button'); create.type = 'button'; create.className = 'secondary';
        create.textContent = 'Créer un nom distinct'; create.addEventListener('click', () => saveReference(true)); suggestions.append(create);
      }
    } catch (failure) { error.textContent = failure.message; }
    finally { button.disabled = false; }
  }
  referenceForm.addEventListener('submit', event => { event.preventDefault(); saveReference(); });
  fields.brand.addEventListener('change', async () => {
    const version = ++modelLoad;
    fields.model.replaceChildren(new Option('Choisir un modèle (facultatif)', ''));
    try {
      const { response, data } = await jsonRequest(`${form.dataset.referenceBase}model/?brand=${encodeURIComponent(fields.brand.value)}`);
      if (version !== modelLoad) return;
      if (!response.ok) throw new Error(data.error);
      data.options.forEach(item => fields.model.add(new Option(item.label, item.value)));
    } catch (failure) { status.textContent = failure.message; }
  });

  const assist = document.querySelector('#request-assistance');
  assist?.addEventListener('click', async () => {
    if (!fields.category.value) { status.textContent = 'Choisissez le type d’appareil avant de demander l’aide de l’agent.'; fields.category.focus(); return; }
    assist.disabled = true;
    const snapshot = JSON.stringify(['category', 'brand', 'model', 'name', 'serial', 'interval_days'].map(name => fields[name].value));
    try {
      const body = new FormData();
      ['category', 'brand', 'model', 'name'].forEach(name => body.set(name, fields[name].value));
      const photo = document.querySelector('#serial-photo').files[0];
      if (photo) body.set('photo', photo);
      const { response, data } = await jsonRequest(form.dataset.assistanceUrl, { method: 'POST', headers: { 'X-CSRFToken': token }, body });
      if (!response.ok) throw new Error(data.error);
      status.textContent = 'Demande envoyée. En attente de l’agent connecté ; vous pouvez continuer la saisie.';
      let attempts = 0;
      const poll = async () => {
        try {
          if (snapshot !== JSON.stringify(['category', 'brand', 'model', 'name', 'serial', 'interval_days'].map(name => fields[name].value))) {
            status.textContent = 'Les informations ont changé : relancez la demande pour éviter de remplacer votre saisie.';
            assist.disabled = false; return;
          }
          const result = await jsonRequest(`${form.dataset.resultBase}${data.id}/`);
          if (!result.response.ok) throw new Error(result.data.error || 'La demande n’est plus accessible.');
          if (result.data.status === 'done') {
            if (result.data.serial) fields.serial.value = result.data.serial;
            if (result.data.interval_days) { fields.interval_days.value = result.data.interval_days; document.querySelector('#asset-details').open = true; }
            status.textContent = `Réponse de l’agent : ${result.data.explanation} Vérifiez les informations avant d’enregistrer.`;
            assist.disabled = false; return;
          }
          if (++attempts >= 60) { status.textContent = 'L’agent n’a pas encore répondu. Vous pouvez poursuivre manuellement ou relancer la demande.'; assist.disabled = false; return; }
          setTimeout(poll, 3000);
        } catch (failure) { status.textContent = failure.message; assist.disabled = false; }
      };
      setTimeout(poll, 1500);
    } catch (failure) { status.textContent = failure.message; assist.disabled = false; }
  });
})();
