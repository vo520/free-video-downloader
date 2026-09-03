import { createApp } from 'vue'
import './style.css'
import App from './App.vue'

const app = createApp(App)

// 全局错误兜底：避免子组件抛错白屏 / 静默失败
// - app.config.errorHandler 捕获渲染 / 生命周期 / watch 等同步异常
// - unhandledrejection 捕获 Promise 异步 reject（axios / SSE 等）
// - 都走 window.__appToast（App.vue setup 里挂上）做用户可见反馈；
//   未注入时降级 console.warn，避免循环依赖。
app.config.errorHandler = (err, _instance, info) => {
  // eslint-disable-next-line no-console
  console.error('[Vue Error]', info, err)
  if (typeof window !== 'undefined' && typeof window.__appToast === 'function') {
    window.__appToast(`页面出错了：${err && err.message ? err.message : '未知错误'}`, 'error')
  }
}
window.addEventListener('unhandledrejection', (e) => {
  const reason = e.reason
  // eslint-disable-next-line no-console
  console.error('[Unhandled Promise]', reason)
  if (typeof window !== 'undefined' && typeof window.__appToast === 'function') {
    const msg = reason && reason.message ? reason.message : (typeof reason === 'string' ? reason : '请求异常')
    window.__appToast(`请求异常：${msg}`, 'error')
  }
})

app.mount('#app')