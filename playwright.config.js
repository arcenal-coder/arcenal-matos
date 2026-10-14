const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser',
  timeout: 45000,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:8766', channel: 'chromium', timezoneId: 'Europe/Paris', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: {
    command: '.venv/bin/python scripts/browser_server.py',
    url: 'http://127.0.0.1:8766/login/',
    timeout: 60000,
    reuseExistingServer: false,
  },
});
