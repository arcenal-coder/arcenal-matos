const { test, expect } = require('@playwright/test');

async function login(page, label) {
  await page.goto('/login/');
  await page.getByLabel('Profil d’essai').selectOption({ label });
  await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
}

test('Confirmation d’annulation : fermer le dialogue conserve la réservation', async ({ page }) => {
  await login(page, 'Gestionnaire Siège — Gestionnaire');
  await page.goto('/assets/new/');
  await page.locator('[name=code]').fill('RC-CANCEL');
  await page.locator('[name=name]').fill('Matériel confirmation RC');
  await page.locator('[name=category]').selectOption({ label: 'Matériel général' });
  await page.locator('[name=site]').selectOption({ label: 'Siège (essai)' });
  await page.locator('[name=custom_fields]').fill('{}');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  const url = new URL(page.url()).pathname;
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await login(page, "Collaborateur d'essai — Collaborateur");
  await page.goto(url + 'reserve/');
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await page.getByRole('row').filter({ hasText: 'Matériel confirmation RC' }).getByRole('link', { name: 'Traiter →' }).click();
  const reservationUrl = page.url();
  page.once('dialog', async dialog => { expect(dialog.message()).toContain('Une nouvelle demande'); await dialog.dismiss(); });
  await page.getByRole('button', { name: 'Annuler', exact: true }).click();
  await expect(page.getByText('En attente', { exact: true })).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Annuler', exact: true }).click();
  await page.goto(reservationUrl);
  await expect(page.getByText('Annulée', { exact: true })).toBeVisible();
});

test('Reflow équivalent à un zoom 200 % sur un écran 1440 px', async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 500 });
  await login(page, 'Gestionnaire Siège — Gestionnaire');
  await page.goto('/assets/new/');
  await expect(page.getByRole('button', { name: 'Enregistrer', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('button', { name: 'Menu', exact: true })).toBeVisible();
});
