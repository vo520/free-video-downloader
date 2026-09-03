<template>
  <div class="subtitle-panel">
    <div v-if="subtitleData.segments && subtitleData.segments.length > 0">
      <div class="flex items-center justify-between mb-4">
        <div class="text-sm text-text-secondary">
          共 {{ subtitleData.segments.length }} 条字幕
          <span
            v-if="subtitleData.language"
            class="ml-2 px-2 py-0.5 bg-primary-light text-primary rounded-full text-xs"
          >
            {{ subtitleData.subtitle_type === 'manual' ? '人工字幕' : '自动字幕' }} · {{ subtitleData.language }}
          </span>
        </div>
        <div class="flex items-center gap-3">
          <!-- 下载字幕按钮 -->
          <div class="relative" ref="subtitleDropdownRef">
            <BaseButton
              @click="showSubtitleDropdown = !showSubtitleDropdown"
              variant="ghost"
              aria-haspopup="menu"
              aria-controls="subtitle-format-menu"
              :aria-expanded="showSubtitleDropdown"
              class="!flex !items-center !gap-1.5 !text-xs !text-primary !hover:text-primary-dark !px-2.5 !py-1.5 !rounded-lg !hover:bg-primary-light"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              下载字幕
              <svg
                class="w-3 h-3 transition-transform"
                :class="showSubtitleDropdown ? 'rotate-180' : ''"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </BaseButton>
            <div
              v-if="showSubtitleDropdown"
              id="subtitle-format-menu"
              role="menu"
              class="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-border-light py-1 z-10 min-w-[120px]"
            >
              <button
                v-for="fmt in subtitleFormats"
                :key="fmt.key"
                @click="downloadSubtitle(fmt.key)"
                type="button"
                role="menuitem"
                class="w-full text-left px-3 py-2 text-xs text-text-primary hover:bg-bg-section flex items-center justify-between"
              >
                <span>{{ fmt.label }}</span>
                <span class="text-text-muted">.{{ fmt.ext }}</span>
              </button>
            </div>
          </div>
          <BaseButton
            @click="subtitleExpanded = !subtitleExpanded"
            variant="ghost"
            class="!text-xs !text-primary !hover:text-primary-dark"
          >
            {{ subtitleExpanded ? '收起' : '展开全部' }}
          </BaseButton>
        </div>
      </div>
      <div
        :class="['space-y-1 overflow-y-auto', subtitleExpanded ? 'max-h-none' : 'max-h-[500px]']"
      >
        <div
          v-for="(seg, idx) in subtitleData.segments"
          :key="idx"
          class="flex gap-3 py-2 px-3 rounded-lg hover:bg-bg-section transition-colors group"
        >
          <span class="flex-shrink-0 text-xs text-primary font-mono pt-0.5 min-w-[60px]">
            {{ formatTime(seg.start) }}
          </span>
          <span class="text-sm text-text-primary leading-relaxed">{{ seg.text }}</span>
        </div>
      </div>
    </div>
    <EmptyState v-else-if="!loading" size="md" variant="info">
      <template #icon>
        <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      </template>
      <template #default>该视频暂无可用字幕</template>
    </EmptyState>
    <div v-else class="flex flex-col items-center justify-center py-16">
      <Spinner variant="ring" size="lg" class="mb-3" />
      <p class="text-text-muted text-sm">正在提取字幕...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import Spinner from '../ui/Spinner.vue'
import EmptyState from '../ui/EmptyState.vue'
import BaseButton from '../ui/BaseButton.vue'
import { sanitizeFilename, downloadBlob } from '../../utils/file.js'
import { formatTime } from '../../utils/format.js'

  const props = defineProps({
    subtitleData: { type: Object, required: true },
    videoTitle: { type: String, default: '' },
    loading: { type: Boolean, default: false },
  })

  const subtitleExpanded = ref(false)
  const showSubtitleDropdown = ref(false)
  const subtitleDropdownRef = ref(null)
  const subtitleFormats = [
    { key: 'srt', label: 'SRT 字幕', ext: 'srt' },
    { key: 'vtt', label: 'VTT 字幕', ext: 'vtt' },
    { key: 'txt', label: '纯文本', ext: 'txt' },
  ]

  // 字幕时间格式化：SRT 用 ',' 分隔毫秒，VTT 用 '.' 分隔毫秒（其余格式相同），合并两处重复实现。
  function formatSubtitleTime(seconds, sep = ',') {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    const ms = Math.round((seconds % 1) * 1000)
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}${sep}${String(ms).padStart(3, '0')}`
  }

  function segmentsToSrt(segments) {
    return segments.map((seg, i) => {
      const start = formatSubtitleTime(seg.start, ',')
      const end = formatSubtitleTime(seg.end, ',')
      return `${i + 1}\n${start} --> ${end}\n${seg.text}\n`
    }).join('\n')
  }

  function segmentsToVtt(segments) {
    const header = 'WEBVTT\n\n'
    const body = segments.map((seg) => {
      const start = formatSubtitleTime(seg.start, '.')
      const end = formatSubtitleTime(seg.end, '.')
      return `${start} --> ${end}\n${seg.text}\n`
    }).join('\n')
    return header + body
  }

  function segmentsToTxt(segments) {
    return segments.map((seg) => seg.text).join('\n')
  }

  function downloadSubtitle(format) {
    showSubtitleDropdown.value = false
    const segments = props.subtitleData.segments
    if (!segments || segments.length === 0) return

    let content = ''
    let ext = format
    const filename = sanitizeFilename(props.videoTitle)

    if (format === 'srt') content = segmentsToSrt(segments)
    else if (format === 'vtt') content = segmentsToVtt(segments)
    else content = segmentsToTxt(segments)

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    downloadBlob(blob, `${filename} - 字幕.${ext}`)
  }

  function handleClickOutside(e) {
    if (subtitleDropdownRef.value && !subtitleDropdownRef.value.contains(e.target)) {
      showSubtitleDropdown.value = false
    }
  }
  // Esc 键关闭下拉菜单（与 AppHeader / ChatPanel 风格一致）
  function handleKeydown(e) {
    if (e.key === 'Escape' && showSubtitleDropdown.value) {
      showSubtitleDropdown.value = false
    }
  }

  onMounted(() => {
    document.addEventListener('click', handleClickOutside)
    document.addEventListener('keydown', handleKeydown)
  })
  onBeforeUnmount(() => {
    document.removeEventListener('click', handleClickOutside)
    document.removeEventListener('keydown', handleKeydown)
  })
</script>