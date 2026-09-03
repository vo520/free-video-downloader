import { ref, provide, onUnmounted } from 'vue'

/**
 * 全局轻提示 composable（替换原 App.vue 内联 appToast + showToast）。
 * - provide('showToast', showToast) 用字符串 key 保持向后兼容：
 *   子组件如 VideoSummary / HistoryDrawer / DownloadTaskCenter 仍 inject('showToast') 调用即可。
 * - 模板需要展示 toast 框时,解构出 appToast 直接 v-if。
 * - 3.5s 自动消失,新 toast 触发会清除旧 timer 避免堆叠。
 * - onUnmounted 清理未触发的 timer，避免组件销毁后 timer 仍在跑、修改已卸载 ref。
 */
export function useToast() {
  const appToast = ref(null)
  let timer = null

  function showToast(message, type = 'info') {
    if (timer) clearTimeout(timer)
    appToast.value = { type, message }
    timer = setTimeout(() => { appToast.value = null }, 3500)
  }

  function hideToast() {
    if (timer) clearTimeout(timer)
    appToast.value = null
  }

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })

  provide('showToast', showToast)

  return { appToast, showToast, hideToast }
}