import { ref } from 'vue'

/**
 * 鉴权弹窗 composable（替换原 App.vue 内联 authModalVisible + authModalMode）。
 * - mode: 'login' | 'register'（AuthModal.initialMode 接收）
 * - 与 useAuth 完全独立:鉴权弹窗只需知道"显示什么模式",不关心当前用户状态。
 */
export function useAuthModal() {
  const authModalVisible = ref(false)
  const authModalMode = ref('login')

  function showAuthModal(mode = 'login') {
    authModalMode.value = mode
    authModalVisible.value = true
  }

  function closeAuthModal() {
    authModalVisible.value = false
  }

  return { authModalVisible, authModalMode, showAuthModal, closeAuthModal }
}