// 下载任务管理器（前端单例）：统一管理并发下载、实时进度、取消(AbortController)、
// 失败重试与 localStorage 持久化。复用 /api/download 端点与既有的流式读取进度逻辑。
// 设计约束：不新增后端接口、不引入新依赖；状态为模块级单例，所有组件共享同一队列。
import { reactive } from 'vue'
import { getApiError } from '../utils/error.js'
import { getToken } from '../api/auth.js'

const STORAGE_KEY = 'fvd_download_tasks'
export const MAX_CONCURRENCY = 2
const DEFAULT_FORMAT_ID = 'bestvideo+bestaudio/best'

// 任务状态：queued | downloading | done | error | canceled
const state = reactive({
  tasks: [],
  panelOpen: false,
})

let seq = 0
const controllers = new Map() // id -> AbortController

function uid() {
  return `${Date.now()}-${++seq}`
}

function persist() {
  try {
    const slim = state.tasks.map((t) => ({
      id: t.id,
      url: t.url,
      formatId: t.formatId,
      title: t.title,
      status: t.status,
      progress: t.progress,
    }))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
  } catch {
    /* 忽略持久化失败 */
  }
}

// 启动时恢复历史任务用于展示；未完成项标记为已取消，避免刷新后自动重新下载。
function restore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const list = JSON.parse(raw)
    state.tasks = list.map((t) => ({
      id: t.id,
      url: t.url,
      formatId: t.formatId || DEFAULT_FORMAT_ID,
      title: t.title || t.url,
      status: t.status === 'done' ? 'done' : 'canceled',
      progress: t.status === 'done' ? 100 : 0,
      received: 0,
      total: 0,
      error: '',
    }))
  } catch {
    /* 忽略损坏数据 */
  }
}

function downloadingCount() {
  return state.tasks.filter((t) => t.status === 'downloading').length
}

function pump() {
  while (downloadingCount() < MAX_CONCURRENCY) {
    const next = state.tasks.find((t) => t.status === 'queued')
    if (!next) break
    start(next)
  }
}

async function start(task) {
  task.status = 'downloading'
  task.error = ''
  task.progress = 0
  task.received = 0
  task.total = 0

  const controller = new AbortController()
  controllers.set(task.id, controller)

  const TIMEOUT_MS = 10 * 60 * 1000
  const timeoutController = new AbortController()
  const timeoutId = setTimeout(() => {
    const err = new Error('download timeout')
    err.isTimeout = true
    timeoutController.abort(err)
  }, TIMEOUT_MS)
  const onUserAbort = () => {
    if (!timeoutController.signal.aborted) timeoutController.abort()
  }
  controller.signal.addEventListener('abort', onUserAbort, { once: true })

  try {
    // 显式注入 Authorization：fetch 不走 axios 拦截器，必须手动带 token；
    // 否则登录用户（含 demo 兜底用户）也会因 401 被后端拒绝，且无法触发 axios 的自动恢复链。
    const token = getToken()
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`

    // fetch 不支持 timeout，需用 AbortController 模拟"超时"中断。
    // - 用户主动取消 controller → 转发 abort 到 timeoutController（fetch 收到 abort 后抛 AbortError）
    // - 网络层超时 → timeoutController 自爆 abort，fetch 抛 AbortError（catch 用 isTimeout 区分）
    // 用 timeoutController 作为 fetch 的 signal：任一 abort 都会中断 fetch。
    const response = await fetch('/api/download', {
      method: 'POST',
      headers,
      body: JSON.stringify({ url: task.url, format_id: task.formatId }),
      signal: timeoutController.signal,
    })
    clearTimeout(timeoutId)
    if (!response.ok) {
      // 构造与 axios 拦截器形态一致的 Error 对象，让 getApiError 走标准分支
      // （避免后端 detail 为对象时被 toString 成 "[object Object]"）
      const body = await response.json().catch(() => ({}))
      const fakeAxiosErr = { response: { status: response.status, data: body } }
      throw new Error(getApiError(fakeAxiosErr, '', `下载失败: ${response.status}`))
    }

    const contentLength = Number(response.headers.get('content-length')) || 0
    task.total = contentLength
    const reader = response.body.getReader()
    const chunks = []
    let received = 0
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value)
      received += value.length
      task.received = received
      if (contentLength) {
        task.progress = Math.min(100, Math.round((received / contentLength) * 100))
      }
    }

    const blob = new Blob(chunks)
    const cd = response.headers.get('content-disposition')
    let filename = 'video.mp4'
    if (cd) {
      const m = cd.match(/filename\*?=(?:UTF-8'')?([^;\n]+)/i)
      if (m) filename = decodeURIComponent(m[1].replace(/"/g, ''))
    }
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    // 延迟释放：a.click() 后浏览器可能尚未真正开始保存大文件，
    // 过早 revoke 会导致 Firefox 等环境下下载失败。
    setTimeout(() => window.URL.revokeObjectURL(url), 1000)

    task.status = 'done'
    task.progress = 100
  } catch (err) {
    // 区分三类中断：超时（网络层 10 分钟无响应） / 用户主动取消 / 其他异常
    // fetch abort 时只抛 AbortError（不带 reason），因此从 timeoutController.signal.reason 读取超时标记
    if (timeoutController.signal.aborted && timeoutController.signal.reason?.isTimeout) {
      task.status = 'error'
      task.error = '下载超时，请检查网络后重试'
    } else if (err && err.name === 'AbortError') {
      task.status = 'canceled'
    } else {
      task.status = 'error'
      task.error = err && err.message ? err.message : '下载失败'
    }
  } finally {
    clearTimeout(timeoutId)
    controller.signal.removeEventListener('abort', onUserAbort)
    controllers.delete(task.id)
    persist()
    pump()
  }
}

function enqueue(url, formatId, title) {
  if (!url) return null
  const normalizedFormatId = formatId || DEFAULT_FORMAT_ID
  // 去重：相同 url+formatId 且仍在队列/下载中的任务不再重复入队，避免重复下载与进度错乱。
  const key = `${url}::${normalizedFormatId}`
  const dup = state.tasks.find(
    (t) => `${t.url}::${t.formatId || DEFAULT_FORMAT_ID}` === key && (t.status === 'queued' || t.status === 'downloading')
  )
  if (dup) return dup
  // 修复：原写法 `reactive({...})` 在外层 reactive 数组中再包一层 reactive 是冗余。
  // Vue 3 不会警告（代理复用），但语义不清晰。改为纯对象，让 Vue 自动代理。
  const task = {
    id: uid(),
    url,
    formatId: normalizedFormatId,
    title: title || url,
    status: 'queued',
    progress: 0,
    received: 0,
    total: 0,
    error: '',
  }
  state.tasks.unshift(task)
  persist()
  pump()
  return task
}

function cancel(id) {
  const c = controllers.get(id)
  if (c) {
    c.abort()
  } else {
    const t = state.tasks.find((x) => x.id === id)
    if (t) t.status = 'canceled'
  }
  persist()
  pump() // 释放排队槽位后立即补位，避免下一个 queued 任务无故延迟
}

function retry(id) {
  const t = state.tasks.find((x) => x.id === id)
  if (!t) return
  t.formatId = t.formatId || DEFAULT_FORMAT_ID
  t.status = 'queued'
  t.progress = 0
  t.error = ''
  persist()
  pump()
}

function remove(id) {
  const c = controllers.get(id)
  if (c) c.abort()
  state.tasks = state.tasks.filter((x) => x.id !== id)
  persist()
  pump() // 移除（含排队中）任务后补位，立即启动下一个 queued 任务
}

function clearFinished() {
  // 仅清除已完成/已取消；保留进行中（downloading/queued）与失败（error，便于重试）。
  state.tasks = state.tasks.filter(
    (t) => t.status === 'downloading' || t.status === 'queued' || t.status === 'error'
  )
  persist()
}

function openPanel() {
  state.panelOpen = true
}
function closePanel() {
  state.panelOpen = false
}
function togglePanel() {
  state.panelOpen = !state.panelOpen
}

// 取与某个 URL 关联的最新任务（用于主流程按钮联动进度）
function latestTaskForUrl(url, formatId = '') {
  const targetFormatId = formatId || ''
  const list = state.tasks.filter(
    (t) => t.url === url && (!targetFormatId || (t.formatId || DEFAULT_FORMAT_ID) === targetFormatId)
  )
  if (!list.length) return null
  // 修复：任务用 unshift 入队，state.tasks 是「新在前」，因此 list[0] 才是最新任务。
  // 原 `list[list.length - 1]` 取到最旧任务，会导致「最新一次成功，但更早一次失败」时
  // 仍把旧 error 透传到主流程（downloadError），用户误以为下载失败。
  return (
    list.find((t) => t.status === 'downloading' || t.status === 'queued') ||
    list[0]
  )
}

let initialized = false
function initDownloadManager() {
  if (initialized) return
  initialized = true
  restore()
}

export function useDownloadManager() {
  return {
    state,
    initDownloadManager,
    enqueue,
    cancel,
    retry,
    remove,
    clearFinished,
    openPanel,
    closePanel,
    togglePanel,
    latestTaskForUrl,
    MAX_CONCURRENCY,
  }
}
