const { test, expect } = require('@playwright/test');

test('signature au bas droit des pages courtes et longues sur ordinateur et mobile', async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/login/');
    await checkFooter(page);
    await page.getByLabel('Profil d’essai').selectOption({ label: 'Gestionnaire Siège — Gestionnaire' });
    await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
    for (const path of ['/inventory/', '/assets/new/']) {
      await page.goto(path);
      await checkFooter(page);
    }
    await page.getByRole('button', { name: 'Déconnexion' }).click();
  }
});

async function checkFooter(page) {
  const signature = page.locator('footer .arcenal-signature');
  await expect(signature).toHaveText('Par ARCenal');
  const geometry = await signature.evaluate(element => {
    const footer = element.closest('footer');
    const box = element.getBoundingClientRect();
    const footerBox = footer.getBoundingClientRect();
    const padding = getComputedStyle(footer);
    return {
      right: box.right,
      expectedRight: footerBox.right - parseFloat(padding.paddingRight),
      bottom: box.bottom + scrollY,
      expectedBottom: document.documentElement.scrollHeight - parseFloat(padding.paddingBottom),
      footerBottom: footerBox.bottom + scrollY,
      viewport: innerHeight,
      mainBottom: document.querySelector('main').getBoundingClientRect().bottom,
      footerTop: footerBox.top,
    };
  });
  expect(Math.abs(geometry.right - geometry.expectedRight)).toBeLessThan(2);
  expect(Math.abs(geometry.bottom - geometry.expectedBottom)).toBeLessThan(2);
  expect(geometry.footerBottom).toBeGreaterThanOrEqual(geometry.viewport);
  expect(geometry.footerTop).toBeGreaterThanOrEqual(geometry.mainBottom - 1);
}
