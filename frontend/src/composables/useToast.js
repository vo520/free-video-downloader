import { ref, provide, onUnmounted } from 'vue'

/**
 * 全局轻提示 composable（替换原 App.vue 内联 appToast + showToast）。
 * - provide('showToast', showToast) 用字符串 key 保持向后兼容：
 *   子组件如 VideoSummary / HistoryDrawer / DownloadTaskCenter 仍 inject('showToast') 调用即可。
 * - 模板需要展示 toast 框时,解构出 appToast 直接 v-if。
 * - 队列模式：多条提示依次展示、互不覆盖。原实现是单槽 + 重置 timer，
 *   批量解析多条失败只剩最后一条、多个下载同时完成也只剩最后一条，
 *   前一条提示被"吃掉"，用户不知道到底发生了什么。
 * - 同一条消息短时间内重复触发时合并计数，不重复排队（避免连点刷屏）。
 * - onUnmounted 清理未触发的 timer，避免组件销毁后 timer 仍在跑、修改已卸载 ref。
 */

const TOAST_DURATION = 3500
const MAX_QUEUE = 5 // 超出则丢弃最旧的待显示项，避免异常刷屏占满内存

export function useToast() {
  const appToast = ref(null)
  // 待显示队列（不含当前正在显示的）
  const queue = []
  let timer = null

  function nextToast() {
    if (appToast.value || queue.length === 0) return
    const item = queue.shift()
    // 计数存在队列项自身（showToast 合并时累加的是 item.count），
    // 原实现另用 recentCounts Map 记录，但那个 Map 从未被写入过真实计数，
    // 取值恒为 1 → App.vue 上的「×N」角标永远不显示。
    appToast.value = { type: item.type, message: item.message, count: item.count || 1 }
    timer = setTimeout(() => {
      timer = null
      appToast.value = null
      nextToast()
    }, TOAST_DURATION)
  }

  function showToast(message, type = 'info') {
    if (!message) return
    const text = String(message)
    const key = `${type}::${text}`
    // 队列里已有相同消息 → 直接合并计数，不重复排队
    const existing = queue.find((t) => t.key === key)
    if (existing) {
      existing.count += 1
      return
    }
    // 当前正在显示的也是同一条 → 合并到当前项
    if (appToast.value && appToast.value.message === text && appToast.value.type === type) {
      appToast.value = { type, message: text, count: (appToast.value.count || 1) + 1 }
      return
    }
    queue.push({ key, type, message: text, count: 1 })
    if (queue.length > MAX_QUEUE) queue.splice(0, queue.length - MAX_QUEUE)
    nextToast()
  }

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })

  provide('showToast', showToast)

  return { appToast, showToast }
}
