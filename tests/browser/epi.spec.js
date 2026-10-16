const { test, expect } = require('@playwright/test');
const { default: AxeBuilder } = require('@axe-core/playwright');

async function login(page, label) {
  await page.goto('/login/');
  await page.getByLabel('Profil d’essai').selectOption({ label });
  await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
}
const manager = 'Gestionnaire Siège — Gestionnaire';
const member = "Collaborateur d'essai — Collaborateur";
const admin = "Administrateur d'essai — Administrateur";
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris' }).format(new Date());
function day(offset) {
  const date = new Date(today() + 'T12:00:00Z'); date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

async function reference(page, name, kind, tracking, usageDays) {
  await page.goto('/epi/catalogue/new/');
  await page.locator('#id_name').fill(name);
  await page.locator('#id_kind').fill(kind);
  await page.locator('#id_tracking').selectOption(tracking);
  await page.locator('#id_unit').selectOption('pair');
  await page.locator('#id_usage_days').fill(String(usageDays));
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(/\/epi\/catalogue\/$/);
}

async function receive(page, name, number, quantity, expiry, serials = '') {
  await page.goto('/epi/stock/new/');
  await page.locator('#id_reference').selectOption({ label: name });
  await page.locator('#id_site').selectOption({ label: 'Siège (essai)' });
  await page.locator('#id_number').fill(number);
  await page.locator('#id_received_on').fill(day(-10));
  await page.locator('#id_received_quantity').fill(String(quantity));
  await page.locator('#id_manufacturer_expiry').fill(expiry);
  await page.locator('#id_unit_price').fill('12.50');
  if (serials) await page.locator('#id_serials').fill(serials);
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(/\/epi\/lots\/\d+\/$/);
}

test('EPI par lots : demande, acceptation, remise, prix privé et destruction', async ({ page }) => {
  await login(page, manager);
  await page.getByRole('navigation', { name: 'Navigation principale' }).getByRole('link', { name: 'EPI', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Gestion des EPI', exact: true })).toBeVisible();
  await reference(page, 'Gants EPI navigateur', 'Gants', 'bulk', 30);
  await receive(page, 'Gants EPI navigateur', 'GANTS-LOT-A', 20, day(365));
  const lotUrl = page.url();
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await login(page, member);
  await page.goto('/epi/requests/new/');
  await page.locator('#id_reference').selectOption({ label: 'Gants EPI navigateur' });
  await page.locator('#id_quantity').fill('3');
  await page.locator('#id_reason').fill('Renouvellement EPI');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  const requestUrl = page.url();
  await expect(page.getByText('À traiter', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await login(page, manager);
  await page.goto(requestUrl);
  await page.getByRole('button', { name: 'Enregistrer la décision' }).click();
  await expect(page.getByText('Acceptée, à remettre', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Choisir ce lot' }).click();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByText('Remise effectuée', { exact: true })).toBeVisible();
  await page.goto(lotUrl);
  await expect(page.getByText('17 paire(s)', { exact: true })).toBeVisible();
  await page.goto('/epi/distributed/');
  const row = page.getByRole('row').filter({ hasText: 'Gants EPI navigateur' });
  await expect(row).toContainText(/37[,.]50/);
  await row.getByRole('link', { name: 'Enregistrer une destruction' }).click();
  await page.locator('#id_reason').fill('Gants déchirés');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: 'Gants déchirés' })).toContainText(/12[,.]50/);
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await login(page, member);
  await page.goto('/epi/mine/');
  await expect(page.getByRole('row').filter({ hasText: 'Gants EPI navigateur' })).toContainText('2');
  await expect(page.getByRole('columnheader', { name: 'Coût historique HT' })).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('37,50');
  await page.goto('/inventory/?q=Gants%20EPI%20navigateur');
  await expect(page.getByText('Aucun équipement.', { exact: false })).toBeVisible();
});

test('EPI individuel : série, validité expirée, remise passée et demande IA explicite', async ({ page }) => {
  await login(page, admin);
  await reference(page, 'Harnais EPI navigateur', 'Harnais', 'individual', 365);
  await receive(page, 'Harnais EPI navigateur', 'HAR-LOT-A', 2, day(-1), 'HAR-SN-01\nHAR-SN-02');
  const lotUrl = page.url();
  await expect(page.getByRole('cell', { name: 'HAR-SN-01', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Remettre à un équipier' }).click();
  await page.locator('#id_recipient').selectOption({ label: "Collaborateur d'essai" });
  await page.locator('#id_unit').selectOption({ index: 1 });
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.locator('.errorlist')).toContainText('expiré à la date de remise');
  await page.locator('#id_issued_on').fill(day(-2));
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(/\/epi\/distributed\/$/);
  await expect(page.getByRole('row').filter({ hasText: 'Harnais EPI navigateur' })).toContainText('Expiré');
  await page.goto(lotUrl);
  await page.getByRole('link', { name: 'Renseigner la validité du lot' }).click();
  await page.locator('#id_manufacturer_expiry').fill(day(90));
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(lotUrl);
  await page.goto('/integration/');
  await page.getByLabel('Activer l’assistance à la saisie par l’agent MCP').check();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto(lotUrl);
  await page.getByRole('link', { name: 'Demander la validité à l’agent' }).click();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(/\/epi\/validity\/$/);
  await expect(page.getByText('En attente de l’agent', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Appliquer la proposition' })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('EPI : formulaires et stock accessibles en clair/sombre et sur mobile', async ({ page }) => {
  await login(page, admin);
  for (const [width, mode] of [[1440, 'light'], [390, 'dark']]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByLabel('Apparence').selectOption(mode);
    for (const path of ['/epi/catalogue/new/', '/epi/stock/new/', '/epi/stock/']) {
      await page.goto(path);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const result = await new AxeBuilder({ page }).include('main').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations).toEqual([]);
    }
  }
});
