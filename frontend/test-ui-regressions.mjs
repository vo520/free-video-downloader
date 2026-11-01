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
import HeroSection from '../src/components/HeroSection.vue'
import EmptyState from '../src/components/ui/EmptyState.vue'
import { useToast } from '../src/composables/useToast.js'

const Root = {
  setup() {
    const { appToast, showToast } = useToast()
    window.__toast = { appToast, showToast }
    return {}
  },
  render() {
    return h('div', [
      h(HeroSection),
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

// ---------- 5. 源码契约：修复点不能被改回去 ----------
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
  await page.goto(`${url}.regression-harness/index.html`)
  await page.waitForSelector('#video-url-input')

  await testEmptyStateDefaultSlot(page)
  await testPasteHint(page)
  await testWindowOpenSemantics(page)
  await testToastMergeCount(page)
  testSourceContracts()

  assert.deepEqual(errors, [], `页面存在运行时错误：${errors.join(' / ')}`)

  console.log('前端 UI 回归验证全部通过')
} finally {
  await browser?.close()
  await server?.close()
  removeHarness()
}
