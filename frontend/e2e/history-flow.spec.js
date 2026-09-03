import { test, expect } from '@playwright/test'
import { installApiMocks, MOCK_HISTORY } from './fixtures.js'

const MOCK_USER_LS = {
  token: 'mock-token-e2e',
  user: {
    id: 1,
    email: 'demo@local.com',
    nickname: 'E2E 测试用户',
    avatar: '',
    is_vip: true,
    vip_expire_at: '2099-12-31',
  },
}

test.describe('历史抽屉完整流程', () => {
  test.beforeEach(async ({ page }) => {
    // 提前写 localStorage（必须在 page 创建后、goto 前注入）：
    //   useAuth.restoreUser 在 App.vue onMounted 时执行，若此时 token 为空会直接 return false，
    //   后续 ensureDefaultUserLazy 写 localStorage 也无法回填 currentUser。
    //   通过 addInitScript 让 page 初始化时已带 token/user → restoreUser 走通 → fetchMe 写 currentUser。
    await page.addInitScript((data) => {
      localStorage.setItem('saveany_token', data.token)
      localStorage.setItem('saveany_user', JSON.stringify(data.user))
    }, MOCK_USER_LS)

    await installApiMocks(page)
    await page.goto('/')
  })

  // 限定到 HistoryDrawer 范围（避免 AppHeader「最近解析」dropdown 同时出现同名条目导致 strict mode 违反）
  const drawer = (page) => page.locator('[aria-label="历史记录抽屉"]')

  test('打开历史抽屉：渲染默认 user → 拉历史 → 渲染列表', async ({ page }) => {
    await expect(page.locator('main')).toBeVisible()
    await openHistoryDrawer(page)

    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible({ timeout: 10_000 })
    await expect(drawer(page).getByText('Tailwind v4 实战').first()).toBeVisible()

    const allTab = page.getByRole('tab', { name: /全部/ })
    await expect(allTab).toHaveAttribute('aria-selected', 'true')
  })

  test('tab 切换：全部 → 解析 → 总结', async ({ page }) => {
    await openHistoryDrawer(page)
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible({ timeout: 10_000 })

    await page.getByRole('tab', { name: /解析/ }).click()
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible()
    await expect(drawer(page).getByText('TypeScript 5.x 新特性深度解读')).toHaveCount(0)

    await page.getByRole('tab', { name: /总结/ }).click()
    await expect(drawer(page).getByText('TypeScript 5.x 新特性深度解读').first()).toBeVisible()
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南')).toHaveCount(0)
  })

  test('搜索：标题/平台过滤', async ({ page }) => {
    await openHistoryDrawer(page)
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible({ timeout: 10_000 })

    const search = page.getByRole('textbox', { name: /搜索历史记录/ })
    await search.fill('Tailwind')

    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南')).toHaveCount(0)
    await expect(drawer(page).getByText('Tailwind v4 实战').first()).toBeVisible()

    await search.fill('')
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible()
  })

  test('删除单条：confirm 确认 → 列表减 1', async ({ page }) => {
    await openHistoryDrawer(page)
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible({ timeout: 10_000 })

    page.once('dialog', (dialog) => dialog.accept())

    // 通过 aria-label 精确定位「Vue 3」这条的删除按钮（避免正则 name 匹配到多条历史）
    const deleteBtn = drawer(page).getByRole('button', { name: '删除历史记录：Vue 3 组合式 API 完全指南' })
    await deleteBtn.click()

    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南')).toHaveCount(0, { timeout: 5_000 })
  })

  test('清空全部：confirm 确认 → 列表清空', async ({ page }) => {
    await openHistoryDrawer(page)
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible({ timeout: 10_000 })

    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: /清空全部历史记录/ }).click()

    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南')).toHaveCount(0, { timeout: 5_000 })
    await expect(drawer(page).getByText('TypeScript 5.x 新特性深度解读')).toHaveCount(0)
  })

  test('Esc 关闭抽屉', async ({ page }) => {
    await openHistoryDrawer(page)
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible({ timeout: 10_000 })

    await page.keyboard.press('Escape')

    // 抽屉关闭：drawer 元素被 unmount，整个范围内的文本自然消失
    await expect(drawer(page)).toHaveCount(0, { timeout: 3_000 })
  })

  test('关开抽屉不重拉（已有 items 时）', async ({ page }) => {
    await openHistoryDrawer(page)
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible({ timeout: 10_000 })

    let historyCalls = 0
    page.on('request', (req) => {
      if (req.url().includes('/api/history') && req.method() === 'GET') historyCalls += 1
    })

    await page.keyboard.press('Escape')
    await openHistoryDrawer(page)

    // 1 次拉取（首次打开），关开不重拉
    expect(historyCalls).toBe(0)
    await expect(drawer(page).getByText('Vue 3 组合式 API 完全指南').first()).toBeVisible()
  })
})

/**
 * 触发历史按钮。HistoryDrawer 是浮动入口（title="历史记录"），
 * AppHeader 也有"最近解析" dropdown 但属于不同组件（localStorage 历史）。
 * 当前 spec 只测 HistoryDrawer，所以优先选择 title="历史记录"。
 */
async function openHistoryDrawer(page) {
  const candidates = [
    page.locator('button[title="历史记录"]'),
    page.locator('button[aria-label*="历史记录抽屉"]'),
  ]
  for (const c of candidates) {
    if (await c.first().isVisible().catch(() => false)) {
      await c.first().click()
      return
    }
  }
  throw new Error('未找到历史抽屉入口按钮')
}
