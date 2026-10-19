const { test, expect } = require('@playwright/test');
const { default: AxeBuilder } = require('@axe-core/playwright');

test('assistance SSO en lecture seule : nom accessible, serveur, nouvelle fenêtre sans contexte', async ({ page, context }) => {
  await page.goto('/login/');
  await page.getByLabel('Profil d’essai').selectOption({ label: "Administrateur d'essai — Administrateur" });
  await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
  await page.goto('/settings/modules/');
  await page.locator('#id_epi_enabled').check();
  await page.locator('#id_dosimeters_enabled').check();
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.goto('/integration/');
  const buttons = page.getByRole('button', { name: 'Demander à ARCenal Agent', exact: true });
  await expect(buttons).toHaveCount(3);
  await expect(buttons.first()).toBeDisabled();
  await expect(page.getByText('Liaison active', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Lier ARCenal Agent', exact: true })).toBeDisabled();
  await page.getByText('Ancienne destination SSO manuelle (technique)', { exact: true }).click();
  await page.locator('#id_sso_url').fill('/test-arcenal-agent/');
  await page.getByRole('button', { name: 'Enregistrer la destination SSO' }).click();
  // An isolated destination URL, not a deployed SSO receiver. A 404 here is
  // expected: this test verifies the redirect, privacy and window isolation.
  const incoming = [];
  context.on('request', request => {
    if (new URL(request.url()).pathname === '/test-arcenal-agent/') {
      incoming.push({ url: request.url(), referer: request.headers()['referer'], method: request.method() });
    }
  });
  for (const title of ['Matériel', 'EPI', 'Dosimètres passifs']) {
    const card = page.locator('.agent-link-card').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
    const pending = context.waitForEvent('page');
    await card.getByRole('button', { name: 'Demander à ARCenal Agent', exact: true }).click();
    const popup = await pending;
    await popup.waitForURL('**/test-arcenal-agent/');
    expect(new URL(popup.url()).pathname).toBe('/test-arcenal-agent/');
    expect(new URL(popup.url()).search).toBe('');
    expect(await popup.evaluate(() => window.opener === null)).toBe(true);
    await popup.close();
  }
  expect(incoming).toHaveLength(3);
  incoming.forEach(request => { expect(request.referer).toBeUndefined(); expect(request.method).toBe('GET'); });
  for (const path of ['/inventory/', '/epi/catalogue/', '/dosimeters/mine/']) {
    await page.goto(path);
    await expect(page.getByRole('button', { name: 'Demander à ARCenal Agent', exact: true })).toBeEnabled();
  }
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto('/integration/');
  const result = await new AxeBuilder({ page }).include('main').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
