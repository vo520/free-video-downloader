import { test, expect } from '@playwright/test'
import { installApiMocks } from './fixtures.js'

test.describe('主链路：粘贴链接 → 解析 → 查看结果', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
    await page.goto('/')
    // 单元素 locator，避免 strict mode violation（main + 多个 section 同时存在）
    await expect(page.locator('main')).toBeVisible()
  })

  test('首页基础渲染', async ({ page }) => {
    // 输入框（稳定 id）
    const input = page.locator('#video-url-input')
    await expect(input).toBeVisible()
    // 解析按钮
    const parseBtn = page.getByRole('button', { name: /解析视频/ })
    await expect(parseBtn.first()).toBeVisible()
  })

  test('粘贴链接 → 解析 → 显示视频信息', async ({ page }) => {
    const input = page.locator('#video-url-input')
    await input.fill('https://www.bilibili.com/video/BV1mock123')

    const parseBtn = page.getByRole('button', { name: /解析视频/ }).first()
    await parseBtn.click()

    // 等待视频标题出现（mock 视频标题）
    await expect(page.getByText(/E2E Mock Video|Vue 3 响应式/)).toBeVisible({ timeout: 15_000 })
    // 至少一个清晰度选项
    await expect(page.getByText(/1080p/).first()).toBeVisible()
  })

  test('解析失败时显示错误提示', async ({ page }) => {
    await page.route('**/api/parse', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: '视频不存在或链接无效' }),
      })
    )

    const input = page.locator('#video-url-input')
    await input.fill('https://invalid.example.com/video/xxx')
    await page.getByRole('button', { name: /解析视频/ }).first().click()

    // toast 错误提示（页面有"失败"/"无效"等字样）
    await expect(page.getByText(/失败|无效/).first()).toBeVisible({ timeout: 10_000 })
  })

  test('空链接时按钮禁用', async ({ page }) => {
    const input = page.locator('#video-url-input')
    await input.fill('   ')
    const parseBtn = page.getByRole('button', { name: /解析视频/ }).first()
    await expect(parseBtn).toBeDisabled()
  })
})