import axios from 'axios'
import { attachToastInterceptor } from '../utils/request'

const TOKEN_KEY = 'saveany_token'
const USER_KEY = 'saveany_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function getSavedUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function _doEnsureDefaultUser() {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) return true

  try {
    const res = await axios.post('/api/auth/register', {
      email: 'demo@local.com',
      password: 'demo123456',
    })
    const { token, user } = res.data.data
    setToken(token)
    saveUser(user)
    return true
  } catch {
    try {
      const res = await axios.post('/api/auth/login', {
        email: 'demo@local.com',
        password: 'demo123456',
      })
      const { token, user } = res.data.data
      setToken(token)
      saveUser(user)
      return true
    } catch {
      // demo 账号不可用(后端数据库丢/服务挂):返回 false,不要让拦截器走 reload,
      // 否则下次请求仍 401 → 又触发 reload,陷入死循环。让上层按普通 401 错误处理。
      return false
    }
  }
}

/**
 * 对外暴露：供 utils/request.js 拦截器在首次请求前 lazy 调用，
 * 避免本模块顶层副作用（Node SSR / 无 localStorage 环境 import 即抛）。
 */
export async function ensureDefaultUser() {
  return _doEnsureDefaultUser()
}

export async function register(email, password) {
  const res = await axios.post('/api/auth/register', { email, password })
  const { token, user } = res.data.data
  setToken(token)
  saveUser(user)
  return user
}

export async function login(email, password) {
  const res = await axios.post('/api/auth/login', { email, password })
  const { token, user } = res.data.data
  setToken(token)
  saveUser(user)
  return user
}

export async function fetchMe() {
  const res = await axios.get('/api/auth/me', { headers: authHeaders() })
  const user = res.data.data
  saveUser(user)
  return user
}

export function logout() {
  removeToken()
  ensureDefaultUser()
}

export function isLoggedIn() {
  return !!getToken()
}

// ===== 鉴权拦截器（B17/C3 前后端协同） =====
// 请求拦截：有 token 时自动附带 Authorization，供后端 get_current_user 校验。
// 响应拦截：遇到 401（token 失效/服务端重启换密钥）自动清除并重建默认登录，刷新页面恢复。
let _authRecovering = false

/**
 * 给 axios 实例附加鉴权拦截器。
 * @param {import('axios').AxiosInstance} instance
 * @param {boolean} [includeRequestInterceptor=true] 是否同时附加请求拦截器（注入 Authorization）。
 *   - 业务实例 request.js 内已自带请求拦截器（包含 ensureDefaultUserLazy 副作用），传 false 避免重复。
 *   - 全局 axios 实例需要（auth.js 顶层调用），保持 true。
 */
export function attachAuthInterceptor(instance, includeRequestInterceptor = true) {
  if (includeRequestInterceptor) {
    instance.interceptors.request.use((config) => {
      const token = getToken()
      if (token) {
        config.headers = config.headers || {}
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })
  }

  instance.interceptors.response.use(
    (response) => response,
    async (error) => {
      // __noAuthRecover：标记为非关键请求（如后台 best-effort 的缓存归档），
      // 401 时仅静默 reject，不触发 token 清理 + 整页 reload，避免误伤主流程状态。
      if (
        error.response &&
        error.response.status === 401 &&
        !error.config?.__noAuthRecover
      ) {
        removeToken()
        if (!_authRecovering) {
          _authRecovering = true
          try {
            const recovered = await ensureDefaultUser()
            if (recovered) {
              window.location.reload()
            }
            // 恢复失败:demo 账号不可用,不 reload,避免死循环;
            // 当前请求 reject 上层,自然走到 catch 显示 toast,用户感知"登录已失效"。
          } finally {
            _authRecovering = false
          }
        }
      }
      return Promise.reject(error)
    }
  )
}

// 为默认 axios 实例挂载，覆盖 VideoCacheAdmin 等直接使用 axios 的调用
attachAuthInterceptor(axios)
attachToastInterceptor(axios)
