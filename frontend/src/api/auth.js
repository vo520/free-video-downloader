import axios from 'axios'

const TOKEN_KEY = 'saveany_token'
const USER_KEY = 'saveany_user'
const DEMO_AUTH_KEY = 'saveany_demo_auth'
// 用户主动「结束访客会话」后置 1：此后不再自动登录公共演示账号。
// 没有这个开关，结束访客会话只会在下一次请求时被 ensureDefaultUserLazy 立刻重建，用户点了等于没点。
const GUEST_OPT_OUT_KEY = 'saveany_guest_optout'
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

/**
 * 当前是否处于「访客会话」。
 *
 * 访客 = 借用公共演示账号（demo@local.com）身份的匿名用户，分两种来源：
 *  1. 自动：首个请求触发 ensureDefaultUser() 静默登录演示账号（DEMO_AUTH_KEY 标记）；
 *  2. 手动：用户主动用演示账号凭据登录（保存的 user.email 即演示邮箱）。
 * 两种来源在服务端落在同一个 user_id 上，因此行为必须一致：都不占个人云端历史、
 *  都不被当作 VIP 个人账号展示，顶栏统一显示「访客模式」。
 */
export function isGuestSession() {
  return !!getToken() && isDemoAuth()
}

/** 用户对象是否为公共演示账号（手动用演示凭据登录时用得上）。 */
export function isGuestUser(user) {
  return (user?.email || '').toLowerCase() === DEMO_EMAIL
}

/** 标记当前为访客会话（手动登录演示账号后调用，让 isDemoAuth 判定一致）。 */
export function markGuestSession() {
  localStorage.setItem(DEMO_AUTH_KEY, '1')
}

/** 用户是否已主动结束访客会话（此后不再自动登录演示账号）。 */
export function isGuestOptOut() {
  return localStorage.getItem(GUEST_OPT_OUT_KEY) === '1'
}

/**
 * 结束访客会话：清掉演示账号 token，并置位「不再自动登录演示账号」。
 *
 * 没有 opt-out 标记的话，下一个请求就会被 request.js 的 ensureDefaultUserLazy
 * 立刻重新登录演示账号，用户点了「结束访客会话」等于什么都没发生。
 */
export function endGuestSession() {
  removeToken()
  removeUser()
  localStorage.setItem(GUEST_OPT_OUT_KEY, '1')
  notifyGuestSession(false)
}

/** 通知 Vue 层访客状态变化（window 钩子模式，与 __appForceLogout 同构）。 */
function notifyGuestSession(active) {
  if (typeof window !== 'undefined' && typeof window.__appGuestSession === 'function') {
    window.__appGuestSession(active)
  }
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
  // 用户主动注册 = 明确选择真实身份，清掉「结束访客会话」的标记
  localStorage.removeItem(GUEST_OPT_OUT_KEY)
  const user = persistAuth(data)
  // 注册即真实身份，访客态必须结束（否则顶栏仍挂着「访客模式」徽标）
  notifyGuestSession(false)
  return user
}

export async function login(email, password) {
  const { data } = await axios.post('/api/auth/login', { email, password })
  localStorage.removeItem(GUEST_OPT_OUT_KEY)
  const user = persistAuth(data)
  // 用公共演示账号的凭据手动登录 = 仍然是访客身份，顶栏应显示「访客模式」
  if (isGuestUser(user)) {
    markGuestSession()
    notifyGuestSession(true)
  } else {
    // 真实账号登录：必须清掉访客态，否则残留的访客标记会让顶栏误显示「访客模式」
    notifyGuestSession(false)
  }
  return user
}

export function logout() {
  removeToken()
  removeUser()
  notifyGuestSession(false)
}

export async function fetchMe() {
  const { data } = await axios.get('/api/auth/me', {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  const user = normalizeAuthPayload(data)
  saveUser(user)
  return user
}

/**
 * 建立访客会话：静默登录公共演示账号。
 *
 * 用户主动「结束访客会话」后不再自动登录（isGuestOptOut），
 * 否则访客点掉提示，下一个请求又被这里悄悄登录回来，等于没点。
 */
export async function ensureDefaultUser() {
  if (getToken()) return true
  if (isGuestOptOut()) return false
  try {
    const { data } = await axios.post('/api/auth/login', {
      email: DEMO_EMAIL,
      password: DEMO_PASSWORD,
    })
    const ok = persistDemoAuth(data)
    if (ok) notifyGuestSession(true)
    return ok
  } catch (err) {
    const status = err.response?.status
    if (status !== 400 && status !== 404) throw err
    const { data } = await axios.post('/api/auth/register', {
      email: DEMO_EMAIL,
      password: DEMO_PASSWORD,
    })
    const ok = persistDemoAuth(data)
    if (ok) notifyGuestSession(true)
    return ok
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
