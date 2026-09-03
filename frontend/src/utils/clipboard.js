// 复制文本到剪贴板：优先 Clipboard API，降级到 textarea + execCommand。
// 复用既有 showToast 反馈由调用方处理，本模块只负责"能否复制"。
export async function copyText(text) {
  if (!text) return false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* 落到降级方案 */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    ta.style.left = '-9999px'
    ta.setAttribute('readonly', '')
    document.body.appendChild(ta)
    ta.focus()
    // iOS Safari 需要先显式选中范围，execCommand('copy') 才能命中文本
    ta.setSelectionRange(0, text.length)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
