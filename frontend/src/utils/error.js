// 统一后端错误文案提取，消除 HistoryDrawer / useVideo / BatchPanel / AuthModal / App / VideoCacheAdmin 的重复实现。
//
// 后端可能返回：
//  - 字符串 detail："记录不存在或无权删除"
//  - 对象 detail：{ error: "..." } 或 { message: "..." }
//  - 业务成功但 success=false 时，错误也可能在 data.error（顶层）
//  - 无 detail / error：回退到 err.message，再回退到 fallback（默认 "网络错误"）
// prefix 非空时在文案前加 "前缀："（如 getApiError(e, '加载失败') → "加载失败：..."）。
// fallback 在彻底无文案时使用（如 getApiError(e, '', '操作失败')）。

export function getApiError(err, prefix = '', fallback = '网络错误') {
  const data = err?.response?.data
  const d = data?.detail
  let msg
  if (typeof d === 'string') msg = d
  else if (d && typeof d === 'object') msg = d.error || d.message
  // 业务层 200 + success:false 的常见错误落点：response.data.message（FastAPI 也用 detail）。
  if (!msg) msg = data?.message || data?.error || err?.message || fallback
  return prefix ? `${prefix}：${msg}` : msg
}

/**
 * 从响应体里提取错误文案（消除 useVideo / BatchPanel 的 '+ res.error' bug）。
 * 后端可能把 error 字段写成：
 *   - 字符串："记录不存在"
 *   - 对象：{ code: 1, message: "记录不存在" } 或 { error: { message: "..." } }（FastAPI HTTPException）
 *   - 嵌套 detail：{ detail: { message: "..." } }
 * 字符串优先；对象按 message → error → detail 优先级；非法值返回 fallback。
 */
export function extractErrorMsg(value, fallback = '未知错误') {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    if (typeof value.message === 'string') return value.message
    if (typeof value.error === 'string') return value.error
    if (value.error && typeof value.error === 'object' && typeof value.error.message === 'string') {
      return value.error.message
    }
    if (typeof value.detail === 'string') return value.detail
    if (value.detail && typeof value.detail === 'object' && typeof value.detail.message === 'string') {
      return value.detail.message
    }
  }
  return fallback
}
