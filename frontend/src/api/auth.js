import axios from 'axios'

const TOKEN_KEY = 'saveany_token'
const USER_KEY = 'saveany_user'
const DEMO_AUTH_KEY = 'saveany_demo_auth'
const DEMO_EMAIL = 'demo@local.com'
const DEMO_PASSWORD = 'demo123456'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

function saveToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
}

function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(DEMO_AUTH_KEY)
}

function saveUser(user) {
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
}

function saveDemoToken(token) {
  if (!token) return
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(DEMO_AUTH_KEY, '1')
  removeUser()
}

function readSavedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function isDemoAuth() {
  return localStorage.getItem(DEMO_AUTH_KEY) === '1' || readSavedUser()?.email === DEMO_EMAIL
}

export function clearDemoUserCache() {
  if (readSavedUser()?.email === DEMO_EMAIL) removeUser()
}

export function getSavedUser() {
  return readSavedUser()
}

function removeUser() {
  localStorage.removeItem(USER_KEY)
}

function normalizeAuthPayload(payload) {
  return payload?.data || payload || {}
}

function persistAuth(payload) {
  const data = normalizeAuthPayload(payload)
  localStorage.removeItem(DEMO_AUTH_KEY)
  saveToken(data.token)
  saveUser(data.user)
  return data.user
}

function persistDemoAuth(payload) {
  const data = normalizeAuthPayload(payload)
  saveDemoToken(data.token)
  return true
}

export function isLoggedIn() {
  return !!getToken() && !isDemoAuth()
}

export async function register(email, password) {
  const { data } = await axios.post('/api/auth/register', { email, password })
  return persistAuth(data)
}

export async function login(email, password) {
  const { data } = await axios.post('/api/auth/login', { email, password })
  return persistAuth(data)
}

export function logout() {
  removeToken()
  removeUser()
}

export async function fetchMe() {
  const { data } = await axios.get('/api/auth/me', {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  const user = normalizeAuthPayload(data)
  saveUser(user)
  return user
}

export async function ensureDefaultUser() {
  if (getToken()) return true
  try {
    const { data } = await axios.post('/api/auth/login', {
      email: DEMO_EMAIL,
      password: DEMO_PASSWORD,
    })
    return persistDemoAuth(data)
  } catch (err) {
    const status = err.response?.status
    if (status !== 400 && status !== 404) throw err
    const { data } = await axios.post('/api/auth/register', {
      email: DEMO_EMAIL,
      password: DEMO_PASSWORD,
    })
    return persistDemoAuth(data)
  }
}

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
    (error) => {
      // 401 判定必须与 request.js 的 handleResponseError 保持一致：
      // __noAuthRecover（best-effort 写入）与 __silent（后台静默轮询）都不应触发全局登出。
      // 否则后台管理面板的静默轮询 401 会把用户静默登出（清 token + 清本地历史）却无任何提示，
      // 而同一 instance 上另一处拦截器却因 __silent 跳过了 401 处理，两边语义相互矛盾。
      if (
        error.response?.status === 401 &&
        !error.config?.__noAuthRecover &&
        !error.config?.__silent
      ) {
        logout()
        // 通知 Vue 层同步清 currentUser / 历史（window.__appForceLogout 由 App.vue 注入）
        if (typeof window !== 'undefined' && typeof window.__appForceLogout === 'function') {
          window.__appForceLogout()
        }
      }
      return Promise.reject(error)
    }
  )
}
