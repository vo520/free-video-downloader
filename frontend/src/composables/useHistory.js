import { ref } from 'vue'
import { fetchHistory, deleteHistoryItem, clearMyHistory } from '../api/history.js'
import { isLoggedIn } from '../api/auth.js'
import { parseSqliteUtcToDate } from '../utils/relativeTime.js'

const HISTORY_KEY = 'fvd_parse_history'
const HISTORY_MAX = 20

/**
 * 前端 URL 归一化：对齐后端 _normalize_video_url 的核心规则，保证未登录本地历史与
 * 服务端历史使用同一把「同一视频」的判定基准，避免 http/https/www/#fragment 等形态差异
 * 被识别为两条记录（曾导致「同一视频出现两条记录」的视觉重复）。
 * 仅覆盖 history 模块需要的轻量规则：去 fragment + 去 www. 前缀 + 协议+host+path 小写，
 * query 保持原样不做排序（避免改变语义）。
 * 注意：这是 best-effort 客户端兜底，不替代后端权威 upsert。
 */
function _normalizeUrl(url) {
  if (!url || typeof url !== 'string') return ''
  let u = url.trim()
  // 去 fragment（# 及之后），同一视频带不同推荐参数/章节不应重复入库
  const hashIdx = u.indexOf('#')
  if (hashIdx >= 0) u = u.slice(0, hashIdx)
  // 协议 + host 统一：去 www. 前缀、protocol 强制 https（http/https 视为同一资源）、
  // host 小写，避免同视频因协议或 www 差异被识别为两条。
  u = u.replace(/^https?:\/\/(www\.)?/i, () => 'https://')
  const protoEnd = u.indexOf('://') + 3
  const hostEnd = u.indexOf('/', protoEnd)
  if (hostEnd > protoEnd) {
    u = u.slice(0, protoEnd) + u.slice(protoEnd, hostEnd).toLowerCase() + u.slice(hostEnd)
  } else {
    u = u.slice(0, protoEnd) + u.slice(protoEnd).toLowerCase()
  }
  return u
}

/**
 * 历史管理 composable（替换原 App.vue 内联 history + 6 个函数）。
 * - 服务端 / localStorage 双源策略保留在 composable 内部:
 *   登录用户走 /api/history?type=parse,未登录用户走 localStorage 临时记录。
 * - 公开 addLocalHistory(url, data) 供 useVideo 在 parse 成功后回填未登录历史。
 * - 公开 clearLocal() 供 useAuth 在 onLogout 回调里清理本地残留（避免下次未登录看到前任账号历史）。
 * - 依赖:showToast（可选,删除/清空失败与成功反馈）。
 */
function _toHistoryItem(row) {
  // 服务端 history 行：{id, type, video_url, title, platform, thumbnail, snapshot, created_at}
  // 前端组件消费：{ url, title, platform, thumbnail, snapshot, ts, id }
  // 后端 created_at 是 SQLite datetime('now') 的 UTC 字串（YYYY-MM-DD HH:MM:SS），
  // 不带时区标识，V8 会按本地时间解析，导致相对时间偏差一个时区偏移（曾导致"刚解析"显示成"8 小时前"）。
  // 复用 utils/relativeTime.parseSqliteUtcToDate 强制按 UTC 解析。
  const parsed = parseSqliteUtcToDate(row.created_at)
  return {
    id: row.id,
    url: row.video_url,
    title: row.title,
    platform: row.platform,
    thumbnail: row.thumbnail,
    snapshot: row.snapshot,
    ts: parsed ? parsed.getTime() : Date.now(),
  }
}

export function useHistory({ showToast } = {}) {
  const history = ref([])

  async function _loadParseHistory(onError = 'reset') {
    try {
      const { items } = await fetchHistory({ type: 'parse', limit: HISTORY_MAX })
      const mapped = items.map(_toHistoryItem)
      // 确保登录态服务端返回也按时间倒序（本地 localStorage 分支已是倒序）；
      // HISTORY_MAX=20，排序开销可忽略，避免后端默认正序导致「最新在前」需求不达标。
      mapped.sort((a, b) => b.ts - a.ts)
      // 客户端去重兜底：后端虽然按 (user_id,type,video_url) UPSERT，但 URL 形态差异
      // （http vs https / 有无 www. / 带不带 fragment）仍可能被当作不同行入库；
      // 这里按归一化 url 去重，保留 ts 最新那条，与本地分支口径一致。
      const seen = new Set()
      history.value = mapped.filter((h) => {
        const key = _normalizeUrl(h.url)
        if (!key || seen.has(key)) return false
        seen.add(key)
        return true
      })
    } catch (err) {
      // 修复：原 catch 完全静默，连 console 都没留，调试 / 排查失败原因困难。
      // keep 模式（refreshHistory 触发）保留旧数据 + toast 提示，避免用户以为列表失效；
      // reset 模式（loadHistory 触发）按设计清空，仅留 console.warn。
      // eslint-disable-next-line no-console
      console.warn('[useHistory] _loadParseHistory failed', err)
      if (onError === 'reset') {
        history.value = []
      } else if (showToast) {
        showToast('刷新历史失败，请稍后重试', 'error')
      }
    }
  }

  async function loadHistory() {
    if (isLoggedIn()) {
      await _loadParseHistory('reset')
      return
    }
    try {
      const raw = localStorage.getItem(HISTORY_KEY)
      history.value = raw ? JSON.parse(raw) : []
    } catch {
      history.value = []
    }
  }

  async function refreshHistory() {
    if (!isLoggedIn()) return
    await _loadParseHistory('keep')
  }

  async function removeHistory(urlOrId) {
    if (isLoggedIn()) {
      const item = history.value.find(h => (h.id != null ? String(h.id) === String(urlOrId) : h.url === urlOrId))
      if (!item || item.id == null) {
        history.value = history.value.filter(h => h.url !== urlOrId)
        return
      }
      try {
        await deleteHistoryItem(item.id)
      } catch (err) {
        if (showToast) showToast('删除失败，请稍后重试', 'error')
        return
      }
      history.value = history.value.filter(h => h.id !== item.id)
      if (showToast) showToast('已删除', 'success')
      return
    }
    history.value = history.value.filter(h => _normalizeUrl(h.url) !== _normalizeUrl(urlOrId))
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value))
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[useHistory] removeHistory localStorage persist failed', err)
    }
  }

  async function clearHistory() {
    if (isLoggedIn()) {
      try {
        await clearMyHistory()
      } catch (err) {
        if (showToast) showToast('清空失败，请稍后重试', 'error')
        return
      }
      const n = history.value.length
      history.value = []
      if (showToast) showToast(n > 0 ? `已清空 ${n} 条记录` : '已清空', 'success')
      return
    }
    history.value = []
    try { localStorage.removeItem(HISTORY_KEY) } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[useHistory] clearHistory localStorage remove failed', err)
    }
  }

  /**
   * 未登录分支回填历史（useVideo.handleParse 调用）。
   * 同一视频（按归一化 url）去重,封顶 HISTORY_MAX,落库到 localStorage。
   * 同步写入 snapshot（来自 parseVideo 返回的 res.data），保证内联「最近解析」条目可点击回看，
   * 还原完整视频信息，避免「点历史看不到视频数据」的体验断点。
   */
  function addLocalHistory(url, data) {
    const normalizedNew = _normalizeUrl(url)
    const withoutDup = history.value.filter((h) => _normalizeUrl(h.url) !== normalizedNew)
    const next = [
      {
        url,
        title: data?.title,
        platform: data?.platform,
        thumbnail: data?.thumbnail,
        snapshot: data,
        ts: Date.now(),
      },
      ...withoutDup,
    ].slice(0, HISTORY_MAX)
    history.value = next
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[useHistory] addLocalHistory localStorage persist failed', err)
    }
  }

  /** 退出登录时清理本地历史（useAuth.onLogout 回调里调用）。 */
  function clearLocal() {
    history.value = []
    try { localStorage.removeItem(HISTORY_KEY) } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[useHistory] clearLocal localStorage remove failed', err)
    }
  }

  return {
    history,
    HISTORY_KEY,
    HISTORY_MAX,
    loadHistory,
    refreshHistory,
    removeHistory,
    clearHistory,
    addLocalHistory,
    clearLocal,
  }
}