// 统一"最高画质"选取与分辨率展示，消除 VideoResult / BatchPanel 的重复算法。
//
// 设计要点：
// - 分辨率优先用权威字段 height（数值像素高度），否则从 label / format_note / resolution
//   中解析 3-4 位数字（如 "1080p" / "2160p60" / "4K" 之类 label 不含数字时也能靠 height 命中）。
// - 这同时修复了原 VideoResult resOf 只解析 label 的隐藏缺陷：当某格式 label 为 "4K" 而
//   height=2160 时，旧逻辑 resOf 返回 0，会被"有分辨率"过滤条件剔除，导致永远推荐不了最高画质。
//
// 对外接口：
// - pickBestFormat(formats, mode='max') → 最佳 format 对象；空列表返回 null
// - formatResolution(fmt)              → 展示文案，如 "1080P"；无法识别返回 ''
// - formatBytes(bytes)                 → 字节格式化（消除 DownloadTaskCenter / VideoCacheAdmin 重复）
// - formatDate(isoStr)                 → YYYY-MM-DD（消除 AppHeader 内联）
// - formatDateTime(isoStr)             → 本地化日期+时间（消除 VideoCacheAdmin 内联）
// - formatViewCount(count)             → 万/亿（消除 VideoResult 内联）
// - formatTime(seconds)                → mm:ss / hh:mm:ss（消除 SubtitlePanel / VideoCacheAdmin 内联）

// 解析单个 format 的数值分辨率（像素高度）
function parseResolution(fmt) {
  if (fmt && typeof fmt.height === 'number' && fmt.height > 0) return fmt.height
  const text = [fmt?.label, fmt?.format_note, fmt?.resolution].filter(Boolean).join(' ')
  const m = text.match(/(\d{3,4})/)
  return m ? parseInt(m[1], 10) : 0
}

/**
 * 选取最佳（分辨率最高）的 format 对象。
 * 候选池优先级：①有音频且能识别分辨率；②否则有音频；③否则全部。
 * mode='min' 时返回分辨率最低（用于"最小体积"预设）。空列表返回 null。
 */
export function pickBestFormat(formats, mode = 'max') {
  const fmts = Array.isArray(formats) ? formats : []
  if (!fmts.length) return null
  const withRes = fmts.filter((f) => parseResolution(f) > 0 && f.has_audio)
  const pool = withRes.length ? withRes : fmts.filter((f) => f.has_audio)
  const base = pool.length ? pool : fmts
  // memoize parseResolution：先 map 一次缓存 resolution，再 sort。
  // 原写法每次 sort 比较都调一次 parseResolution → O(n² log n)；
  // 改写后 O(n log n)，大视频（几百个 format）不再卡顿。
  const scored = base.map((f) => [f, parseResolution(f)])
  scored.sort((a, b) => b[1] - a[1])
  return mode === 'min' ? (scored[scored.length - 1]?.[0] || null) : (scored[0]?.[0] || null)
}

/**
 * 返回展示用分辨率文案，如 "1080P"；无法识别返回 ''。
 */
export function formatResolution(fmt) {
  const r = parseResolution(fmt)
  return r ? `${r}P` : ''
}

// 统一字节格式化（消除 DownloadTaskCenter.formatSize 与 VideoCacheAdmin.formatFileSize 的重复逻辑）。
// 0 / 非法值返回 '0 B'；按 1024 进制在 B/KB/MB/GB 间自动选择单位，decimals 控制小数位。
export function formatBytes(bytes, decimals = 1) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  const value = bytes / Math.pow(1024, i)
  return `${i === 0 ? value.toFixed(0) : value.toFixed(decimals)} ${units[i]}`
}

/**
 * YYYY-MM-DD 日期格式化（消除 AppHeader 内联 vip_expire_at 展示）。
 * 替代原 AppHeader.formatDate 单文件实现。
 * @param {string|Date} isoStr ISO 字符串或 Date 对象
 * @returns {string} YYYY-MM-DD；非法值返回 ''
 */
export function formatDate(isoStr) {
  if (!isoStr) return ''
  const d = isoStr instanceof Date ? isoStr : new Date(isoStr)
  if (isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/**
 * 本地化日期+时间（如 "2026/8/20 18:00:00"），消除 VideoCacheAdmin 内联 last_access_at 展示。
 * 用 toLocaleDateString/toLocaleTimeString 而非 YYYY-MM-DD HH:mm:ss，因为后台缓存管理页面
 * 给运营看，需要本地化展示才直观。
 * @param {string|Date} isoStr ISO 字符串或 Date 对象
 * @returns {string} 本地化字符串；非法值返回 ''
 */
export function formatDateTime(isoStr) {
  if (!isoStr) return ''
  const d = isoStr instanceof Date ? isoStr : new Date(isoStr)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString()
}

/**
 * 播放量/计数的"万/亿"展示（消除 VideoResult 内联；与 formatBytes 同类视图格式化）。
 * @param {number} count 原始数字
 * @returns {string} 1.5万 / 1.2亿 / 1,234 形式
 */
export function formatViewCount(count) {
  if (!count) return ''
  if (count >= 100000000) return (count / 100000000).toFixed(1) + '亿'
  if (count >= 10000) return (count / 10000).toFixed(1) + '万'
  return count.toLocaleString()
}

/**
 * 视频时间码展示（消除 SubtitlePanel 内联 formatTime）。
 * 自动选择 mm:ss 或 hh:mm:ss 形式。
 * @param {number} seconds 秒数
 * @returns {string} m:ss / h:mm:ss
 */
export function formatTime(seconds) {
  if (seconds == null || isNaN(seconds)) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}
