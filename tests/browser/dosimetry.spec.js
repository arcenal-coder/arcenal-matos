const { test, expect } = require('@playwright/test');
const { default: AxeBuilder } = require('@axe-core/playwright');

const admin = "Administrateur d'essai — Administrateur";
const manager = 'Gestionnaire Siège — Gestionnaire';
const member = "Collaborateur d'essai — Collaborateur";
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris' }).format(new Date());
function day(offset) {
  const date = new Date(today() + 'T12:00:00Z'); date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}
async function login(page, label) {
  await page.goto('/login/');
  await page.getByLabel('Profil d’essai').selectOption({ label });
  await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
}
async function setModules(page, epi, dosimeters) {
  await page.goto('/settings/modules/');
  await page.locator('#id_epi_enabled').setChecked(epi);
  await page.locator('#id_dosimeters_enabled').setChecked(dosimeters);
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
}
async function configurePeriod(page, suffix) {
  await page.goto('/dosimeters/configuration/laboratories/');
  await page.locator('#id_name').fill(`Laboratoire ${suffix}`);
  await page.locator('#id_address').fill('Adresse du laboratoire');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto('/dosimeters/configuration/periods/');
  await page.locator('#id_name').fill(`Port ${suffix}`);
  await page.locator('#id_laboratory').selectOption({ label: `Laboratoire ${suffix}` });
  await page.locator('#id_start_on').fill(day(-10));
  await page.locator('#id_end_on').fill(day(20));
  await page.locator('#id_return_due_on').fill(day(25));
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
}
async function receive(page, suffix, codes, kind = 'personal') {
  await page.goto('/dosimeters/badges/new/');
  await page.locator('#id_site').selectOption({ label: 'Siège (essai)' });
  await page.locator('#id_period').selectOption({ label: `Port ${suffix} · Laboratoire ${suffix}` });
  await page.locator('#id_codes').fill(codes);
  await page.locator('#id_received_on').fill(day(-12));
  await page.locator('#id_kind').selectOption(kind);
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page).toHaveURL(/\/dosimeters\/badges\/$/);
}

test('interrupteurs indépendants, accès bloqués et données EPI conservées', async ({ page }) => {
  await login(page, admin);
  await setModules(page, true, false);
  await page.goto('/epi/catalogue/new/');
  await page.locator('#id_name').fill('Référence conservée activation');
  await page.locator('#id_kind').fill('Test activation');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await setModules(page, false, true);
  const navigation = page.getByRole('navigation', { name: 'Navigation principale' });
  await expect(navigation.getByRole('link', { name: 'EPI', exact: true })).toHaveCount(0);
  await expect(navigation.getByRole('link', { name: 'Dosimètres', exact: true })).toBeVisible();
  const blocked = await page.goto('/epi/catalogue/');
  expect(blocked.status()).toBe(404);
  await setModules(page, true, false);
  await page.goto('/epi/catalogue/');
  await expect(page.getByText('Référence conservée activation', { exact: true })).toBeVisible();
  const disabled = await page.goto('/dosimeters/');
  expect(disabled.status()).toBe(404);
  await page.goto('/inventory/');
  await expect(page.getByRole('heading', { name: 'Inventaire', exact: true })).toBeVisible();
});

test('badges passifs : préaffectation, remise, retour, envoi, perte et remplacement', async ({ page }) => {
  await login(page, admin);
  await setModules(page, true, true);
  await configurePeriod(page, 'navigateur');
  await receive(page, 'navigateur', 'PASS-01\nPASS-02');
  await page.getByRole('link', { name: 'PASS-01', exact: true }).click();
  const badgeUrl = page.url();
  await page.getByRole('link', { name: 'Préaffecter', exact: true }).click();
  await page.locator('#id_recipient').selectOption({ label: "Collaborateur d'essai" });
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.getByRole('link', { name: 'Distribuer', exact: true }).click();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByText('Distribué / en période', { exact: true })).toBeVisible();
  await login(page, member);
  await page.goto('/dosimeters/mine/');
  await expect(page.getByRole('link', { name: 'PASS-01', exact: true })).toBeVisible();
  await expect(page.locator('main')).not.toContainText('PASS-02');
  expect((await page.request.get('/dosimeters/badges/')).status()).toBe(403);
  await login(page, manager);
  await page.goto(badgeUrl);
  await page.getByRole('link', { name: 'Enregistrer la collecte' }).click();
  await page.getByRole('button', { name: 'Confirmer la collecte' }).click();
  await page.getByRole('link', { name: 'PASS-01', exact: true }).click();
  await page.getByRole('link', { name: 'Envoyer au laboratoire' }).click();
  await page.locator('#id_tracking').fill('SUIVI-NAVIGATEUR');
  await page.getByRole('button', { name: 'Confirmer l’expédition' }).click();
  await expect(page).toHaveURL(/\/dosimeters\/shipments\/\d+\/$/);
  await expect(page.getByText('SUIVI-NAVIGATEUR', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'PASS-01', exact: true })).toBeVisible();
  await page.goto('/dosimeters/badges/');
  await page.getByRole('link', { name: 'PASS-02', exact: true }).click();
  await page.getByRole('link', { name: 'Déclarer une perte / annulation' }).click();
  await page.locator('#id_reason').fill('Badge égaré avant la distribution');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByText('Perdu', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Réceptionner un remplacement' }).click();
  await page.locator('#id_new_code').fill('PASS-02-R');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByText('Remplace le badge PASS-02', { exact: true })).toBeVisible();
});

test('assistant logistique en attente et interfaces accessibles ordinateur/mobile', async ({ page }) => {
  await login(page, admin);
  await setModules(page, true, true);
  await configurePeriod(page, 'assistant');
  await receive(page, 'assistant', 'TEMOIN-AI', 'witness');
  await page.getByRole('link', { name: 'TEMOIN-AI', exact: true }).click();
  await page.getByRole('link', { name: 'Mettre le témoin en période' }).click();
  await expect(page.locator('#id_recipient')).toHaveCount(0);
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto('/integration/');
  await page.getByText('Configuration MCP existante (technique)', { exact: true }).click();
  await page.getByLabel('Activer l’assistance à la saisie par l’agent MCP').check();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto('/dosimeters/assistance/');
  await page.locator('#id_site').selectOption({ label: 'Siège (essai)' });
  await page.locator('#id_period').selectOption({ label: 'Port assistant · Laboratoire assistant' });
  await page.locator('#id_kind').selectOption('collection');
  await page.getByRole('button', { name: 'Demander l’aide de l’agent' }).click();
  await expect(page.getByText('En attente de l’agent', { exact: true })).toBeVisible();
  for (const [width, mode] of [[1440, 'light'], [390, 'dark']]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByLabel('Apparence').selectOption(mode);
    for (const url of ['/settings/modules/', '/dosimeters/badges/', '/dosimeters/badges/new/', '/dosimeters/operations/collection/']) {
      await page.goto(url);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const result = await new AxeBuilder({ page }).include('main').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations).toEqual([]);
    }
  }
});
