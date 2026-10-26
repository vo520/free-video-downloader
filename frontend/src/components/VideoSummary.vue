<template>
  <div class="bg-white/85 rounded-[1.5rem] border border-white/80 shadow-2xl shadow-slate-900/10 overflow-hidden h-full flex flex-col backdrop-blur">
    <!-- 标签页导航 -->
    <div class="flex border-b border-border-light/80 bg-slate-50/50">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        @click="activeTab = tab.key"
        :class="[
          'flex items-center gap-2 px-5 py-3.5 text-sm font-medium transition-all relative cursor-pointer',
          activeTab === tab.key
            ? 'text-primary'
            : 'text-text-secondary hover:text-text-primary'
        ]"
      >
        <span>{{ tab.icon }}</span>
        <span>{{ tab.label }}</span>
        <div
          v-if="activeTab === tab.key"
          class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
        ></div>
      </button>
    </div>

    <!-- 内容区域：4 个 panel 自包含交互逻辑 -->
    <div class="p-5 sm:p-6 min-h-[400px] flex-1 overflow-y-auto">
      <SummaryPanel
        v-if="activeTab === 'summary'"
        :summary-text="summaryText"
        :loading="loading"
        :loading-message="loadingMessage"
        :quota-info="quotaInfo"
        @need-vip="emit('need-vip')"
      />
      <SubtitlePanel
        v-if="activeTab === 'subtitle'"
        :subtitle-data="subtitleData"
        :video-title="videoTitle"
        :loading="loading"
      />
      <MindmapPanel
        v-if="activeTab === 'mindmap'"
        :mindmap-markdown="mindmapMarkdown"
        :video-title="videoTitle"
        :loading="loading"
      />
      <ChatPanel
        v-if="activeTab === 'qa'"
        :video-url="videoUrl"
        :subtitle-text="subtitleData.full_text || ''"
        @need-login="emit('need-login')"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { summarizeVideo } from '../api/summarize.js'
import SummaryPanel from './panels/SummaryPanel.vue'
import SubtitlePanel from './panels/SubtitlePanel.vue'
import MindmapPanel from './panels/MindmapPanel.vue'
import ChatPanel from './panels/ChatPanel.vue'

  const props = defineProps({
    videoUrl: { type: String, required: true },
    videoTitle: { type: String, default: '' },
    user: { type: Object, default: null },
    // 是否挂载时自动触发 AI 总结。默认 true（主输入框解析/重新总结按钮触发场景），
    // 点历史回看已解析过的视频时传 false，避免重跑流式 AI 总结（浪费每日配额 + 等待时间）。
    // 用户可手动点 VideoResult 顶部的「AI 总结」按钮触发。
    autoTrigger: { type: Boolean, default: true },
  })
  const emit = defineEmits(['loading-change', 'need-login', 'need-vip'])

  // 复用 App 提供的全局轻提示（兜底为 console，避免未注入时崩溃）
  const showToast = inject('showToast', (msg) => { console.warn('[toast]', msg) })

  const tabs = [
    { key: 'summary', label: '总结摘要', icon: '📝' },
    { key: 'subtitle', label: '字幕文本', icon: '📄' },
    { key: 'mindmap', label: '思维导图', icon: '🧠' },
    { key: 'qa', label: 'AI 问答', icon: '💬' },
  ]

  const activeTab = ref('summary')
  const loading = ref(false)
  const loadingMessage = ref('正在提取视频字幕...')

  // 当前 SSE 总结请求的 AbortController：重新触发或组件销毁时立即中断旧请求，
  // 避免旧 chunk 继续接收并污染新状态（race condition）。
  let currentController = null

  // 顶层 SSE 状态：4 个 panel 通过 props 共享，按需渲染
  const summaryText = ref('')
  const subtitleData = ref({ segments: [], has_subtitle: false, full_text: '' })
  const mindmapMarkdown = ref('')
  const quotaInfo = ref(null)

  watch(loading, (val) => {
    emit('loading-change', val)
  })

  async function startSummarize() {
    // 先中断上一次可能未完成的总结请求，避免旧 chunk 持续触发回调污染新状态
    if (currentController) currentController.abort()
    const controller = new AbortController()
    currentController = controller

    loading.value = true
    summaryText.value = ''
    mindmapMarkdown.value = ''
    quotaInfo.value = null
    loadingMessage.value = '正在提取视频字幕...'

    try {
      await summarizeVideo(props.videoUrl, 'zh', {
        subtitle: (data) => {
          try {
            subtitleData.value = JSON.parse(data)
            if (subtitleData.value.has_subtitle) {
              loadingMessage.value = 'AI 正在分析视频内容...'
            }
          } catch (e) { /* ignore parse error */ }
        },
        summary: (data) => {
          try { summaryText.value += JSON.parse(data) } catch { summaryText.value += data }
        },
        mindmap: (data) => {
          try {
            const parsed = JSON.parse(data)
            mindmapMarkdown.value = parsed.markdown || ''
          } catch (e) { /* ignore parse error */ }
        },
        quota: (data) => {
          try { quotaInfo.value = JSON.parse(data) } catch {}
        },
        done: () => {
          loading.value = false
        },
        error: (data) => {
          loading.value = false
          try {
            const parsed = JSON.parse(data)
            if (parsed.need_login) {
              emit('need-login')
              return
            }
            if (parsed.need_vip) {
              emit('need-vip')
              return
            }
            showToast(parsed.message || '总结失败', 'error')
          } catch (e) {
            showToast('总结失败: ' + data, 'error')
          }
        },
      }, props.videoTitle, '', controller.signal)
    } catch (err) {
      // 用户主动中断不视为错误（避免离开页面时弹错误 toast）
      if (err.name === 'AbortError') return
      loading.value = false
      showToast('总结请求失败: ' + err.message, 'error')
    } finally {
      if (currentController === controller) currentController = null
    }
  }

  onMounted(() => {
    // autoTrigger=false 时不自动跑总结（点历史回看已解析过的视频，避免重跑浪费配额）
    if (props.autoTrigger) startSummarize()
  })

  // 组件卸载时中断未完成的总结请求，避免回调在已销毁组件上更新状态
  onBeforeUnmount(() => {
    if (currentController) currentController.abort()
  })
</script>