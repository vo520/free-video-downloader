import request from '../utils/request'

export async function parseVideo(url) {
  const { data } = await request.post('/parse', { url })
  return data
}

export async function getDirectUrl(url, formatId) {
  const { data } = await request.post('/direct-url', { url, format_id: formatId })
  return data
}

export function getDownloadUrl() {
  return '/api/download'
}

export async function downloadViaServer(url, formatId) {
  const response = await request.post(
    '/download',
    { url, format_id: formatId },
    { responseType: 'blob', timeout: 600000 }
  )
  return response
}

// 将解析结果归档到视频缓存（best-effort，失败不影响主流程）。
// __silent：缓存归档属后台非关键写，即便 401/5xx 也只静默失败，
// 避免触发全局拦截器的 toast 噪音干扰主流程状态。
// __noAuthRecover：同时禁止 401 触发全局登出恢复——归档失败不该把用户的登录态清掉
// （清掉后界面仍显示已登录、下一次请求会被 ensureDefaultUserLazy 换成 demo 账号 token）。
export async function saveVideoCache(data) {
  const { data: res } = await request.post('/video-cache/videos', data, {
    __silent: true,
    __noAuthRecover: true,
  })
  return res
}
