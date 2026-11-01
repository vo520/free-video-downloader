<template>
  <div class="bg-white/90 rounded-2xl border border-border shadow-lg overflow-hidden h-full flex flex-col">
    <!-- 标签页导航 -->
    <div class="flex border-b border-border-light/80 bg-surface-muted/50 overflow-x-auto">
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
    <!-- :key 绑定 activeTab：切换 tab 时重建内容容器，滚动位置回到顶部。
         不加 key 时会沿用上一个 tab 的滚动位置，切到短内容 tab 时一片空白。 -->
    <div :key="activeTab" class="p-5 sm:p-6 min-h-[400px] flex-1 overflow-y-auto">
      <!-- 配额闸门：免费用户点「生成 AI 总结」前先确认，避免自动触发静默扣减当日次数。
           只挡「总结摘要」tab —— AI 问答是用户主动提问，不属于自动消耗。 -->
      <div v-if="activeTab === 'summary' && quotaGate" class="flex flex-col items-center justify-center text-center py-10">
        <div class="w-14 h-14 rounded-2xl bg-primary-light/80 text-primary flex items-center justify-center mb-4">
          <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a1 1 0 11-2 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <h3 class="text-base font-semibold text-text-primary">AI 视频总结</h3>
        <template v-if="quotaGate.status === 'ready'">
          <p class="mt-2 text-sm text-text-secondary">
            今日剩余 <strong class="text-primary">{{ quotaGate.remaining }}</strong> / {{ quotaGate.limit }} 次免费总结
          </p>
          <p class="mt-1 text-xs text-text-muted">生成总结会消耗 1 次当日额度，确认后开始</p>
          <div class="mt-5 flex items-center gap-2">
            <BaseButton variant="primary" @click="startSummarize">生成 AI 总结</BaseButton>
            <BaseButton v-if="quotaGate.remaining <= 1" variant="ghost" class="text-primary! hover:underline!" @click="emit('need-vip')">
              升级 VIP 无限使用
            </BaseButton>
          </div>
        </template>
        <template v-else-if="quotaGate.status === 'exhausted'">
          <p class="mt-2 text-sm text-text-secondary">
            今日免费总结次数已用完（每日 {{ quotaGate.limit }} 次）
          </p>
          <p class="mt-1 text-xs text-text-muted">开通 VIP 后可无限次生成总结</p>
          <div class="mt-5">
            <BaseButton variant="primary" @click="emit('need-vip')">开通 VIP 无限使用</BaseButton>
          </div>
        </template>
        <template v-else-if="quotaGate.status === 'login'">
          <p class="mt-2 text-sm text-text-secondary">登录后即可生成 AI 总结</p>
          <div class="mt-5">
            <BaseButton variant="primary" @click="emit('need-login')">立即登录</BaseButton>
          </div>
        </template>
        <template v-else>
          <p class="mt-2 text-sm text-text-secondary">获取剩余次数失败，请稍后重试</p>
          <div class="mt-5">
            <BaseButton variant="primary" @click="loadQuota">重新检测</BaseButton>
          </div>
        </template>
      </div>
      <SummaryPanel
        v-else-if="activeTab === 'summary'"
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
import { summarizeVideo, fetchSummaryQuota } from '../api/summarize.js'
import SummaryPanel from './panels/SummaryPanel.vue'
import SubtitlePanel from './panels/SubtitlePanel.vue'
import MindmapPanel from './panels/MindmapPanel.vue'
import ChatPanel from './panels/ChatPanel.vue'
import BaseButton from './ui/BaseButton.vue'

  const props = defineProps({
    videoUrl: { type: String, required: true },
    videoTitle: { type: String, default: '' },
    user: { type: Object, default: null },
    // 是否挂载时自动触发 AI 总结。默认 true（主输入框解析/重新总结按钮触发场景），
    // 点历史回看已解析过的视频时传 false，避免重跑流式 AI 总结（浪费每日配额 + 等待时间）。
    // 用户可手动点 VideoResult 顶部的「AI 总结」按钮触发。
    autoTrigger: { type: Boolean, default: true },
    // 是否由用户主动点击「AI 总结」按钮触发（而非解析成功后自动触发）。
    // 主动点击 = 用户已明确表达意图，直接开始，不再走配额确认闸门；
    // 自动触发则必须先确认，否则免费用户的每日次数会被静默扣掉。
    manualTrigger: { type: Boolean, default: false },
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

  // 配额闸门：非 null 时接管「总结摘要」tab 的展示，替代直接发起总结。
  // 背景：解析成功后自动触发总结会直接 POST /api/summarize，
  // 免费用户当天 3 次额度会被静默扣掉一次，用户完全不知情。
  // 现在改为：VIP 照旧自动生成；免费用户先看到「今日剩余 N 次」，点击才消耗。
  // status: ready(可生成) | exhausted(额度用尽) | login(未登录) | error(检测失败)
  const quotaGate = ref(null)

  // 当前 SSE 总结请求的 AbortController：重新触发或组件销毁时立即中断旧请求，
  // 避免旧 chunk 继续接收并污染新状态（race condition）。
  let currentController = null

  // 卸载标记：onMounted 里 loadQuota() 是异步的，用户在配额请求返回前换视频/回看历史时
  // 组件已销毁，await 之后仍会继续 startSummarize()（在死实例上跑 SSE、白扣免费额度）。
  // 所有「await 之后还要继续干活」的路径都必须先检查该标记。
  let unmounted = false

  // 顶层 SSE 状态：4 个 panel 通过 props 共享，按需渲染
  const summaryText = ref('')
  const subtitleData = ref({ segments: [], has_subtitle: false, full_text: '' })
  const mindmapMarkdown = ref('')
  const quotaInfo = ref(null)

  watch(loading, (val) => {
    emit('loading-change', val)
  })

  /**
   * 查询当前用户的 AI 总结配额，决定是否直接生成还是先让用户确认。
   *
   * VIP：无限额度，直接生成（保留原有「解析完自动出总结」的体验）。
   * 免费用户：剩余次数 > 0 时展示「今日剩余 N 次」CTA，用户点击才消耗额度；
   *           额度用尽时引导开通 VIP。
   * 未登录 / 查询失败：分别提示登录与重试，绝不在未知状态下自动消耗额度。
   */
  async function loadQuota() {
    try {
      const data = await fetchSummaryQuota()
      // 配额请求返回前组件已卸载：不再下发任何状态、更不能触发 startSummarize
      if (unmounted) return
      if (!data) {
        quotaGate.value = { status: 'error' }
        return
      }
      if (!data.logged_in) {
        quotaGate.value = { status: 'login' }
        return
      }
      if (data.is_vip) {
        quotaGate.value = null
        startSummarize()
        return
      }
      quotaGate.value = {
        status: data.allowed ? 'ready' : 'exhausted',
        remaining: data.remaining,
        limit: data.limit,
      }
    } catch (err) {
      quotaGate.value = { status: 'error' }
    }
  }

  async function startSummarize() {
    // 实例已销毁（典型：配额查询期间切走视频）：绝不再发起新的 SSE 请求
    if (unmounted) return
    // 用户已确认（或 VIP 自动触发），闸门让位给真实内容
    quotaGate.value = null
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
      // SSE 流被代理截断时可能收不到 done/error 事件，此时 await 已正常返回，
      // 若不复位 loading 会永久转圈（App 的 summarizing 也会一直为 true，
      // 导致「AI 总结」按钮永久 loading 不可点）。这里兜底复位。
      if (loading.value) loading.value = false
      if (currentController === controller) currentController = null
    }
  }

  onMounted(() => {
    // autoTrigger=false 时不自动跑总结（点历史回看已解析过的视频，避免重跑浪费配额）
    if (!props.autoTrigger) return
    // 用户主动点「AI 总结」：意图明确，直接开始，不占用配额确认闸门
    if (props.manualTrigger) {
      startSummarize()
      return
    }
    // 自动触发：先查配额。VIP 直接生成；免费用户先看到「今日剩余 N 次」再决定
    loadQuota()
  })

  // 组件卸载时中断未完成的总结请求，避免回调在已销毁组件上更新状态
  onBeforeUnmount(() => {
    unmounted = true
    if (currentController) currentController.abort()
    // 卸载时若仍在 loading，必须主动通知宿主复位，否则 App 的 summarizing 会永久为 true，
    // 「AI 总结」按钮带着 loading 状态永久禁用（BaseButton 会用 loading 直接禁用点击）。
    // 注意：不能依赖上面的 watch(loading)——组件销毁时它的调度任务会被一并停掉，
    // flush 回调不保证执行，所以这里直接 emit。
    if (loading.value) {
      loading.value = false
      emit('loading-change', false)
    }
  })
</script>