// 把一段文本按换行 / 逗号 / 中文逗号 / 空白拆成候选 URL 列表。
// 仅保留以 http(s):// 开头的合法片段（去前后空格）。
// 用于：
//   - HeroSection 粘贴多链接时识别「去批量解析」快捷入口
//   - BatchPanel 粘贴批量 URL 时拆分成可逐条解析的列表
// 与两组件内既有的 splitUrls 实现保持完全一致的行为（最小改动抽出复用）。
export function splitUrls(text) {
  return (text || '')
    .split(/[\n,，\s]+/)
    .map((s) => s.trim())
    .filter((s) => /^https?:\/\//i.test(s))
}
