import { ref } from 'vue'
import { getSavedUser, fetchMe, logout as logoutApi, isLoggedIn } from '../api/auth.js'

/**
 * 用户鉴权 composable（替换原 App.vue 内联 currentUser + restoreUser + handleAuthSuccess + handleLogout）。
 * - onLogout: 退出登录时回调,供宿主清理关联状态（如清掉历史/关闭抽屉等）。
 *   注意 onLogout 内**不应**重新调 logoutApi（避免重复 removeToken 副作用）。
 * - 依赖注入:无（isLoggedIn 直接 import 模块函数）。
 */
export function useAuth({ onLogout } = {}) {
  const currentUser = ref(null)

  async function restoreUser() {
    if (!isLoggedIn()) return false
    const saved = getSavedUser()
    if (saved) currentUser.value = saved
    try {
      currentUser.value = await fetchMe()
      return true
    } catch {
      handleLogout()
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