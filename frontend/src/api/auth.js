import axios from 'axios'

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

async function ensureDefaultUser() {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) return
  
  try {
    const res = await axios.post('/api/auth/register', { 
      email: 'demo@local.com', 
      password: 'demo123456' 
    })
    const { token, user } = res.data.data
    setToken(token)
    saveUser(user)
  } catch {
    try {
      const res = await axios.post('/api/auth/login', { 
        email: 'demo@local.com', 
        password: 'demo123456' 
      })
      const { token, user } = res.data.data
      setToken(token)
      saveUser(user)
    } catch {}
  }
}

ensureDefaultUser()

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
