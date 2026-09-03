// 共享相对时间格式化工具：把 SQLite datetime('now') 的 UTC 字符串（YYYY-MM-DD HH:MM:SS），
// 强制按 UTC 解析后输出"刚刚 / N 分钟前 / N 小时前 / N 天前 / M月D日"语义。
//
// SQLite 默认 datetime('now') 输出的是无时区的 UTC 字符串（'YYYY-MM-DD HH:MM:SS'）。
// V8 默认按本地时区解析，会导致相对时间偏差一个时区偏移（曾导致"刚解析"显示成"8 小时前"）。
// 这里显式追加 'T' + 'Z'，强制按 UTC 解析，与后端 add_history 的归一化一致。
//
// 替代 HistoryDrawer.formatTime 与 App.vue.formatRelative 两处重复实现，统一调用入口。

/**
 * 把 SQLite datetime('now') 风格的字符串（无时区）一并按 UTC 解析。
 * 使用场景：
 *  - useHistory._toHistoryItem：服务端行 created_at → 数字 ts（用于排序/过滤/显示）
 *  - formatRelativeTime：渲染时再 format（同样按 UTC，避免时区偏移）
 * 无时区标识时显式追加 'Z'，已带时区（Z / +08:00）或已是 Date 等其他类型原样交给 Date 构造。
 */
export function parseSqliteUtcToDate(ts) {
  if (!ts) return null
  const iso = typeof ts === 'string' && !/[Zz]|[+-]\d{2}:?\d{2}/.test(ts)
    ? ts.replace(' ', 'T') + 'Z'
    : ts
  const d = new Date(iso)
  return isNaN(d.getTime()) ? null : d
}

export function formatRelativeTime(ts) {
  if (!ts) return ''
  const d = parseSqliteUtcToDate(ts)
  if (!d) return String(ts)
  const diff = Date.now() - d.getTime()
  const min = 60000, hour = 3600000, day = 86400000
  if (diff < min) return '刚刚'
  if (diff < hour) return Math.floor(diff / min) + ' 分钟前'
  if (diff < day) return Math.floor(diff / hour) + ' 小时前'
  if (diff < 30 * day) return Math.floor(diff / day) + ' 天前'
  return `${d.getMonth() + 1}月${d.getDate()}日`
}