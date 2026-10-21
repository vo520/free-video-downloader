import { ref } from 'vue'
import { getSavedUser, fetchMe, logout as logoutApi, isLoggedIn, isDemoAuth, clearDemoUserCache } from '../api/auth.js'

/**
 * 用户鉴权 composable（替换原 App.vue 内联 currentUser + restoreUser + handleAuthSuccess + handleLogout）。
 * - onLogout: 退出登录时回调,供宿主清理关联状态（如清掉历史/关闭抽屉等）。
 *   注意 onLogout 内**不应**重新调 logoutApi（避免重复 removeToken 副作用）。
 * - 依赖注入:无（isLoggedIn 直接 import 模块函数）。
 */
export function useAuth({ onLogout } = {}) {
  const currentUser = ref(null)

  async function restoreUser() {
    if (!isLoggedIn() || isDemoAuth()) {
      clearDemoUserCache()
      return false
    }
    const saved = getSavedUser()
    if (saved) currentUser.value = saved
    try {
      currentUser.value = await fetchMe()
      return true
    } catch (err) {
      // 仅当鉴权明确失效（401/403）才登出并清理本地历史；网络抖动 / 后端 5xx 时
      // 保留本地缓存用户与 token，避免页面加载瞬间的瞬时故障把用户登出并清空历史。
      const status = err?.response?.status
      if (status === 401 || status === 403) {
        handleLogout()
      }
      return false
    }
  }

  function handleAuthSuccess(user) {
    currentUser.value = user
  }

  function handleLogout() {
    logoutApi()
    currentUser.value = null
    if (onLogout) onLogout()
  }

  return {
    currentUser,
    restoreUser,
    handleAuthSuccess,
    handleLogout,
  }
}