import { defineConfig } from '@playwright/test';
import path from 'path';
const root = path.resolve(__dirname, '../..');
const db = path.join(root, 'output/e2e/studio-test.sqlite');
const media = path.join(root, 'output/e2e/media');
export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:3001', browserName: 'chromium', channel: 'chrome', viewport: { width: 1440, height: 900 } },
  globalSetup: './tests/setup.ts',
  webServer: [
    { command: `${root}/.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8001 --no-access-log`, cwd: root,
      env: { FILM_STUDIO_DB: db, FILM_STUDIO_MEDIA: media, FILM_STUDIO_TEST_MODE: '1',
        DARL_API_KEY: '', LLM_API_KEY: '', IMAGE_API_KEY: '', H3_SERVER_ON: '0' },
      url: 'http://127.0.0.1:8001/api/health', reuseExistingServer: false, timeout: 30000 },
    { command: 'npm run dev -- -p 3001', cwd: __dirname,
      env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8001', NEXT_TEST_DIST_DIR: '.next-e2e' },
      url: 'http://127.0.0.1:3001', reuseExistingServer: false, timeout: 30000 },
  ],
});
