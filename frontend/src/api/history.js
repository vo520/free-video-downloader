import request from '../utils/request'

/**
 * 拉取当前用户的云端历史记录（解析/下载/总结）。
 * @param {object} opts
 * @param {'parse'|'download'|'summary'|null} [opts.type]
 * @param {number} [opts.limit]
 * @param {number} [opts.offset]
 * @returns {Promise<{items: Array, total: number}>}
 */
export async function fetchHistory({ type = null, limit = 50, offset = 0 } = {}) {
  const params = { limit, offset }
  if (type) params.type = type
  const { data } = await request.get('/history', { params })
  // 后端返回 { success: true, data: rows(数组), total }：
  //   total 在顶层信封（axios response.data.total），data 字段直接是数组，
  //   曾误取 data.data.total（数组上无此属性），导致 total 恒为 0，
  //   HistoryDrawer 的「加载更多」守卫 items.length >= total 恒真，翻页永久失效。
  const payload = data?.data || {}
  return {
    items: Array.isArray(payload) ? payload : (payload.items || []),
    total: data?.total ?? (payload.total || 0),
  }
}

/**
 * 删除单条云端历史。
 * @param {number|string} historyId
 */
export async function deleteHistoryItem(historyId) {
  await request.delete(`/history/${historyId}`)
}

/**
 * 清空当前用户全部云端历史。
 */
export async function clearMyHistory() {
  await request.post('/history/clear')
}
