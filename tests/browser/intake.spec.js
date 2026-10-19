const { test, expect } = require('@playwright/test');

async function login(page, label) {
  await page.goto('/login/');
  await page.getByLabel('Profil d’essai').selectOption({ label });
  await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
}
async function addReference(page, kind, name) {
  await page.locator(`[data-add-reference=${kind}]`).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Nom de la référence', { exact: true }).fill(name);
  await dialog.getByRole('button', { name: 'Ajouter à la liste' }).click();
  await expect(dialog).not.toBeVisible();
}

test('saisie simple, références sur place, identifiant automatique et retour inventaire', async ({ page }) => {
  await login(page, 'Gestionnaire Siège — Gestionnaire');
  await page.goto('/assets/new/');
  await expect(page.locator('[name=code]')).toHaveCount(0);
  await expect(page.locator('[name=custom_fields]')).toHaveCount(0);
  await page.locator('#id_name').fill('Moniteur simplifié');
  const saveBox = await page.locator('.form-actions button').boundingBox();
  const cancelBox = await page.locator('.form-actions a').boundingBox();
  expect(cancelBox.x - saveBox.x - saveBox.width).toBeGreaterThanOrEqual(16);
  await addReference(page, 'category', 'Moniteurs de contrôle');
  await addReference(page, 'brand', 'Philips');
  await addReference(page, 'model', 'MX40');
  await expect(page.locator('#id_name')).toHaveValue('Moniteur simplifié');
  await page.locator('[data-add-reference=brand]').click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Nom de la référence', { exact: true }).fill('filips');
  await dialog.getByRole('button', { name: 'Ajouter à la liste' }).click();
  await dialog.getByRole('button', { name: 'Utiliser Philips' }).click();
  await expect(page.locator('#id_brand')).toHaveValue('Philips');
  await expect(page.locator('#id_model').getByRole('option', { name: 'MX40', exact: true })).toBeAttached();
  await expect(page.locator('#id_model')).toHaveValue('MX40');
  await page.locator('#id_site').selectOption({ label: 'Siège (essai)' });
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(/\/inventory\/$/);
  await page.getByRole('link', { name: /Moniteur simplifié/ }).click();
  await expect(page.getByRole('heading', { name: 'Moniteur simplifié', exact: true })).toBeVisible();
  await expect(page.getByText(/MONITEURSDEC-\d+-000001/)).toBeVisible();
  await page.goto('/assets/new/');
  await page.locator('#id_name').fill('Ne pas enregistrer');
  await page.getByRole('link', { name: 'Annuler', exact: true }).click();
  await expect(page).toHaveURL(/\/inventory\/$/);
  await expect(page.getByText('Ne pas enregistrer', { exact: true })).toHaveCount(0);
});

test('Paramètres et assistance conditionnelle : attente puis réponse dans le formulaire', async ({ page }) => {
  await login(page, "Administrateur d'essai — Administrateur");
  const navigation = page.getByRole('navigation', { name: 'Navigation principale' });
  await expect(navigation.getByText('Administration', { exact: true })).toHaveCount(0);
  for (const name of ['Agent & MCP', 'Gestion des utilisateurs', 'Sites', 'Catégories & périodicités']) {
    await navigation.getByRole('link', { name, exact: true }).click();
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  }
  await page.goto('/settings/sites/');
  const logo = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 80; canvas.height = 24;
    const context = canvas.getContext('2d'); context.fillStyle = '#4080c0'; context.fillRect(8, 4, 64, 16);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await page.getByLabel('Choisir le logo').setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: Buffer.from(logo, 'base64') });
  await page.getByRole('button', { name: 'Enregistrer le logo' }).click();
  await expect(page.locator('.brand .company-logo')).toBeVisible();
  const brandLayout = await page.locator('.brand').evaluate(element => {
    const image = element.querySelector('img');
    return { loaded: image.complete && image.naturalWidth > 0, bottom: image.getBoundingClientRect().bottom,
      titleTop: element.querySelector('span').getBoundingClientRect().top, background: getComputedStyle(image).backgroundColor };
  });
  expect(brandLayout.loaded).toBe(true);
  expect(brandLayout.bottom).toBeLessThanOrEqual(brandLayout.titleTop);
  expect(brandLayout.background).toBe('rgba(0, 0, 0, 0)');
  await page.goto('/integration/');
  await page.getByText('Configuration MCP existante (technique)', { exact: true }).click();
  await page.getByLabel('Activer l’assistance à la saisie par l’agent MCP').check();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto('/assets/new/');
  await page.locator('#id_name').fill('Appareil assisté');
  await page.getByLabel('Type d’appareil / catégorie').selectOption({ label: 'Matériel général' });
  // Exercise the UI with a simulated agent reply; MCP round-trip is verified separately.
  await page.route('**/intake/assistance/*/', route => route.fulfill({ json: {
    status: 'done', serial: 'SN-RECONNU', interval_days: 365, explanation: 'Notice fabricant : contrôle annuel.',
  } }));
  await page.getByRole('button', { name: 'Demander à l’agent' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Demande envoyée' })).toBeVisible();
  await expect(page.locator('#id_serial')).toHaveValue('SN-RECONNU');
  await expect(page.getByLabel('Contrôle tous les (jours)')).toHaveValue('365');
  await expect(page.getByRole('status').filter({ hasText: 'Notice fabricant' })).toBeVisible();
});
