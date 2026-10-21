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
      if (error.response?.status === 401 && !error.config?.__noAuthRecover) {
        logout()
      }
      return Promise.reject(error)
    }
  )
}
