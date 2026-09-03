import { test, expect } from '@playwright/test'
import { installApiMocks, MOCK_VIDEO } from './fixtures.js'

const HOST = 'localhost:5180'
const HISTORY_KEY = 'fvd_parse_history'

// 关闭默认用户自动注册/登录：让 ensureDefaultUser 返回 false，不写 token，
// 从而 isLoggedIn() 始终为 false，强制走「未登录 → localStorage 本地历史」路径。
// 必须在 installApiMocks 之后注册（后注册者优先级更高），覆盖其 success:true 的 register/login。
async function disableDefaultUser(page) {
  const fail = (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: false }) })
  await page.route(`http://${HOST}/api/auth/register`, fail)
  await page.route(`http://${HOST}/api/auth/login`, fail)
}

test.describe('未登录本地历史：可点击回看 + URL 去重', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
    await disableDefaultUser(page)
    await page.goto('/')
    await expect(page.locator('main')).toBeVisible()
  })

  test('解析后写入本地历史，点击回看可显示视频信息（修复后应通过）', async ({ page }) => {
    const input = page.locator('#video-url-input')
    await input.fill('https://www.bilibili.com/video/BVrepro001')
    await page.getByRole('button', { name: /解析视频/ }).first().click()

    // 解析成功 → 视频信息面板出现
    await expect(page.getByText(MOCK_VIDEO.title)).toBeVisible({ timeout: 15_000 })

    // 刷新页面：videoData 重置为空 → 内联「最近解析」列表可见
    await page.reload()
    await expect(page.locator('main')).toBeVisible()
    const recent = page.locator('section', { hasText: '最近解析' })
    await expect(recent).toBeVisible()
    await expect(recent.getByText(MOCK_VIDEO.title).first()).toBeVisible()

    // 点击历史条目 → 应回看显示视频信息（当前代码因缺 snapshot 无法显示 → 此断言现在失败）
    await recent.getByText(MOCK_VIDEO.title).first().click()
    await expect(page.getByText(MOCK_VIDEO.title)).toBeVisible({ timeout: 10_000 })
    // 视频信息面板含「选择清晰度和格式」标题，确认已进入视频信息视图
    await expect(page.getByText('选择清晰度和格式')).toBeVisible()
  })

  test('同视频不同 URL 形态只保留 1 条本地历史（去重修复后应通过）', async ({ page }) => {
    const input = page.locator('#video-url-input')
    const btn = page.getByRole('button', { name: /解析视频/ }).first()

    // 同一条视频的两种 URL 形态（http + www / https 无 www）
    await input.fill('https://www.youtube.com/watch?v=reproDup')
    await btn.click()
    await expect(page.getByText(MOCK_VIDEO.title)).toBeVisible({ timeout: 15_000 })

    await input.fill('http://youtube.com/watch?v=reproDup')
    await btn.click()
    await expect(page.getByText(MOCK_VIDEO.title)).toBeVisible({ timeout: 15_000 })

    // 读取本地历史，断言只保留了 1 条（当前代码会因未归一化而存成 2 条 → 此断言现在失败）
    const raw = await page.evaluate((k) => localStorage.getItem(k), HISTORY_KEY)
    const list = raw ? JSON.parse(raw) : []
    expect(list.length, `本地历史应为去重后 1 条，实际: ${JSON.stringify(list)}`).toBe(1)
    // 归一化后两条 url 视作同一资源；保留最新一次用户输入的原始形态（http://youtube.com...），
    // 以便回看时 currentUrl 与用户分享/复制的链接一致，不强制覆盖为 https。
    expect(['http://youtube.com/watch?v=reproDup', 'https://youtube.com/watch?v=reproDup', 'https://www.youtube.com/watch?v=reproDup'])
      .toContain(list[0].url)
  })

  test('遗留的无 snapshot 本地历史点击时优雅降级（不应崩溃）', async ({ page }) => {
    // 模拟修复前已存储的本地历史（无 snapshot）
    const legacy = [
      {
        url: 'https://www.bilibili.com/video/BVlegacy001',
        title: 'Legacy 无快照视频',
        platform: 'bilibili',
        ts: Date.now(),
      },
    ]
    await page.evaluate(([k, v]) => localStorage.setItem(k, v), [HISTORY_KEY, JSON.stringify(legacy)])
    await page.reload()
    await expect(page.locator('main')).toBeVisible()

    const recent = page.locator('section', { hasText: '最近解析' })
    await expect(recent.getByText('Legacy 无快照视频').first()).toBeVisible()
    await recent.getByText('Legacy 无快照视频').first().click()

    // 降级提示出现且不崩溃；视频信息面板不出现
    await expect(page.getByText(/无完整数据|重新解析/).first()).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('选择清晰度和格式')).toHaveCount(0)
  })
})
