/**
 * AI 视频总结 API 封装
 * 使用原生 fetch + ReadableStream 处理 SSE 流式响应
 *
 * 注意：SSE 必须用 fetch，不能走 axios（axios 默认 buffer stream 不透出）。
 * 但统一通过 utils/request.js 的 showFetchError 走语义化 toast，
 * 错误码语义与 axios 拦截器保持一致。
 *
 * 取消支持：summarizeVideo / chatWithVideo 都可选接受 AbortSignal，
 * 用于组件销毁 / 重新触发总结时立即中断旧请求，避免旧回调污染新状态。
 */

import { getToken } from './auth'
import { showFetchError } from '../utils/request'
import { getApiError } from '../utils/error'

async function handleSSEStream(response, callbacks, signal) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''
  let dataLines = []
  let hasData = false

  // 中断后立刻取消底层 reader.read()，避免持续接收 chunk 触发回调
  const onAbort = () => {
    try { reader.cancel() } catch { /* noop */ }
  }
  if (signal) {
    if (signal.aborted) { reader.cancel(); return }
    signal.addEventListener('abort', onAbort, { once: true })
  }

  function dispatch() {
    if (hasData && currentEvent) {
      const handler = callbacks[currentEvent]
      if (handler) handler(dataLines.join('\n'))
    }
    dataLines = []
    hasData = false
    currentEvent = ''
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line === '') {
          dispatch()
          continue
        }

        if (line.startsWith(':')) continue

        const colonIdx = line.indexOf(':')
        if (colonIdx < 0) continue

        const field = line.slice(0, colonIdx)
        let val = line.slice(colonIdx + 1)
        if (val.startsWith(' ')) val = val.slice(1)

        if (field === 'event') {
          currentEvent = val
        } else if (field === 'data') {
          hasData = true
          dataLines.push(val)
        }
      }
    }
    // 处理流末残留行：若最后一段数据无结尾换行，buffer 里可能还留着末事件（含 done），
    // 不处理会导致 done 事件丢失、loading 永久转圈。
    if (buffer) {
      const line = buffer
      buffer = ''
      if (line !== '' && !line.startsWith(':')) {
        const colonIdx = line.indexOf(':')
        if (colonIdx >= 0) {
          const field = line.slice(0, colonIdx)
          let val = line.slice(colonIdx + 1)
          if (val.startsWith(' ')) val = val.slice(1)
          if (field === 'event') {
            currentEvent = val
          } else if (field === 'data') {
            hasData = true
            dataLines.push(val)
          }
        }
      }
    }
    dispatch()
  } finally {
    if (signal) signal.removeEventListener('abort', onAbort)
  }
}

function authHeaders() {
  const token = getToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

export async function summarizeVideo(url, language = 'zh', callbacks = {}, title = '', platform = '', signal = null) {
  const response = await fetch('/api/summarize', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url, language, title, platform }),
    signal,
  })

  if (!response.ok) {
    showFetchError(response)
    throw new Error(getApiError({ response: { status: response.status, data: null } }, '总结失败'))
  }

  await handleSSEStream(response, callbacks, signal)
}

export async function chatWithVideo(url, question, subtitleText = '', callbacks = {}, signal = null) {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url, question, subtitle_text: subtitleText }),
    signal,
  })

  if (!response.ok) {
    showFetchError(response)
    throw new Error(getApiError({ response: { status: response.status, data: null } }, '问答失败'))
  }

  await handleSSEStream(response, callbacks, signal)
}
