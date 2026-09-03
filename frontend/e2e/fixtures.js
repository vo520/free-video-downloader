/**
 * Mock 后端 fixture：拦截 /api/** 返回预设数据，CI 与本地均无需后端。
 * - 默认拦截 GET /api/history（解析/下载/总结 3 种类型共 6 条）。
 * - 默认拦截 POST /api/parse（返回 bilibili 视频 mock 数据）。
 * - 默认拦截 DELETE /api/history/:id 与 POST /api/history/clear。
 * - 默认拦截 POST /api/auth/default-user（默认用户 lazy init）。
 *
 * 用法：
 *   test.beforeEach(async ({ page }) => {
 *     await installApiMocks(page)
 *   })
 *
 * 也可覆盖特定场景：
 *   await installApiMocks(page, { historyItems: [...] })
 */
export const MOCK_VIDEO = {
  id: 'BV1mock123',
  title: 'E2E Mock Video · Vue 3 响应式原理解析',
  platform: 'bilibili',
  uploader: 'E2E 测试频道',
  duration: 596,
  thumbnail: 'data:image/svg+xml;utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100">' +
    '<rect width="160" height="100" fill="#1e293b"/>' +
    '<text x="80" y="55" text-anchor="middle" fill="#94a3b8" font-size="14">Mock</text></svg>'
  ),
  formats: [
    { format_id: 'best', label: '1080p · 最佳画质', has_audio: true, resolution: '1920x1080', ext: 'mp4' },
    { format_id: '1080p', label: '1080p', has_audio: true, resolution: '1920x1080', ext: 'mp4' },
    { format_id: '720p', label: '720p', has_audio: true, resolution: '1280x720', ext: 'mp4' },
    { format_id: '480p', label: '480p', has_audio: true, resolution: '854x480', ext: 'mp4' },
    { format_id: 'audio', label: '仅音频 (m4a)', has_audio: true, resolution: '0x0', ext: 'm4a' },
  ],
}

export const MOCK_HISTORY = [
  {
    id: 1,
    type: 'parse',
    video_url: 'https://www.bilibili.com/video/BV1mock001',
    title: 'Vue 3 组合式 API 完全指南',
    platform: 'bilibili',
    thumbnail: '',
    snapshot: { id: 'BV1mock001', title: 'Vue 3 组合式 API 完全指南', formats: MOCK_VIDEO.formats },
    created_at: '2026-08-21 10:00:00',
    extra: null,
  },
  {
    id: 2,
    type: 'parse',
    video_url: 'https://www.youtube.com/watch?v=mock002',
    title: 'Tailwind v4 实战：从零搭建企业级 UI',
    platform: 'youtube',
    thumbnail: '',
    snapshot: { id: 'mock002', title: 'Tailwind v4 实战', formats: MOCK_VIDEO.formats },
    created_at: '2026-08-20 15:30:00',
    extra: null,
  },
  {
    id: 3,
    type: 'summary',
    video_url: 'https://www.bilibili.com/video/BV1mock003',
    title: 'TypeScript 5.x 新特性深度解读',
    platform: 'bilibili',
    thumbnail: '',
    snapshot: null,
    created_at: '2026-08-19 09:15:00',
    extra: JSON.stringify({
      summary: '## 核心要点\n\n- **装饰器元数据** 标准化\n- **const 类型参数**\n- **正则语法收紧**\n\n详细：[TypeScript 5.x 发布说明](https://devblogs.microsoft.com/typescript/)',
      mindmap: '- TypeScript 5.x\n  - 新特性\n    - 装饰器元数据\n    - const 类型参数\n    - 正则语法收紧',
    }),
  },
  {
    id: 4,
    type: 'download',
    video_url: 'https://www.youtube.com/watch?v=mock004',
    title: 'Playwright E2E 测试最佳实践',
    platform: 'youtube',
    thumbnail: '',
    snapshot: null,
    created_at: '2026-08-18 22:00:00',
    extra: JSON.stringify({ format_id: '1080p' }),
  },
  {
    id: 5,
    type: 'parse',
    video_url: 'https://v.douyin.com/mock005',
    title: '抖音视频批量下载方案',
    platform: 'douyin',
    thumbnail: '',
    snapshot: null,
    created_at: '2026-08-17 11:20:00',
    extra: null,
  },
  {
    id: 6,
    type: 'summary',
    video_url: 'https://www.bilibili.com/video/BV1mock006',
    title: 'Rust 入门到精通',
    platform: 'bilibili',
    thumbnail: '',
    snapshot: null,
    created_at: '2026-08-15 14:00:00',
    extra: JSON.stringify({ summary: '## Rust 三大核心\n\n1. 所有权系统\n2. 借用检查器\n3. 生命周期标注', mindmap: '' }),
  },
]

/**
 * 安装 /api mock 路由。
 * 路由顺序：精确路径优先，最后兜底。
 *
 * 注意：所有 glob 必须以 `http://HOST/api/` 开头（绝对路径），
 * 否则相对 glob 会误匹配 vite 的 `/src/api/payment.js` 模块请求，
 * 返回 application/json 导致 "MIME type" 报错，页面 JS 全失败。
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} [opts]
 * @param {Array} [opts.historyItems]  自定义历史列表
 * @param {boolean} [opts.parseError=false] 模拟解析失败
 */
export async function installApiMocks(page, opts = {}) {
  const historyItems = opts.historyItems ?? MOCK_HISTORY
  // 强制 host 部分绝对路径，避免误匹配 vite 的 /src/api/* 模块。
  // 注意：page.url() 在 goto 前是 'about:blank'，new URL('about:blank').host === ''，
  //       拼出 'http:///api/...' 无效 URL，Playwright 静默忽略所有 route。
  //       直接硬编码 baseURL（playwright.config.js: http://localhost:5180）。
  const HOST = 'localhost:5180'

  // ⚠️ Playwright 路由优先级：后注册者优先（不是 glob specificity）。
  //    兜底路由必须最先注册，精确路由后注册，否则精确路由会被兜底"吃掉"。
  // 0) 兜底：先注册，最后才匹配不到精确路由的所有 /api/* 请求
  await page.route(`http://${HOST}/api/**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {} }),
    })
  )

  // 1) 历史列表（GET /api/history）—— 在 /api/history/* 之前，因为 list 也匹配 /api/history/items
  await page.route(`http://${HOST}/api/history**`, (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const url = new URL(route.request().url())
    const typeFilter = url.searchParams.get('type')
    const items = typeFilter ? historyItems.filter((it) => it.type === typeFilter) : historyItems
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { items, total: items.length } }),
    })
  })

  // 2) 删除单条（DELETE /api/history/:id）—— glob * 不跨 /
  await page.route(`http://${HOST}/api/history/*`, (route) => {
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
    }
    return route.continue()
  })

  // 3) 历史清空（POST /api/history/clear）
  await page.route(`http://${HOST}/api/history/clear`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
  )

  // 4) 解析接口（POST /api/parse）
  await page.route(`http://${HOST}/api/parse`, (route) => {
    if (opts.parseError) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: '链接无效' }),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: MOCK_VIDEO }),
    })
  })

  // 5) 默认用户 lazy init（最后注册，最优先）
  await page.route(`http://${HOST}/api/auth/default-user`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
  )

  // 6) 鉴权：mock 返回有效 token + user，让 ensureDefaultUser 流程写 localStorage，
  //     这样 isLoggedIn()=true、currentUser 有值，HistoryDrawer 才会挂载（v-if="currentUser"）。
  const MOCK_AUTH_PAYLOAD = {
    success: true,
    data: {
      token: 'mock-token-e2e',
      user: {
        id: 1,
        email: 'demo@local.com',
        nickname: 'E2E 测试用户',
        avatar: '',
        is_vip: true,
        vip_expire_at: '2099-12-31',
      },
    },
  }
  // /api/auth/me：useAuth.restoreUser 调用，确保刷新页面时 currentUser 还能恢复
  await page.route(`http://${HOST}/api/auth/me`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AUTH_PAYLOAD) })
  )
  await page.route(`http://${HOST}/api/auth/register`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AUTH_PAYLOAD) })
  )
  await page.route(`http://${HOST}/api/auth/login`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AUTH_PAYLOAD) })
  )
}