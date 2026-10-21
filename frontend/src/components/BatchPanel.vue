<template>
  <section class="py-6 bg-transparent">
    <div class="max-w-3xl mx-auto px-4 sm:px-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-base font-semibold text-text-primary flex items-center gap-2">
          <svg class="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          批量解析下载
        </h3>
        <BaseButton @click="$emit('close')" variant="ghost" class="!text-xs !text-text-muted !hover:text-primary">
          返回单条模式
        </BaseButton>
      </div>

      <div
        class="rounded-2xl border border-border-light bg-bg-section p-4 transition-colors"
        :class="dragActive ? 'border-primary ring-2 ring-primary/20' : ''"
        @dragover.prevent="dragActive = true"
        @dragleave.prevent="onDragLeave"
        @drop.prevent="onDrop"
      >
        <label for="batch-urls" class="sr-only">粘贴多个视频链接</label>
        <textarea
          id="batch-urls"
          v-model="urlsText"
          rows="5"
          placeholder="每行一个视频链接，支持批量解析与下载&#10;https://www.youtube.com/watch?v=...&#10;https://www.bilibili.com/video/BV..."
          class="w-full resize-y rounded-xl border border-border bg-white px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
        ></textarea>
        <div class="flex flex-wrap items-center gap-3 mt-3">
          <BaseButton
            @click="parseAll"
            :disabled="!validUrls.length"
            :loading="parsing"
            variant="primary"
          >
            {{ parsing ? '解析中...' : '批量解析' }}（{{ validUrls.length }}）
          </BaseButton>
          <BaseButton
            v-if="doneItems.length"
            @click="downloadAll"
            :disabled="downloadingAll || !downloadableItems.length"
            variant="secondary"
          >
            <template #icon>
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </template>
            {{ downloadingAll ? '加入队列...' : '全部下载' }}（{{ downloadableItems.length }}）
          </BaseButton>
          <span class="text-xs text-text-muted">解析完成后再逐条或一键下载</span>
        </div>
      </div>

      <!-- 结果列表 -->
      <ul v-if="items.length" class="mt-4 space-y-2">
        <li
          v-for="item in items"
          :key="item.url"
          class="flex items-center gap-3 px-4 py-3 rounded-xl border border-border-light hover:border-primary/40 transition-all"
        >
          <div class="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
            :class="item.status === 'done' ? 'bg-success/10 text-success'
              : item.status === 'error' ? 'bg-red-50 text-error'
              : 'bg-gray-100 text-text-muted'">
            <Spinner v-if="item.status === 'parsing'" size="xs" />
            <svg v-else-if="item.status === 'done'" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <svg v-else-if="item.status === 'error'" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <span v-else class="text-xs font-mono">{{ statusNo(item) }}</span>
          </div>

          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-text-primary truncate">
              {{ item.data?.title || item.url }}
            </p>
            <p class="text-xs text-text-muted truncate">
              <template v-if="item.status === 'done'">{{ item.data?.platform }}</template>
              <template v-else-if="item.status === 'error'">{{ item.error }}</template>
              <template v-else-if="item.status === 'parsing'">解析中...</template>
              <template v-else>等待解析</template>
            </p>
          </div>

          <!-- 格式选择 -->
          <select
            v-if="item.status === 'done'"
            v-model="item.selectedFormat"
            :aria-label="`选择 ${item.data?.title || item.url} 的清晰度`"
            class="shrink-0 h-8 rounded-lg border border-border bg-white text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            <option v-for="f in item.data.formats" :key="f.format_id" :value="f.format_id">
              {{ f.label }}
            </option>
          </select>

          <BaseButton
            v-if="item.status === 'done'"
            @click="downloadOne(item)"
            :disabled="!canDownload(item)"
            variant="primary"
            size="sm"
            class="!shrink-0 !inline-flex !items-center !gap-1.5 !h-8 !px-3 !rounded-lg !text-xs !font-medium"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            下载
          </BaseButton>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, inject, onBeforeUnmount } from 'vue'
import { parseVideo } from '../api/video.js'
import { splitUrls } from '../utils/splitUrls.js'
import { pickBestFormat } from '../utils/format.js'
import { getApiError, extractErrorMsg } from '../utils/error.js'
import Spinner from './ui/Spinner.vue'
import BaseButton from './ui/BaseButton.vue'

const props = defineProps({
  seed: { type: String, default: '' },
})
const emit = defineEmits(['download', 'close'])
const showToast = inject('showToast', () => {})

// "批量下载" 按钮的 loading 复位 timer：保留 timerId 便于组件卸载时清理，
// 避免在 300ms 内父组件切走 → timer 触发访问已失效 ref 报错。
let downloadingAllTimer = null

// 从主页输入框拖入/粘贴的多链接，自动填入文本框
watch(
  () => props.seed,
  (v) => {
    if (v) urlsText.value = v
  }
)

const urlsText = ref(props.seed || '')
const items = ref([]) // {url, status, data, error, selectedFormat}
const parsing = ref(false)
const downloadingAll = ref(false)
const dragActive = ref(false)

const validUrls = computed(() => splitUrls(urlsText.value))
const downloadableItems = computed(() => items.value.filter((i) => canDownload(i)))
const doneItems = computed(() => items.value.filter((i) => i.status === 'done'))

function canDownload(item) {
  return item.status === 'done' && !!item.selectedFormat
}

function statusNo(item) {
  const idx = items.value.indexOf(item)
  return idx >= 0 ? idx + 1 : ''
}

function onDrop(e) {
  dragActive.value = false
  const text = e.dataTransfer?.getData('text') || e.dataTransfer?.getData('text/plain') || ''
  if (text) {
    const cur = urlsText.value.trim()
    urlsText.value = (cur ? cur + '\n' : '') + text.trim()
  }
}

// dragleave 容器外守卫：仅在 relatedTarget 真正离开当前容器时才取消高亮，
// 避免拖到子元素切换时反复闪烁（与 HeroSection 一致的实现）。
function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    dragActive.value = false
  }
}

// 默认选中"最高画质"：复用 utils/format.js 的 pickBestFormat，与 VideoResult 策略一致
function pickDefaultFormat(data) {
  const best = pickBestFormat(data.formats)
  return best ? best.format_id : ''
}

async function parseAll() {
  const urls = validUrls.value
  if (!urls.length) return
  parsing.value = true
  items.value = urls.map((url) => ({
    url,
    status: 'parsing',
    data: null,
    error: '',
    selectedFormat: '',
  }))
  // 并发限制：原 Promise.all 一次性并发 N 条请求，批量 20+ 链接时直接压垮后端 yt-dlp。
  // 改为每批 BATCH_PARSE_CONCURRENCY 个并行：保持速度的同时保护后端。
  const BATCH_PARSE_CONCURRENCY = 3
  try {
    for (let i = 0; i < items.value.length; i += BATCH_PARSE_CONCURRENCY) {
      const chunk = items.value.slice(i, i + BATCH_PARSE_CONCURRENCY)
      await Promise.all(
        chunk.map(async (item) => {
          try {
            const res = await parseVideo(item.url)
            if (res.success) {
              item.data = res.data
              item.selectedFormat = pickDefaultFormat(res.data)
              item.status = 'done'
            } else {
              item.status = 'error'
              item.error = extractErrorMsg(res.error, '解析失败')
            }
          } catch (err) {
            item.status = 'error'
            item.error = getApiError(err)
          }
        })
      )
    }
    const ok = doneItems.value.length
    const fail = items.value.length - ok
    showToast(`批量解析完成：成功 ${ok} 个，失败 ${fail} 个`, fail ? 'info' : 'success')
  } finally {
    parsing.value = false
  }
}

function downloadOne(item) {
  if (!canDownload(item)) {
    showToast('该视频暂无可下载格式', 'info')
    return
  }
  emit('download', { url: item.url, formatId: item.selectedFormat, title: item.data.title })
}

function downloadAll() {
  const list = downloadableItems.value
  if (!list.length) {
    showToast('暂无可下载格式', 'info')
    return
  }
  // 逐条交给任务中心（任务中心自行控制并发）。入队为同步操作，瞬时完成，
  // 仅短暂置 loading 给出视觉反馈，避免按钮文案在点击瞬间无变化。
  downloadingAll.value = true
  list.forEach(downloadOne)
  showToast('已加入下载队列', 'success')
  clearTimeout(downloadingAllTimer)
  downloadingAllTimer = setTimeout(() => { downloadingAll.value = false }, 300)
}

// 卸载时清理未触发的 timer，避免组件已销毁 timer 才触发 ref 操作报错
onBeforeUnmount(() => {
  clearTimeout(downloadingAllTimer)
})
</script>
