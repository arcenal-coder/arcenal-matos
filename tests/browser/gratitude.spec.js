const { test, expect } = require('@playwright/test');
const { default: AxeBuilder } = require('@axe-core/playwright');
const fs = require('node:fs/promises');
const { version } = require('../../package.json');

async function openWorkspace(page) {
  await page.goto('/login/');
  await page.getByLabel('Profil d’essai').selectOption({ label: 'Gestionnaire Siège — Gestionnaire' });
  await page.getByRole('button', { name: 'Ouvrir l’espace' }).click();
}
function contrast(first, second) {
  const luminance = value => {
    const rgb = value.startsWith('#')
      ? value.slice(1).match(/.{2}/g).map(channel => parseInt(channel, 16))
      : value.match(/[\d.]+/g).slice(0, 3).map(Number);
    const channels = rgb.map(channel => {
      const normalized = channel / 255;
      return normalized <= .04045 ? normalized / 12.92 : ((normalized + .055) / 1.055) ** 2.4;
    });
    return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
  };
  const a = luminance(first), b = luminance(second);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}

for (const width of [1440, 1024, 390]) {
  for (const mode of ['light', 'dark']) {
    test(`Gratitude ${mode}, ${width}px : palette, contraste et accessibilité`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await openWorkspace(page);
      await page.getByLabel('Apparence').selectOption(mode);
      await page.goto('/inventory/');
      await expect(page.locator('html')).toHaveAttribute('data-theme', mode);
      await expect(page.locator('nav a[aria-current=page]')).toHaveAttribute('href', '/inventory/');
      await page.evaluate(() => document.fonts.ready);
      const tokens = await page.evaluate(() => {
        const computed = getComputedStyle(document.documentElement);
        const names = ['surface', 'surface-secondary', 'text', 'text-secondary', 'primary', 'primary-text',
          'success', 'success-surface', 'warning', 'warning-surface', 'error', 'error-surface', 'input-boundary', 'focus'];
        return Object.fromEntries(names.map(name => [name, computed.getPropertyValue('--arc-' + name).trim()]));
      });
      expect(tokens.surface).toBe(mode === 'light' ? '#fffdf8' : '#20232a');
      for (const [foreground, background] of [['text', 'surface'], ['text-secondary', 'surface'],
        ['text-secondary', 'surface-secondary'], ['primary-text', 'primary'], ['primary', 'surface'],
        ['success', 'success-surface'], ['warning', 'warning-surface'], ['error', 'error-surface']]) {
        expect(contrast(tokens[foreground], tokens[background]), `${foreground} / ${background}`).toBeGreaterThanOrEqual(4.5);
      }
      expect(contrast(tokens['input-boundary'], tokens.surface)).toBeGreaterThanOrEqual(3);
      const tooSmall = await page.evaluate(() => [...document.querySelectorAll('a,button,label,small,p,th,td,code,.eyebrow,.navlabel')]
        .filter(element => element.getBoundingClientRect().height && parseFloat(getComputedStyle(element).fontSize) < 12)
        .map(element => element.textContent.trim()));
      expect(tooSmall).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
      expect(audit.violations).toEqual([]);
      await fs.mkdir('.local/screenshots/rc', { recursive: true });
      await page.screenshot({ path: `.local/screenshots/rc/gratitude-${mode}-${width}.png`, fullPage: true });
    });
  }
}

test('Système suit le navigateur en temps réel, choix manuel prioritaire et persistant', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await openWorkspace(page);
  await page.getByLabel('Apparence').selectOption('system');
  const surface = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--arc-surface').trim());
  expect(await surface()).toBe('#fffdf8');
  await page.emulateMedia({ colorScheme: 'dark' });
  expect(await surface()).toBe('#20232a');
  await page.getByLabel('Apparence').selectOption('light');
  expect(await surface()).toBe('#fffdf8');
  await page.reload();
  await expect(page.getByLabel('Apparence')).toHaveValue('light');
  expect(await surface()).toBe('#fffdf8');
});

test('Clavier, navigation compacte et mouvements réduits', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openWorkspace(page);
  const menu = page.getByRole('button', { name: 'Menu', exact: true });
  await menu.focus();
  await page.keyboard.press('Enter');
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('navigation')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await expect(menu).toBeFocused();
  expect(await menu.evaluate(element => getComputedStyle(element).outlineWidth)).toBe('3px');
  expect((await menu.boundingBox()).height).toBeGreaterThanOrEqual(44);
  await page.goto('/scan/');
  expect(await page.locator('#start-scan').evaluate(element => getComputedStyle(element).transitionDuration)).toBe('0s');
});

test('État erreur en clair et sombre, formulaire accessible et version RC visible', async ({ page }) => {
  await openWorkspace(page);
  for (const mode of ['light', 'dark']) {
    await page.getByLabel('Apparence').selectOption(mode);
    await page.goto('/assets/new/');
    await page.locator('main form').evaluate(form => { form.noValidate = true; });
    await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
    await expect(page.locator('.errorlist').first()).toBeVisible();
    await expect(page.locator('footer')).toContainText(version);
    const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(audit.violations).toEqual([]);
    await page.screenshot({ path: `.local/screenshots/rc/gratitude-error-${mode}.png`, fullPage: true });
  }
});
