// 统一的浏览器端文件下载与文件名安全化工具：
// 消除 SubtitlePanel / MindmapPanel / VideoCacheAdmin 三处重复的 createObjectURL + a.click + revokeObjectURL 实现。
// 零新增依赖，纯原生 API。

/**
 * 文件名安全化：剔除操作系统禁用的字符，并裁剪到指定长度。
 * @param {string} name 原始文件名（通常为视频标题）
 * @param {number} [maxLen=80] 最大长度
 * @returns {string} 安全文件名（空值回退到「文件」）
 */
export function sanitizeFilename(name, maxLen = 80) {
  return (name || '文件').replace(/[\\/*?:"<>|]/g, '_').substring(0, maxLen)
}

/**
 * 触发浏览器下载一个 Blob（自动生成临时 URL 并延迟释放）。
 * 延迟 1s revoke 与 useDownloadManager 的视频下载对齐：
 * a.click() 后浏览器可能尚未真正开始保存大文件，过早 revoke 会导致 Firefox 等环境下下载失败。
 * @param {Blob} blob 待下载内容
 * @param {string} filename 下载文件名
 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
