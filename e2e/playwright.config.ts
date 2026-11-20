import { defineConfig } from '@playwright/test'

/**
 * Browser tests (P18). The server is started by CI (or by you) before running:
 *   python e2e/server.py .e2e-data      with ADMIN_EMAIL / ADMIN_PASSWORD set
 * E2E_DB points at that data dir's app.db, for the tamper test (J4).
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: false, // one server, one database: journeys run in order
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
