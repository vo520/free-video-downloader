/**
 * 统一 axios 实例 + 语义化错误 toast
 *
 * 设计要点：
 * - 单一 axios.create({ baseURL: '/api' }) 实例，业务层不再各自 axios.create
 * - 复用 auth.js 的 attachAuthInterceptor(鉴权 + token 自动恢复)（includeRequestInterceptor=false
 *   避免与本文件下方自写的请求拦截器重复注入 Authorization）
 * - 业务级错误码语义化：通过 window.__appToast 回调 showToast，避免在 util 中 import composable
 *   （composable 需要 setup context，util 文件无法直接调用）
 * - __noAuthRecover 选项：best-effort 请求（如后台缓存归档）401 时不触发 reload + token 清理
 * - provideLazyDefaultUser：把 ensureDefaultUser 的副作用从 auth.js 顶层挪到拦截器内 lazy 触发
 *
 * 配套：
 * - App.vue 的 setup 里执行 window.__appToast = showToast 注入回调
 * - auth.js 已删除 ensureDefaultUser() 顶层调用，统一在此处首次请求时初始化
 */

import axios from 'axios'
import { attachAuthInterceptor, getToken, ensureDefaultUser } from '../api/auth'

// 业务级错误码 → 语义化提示文案
const ERROR_MESSAGES = {
  400: '请求参数有误',
  401: '登录已失效，请稍后再试',
  403: '没有访问权限',
  404: '资源不存在',
  408: '请求超时',
  413: '文件过大',
  429: '操作太频繁，请稍后再试',
  500: '服务器开小差了，请稍后再试',
  502: '服务暂时不可用',
  503: '服务维护中',
  504: '网关超时',
}

// 默认用户 lazy 初始化：避免 auth.js 顶层副作用（Node SSR 无 localStorage 会抛）。
// 语义：promise pending 中 → 并发请求复用同一次初始化（避免重复创建 demo 用户）；
// promise 已 settle 且 token 仍为空（登出 / 初始化失败场景）→ 下一次调用重新触发。
let _defaultUserPromise = null
let _defaultUserSettled = true
async function ensureDefaultUserLazy() {
  if (getToken()) return // 已有 token，跳过
  if (!_defaultUserPromise || _defaultUserSettled) {
    _defaultUserSettled = false
    _defaultUserPromise = ensureDefaultUser()
      .catch(() => false)
      .finally(() => {
        _defaultUserSettled = true
      })
  }
  return _defaultUserPromise
}

/**
 * 给 window.__appToast 回调统一触发语义化 toast：
 * - 5xx / 429 → warning（提示用户稍后重试）
 * - 其他 4xx → error（业务/客户端错误）
 * 抽成函数后，handleResponseError（axios）与 showFetchError（fetch）共用同一份 toast 颜色/调用逻辑。
 */
function triggerStatusToast(status, msg) {
  if (!msg || typeof window === 'undefined' || typeof window.__appToast !== 'function') return
  window.__appToast(msg, status >= 500 || status === 429 ? 'warning' : 'error')
}

/**
 * 业务级错误响应统一处理：best-effort 静默跳过、语义化 toast、保留原 reject 给上层 catch。
 * 抽成函数后，request.js 主响应拦截器 与 attachToastInterceptor 都复用同一份逻辑，
 * 避免两处分支不一致（曾实际发生：attachToastInterceptor 漏判 status===429 toast 颜色）。
 */
function handleResponseError(error) {
  // 不对 best-effort 请求弹错误（避免误伤主流程状态）
  if (error.config?.__silent) {
    return Promise.reject(error)
  }

  const status = error.response?.status
  const msg =
    ERROR_MESSAGES[status] ||
    (error.message === 'Network Error' ? '网络异常，请检查连接' : null)
  triggerStatusToast(status, msg)
  return Promise.reject(error)
}

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：lazy 初始化默认用户 + 注入 Authorization（业务实例独占的业务请求会走这里）。
// try/catch 包裹 ensureDefaultUserLazy：后端宕机 / 网络断开时不应让所有业务请求被 reject，
// 降级为 console.warn 后继续（无 token 也能让前端先加载出来）。
request.interceptors.request.use(async (config) => {
  try {
    await ensureDefaultUserLazy()
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('[request] ensureDefaultUserLazy failed', e)
  }
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：业务级错误语义化 toast + 原样 reject 给上层 catch
request.interceptors.response.use(
  (response) => response,
  handleResponseError
)

// 复用 auth.js 现有 401 → 自动恢复逻辑（重载页面等）；includeRequestInterceptor=false
// 避免与上方自写的请求拦截器重复注入 Authorization。
attachAuthInterceptor(request, false)

export default request

/**
 * 把后端 `{ data: { code, message, data } }` 统一解包为 `data` 字段。
 * 业务层 90% 场景都是 `const { data } = await api.post(...)` 然后 `return data.data`，
 * 抽到这里让调用方少写一层。
 */
export function unwrap(response) {
  return response.data?.data
}

/**
 * 给 fetch 流式调用（SSE）用的错误归一化工具：
 * fetch 不走 axios interceptor，需要手动调一下确保 SSE 失败也能弹 toast。
 * 返回 true 表示已处理（调用方应 throw 或 reject），false 表示未处理（调用方按原逻辑走）。
 */
export function showFetchError(response, opts = {}) {
  if (response.ok) return false
  if (opts.silent) return false
  const status = response.status
  triggerStatusToast(status, ERROR_MESSAGES[status])
  return true
}

/**
 * 给已有 axios 实例（如 VideoCacheAdmin 直接 import 的全局 axios）挂业务错误 toast 拦截器。
 * 与 request.js 内置拦截器共享 handleResponseError，确保语义一致。
 */
export function attachToastInterceptor(instance) {
  instance.interceptors.response.use(
    (response) => response,
    handleResponseError
  )
}
