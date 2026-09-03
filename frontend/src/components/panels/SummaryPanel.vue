<template>
  <div class="summary-panel">
    <!-- 加载状态：SSE 还没产出第一段 summary 时显示 -->
    <div
      v-if="loading && !summaryText"
      class="flex flex-col items-center justify-center py-16"
    >
      <Spinner variant="ring" size="xl" class="mb-4" />
      <p class="text-text-secondary text-sm">{{ loadingMessage }}</p>
    </div>

    <!-- 总结摘要 -->
    <div
      v-if="summaryText"
      class="prose prose-slate prose-sm max-w-none summary-prose"
      v-html="renderedSummary"
    ></div>
    <div
      v-if="loading && summaryText"
      class="mt-2 inline-flex items-center gap-1.5 text-xs text-text-muted"
    >
      <span class="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></span>
      AI 正在生成中...
    </div>

    <!-- 免费用户剩余次数提示 -->
    <div
      v-if="quotaInfo && quotaInfo.remaining >= 0 && !loading"
      class="mt-4 p-3 rounded-xl bg-primary-light border border-primary/20 flex items-center justify-between"
    >
      <span class="text-sm text-primary">
        今日剩余 AI 总结次数：<strong>{{ quotaInfo.remaining }}</strong> / {{ quotaInfo.limit }}
      </span>
      <BaseButton
        v-if="quotaInfo.remaining <= 1"
        @click="emit('need-vip')"
        variant="ghost"
        class="!text-xs !font-medium !text-primary !hover:underline"
      >
        升级 VIP 无限使用
      </BaseButton>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { renderMarkdown } from '../../utils/markdown.js'
import Spinner from '../ui/Spinner.vue'
import BaseButton from '../ui/BaseButton.vue'

  const props = defineProps({
    summaryText: { type: String, default: '' },
    loading: { type: Boolean, default: false },
    loadingMessage: { type: String, default: '' },
    quotaInfo: { type: Object, default: null },
  })
  const emit = defineEmits(['need-vip'])

  // 流式 Markdown 渲染节流：SSE 每个 chunk 追加 summaryText，原实现 computed 直接重算
  // 整个 markdown→HTML→DOMPurify，长视频 100+ chunk 累计开销 ~3s。改为 150ms 合并渲染，
  // 既保留流式可见性（首屏立即渲染，后续节流），又大幅降低重渲染开销。
  const renderedSummary = ref('')
  let renderTimer = null
  let pendingText = ''
  let lastText = ''

  watch(
    () => props.summaryText,
    (text) => {
      pendingText = text
      if (renderTimer) return
      renderTimer = setTimeout(() => {
        renderTimer = null
        if (pendingText === lastText) return
        lastText = pendingText
        renderedSummary.value = renderMarkdown(pendingText)
      }, 150)
    },
    { immediate: true }
  )

  // 组件卸载时清理 pending 的节流 timer，避免已销毁组件仍触发 renderMarkdown + ref 写入。
  onBeforeUnmount(() => {
    if (renderTimer) {
      clearTimeout(renderTimer)
      renderTimer = null
    }
  })
</script>

<style scoped>
  /* 总结摘要 Markdown 排版定制（从 VideoSummary.vue 迁出）*/
  .summary-prose :deep(h1) {
    font-size: 1.25rem;
    font-weight: 700;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    color: var(--color-text-primary);
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--color-primary-light);
  }
  .summary-prose :deep(h2) {
    font-size: 1.125rem;
    font-weight: 700;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    color: var(--color-text-primary);
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--color-border-light);
  }
  .summary-prose :deep(h3) {
    font-size: 1rem;
    font-weight: 600;
    margin-top: 1.25rem;
    margin-bottom: 0.5rem;
    color: var(--color-text-primary);
  }
  .summary-prose :deep(p) {
    margin-bottom: 0.75rem;
    line-height: 1.8;
    color: var(--color-text-primary);
  }
  .summary-prose :deep(ul),
  .summary-prose :deep(ol) {
    margin-bottom: 0.75rem;
    padding-left: 1.5rem;
  }
  .summary-prose :deep(li) {
    margin-bottom: 0.35rem;
    line-height: 1.8;
  }
  .summary-prose :deep(li::marker) {
    color: var(--color-primary);
  }
  .summary-prose :deep(strong) {
    color: var(--color-text-primary);
    font-weight: 600;
  }
  .summary-prose :deep(hr) {
    margin: 1.5rem 0;
    border-color: var(--color-border-light);
  }
  .summary-prose :deep(blockquote) {
    border-left: 3px solid var(--color-primary);
    padding: 0.75rem 1rem;
    color: var(--color-text-secondary);
    font-style: normal;
    margin: 1rem 0;
    background: var(--color-bg-section);
    border-radius: 0 8px 8px 0;
  }
  .summary-prose :deep(code) {
    background: var(--color-bg-section);
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    font-size: 0.85em;
    color: var(--color-primary-dark);
    font-weight: 500;
  }
  .summary-prose :deep(pre) {
    background: #1e293b;
    color: #e2e8f0;
    border-radius: 8px;
    padding: 1rem;
    overflow-x: auto;
    margin: 1rem 0;
  }
  .summary-prose :deep(pre code) {
    background: none;
    padding: 0;
    color: inherit;
    font-weight: normal;
  }
  .summary-prose :deep(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 0.875rem;
  }
  .summary-prose :deep(th) {
    background: var(--color-bg-section);
    padding: 0.5rem 0.75rem;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid var(--color-border);
  }
  .summary-prose :deep(td) {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--color-border-light);
  }
  .summary-prose :deep(a) {
    color: var(--color-primary);
    text-decoration: none;
  }
  .summary-prose :deep(a:hover) {
    text-decoration: underline;
  }
</style>