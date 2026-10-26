<template>
  <!-- 浮动入口按钮 -->
  <BaseButton
    @click="togglePanel"
    variant="primary"
    class="!fixed !bottom-6 !right-6 !z-[150] !flex !items-center !gap-2 !h-12 !pl-4 !pr-5 !rounded-full !shadow-xl !shadow-primary/25"
    title="下载任务中心"
  >
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
    <span class="text-sm font-medium">下载任务</span>
    <span
      v-if="activeCount > 0"
      class="min-w-5 h-5 px-1 rounded-full bg-white/25 text-xs font-semibold flex items-center justify-center"
    >{{ activeCount }}</span>
  </BaseButton>

  <!-- 抽屉面板 -->
  <Teleport to="body">
    <transition name="task-slide">
      <div
        v-if="state.panelOpen"
        role="dialog"
        aria-modal="true"
        aria-labelledby="download-task-title"
        class="fixed bottom-0 right-0 z-[160] w-full sm:w-[400px] max-h-[80vh] bg-white/95 rounded-t-2xl sm:rounded-2xl shadow-2xl shadow-slate-900/15 border border-white/80 backdrop-blur flex flex-col"
        @keydown.esc.window="closePanel"
      >
        <!-- 头部 -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-light">
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            <h3 id="download-task-title" class="text-base font-semibold text-text-primary">下载任务中心</h3>
          </div>
          <div class="flex items-center gap-2">
            <BaseButton
              v-if="finishedCount > 0"
              @click="onClearFinished"
              variant="ghost"
              class="!text-xs !text-text-muted !hover:text-primary"
            >清除已完成</BaseButton>
            <BaseButton
              @click="closePanel"
              variant="ghost"
              class="!p-1 !text-text-muted !hover:text-text-primary"
              title="收起"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </BaseButton>
          </div>
        </div>

        <!-- 列表 -->
        <div class="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          <EmptyState
            v-if="state.tasks.length === 0"
            size="md"
            variant="empty"
            title="暂无下载任务"
            desc="去解析视频后点击下载即可加入队列"
          />

          <div
            v-for="t in state.tasks"
            :key="t.id"
            class="rounded-xl border border-border-light p-3"
          >
            <div class="flex items-start justify-between gap-2 mb-2">
              <p class="text-sm font-medium text-text-primary truncate flex-1" :title="t.title">
                {{ t.title }}
              </p>
              <span
                :class="[
                  'shrink-0 text-xs px-2 py-0.5 rounded-full font-medium',
                  statusClass(t.status)
                ]"
              >{{ statusLabel(t.status) }}</span>
            </div>

            <!-- 进度条 -->
            <div v-if="t.status === 'downloading' || t.status === 'queued' || t.status === 'done'" class="mb-2">
              <div class="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  class="h-full transition-all duration-200"
                  :class="t.status === 'done' ? 'bg-success' : 'bg-primary'"
                  :style="{ width: t.progress + '%' }"
                ></div>
              </div>
              <div class="flex justify-between mt-1 text-xs text-text-muted">
                <span>{{ t.status === 'queued' ? '排队中...' : (t.progress + '%') }}</span>
                <span v-if="t.total">{{ formatBytes(t.received) }} / {{ formatBytes(t.total) }}</span>
              </div>
            </div>

            <p v-if="t.status === 'error'" class="text-xs text-error mb-2 truncate" :title="t.error">
              {{ t.error }}
            </p>

            <!-- 操作 -->
            <div class="flex items-center gap-2">
              <BaseButton
                v-if="t.status === 'downloading' || t.status === 'queued'"
                @click="cancel(t.id)"
                variant="outline"
                class="!flex-1 !h-8 !rounded-lg !text-xs !font-medium !text-text-secondary !hover:border-error !hover:text-error !border-border-light"
              >取消</BaseButton>
              <BaseButton
                v-if="t.status === 'error' || t.status === 'canceled'"
                @click="retry(t.id)"
                variant="outline"
                class="!flex-1 !h-8 !rounded-lg !text-xs !font-medium !text-text-secondary !hover:border-primary !hover:text-primary !border-border-light"
              >重试</BaseButton>
              <BaseButton
                v-if="t.status === 'done'"
                @click="remove(t.id)"
                variant="outline"
                class="!flex-1 !h-8 !rounded-lg !text-xs !font-medium !text-text-secondary !hover:text-text-primary !border-border-light"
              >移除</BaseButton>
              <BaseButton
                v-if="t.status === 'error' || t.status === 'canceled'"
                @click="remove(t.id)"
                variant="ghost"
                class="!w-8 !h-8 !rounded-lg !flex !items-center !justify-center !text-text-muted !hover:text-error"
                title="删除"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </BaseButton>
            </div>
          </div>
        </div>

        <p class="px-5 py-2 text-xs text-text-muted border-t border-border-light flex items-center gap-1">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          并发下载上限 {{ maxConcurrency }} 个，可随时取消或重试
        </p>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, computed, inject, onMounted } from 'vue'
import { useDownloadManager } from '../composables/useDownloadManager.js'
import { formatBytes } from '../utils/format.js'
import EmptyState from './ui/EmptyState.vue'
import BaseButton from './ui/BaseButton.vue'

const { state, cancel, retry, remove, clearFinished, closePanel, togglePanel, MAX_CONCURRENCY } =
  useDownloadManager()

// 注入放最前面（修复：原 showToast 在 watch 之后才声明，但 onClearFinished 已在上方引用，定义顺序倒置阅读性差）
const showToast = inject('showToast', () => {})
const maxConcurrency = MAX_CONCURRENCY

// 清除已完成任务后给 toast 反馈（与 HistoryDrawer / App.vue 删除/清空风格一致），
// 同时把对应 id 从 notified 集合移除，否则 next tick 状态变化可能因 id 已通知而跳过本次成功提示。
function onClearFinished() {
  const clearedIds = state.tasks
    .filter((t) => t.status === 'done' || t.status === 'canceled')
    .map((t) => t.id)
  clearFinished()
  clearedIds.forEach((id) => notified.value.delete(id))
  if (clearedIds.length > 0) {
    showToast(`已清除 ${clearedIds.length} 条已完成任务`, 'success')
  }
}

const activeCount = computed(
  () =>
    state.tasks.filter((t) => t.status === 'downloading' || t.status === 'queued')
      .length
)
// "清除已完成"只移除 done / canceled，故计数也只统计这两项；
// 失败(error)任务需保留以便重试，不应计入"已完成"，否则按钮在仅有失败任务时
// 仍显示却点了无反应。
const finishedCount = computed(
  () => state.tasks.filter((t) => t.status === 'done' || t.status === 'canceled').length
)

const notified = ref(new Set())

function statusLabel(s) {
  return (
    {
      queued: '排队中',
      downloading: '下载中',
      done: '已完成',
      error: '失败',
      canceled: '已取消',
    }[s] || s
  )
}
function statusClass(s) {
  return (
    {
      queued: 'bg-gray-100 text-text-secondary',
      downloading: 'bg-primary-light text-primary',
      done: 'bg-green-50 text-success',
      error: 'bg-red-50 text-error',
      canceled: 'bg-gray-100 text-text-muted',
    }[s] || 'bg-gray-100 text-text-muted'
  )
}
// 任务状态变更时给出轻提示（完成/失败各提示一次）。
// 关键：监听带 prev 比对，状态变化（重试 / 重新入队 / 取消重做）时主动清理该 id 的 notified 标记，
// 否则重试后的 done/error 会因 id 已在 notified 集合中被跳过，导致失败/成功无提示。
watch(
  () => state.tasks.map((t) => ({ id: t.id, status: t.status })),
  (now, prev) => {
    const prevById = new Map((prev || []).map((t) => [t.id, t.status]))
    now.forEach((t) => {
      const prevStatus = prevById.get(t.id)
      if (prevStatus !== undefined && prevStatus !== t.status) {
        notified.value.delete(t.id)
      }
    })
    now.forEach((t) => {
      if (notified.value.has(t.id)) return
      if (t.status === 'done') {
        notified.value.add(t.id)
        showToast('下载完成，请到下载目录查看', 'success')
      } else if (t.status === 'error') {
        notified.value.add(t.id)
        const task = state.tasks.find((x) => x.id === t.id)
        showToast('下载失败：' + (task?.error || '请稍后重试'), 'error')
      }
    })
  }
)

onMounted(() => {
  // 预标记已存在任务，避免刷新后对已持久化任务重复提示
  state.tasks.forEach((t) => notified.value.add(t.id))
})
</script>

<style scoped>
.task-slide-enter-active,
.task-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.task-slide-enter-from,
.task-slide-leave-to {
  transform: translateY(20px);
  opacity: 0;
}
</style>
