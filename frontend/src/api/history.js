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
  // 后端返回 { success: true, data: { items: [], total } }：
  //   axios response.data = {success, data:{items,total}}，
  //   需二次解包 data.data.items（曾误写为 data.data，导致 items 为对象、.map 报错）
  const payload = data?.data || {}
  return {
    items: Array.isArray(payload) ? payload : (payload.items || []),
    total: payload.total || 0,
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
