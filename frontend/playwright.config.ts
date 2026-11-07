import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

const python = resolve(
  '..',
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:8001',
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${python}" -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8001`,
    url: 'http://127.0.0.1:8001/api/health',
    reuseExistingServer: false,
    env: {
      AUSPOST_API_KEY: '',
      AUSPOST_API_SECRET: '',
      AUSPOST_STARTRACK_ACCOUNT: '',
      AUSPOST_POST_ACCOUNT: '',
      SHIPPING_ESTIMATE_ENABLED: 'true',
      TNT_TRACKING_ENABLED: 'false',
      DATA_DIR: '',
    },
    timeout: 20_000,
  },
});
