/**
 * 访客会话回归验证（无需测试框架，node 直接运行）。
 *
 * 背景：本轮把「借用公共演示账号」显式建模为访客模式，涉及三处易回退的约定：
 *  1. 访客态判定：有 token 且带演示账号标记才算访客；
 *  2. 「结束访客会话」必须置位 opt-out 标记，否则下一个请求会被 ensureDefaultUser
 *     立刻重新登录演示账号，用户点了等于没点；
 *  3. 真实账号登录必须清掉访客态，否则顶栏会一直挂着「访客模式」徽标。
 *
 * 本脚本直接 import 真实的 src/api/auth.js（不是复刻逻辑），
 * 用最小 localStorage / window 桩驱动这些行为。
 *
 * 运行：node test-guest-session.mjs
 */
import assert from 'node:assert/strict'

// ---- 浏览器 API 桩（auth.js 依赖 localStorage 与 window 钩子）----
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
}
const guestEvents = []
globalThis.window = {
  __appGuestSession: (active) => guestEvents.push(active),
}

const {
  isGuestSession,
  isGuestUser,
  markGuestSession,
  isGuestOptOut,
  endGuestSession,
  getToken,
  getSavedUser,
} = await import('./src/api/auth.js')

const TOKEN_KEY = 'saveany_token'
const USER_KEY = 'saveany_user'
const DEMO_AUTH_KEY = 'saveany_demo_auth'

// ---- 1. 未登录时不是访客 ----
assert.equal(isGuestSession(), false, '无 token 时不应判定为访客')
assert.equal(isGuestOptOut(), false, '初始不应有 opt-out 标记')

// ---- 2. 演示账号 token + 标记 → 访客 ----
localStorage.setItem(TOKEN_KEY, 'demo-token')
markGuestSession()
assert.equal(isGuestSession(), true, '演示账号 token + 标记应判定为访客')
assert.equal(getToken(), 'demo-token')

// ---- 3. 真实账号（无演示标记）→ 不是访客 ----
localStorage.removeItem(DEMO_AUTH_KEY)
assert.equal(isGuestSession(), false, '真实账号不应判定为访客')
markGuestSession() // 复原演示标记

// ---- 4. 访客身份判定工具 ----
assert.equal(isGuestUser({ email: 'demo@local.com' }), true)
assert.equal(isGuestUser({ email: 'DEMO@LOCAL.com' }), true)
assert.equal(isGuestUser({ email: 'real@example.com' }), false)
assert.equal(isGuestUser(null), false)
assert.equal(isGuestUser({}), false)

// ---- 5. 结束访客会话：清 token、清用户、置 opt-out、通知 Vue 层 ----
guestEvents.length = 0
endGuestSession()
assert.equal(getToken(), null, '结束访客会话必须清掉演示 token')
assert.equal(getSavedUser(), null, '结束访客会话必须清掉缓存的演示用户')
assert.equal(isGuestOptOut(), true, '结束访客会话必须置位 opt-out 标记')
assert.equal(isGuestSession(), false, '结束访客会话后不再是访客')
assert.deepEqual(guestEvents, [false], '必须通知 Vue 层访客态结束')

// ---- 6. opt-out 标记存在时，不得再自动建立访客会话 ----
// ensureDefaultUser 在 opt-out 下必须直接返回 false（不发任何网络请求）。
const { ensureDefaultUser } = await import('./src/api/auth.js')
assert.equal(await ensureDefaultUser(), false, 'opt-out 后不得自动重建访客会话')
assert.equal(getToken(), null, 'opt-out 后不得写入演示 token')

// ---- 7. opt-out 是「用户主动结束」才置位：重新登录真实账号应被允许 ----
// （登录路径会先 removeItem(GUEST_OPT_OUT_KEY)，此处只验证 opt-out 是可清除的）
localStorage.removeItem('saveany_guest_optout')
assert.equal(isGuestOptOut(), false, 'opt-out 标记应可被登录/注册流程清除')

console.log('访客会话回归验证全部通过')
