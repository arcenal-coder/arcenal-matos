const { test, expect } = require('@playwright/test');
const fs = require('node:fs/promises');

async function login(page, label) {
  await page.goto('/login/');
  await page.getByLabel('Profil d’essai').selectOption({ label });
  await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
  await expect(page.getByRole('heading', { name: 'Tableau de bord' })).toBeVisible();
}
async function downloadBytes(download) {
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return Buffer.concat(chunks);
}

test('parcours réel : fiche, demande, validation, sortie, retour et maintenance', async ({ page }) => {
  const failures = [];
  page.on('pageerror', error => failures.push(error.message));
  await login(page, 'Gestionnaire Siège — Gestionnaire');
  await page.goto('/assets/new/');
  await page.locator('[name=name]').fill('Perceuse E2E');
  await page.locator('[name=category]').selectOption({ label: 'Matériel général' });
  await page.locator('[name=site]').selectOption({ label: 'Siège (essai)' });
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(/\/inventory\/$/);
  await page.getByRole('link', { name: /Perceuse E2E/ }).click();
  await expect(page.getByRole('heading', { name: 'Perceuse E2E', exact: true })).toBeVisible();
  const assetUrl = new URL(page.url()).pathname;
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await login(page, "Collaborateur d'essai — Collaborateur");
  await page.goto(assetUrl);
  await page.getByRole('link', { name: 'Demander ce matériel' }).click();
  await page.locator('[name=reason]').fill('Intervention interne');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByText('Demande transmise au gestionnaire')).toBeVisible();
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await login(page, 'Gestionnaire Siège — Gestionnaire');
  await page.goto('/reservations/');
  await page.getByRole('link', { name: 'Traiter →' }).first().click();
  await page.getByRole('button', { name: 'Valider le prêt' }).click();
  await page.getByRole('link', { name: 'Traiter →' }).first().click();
  await page.getByRole('link', { name: 'Enregistrer la sortie' }).click();
  await page.locator('[name=condition]').fill('Bon état, batterie chargée');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByText('Bon état, batterie chargée')).toBeVisible();
  await page.getByRole('link', { name: 'Enregistrer le retour' }).click();
  await page.locator('[name=condition]').fill('Mandrin endommagé');
  await page.locator('[name=damaged]').check();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto(assetUrl);
  await expect(page.getByText('Indisponible', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Intervention', exact: true }).click();
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris' }).format(new Date());
  await page.locator('[name=scheduled_date]').fill(today);
  await page.locator('[name=description]').fill('Réparation du mandrin');
  await page.locator('[name=cost]').fill('25');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.getByRole('button', { name: 'Terminer aujourd’hui' }).click();
  await page.goto(assetUrl);
  await page.getByRole('button', { name: 'Remettre en service' }).click();
  await page.goto(assetUrl);
  await expect(page.getByText('Disponible', { exact: true })).toBeVisible();
  await fs.mkdir('.local/screenshots', { recursive: true });
  await page.screenshot({ path: '.local/screenshots/asset-desktop.png', fullPage: true });
  expect(failures).toEqual([]);
});

test('modèle CSV, import atomique et rapports PDF/CSV', async ({ page }) => {
  await login(page, 'Gestionnaire Siège — Gestionnaire');
  await page.goto('/import/');
  const templatePromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Télécharger le modèle' }).click();
  const content = (await downloadBytes(await templatePromise)).toString('utf8').replace(/^\uFEFF/, '');
  const row = ['E2E-CSV', 'Équipement importé', 'Matériel général', '', '', '', 'Siège (essai)', 'Réserve', 'available', '', '', '', 'non', '', '', '', '{}'].join(';');
  await page.locator('input[type=file]').setInputFiles({ name: 'inventaire.csv', mimeType: 'text/csv', buffer: Buffer.from(content + row + '\r\n') });
  await page.getByRole('button', { name: 'Vérifier et importer' }).click();
  await expect(page.getByText('1 équipement(s) importé(s)')).toBeVisible();
  await page.goto('/reports/');
  const pdfPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'PDF inventaire / audit' }).click();
  expect((await downloadBytes(await pdfPromise)).subarray(0, 4).toString()).toBe('%PDF');
  const csvPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'CSV exploitable' }).click();
  expect((await downloadBytes(await csvPromise)).toString()).toContain('E2E-CSV');
});

test('administrateur : export YAML sans secret et écrans de configuration', async ({ page }) => {
  await login(page, "Administrateur d'essai — Administrateur");
  await page.goto('/integration/');
  await page.getByText('Configuration MCP existante (technique)', { exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Agent & MCP' })).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Télécharger le YAML' }).click();
  const yaml = (await downloadBytes(await downloadPromise)).toString();
  expect(yaml).toContain('schema: arcenal-agent-link');
  expect(yaml).toContain('credential_ref: MATOS_MCP_TOKEN');
  expect(yaml).toContain('supplier_requests.approve');
  await page.goto('/settings/');
  await expect(page.getByRole('heading', { name: 'Paramètres' })).toBeVisible();
});

test('affichage mobile et refus de gestion hors site', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'Gestionnaire Atelier — Gestionnaire');
  await page.goto('/inventory/');
  await expect(page.getByText('Perceuse E2E')).toHaveCount(0);
  await expect(page.getByText('Équipement importé')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await fs.mkdir('.local/screenshots', { recursive: true });
  await page.screenshot({ path: '.local/screenshots/inventory-mobile.png', fullPage: true });
});

test('décodage réel du QR généré depuis une image', async ({ page }) => {
  await login(page, 'Gestionnaire Siège — Gestionnaire');
  await page.goto('/inventory/?q=Perceuse%20E2E');
  await page.getByRole('link', { name: 'Perceuse E2E' }).click();
  const imageUrl = await page.getByAltText('QR code de la fiche').getAttribute('src');
  const image = await page.request.get(imageUrl);
  await page.goto('/scan/');
  await page.locator('#scan-image').setInputFiles({ name: 'etiquette.png', mimeType: 'image/png', buffer: await image.body() });
  await expect(page.getByRole('heading', { name: 'Perceuse E2E', exact: true })).toBeVisible();
});
