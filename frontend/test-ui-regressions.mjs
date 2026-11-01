/**
 * 前端 UI 回归验证（真实 Chrome + 真实 Vue，无需测试框架，node 直接运行）。
 *
 * 覆盖本轮修复的四类真实缺陷：
 *  1. EmptyState 缺少默认插槽出口 —— 父组件写的 <template #default> 被静默丢弃，
 *     SubtitlePanel / MindmapPanel 的提示文案永远不显示。
 *  2. HeroSection 多链接粘贴快捷入口永不显示 —— @paste 里同步赋值 + nextTick（微任务）
 *     会被随后触发的 @input 清零（浏览器实际顺序：paste → 微任务 → beforeinput → input）。
 *  3. VideoCacheAdmin 下载按钮每次都误报"新窗口被拦截"并覆盖剪贴板 ——
 *     window.open(url, '_blank', 'noopener') 按规范恒返回 null（与是否被拦截无关）。
 *  4. useToast 队列内重复消息合并后仍显示 ×1 —— 合并计数写在队列项上，
 *     展示时却去读从未写入真实计数的 recentCounts Map。
 *
 * 运行：node test-ui-regressions.mjs
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { chromium } from '@playwright/test'

const ROOT = path.dirname(fileURLToPath(import.meta.url))
const SRC = path.join(ROOT, 'src')
const HARNESS_DIR = path.join(ROOT, '.regression-harness')

// ---------- 临时挂载页：直接挂载真实组件，验证真实渲染/交互结果 ----------
const HARNESS_HTML = `<!DOCTYPE html>
<html lang="zh-CN">
  <head><meta charset="UTF-8" /><title>regression harness</title></head>
  <body><div id="app"></div><script type="module" src="./main.js"></script></body>
</html>
`

const HARNESS_JS = `import { createApp, h } from 'vue'
import AppHeader from '../src/components/AppHeader.vue'
import HeroSection from '../src/components/HeroSection.vue'
import EmptyState from '../src/components/ui/EmptyState.vue'
import HistoryDrawer from '../src/components/HistoryDrawer.vue'
import { useToast } from '../src/composables/useToast.js'
import { useDownloadManager } from '../src/composables/useDownloadManager.js'
import { normalizeHistoryUrl } from '../src/composables/useHistory.js'

const Root = {
  setup() {
    const { appToast, showToast } = useToast()
    window.__toast = { appToast, showToast }
    window.__dm = useDownloadManager()
    window.__normalizeHistoryUrl = normalizeHistoryUrl
    return {}
  },
  render() {
    return h('div', [
      // 顶栏：验证移动端「最近解析」能真正展开历史列表（历史数据直接从 props 注入）
      h(AppHeader, {
        history: [
          { id: 7, title: '移动端历史条目', url: 'https://example.com/v/7', platform: 'youtube', ts: Date.now() },
        ],
      }),
      h(HeroSection, {
        onParse: (u) => { window.__lastParse = u },
        onOpenBatch: (t) => { window.__lastBatch = t },
      }),
      h(HistoryDrawer),
      h('div', { id: 'es-host' }, [
        h(EmptyState, { variant: 'info', size: 'sm' }, { default: () => '默认插槽文案' }),
        h(EmptyState, { variant: 'info', size: 'sm' }, { action: () => '动作插槽文案' }),
      ]),
    ])
  },
}

createApp(Root).mount('#app')
`

function writeHarness() {
  fs.mkdirSync(HARNESS_DIR, { recursive: true })
  fs.writeFileSync(path.join(HARNESS_DIR, 'index.html'), HARNESS_HTML)
  fs.writeFileSync(path.join(HARNESS_DIR, 'main.js'), HARNESS_JS)
}

function removeHarness() {
  fs.rmSync(HARNESS_DIR, { recursive: true, force: true })
}

// ---------- 1. EmptyState 默认插槽必须真的渲染 ----------
async function testEmptyStateDefaultSlot(page) {
  const hostText = await page.locator('#es-host').innerText()
  assert.ok(
    hostText.includes('默认插槽文案'),
    `EmptyState 默认插槽内容未渲染（实际文本：${JSON.stringify(hostText)}）`
  )
  assert.ok(
    hostText.includes('动作插槽文案'),
    'EmptyState #action 插槽内容未渲染'
  )
}

// ---------- 2. 多链接输入 → 批量解析快捷入口必须出现 ----------
async function testPasteHint(page) {
  const input = page.locator('#video-url-input')
  await input.click()

  // 模拟浏览器粘贴：先派发 paste 事件（组件不再监听它），再插入文本触发 input
  await page.evaluate(() => {
    const el = document.getElementById('video-url-input')
    const dt = new DataTransfer()
    dt.setData('text/plain', 'https://a.example.com/1 https://b.example.com/2')
    el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }))
  })
  await page.keyboard.insertText('https://a.example.com/1 https://b.example.com/2')

  // 等过 fade transition 的时长再断言：旧实现里提示只会闪现一帧就被 @input 清零，
  // 立刻断言会误判为"出现过"，必须等它稳定下来才算真的显示出来。
  await page.waitForTimeout(500)
  const hint = page.getByText(/检测到\s*2\s*个链接/)
  assert.equal(await hint.count(), 1, '多链接输入后未出现"检测到 2 个链接"的批量入口')

  // 退回到单条链接 → 入口必须消失（同样要等 fade transition 结束，否则元素仍在 DOM 里）
  await input.fill('https://a.example.com/1')
  await page.waitForTimeout(500)
  assert.equal(
    await page.getByText(/检测到\s*\d+\s*个链接/).count(),
    0,
    '单条链接时批量入口未隐藏'
  )

  // 多链接 → 点示例按钮（程序化赋值，不触发 input）：过期的批量入口必须一起消失，
  // 否则输入框里已是单条链接，点提示却会把旧的粘贴文本送进批量面板。
  await input.fill('https://a.example.com/1 https://b.example.com/2')
  await page.waitForTimeout(500)
  await page.getByRole('button', { name: 'YouTube' }).click()
  await page.waitForTimeout(500)
  assert.equal(
    await page.getByText(/检测到\s*\d+\s*个链接/).count(),
    0,
    '点击示例按钮后仍残留过期的批量入口'
  )
}

// ---------- 2.1 主按钮提交多链接必须进入批量解析 ----------
// 输入框若保留 type="url"，浏览器原生校验会在 submit 之前拦下「多个链接 / 分享文案」，
// onSubmit 里的 splitUrls 分支永远走不到，用户点「解析视频」只会看到校验气泡。
async function testSubmitMultipleUrls(page) {
  await page.evaluate(() => { window.__lastParse = null; window.__lastBatch = null })
  const input = page.locator('#video-url-input')
  await input.fill('https://a.example.com/1 https://b.example.com/2')
  await page.locator('form button[type="submit"]').first().click()
  await page.waitForTimeout(200)

  const submitted = await page.evaluate(() => ({ batch: window.__lastBatch, parse: window.__lastParse }))
  assert.ok(
    submitted.batch && submitted.batch.includes('https://a.example.com/1'),
    '多链接点「解析视频」未进入批量解析（提交被原生校验拦下）'
  )
  assert.equal(submitted.parse, null, '多链接不应被当成单条链接直接解析')

  // 单条链接仍应正常触发单条解析
  await page.evaluate(() => { window.__lastParse = null; window.__lastBatch = null })
  await input.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  await page.locator('form button[type="submit"]').first().click()
  await page.waitForTimeout(200)
  const single = await page.evaluate(() => window.__lastParse)
  assert.ok(
    typeof single === 'string' && single.includes('dQw4w9WgXcQ'),
    '单条链接未触发单条解析'
  )
}

// ---------- 2.2 移动端「最近解析」必须展开列表而不是关掉整个面板 ----------
async function testMobileHeaderHistory(page) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(200)

  await page.locator('button[aria-label="打开菜单"]').click()
  const menu = page.locator('#mobile-menu')
  await menu.waitFor({ state: 'visible' })

  await menu.getByRole('button', { name: /最近解析/ }).click()
  await page.waitForTimeout(150)

  assert.ok(
    await menu.isVisible(),
    '移动端点击「最近解析」把整个菜单面板关掉了，历史列表永远看不到'
  )
  assert.ok(
    await page.getByText('移动端历史条目').isVisible(),
    '移动端「最近解析」未展开历史列表'
  )

  // 恢复桌面视口，避免影响后续依赖桌面布局的用例
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.waitForTimeout(150)
}

// ---------- 3. window.open 带 noopener 恒返回 null（误报根因） ----------
async function testWindowOpenSemantics(page) {
  const result = await page.evaluate(() => {
    const withNoopener = window.open('about:blank', '_blank', 'noopener,noreferrer')
    const plain = window.open('about:blank', '_blank')
    const openerBroken = plain ? (plain.opener = null) : 'null-window'
    plain?.close()
    return { withNoopenerIsNull: withNoopener === null, plainIsWindow: plain !== null, openerBroken }
  })
  assert.equal(
    result.withNoopenerIsNull,
    true,
    '前提不成立：window.open 带 noopener 特性时本应恒返回 null'
  )
  assert.equal(result.plainIsWindow, true, '前提不成立：window.open 不带特性时应返回窗口对象')
}

// ---------- 4. toast 队列内重复消息必须合并出 ×N ----------
async function testToastMergeCount(page) {
  await page.evaluate(() => {
    const { showToast } = window.__toast
    showToast('队列消息 A')
    showToast('队列消息 B')
    showToast('队列消息 B') // B 还在队列里，应合并为 ×2
  })
  // 等当前 toast 超时后，队列里的 B 才被展示出来
  await page.waitForFunction(
    () => window.__toast.appToast.value?.message === '队列消息 B',
    null,
    { timeout: 6000 }
  )
  const count = await page.evaluate(() => window.__toast.appToast.value?.count)
  assert.equal(count, 2, `队列内重复消息的合并计数丢失（count=${count}，期望 2）`)
}

// ---------- 5. 下载重试必须有状态守卫（防止同一任务并发启动两次） ----------
async function testRetryStateGuard(page) {
  const result = await page.evaluate(() => {
    const { state, retry } = window.__dm
    // 直接构造任务验证 retry 的状态守卫：只有 error / canceled 才允许重试
    state.tasks.length = 0
    const make = (id, status) => ({
      id,
      url: `https://noop.test/${id}`,
      formatId: '',
      title: id,
      status,
      progress: 50,
      received: 1,
      total: 2,
      error: '',
    })
    const downloading = make('t-downloading', 'downloading')
    const done = make('t-done', 'done')
    state.tasks.push(downloading, done)
    retry('t-downloading')
    retry('t-done')
    return {
      downloading: downloading.status,
      done: done.status,
      count: state.tasks.length,
    }
  })
  assert.equal(
    result.downloading,
    'downloading',
    '重试把进行中的任务改回 queued，会让同一任务并发启动两个下载'
  )
  assert.equal(result.done, 'done', '已完成任务不应被重试重新下载')
  assert.equal(result.count, 2, '重试不得新增任务')
}

// ---------- 6. 前端 URL 归一化必须与后端一致（裸数字抖音 ID 补全） ----------
async function testNormalizeHistoryUrl(page) {
  const result = await page.evaluate(() => {
    const fn = window.__normalizeHistoryUrl
    return {
      bare: fn('7001234'),
      padded: fn('  7001234  '),
      full: fn('https://www.douyin.com/video/7001234'),
      messy: fn('http://www.Douyin.com/video/7001234#comment'),
      empty: fn(''),
    }
  })
  const expected = 'https://douyin.com/video/7001234'
  assert.equal(result.bare, expected, '裸数字抖音 ID 未补全为完整链接')
  assert.equal(result.padded, expected, '带首尾空格的裸数字 ID 未正确归一化')
  assert.equal(result.full, expected, '完整抖音链接归一化结果不一致')
  assert.equal(result.messy, expected, 'http/www/大小写/fragment 未归一化到同一形态')
  assert.equal(result.empty, '', '空值应返回空字符串')
}

// ---------- 7. 历史抽屉：搜索态删除必须同步、重新打开必须看到新记录 ----------
// 用 route 拦截 /api/history，直接驱动真实 HistoryDrawer 的状态流转：
//  - 搜索态下列表由服务端搜索结果显示，删除后旧实现只过滤 items → 已删条目仍留在搜索列表里；
//  - 旧实现只在首次打开（items 为空）时拉取，抽屉关闭期间新增的历史永远看不到。
const historyFixture = []

function makeHistoryItem(id, title) {
  return {
    id,
    type: 'parse',
    title,
    video_url: `https://example.com/v/${id}`,
    platform: 'youtube',
    created_at: '2026-01-01T00:00:00+00:00',
    thumbnail: '',
    snapshot: { title },
    extra: null,
  }
}

// 总结记录：onlyViaSearch 用于模拟「不在首屏已加载页里、只有搜索才命中」的旧历史
function makeSummaryItem(id, title) {
  return {
    id,
    type: 'summary',
    title,
    video_url: `https://example.com/v/${id}`,
    platform: 'youtube',
    created_at: '2026-01-01T00:00:00+00:00',
    thumbnail: '',
    snapshot: null,
    extra: JSON.stringify({ summary: '## 历史总结正文\n\n- 要点一' }),
    onlyViaSearch: true,
  }
}

async function installHistoryRoutes(page, fixture) {
  // 必须按路径前缀精确匹配：用 /\/api\/history/ 正则会连 Vite 提供的源码模块
  // /src/api/history.js 一起拦截，把 JS 当 JSON 返回 → 模块图加载失败、整页空白。
  await page.route((url) => url.pathname.startsWith('/api/history'), async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    if (req.method() === 'DELETE') {
      const id = Number(url.pathname.split('/').pop())
      const idx = fixture.findIndex((it) => it.id === id)
      if (idx >= 0) fixture.splice(idx, 1)
      return route.fulfill({ json: { success: true } })
    }
    if (req.method() === 'POST') {
      fixture.length = 0
      return route.fulfill({ json: { success: true, deleted: 0 } })
    }
    const kw = (url.searchParams.get('search') || '').toLowerCase()
    // 非搜索态列表模拟分页：onlyViaSearch 的记录不在已加载页里，只有搜索才能命中
    const list = kw
      ? fixture.filter((it) => it.title.toLowerCase().includes(kw))
      : fixture.filter((it) => !it.onlyViaSearch)
    return route.fulfill({ json: { success: true, data: list, total: list.length } })
  })
}

async function testHistoryDrawerSync(page, fixture) {
  await page.locator('button[title="历史记录"]').click()
  await page.waitForFunction(() => document.body.innerText.includes('可搜索条目 A'))

  // 输入关键词 → 300ms 防抖后走服务端搜索，列表改由 searchResults 驱动
  await page.getByLabel('搜索历史记录').fill('可搜索条目 A')
  await page.waitForTimeout(600)

  await page.locator('[aria-label="删除历史记录：可搜索条目 A"]').click()
  await page.waitForFunction(
    () => !document.body.innerText.includes('可搜索条目 A'),
    null,
    { timeout: 3000 }
  )

  // 关闭抽屉后服务端新增一条，重新打开必须能看到（静默刷新首页）
  await page.locator('button[aria-label="收起历史记录抽屉"]').click()
  fixture.push(makeHistoryItem(99, '关闭期间新增条目 C'))
  await page.locator('button[title="历史记录"]').click()
  await page.waitForFunction(
    () => document.body.innerText.includes('关闭期间新增条目 C'),
    null,
    { timeout: 3000 }
  )
}

// ---------- 7.1 历史抽屉：搜索命中的旧记录也必须能展开回看总结 ----------
// 旧实现只按 items（首屏已加载页）预解析 extra，搜索命中但不在该页里的记录
// getExtra 恒为空 → 展开只出现一个空白的 border-top 区块，总结永远看不到。
async function testHistoryDrawerSearchExtras(page) {
  await page.getByLabel('搜索历史记录').fill('旧总结条目 D')
  await page.waitForTimeout(600)
  await page.getByText('旧总结条目 D', { exact: true }).click()
  await page.waitForFunction(
    () => document.body.innerText.includes('历史总结正文'),
    null,
    { timeout: 3000 }
  )
  assert.ok(
    (await page.getByText('要点一').count()) > 0,
    '搜索结果中的总结记录展开后未渲染 Markdown 正文（extra 未被解析）'
  )
  // 清空关键词，避免影响后续用例
  await page.getByLabel('搜索历史记录').fill('')
  await page.waitForTimeout(400)
}

// ---------- 8. 源码契约：修复点不能被改回去 ----------
function testSourceContracts() {
  const read = (p) => fs.readFileSync(path.join(SRC, p), 'utf8')
  // 注释里会提到 window.open(..., 'noopener') 作为对比说明，先剥掉注释再校验代码
  const stripComments = (s) =>
    s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '').replace(/^\s*\/\/.*$/gm, '')

  const cacheAdmin = read('components/VideoCacheAdmin.vue')
  const cacheAdminCode = stripComments(cacheAdmin)
  assert.ok(
    !/window\.open\([^)]*noopener/.test(cacheAdminCode),
    'VideoCacheAdmin 又使用了带 noopener 的 window.open（按规范恒返回 null → 误报弹窗被拦截）'
  )
  assert.ok(
    /window\.open\(video\.download_url,\s*'_blank'\)/.test(cacheAdminCode),
    'VideoCacheAdmin 的下载窗口未使用不带特性的 window.open'
  )
  assert.ok(
    /win\.opener\s*=\s*null/.test(cacheAdminCode),
    'VideoCacheAdmin 未手动断开 opener 引用（等价 noopener 的防护丢失）'
  )

  const mindmap = read('components/panels/MindmapPanel.vue')
  const mindmapCode = stripComments(mindmap)
  const destroyIdx = mindmapCode.indexOf('destroyMarkmap()')
  const createIdx = mindmapCode.indexOf('Markmap.create(')
  assert.ok(destroyIdx !== -1, 'MindmapPanel 缺少 destroyMarkmap（markmap 实例泄漏）')
  assert.ok(
    destroyIdx < createIdx,
    'MindmapPanel 未在重建前销毁旧 markmap 实例（旧实例的监听器会一直残留）'
  )
  // 全屏 API 返回 Promise，同步 try/catch 抓不到 reject：失败会冒泡到 main.js 的
  // unhandledrejection，弹通用「请求异常」错误，而预期的友好文案永远不会出现。
  // 注意：MindmapPanel 的 script 内容有缩进，不能用 `\n}` 定位函数结尾，按相邻函数切片。
  const fsStart = mindmapCode.indexOf('function toggleFullscreen()')
  const fsEnd = mindmapCode.indexOf('function onFullscreenChange(')
  assert.ok(
    fsStart !== -1 && fsEnd > fsStart,
    'MindmapPanel 缺少 toggleFullscreen'
  )
  const fsBody = mindmapCode.slice(fsStart, fsEnd)
  assert.ok(
    /catchFullscreenPromise\([^)]*requestFullscreen\(\)/.test(fsBody),
    'MindmapPanel 未接住 requestFullscreen() 的 Promise reject（全屏失败会弹通用「请求异常」）'
  )
  assert.ok(
    /catchFullscreenPromise\([^)]*exitFullscreen\(\)/.test(fsBody),
    'MindmapPanel 未接住 exitFullscreen() 的 Promise reject（退出失败会弹通用「请求异常」）'
  )

  const hero = read('components/HeroSection.vue')
  const heroCode = stripComments(hero)
  assert.ok(
    /@input="onInput"/.test(heroCode),
    'HeroSection 未在 input 事件里判定多链接（粘贴快捷入口会再次失效）'
  )
  assert.ok(
    !/nextTick/.test(heroCode),
    'HeroSection 仍依赖 nextTick 设置粘贴提示（微任务早于 input，会被清零）'
  )
  // 全局 Cmd/Ctrl+K 不能从其它输入控件抢焦点：历史搜索框 / 登录弹窗 / 批量输入框 / AI 问答框
  // 都在遮罩之后，抢走后用户输入会落到看不见的 hero 输入框里。
  const heroKeyDown = heroCode.match(/function onKeyDown\(e\)\s*\{([\s\S]*?)\n\}/)
  assert.ok(heroKeyDown, 'HeroSection 缺少 onKeyDown')
  assert.ok(
    /isEditableTarget\(e\.target\)/.test(heroKeyDown[1]),
    'HeroSection 的 Cmd/Ctrl+K 未放过其它输入控件（会抢走焦点）'
  )

  // VideoSummary 卸载时必须主动复位 loading 并阻止「await 之后继续干活」：
  //  - 不复位 → 宿主 App 的 summarizing 永久为 true，「AI 总结」按钮永久 loading 不可点；
  //  - 不拦 loadQuota 的后续流程 → 配额请求回来时组件已销毁，仍会发起 SSE 白扣免费额度。
  const summaryCode = stripComments(read('components/VideoSummary.vue'))
  const summaryUnmount = summaryCode.match(/onBeforeUnmount\(\(\)\s*=>\s*\{([\s\S]*?)\n\s*\}\)/)
  assert.ok(summaryUnmount, 'VideoSummary 缺少 onBeforeUnmount')
  assert.ok(
    /unmounted\s*=\s*true/.test(summaryUnmount[1]),
    'VideoSummary 卸载时未设置 unmounted 标记（异步回调仍会作用到已销毁实例）'
  )
  assert.ok(
    /emit\('loading-change',\s*false\)/.test(summaryUnmount[1]),
    'VideoSummary 卸载时未直接 emit loading-change(false)（watch 已被销毁，宿主 summarizing 会卡死）'
  )
  assert.ok(
    (summaryCode.match(/if\s*\(unmounted\)\s*return/g) || []).length >= 2,
    'VideoSummary 的 loadQuota / startSummarize 缺少卸载守卫（销毁后仍会发起总结请求）'
  )

  // VideoResult 的画中画切换：当前元素已在 PiP 时必须走退出分支，
  // 否则二次点击会重复 requestPictureInPicture 被拒绝 → 误报「不支持画中画」且退不出去。
  const resultCode = stripComments(read('components/VideoResult.vue'))
  const togglePip = resultCode.match(/function togglePip\(\)\s*\{([\s\S]*?)\n\}/)
  assert.ok(togglePip, 'VideoResult 缺少 togglePip')
  const pipBody = togglePip[1]
  const sameElIdx = pipBody.indexOf('document.pictureInPictureElement === v')
  const requestIdx = pipBody.indexOf('requestPictureInPicture')
  assert.ok(
    sameElIdx !== -1 && sameElIdx < requestIdx,
    'VideoResult 的 togglePip 未在请求画中画之前判断「当前元素已在画中画中」'
  )
  assert.ok(
    /exitPictureInPicture/.test(pipBody.slice(sameElIdx, requestIdx === -1 ? undefined : requestIdx)),
    'VideoResult 的 togglePip 在已处于画中画时未调用 exitPictureInPicture（无法退出）'
  )

  // 切换清晰度后必须丢弃上一次换来的预览直链，否则新格式下点预览播的仍是旧画质。
  assert.ok(
    /watch\(selectedFormat,\s*\(\)\s*=>\s*\{[\s\S]*?fetchedUrl\.value\s*=\s*''/.test(resultCode),
    'VideoResult 切换格式后未清空 fetchedUrl（预览仍播放上一格式的直链）'
  )
  // 预览请求在途时切换格式：watch 因 fetchedUrl 为空直接跳过，旧格式直链返回后仍会被写入。
  // 必须记录发起时的格式并在 await 之后比对，否则预览播放的是已取消选中的画质。
  const openPreview = resultCode.match(/async function openPreview\(\)\s*\{([\s\S]*?)\n\}/)
  assert.ok(openPreview, 'VideoResult 缺少 openPreview')
  assert.ok(
    /formatAtRequest\s*!==\s*selectedFormat\.value/.test(openPreview[1]),
    'VideoResult 的 openPreview 未在 await 后校验格式是否已切换（会展示旧格式直链）'
  )

  // ChatPanel 的 need_login 分支必须写入终止文案并立即渲染：
  // loading 在此之前已被置 false，finally 的兜底（if (aiMessage.loading)）不会执行，
  // 直接 return 会在问答列表里永久留下一条空白的 assistant 气泡。
  const chatCode = stripComments(read('components/panels/ChatPanel.vue'))
  const needLoginIdx = chatCode.indexOf('parsed.need_login')
  assert.ok(needLoginIdx !== -1, 'ChatPanel 缺少 need_login 分支')
  const needLoginBlock = chatCode.slice(needLoginIdx, needLoginIdx + 400)
  assert.ok(
    /aiMessage\.content\s*=/.test(needLoginBlock),
    'ChatPanel 的 need_login 分支未写入提示文案（会留下永久空白的 assistant 气泡）'
  )
  assert.ok(
    /flushRenderedNow\(aiIndex\)/.test(needLoginBlock),
    'ChatPanel 的 need_login 分支未立即渲染（提示文案不会显示）'
  )
  assert.ok(
    needLoginBlock.indexOf('flushRenderedNow(aiIndex)') < needLoginBlock.indexOf("emit('need-login')"),
    'ChatPanel 的 need_login 分支必须先渲染再 emit，否则父组件弹窗后气泡仍为空'
  )

  // toast 入场动画只能做纵向位移：左下角全局 toast 没有水平位移类，
  // keyframe 里带 -50% 会让它每次弹出先横移半个自身宽度再瞬间跳回。
  // 顶部居中 toast 的水平居中由容器上的 -translate-x-1/2 负责，动画必须挂在内层卡片。
  const appCode = stripComments(read('App.vue'))
  assert.ok(
    /delete window\.__appGuestSession/.test(appCode),
    'App.vue 卸载时未清理 window.__appGuestSession（钩子残留并指向已销毁的 ref）'
  )
  const toastKeyframes = appCode.match(/@keyframes toast-in\s*\{[\s\S]*?\n\}/)
  assert.ok(toastKeyframes, 'App.vue 缺少 toast-in 入场动画')
  assert.ok(
    !/translateX?\(\s*-50%/.test(toastKeyframes[0]),
    'toast-in keyframe 含 -50% 水平位移（左下角全局 toast 会先横移再跳回）'
  )
  const paymentToastTag = appCode.match(/<div v-if="paymentToast"[^>]*>/)
  assert.ok(paymentToastTag, '未找到支付 toast 容器')
  assert.ok(
    paymentToastTag[0].includes('-translate-x-1/2') && !paymentToastTag[0].includes('animate-toast-in'),
    '支付 toast 的入场动画挂在了带 -translate-x-1/2 的容器上（水平位移会叠加）'
  )
}

// ============================ 主流程 ============================
writeHarness()
let server
let browser
try {
  server = await createServer({
    root: ROOT,
    server: { port: 5199, strictPort: false },
    logLevel: 'error',
  })
  await server.listen()
  const url = server.resolvedUrls.local[0]

  browser = await chromium.launch({ channel: 'chrome' })
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  // 删除历史会弹 confirm：统一接受，否则 Playwright 默认 dismiss，删除逻辑不会执行
  page.on('dialog', (d) => d.accept())
  // 预置 token：request.js 无 token 时会先静默创建演示用户，测试里直接跳过这段
  await page.addInitScript(() => localStorage.setItem('saveany_token', 'regression-token'))
  historyFixture.push(
    makeHistoryItem(1, '可搜索条目 A'),
    makeHistoryItem(2, '其他条目 B'),
    makeSummaryItem(3, '旧总结条目 D')
  )
  await installHistoryRoutes(page, historyFixture)
  await page.goto(`${url}.regression-harness/index.html`)
  await page.waitForSelector('#video-url-input')

  await testEmptyStateDefaultSlot(page)
  await testPasteHint(page)
  await testSubmitMultipleUrls(page)
  await testMobileHeaderHistory(page)
  await testWindowOpenSemantics(page)
  await testToastMergeCount(page)
  await testRetryStateGuard(page)
  await testNormalizeHistoryUrl(page)
  await testHistoryDrawerSync(page, historyFixture)
  await testHistoryDrawerSearchExtras(page)
  testSourceContracts()

  assert.deepEqual(errors, [], `页面存在运行时错误：${errors.join(' / ')}`)

  console.log('前端 UI 回归验证全部通过')
} finally {
  await browser?.close()
  await server?.close()
  removeHarness()
}
