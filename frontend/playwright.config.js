import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E 配置
 * - 默认启动 vite dev（webServer），无需手动起服务。
 * - 默认使用 Chromium，CI 可扩展 Firefox/WebKit。
 * - 拦截 /api/** mock 返回，避免依赖真实后端。
 * - trace/screenshot/video 仅在失败时保留，便于本地调试。
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://localhost:5180',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
  },
  expect: {
    timeout: 5_000,
  },
  timeout: 30_000,
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev -- --port 5180 --strictPort',
    url: 'http://localhost:5180',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})