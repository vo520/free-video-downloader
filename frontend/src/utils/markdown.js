// 共享 Markdown 渲染工具：marked 解析 + DOMPurify 消毒，统一 AI 产出（总结/问答/历史回看）的渲染口径。
// AI 输出不可信，必须经 DOMPurify 过滤 XSS（<script>/on*=/javascript: 等）后再交由 v-html 渲染。
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  breaks: true,
  gfm: true,
})

export function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(text))
}
