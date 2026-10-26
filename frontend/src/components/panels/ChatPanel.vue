<template>
  <div class="chat-panel">
    <div class="space-y-4">
      <!-- 对话列表 -->
      <div
        ref="chatContainer"
        class="space-y-4 max-h-[400px] overflow-y-auto pr-1"
      >
        <EmptyState
          v-if="chatMessages.length === 0"
          size="md"
          variant="empty"
          title="向 AI 提问关于这个视频的任何问题"
          desc="例如：「这个视频的核心观点是什么？」"
        >
          <template #icon>
            <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </template>
        </EmptyState>
        <div
          v-for="(msg, idx) in chatMessages"
          :key="idx"
          :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']"
        >
          <div
            :class="[
              'max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed',
              msg.role === 'user'
                ? 'bg-primary text-white rounded-br-md'
                : 'bg-bg-section text-text-primary rounded-bl-md border border-border-light'
            ]"
          >
            <div
              v-if="msg.role === 'assistant'"
              class="chat-prose prose prose-slate prose-sm max-w-none"
              v-html="renderMarkdown(msg.content)"
            ></div>
            <span v-else>{{ msg.content }}</span>
            <span
              v-if="msg.role === 'assistant' && msg.loading"
              class="inline-block w-1.5 h-4 bg-primary/60 rounded-sm animate-pulse ml-0.5 align-text-bottom"
            ></span>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="flex gap-2 pt-3 border-t border-border-light">
        <input
          v-model="chatInput"
          @keydown.enter.prevent="sendQuestion"
          type="text"
          placeholder="输入你的问题..."
          aria-label="向 AI 提问关于视频内容的问题"
          class="flex-1 h-11 px-4 rounded-xl border border-border bg-white text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
          :disabled="chatLoading"
        />
        <BaseButton
          @click="sendQuestion"
          :disabled="!chatInput.trim()"
          :loading="chatLoading"
          variant="primary"
          shape="square"
        >
          <template #icon>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </template>
          发送
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, inject, onBeforeUnmount } from 'vue'
import { renderMarkdown } from '../../utils/markdown.js'
import { chatWithVideo } from '../../api/summarize.js'
import EmptyState from '../ui/EmptyState.vue'
import BaseButton from '../ui/BaseButton.vue'

  const props = defineProps({
    videoUrl: { type: String, required: true },
    subtitleText: { type: String, default: '' },
  })
  const emit = defineEmits(['need-login'])

  // showToast 由父组件通过 provide/inject 注入
  const showToast = inject('showToast', (msg, type) => { console.warn('[toast]', msg) })

  const chatMessages = ref([])
  const chatInput = ref('')
  const chatLoading = ref(false)
  const chatContainer = ref(null)

  // 当前问答 SSE 请求的 AbortController：组件卸载或重新提问时中断旧请求，
  // 避免旧 chunk 继续接收触发已销毁组件的状态更新。
  let currentChatController = null

  function scrollChatToBottom() {
    nextTick(() => {
      if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight
      }
    })
  }

  async function sendQuestion() {
    const question = chatInput.value.trim()
    if (!question || chatLoading.value) return

    chatInput.value = ''
    chatMessages.value.push({ role: 'user', content: question })

    const aiMessage = { role: 'assistant', content: '', loading: true }
    chatMessages.value.push(aiMessage)
    chatLoading.value = true

    // 中断上一轮可能未完成的问答请求，避免旧 chunk 污染新消息
    if (currentChatController) currentChatController.abort()
    // 局部保存引用：旧请求的 finally 会无条件执行 currentChatController = null，
    // 若无引用比对，快速连续提问时会把本轮新 controller 误清，导致下一轮无法 abort。
    const controller = new AbortController()
    currentChatController = controller

    await nextTick()
    scrollChatToBottom()

    try {
      await chatWithVideo(
        props.videoUrl,
        question,
        props.subtitleText,
        {
          answer: (data) => {
            try { aiMessage.content += JSON.parse(data) } catch { aiMessage.content += data }
            scrollChatToBottom()
          },
          done: () => {
            aiMessage.loading = false
            chatLoading.value = false
          },
          error: (data) => {
            aiMessage.loading = false
            chatLoading.value = false
            try {
              const parsed = JSON.parse(data)
              if (parsed.need_login) {
                emit('need-login')
                return
              }
              aiMessage.content = '❌ ' + (parsed.message || '回答失败')
            } catch (e) {
              aiMessage.content = '❌ 回答失败'
            }
          },
        },
        currentChatController.signal
      )
    } catch (err) {
      // 用户主动中断不视为错误
      if (err.name === 'AbortError') return
      aiMessage.loading = false
      chatLoading.value = false
      aiMessage.content = '❌ 请求失败: ' + err.message
    } finally {
      // 只清空本轮自己的 controller：若新提问已接管（currentChatController 指向新 controller），
      // 本 finally 不应清掉它，否则下一轮 sendQuestion 无法再 abort 新请求。
      if (currentChatController === controller) currentChatController = null
    }
  }

  // 组件卸载时中断未完成的问答请求
  onBeforeUnmount(() => {
    if (currentChatController) currentChatController.abort()
  })
</script>

<style scoped>
  /* AI 问答 Markdown 排版（更紧凑） */
  .chat-prose :deep(p) {
    margin-bottom: 0.5rem;
    line-height: 1.7;
  }
  .chat-prose :deep(p:last-child) {
    margin-bottom: 0;
  }
  .chat-prose :deep(ul),
  .chat-prose :deep(ol) {
    margin-bottom: 0.5rem;
    padding-left: 1.25rem;
  }
  .chat-prose :deep(li) {
    margin-bottom: 0.2rem;
    line-height: 1.7;
  }
  .chat-prose :deep(li::marker) {
    color: var(--color-primary);
  }
  .chat-prose :deep(code) {
    background: rgba(0, 0, 0, 0.06);
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    font-size: 0.85em;
  }
  .chat-prose :deep(blockquote) {
    border-left: 2px solid var(--color-primary);
    padding-left: 0.75rem;
    color: var(--color-text-secondary);
    margin: 0.5rem 0;
  }
  .chat-prose :deep(strong) {
    font-weight: 600;
  }
</style>