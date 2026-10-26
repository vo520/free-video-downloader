<template>
  <div class="bg-white/85 rounded-[1.5rem] border border-white/80 shadow-2xl shadow-slate-900/10 overflow-hidden h-full backdrop-blur">
    <!-- 视频信息头部 -->
    <div class="flex flex-col gap-5 p-5 sm:p-6">
      <div class="relative w-full aspect-video rounded-[1.25rem] overflow-hidden bg-slate-100 shadow-inner ring-1 ring-black/5">
        <!-- 内联预览播放器 -->
        <video
          v-if="showPreview && previewUrl"
          :ref="onVideoEl"
          :src="previewUrl"
          controls
          autoplay
          playsinline
          class="w-full h-full object-contain bg-black"
        ></video>
        <!-- 播放器增强：倍速 + 画中画（复用原生 video 能力，零新增依赖） -->
        <div
          v-if="showPreview"
          class="absolute top-2 right-2 flex items-center gap-1 px-1.5 py-1 rounded-full bg-black/60 backdrop-blur text-white text-xs"
        >
          <button
            v-for="r in [0.5, 1, 1.5, 2]"
            :key="r"
            @click="setRate(r)"
            :class="[
              'px-1.5 py-0.5 rounded-full transition-colors cursor-pointer',
              currentRate === r ? 'bg-white text-black' : 'hover:bg-white/20'
            ]"
          >{{ r }}x</button>
          <span class="w-px h-3 bg-white/30"></span>
          <button
            @click="togglePip"
            :class="[
              'px-1.5 py-0.5 rounded-full transition-colors cursor-pointer',
              pipActive ? 'bg-white text-black' : 'hover:bg-white/20'
            ]"
            :title="pipActive ? '退出画中画' : '画中画'"
            :aria-pressed="pipActive"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 7h6a2 2 0 012 2v6m4-8a2 2 0 012 2v8a2 2 0 01-2 2H8a2 2 0 01-2-2v-4m-4-8h10a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />
            </svg>
          </button>
        </div>
        <template v-else>
          <!-- 封面：统一复用 VideoThumbnail（无图/加载失败时降级为占位图标，替代原 DOM hack） -->
          <VideoThumbnail :url="thumbnailUrl" :alt="video.title" size="lg" />
          <!-- 预览按钮 -->
          <button
            v-if="previewUrl || videoUrl"
            @click="openPreview"
            :disabled="previewLoading"
            class="absolute inset-0 flex items-center justify-center bg-black/20 hover:bg-black/35 transition-colors group disabled:cursor-wait"
            title="预览播放"
          >
            <span class="w-16 h-16 rounded-full bg-white/95 flex items-center justify-center shadow-2xl shadow-black/20 ring-1 ring-white/70 group-hover:scale-105 transition-transform">
              <Spinner v-if="previewLoading" size="md" class="text-primary" />
              <svg v-else class="w-6 h-6 text-primary ml-1" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </span>
          </button>
        </template>
        <div v-if="video.duration_string && !showPreview" class="absolute bottom-2 right-2 px-2 py-0.5 bg-black/70 text-white text-xs rounded-md">
          {{ video.duration_string }}
        </div>
        <!-- 返回封面 -->
        <button
          v-if="showPreview"
          @click="showPreview = false"
          class="absolute top-2 left-2 px-2 py-1 bg-black/60 text-white text-xs rounded hover:bg-black/80 transition-colors"
        >
          返回封面
        </button>
      </div>

      <div class="flex-1 min-w-0">
        <div class="flex items-start gap-2 mb-2">
          <h3 class="text-lg font-semibold text-text-primary leading-snug line-clamp-2 flex-1">{{ video.title }}</h3>
          <BaseButton
            @click="copyLink"
            variant="ghost"
            class="!shrink-0 !mt-0.5 !p-1.5 !rounded-lg !text-text-muted !hover:text-primary !hover:bg-primary-light"
            title="复制视频链接"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </BaseButton>
        </div>
        <div class="flex flex-wrap items-center gap-3 text-sm text-text-secondary mb-3">
          <span class="inline-flex items-center gap-1">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            {{ video.uploader }}
          </span>
          <span class="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-light text-primary rounded-full text-xs font-medium">
            {{ video.platform }}
          </span>
          <span v-if="video.view_count" class="inline-flex items-center gap-1">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            {{ formatViewCount(video.view_count) }}
          </span>
        </div>
        <p v-if="video.description" class="text-sm text-text-muted line-clamp-2">
          {{ video.description }}
        </p>
      </div>
    </div>

    <!-- 格式选择 -->
    <div class="border-t border-border-light/80 bg-slate-50/45 px-5 sm:px-6 py-5">
      <h4 class="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
        <svg class="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
        </svg>
        选择清晰度和格式
      </h4>

      <!-- 快捷预设 -->
      <div class="flex flex-wrap gap-2 mb-4">
        <button
          v-for="p in presets"
          :key="p.type"
          @click="applyPreset(p.type)"
          :class="[
            'px-3 py-1.5 rounded-full text-xs font-medium border transition-all',
            activePreset === p.type
              ? 'border-primary bg-primary-light text-primary'
              : 'border-border-light text-text-secondary hover:border-primary/40 hover:bg-gray-50'
          ]"
        >
          {{ p.label }}
        </button>
      </div>

      <div class="grid grid-cols-1 gap-2.5">
        <button
          v-for="fmt in video.formats"
          :key="fmt.format_id"
          @click="selectedFormat = fmt.format_id; activePreset = ''"
          :class="[
            'flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all cursor-pointer',
            selectedFormat === fmt.format_id
              ? 'border-primary bg-primary-light ring-1 ring-primary/20'
              : 'border-border-light hover:border-primary/40 hover:bg-gray-50'
          ]"
        >
          <div class="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
            :class="selectedFormat === fmt.format_id ? 'bg-primary text-white' : 'bg-gray-100 text-text-muted'">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
            </svg>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium text-text-primary truncate">{{ fmt.label }}</span>
              <span v-if="formatResolution(fmt)" class="shrink-0 px-1.5 py-0.5 rounded bg-gray-100 text-text-muted text-[10px] font-medium">{{ formatResolution(fmt) }}</span>
              <span v-if="fmt.format_id === recommendedId" class="shrink-0 px-1.5 py-0.5 rounded bg-primary-light text-primary text-[10px] font-medium">推荐</span>
            </div>
            <div class="text-xs text-text-muted">{{ fmt.ext.toUpperCase() }} {{ fmt.has_audio ? '· 含音频' : '· 仅视频' }}</div>
          </div>
        </button>
      </div>

      <!-- 下载按钮 -->
      <div class="mt-6 flex flex-col items-stretch gap-3">
        <BaseButton
          @click="emit('download', selectedFormat)"
          :disabled="!selectedFormat"
          :loading="downloading"
          variant="primary"
          size="lg"
          block
        >
          <template #icon>
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </template>
          {{ downloading ? '下载中，请稍候...' : '立即下载' }}
        </BaseButton>
        <!-- AI 总结按钮（重新总结） -->
        <BaseButton
          @click="emit('summarize')"
          :loading="summarizing"
          variant="secondary"
          size="lg"
          block
        >
          <template #icon>
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </template>
          {{ summarizing ? '总结中...' : 'AI 总结' }}
        </BaseButton>
      <div v-if="downloadProgress > 0" class="mt-3">
        <div class="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div class="h-full bg-primary transition-all duration-200" :style="{ width: downloadProgress + '%' }"></div>
        </div>
        <div class="text-xs text-text-muted text-center mt-1">{{ downloadProgress }}%</div>
      </div>
      <!-- 下载失败提示：与任务中心同源（downloadManager 最新任务 error 态），样式对齐 App.vue 全局 toast 的错误配色 -->
      <div v-if="downloadError" class="mt-3 flex items-start gap-2 px-4 py-3 rounded-xl border border-red-200 bg-red-50 text-red-800">
        <svg class="w-4 h-4 shrink-0 mt-0.5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
        <span class="text-xs font-medium leading-relaxed">{{ downloadError }}</span>
      </div>
        <span v-if="selectedFormat" class="text-xs text-text-muted text-center">
          已选择: {{ selectedLabel }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, onBeforeUnmount } from 'vue'
import { getDirectUrl } from '../api/video.js'
import { copyText } from '../utils/clipboard.js'
import { pickBestFormat, formatResolution, formatViewCount } from '../utils/format.js'
import Spinner from './ui/Spinner.vue'
import BaseButton from './ui/BaseButton.vue'
import VideoThumbnail from './VideoThumbnail.vue'

const props = defineProps({
  video: { type: Object, required: true },
  downloading: Boolean,
  downloadProgress: { type: Number, default: 0 },
  downloadError: { type: String, default: '' },
  summarizing: Boolean,
  videoUrl: { type: String, default: '' },
})
const emit = defineEmits(['download', 'summarize', 'format-change'])

// 复用全局轻提示（与 App.vue 同源，避免重复造 toast）
const showToast = inject('showToast', () => {})

const thumbnailUrl = computed(() => {
  if (!props.video.thumbnail) return ''
  return '/api/proxy/thumbnail?url=' + encodeURIComponent(props.video.thumbnail)
})

// 内联预览：优先用顶层直链，其次取格式列表中嵌入的 _direct_url，仍无则运行时向接口拉取
const basePreviewUrl = computed(() => {
  if (props.video.direct_url) return props.video.direct_url
  if (props.video.download_url) return props.video.download_url
  const f = (props.video.formats || []).find(fmt => fmt._direct_url)
  return f ? f._direct_url : ''
})
const fetchedUrl = ref('')
const previewUrl = computed(() => basePreviewUrl.value || fetchedUrl.value)
const previewLoading = ref(false)

async function openPreview() {
  if (previewUrl.value) {
    showPreview.value = true
    return
  }
  // yt-dlp 结果不带顶层直链，向现有 /api/direct-url 接口拉取（复用后端能力，零新增依赖）
  if (!props.videoUrl) return
  previewLoading.value = true
  try {
    const res = await getDirectUrl(props.videoUrl, selectedFormat.value)
    if (res.success && res.data && res.data.direct_url) {
      fetchedUrl.value = res.data.direct_url
      showPreview.value = true
    } else {
      showToast('该视频暂不支持在线预览', 'info')
    }
  } catch {
    showToast('获取预览地址失败，请稍后重试', 'error')
  } finally {
    previewLoading.value = false
  }
}
const showPreview = ref(false)

// 播放器增强：倍速 + 画中画
// 用 videoElement 跟踪当前已挂载的 video 元素：v-if 切换/组件销毁时会重新赋值，
// 函数式 ref 钩子（onVideoEl / cleanupVideoEl）负责同步 PiP 监听和倍速。
const videoElement = ref(null)
const currentRate = ref(1)

function setRate(r) {
  currentRate.value = r
  if (videoElement.value) videoElement.value.playbackRate = r
}

function togglePip() {
  const v = videoElement.value
  if (!v) return
  try {
    if (document.pictureInPictureElement && document.pictureInPictureElement !== v) {
      document.exitPictureInPicture().catch(() => {})
    } else if (v.requestPictureInPicture) {
      v.requestPictureInPicture().catch(() => showToast('当前浏览器不支持画中画', 'info'))
    }
  } catch {
    showToast('当前浏览器不支持画中画', 'info')
  }
}

// 监听原生 PiP 事件：用户在系统 PiP 窗口关闭时同步关闭 showPreview，
// 避免出现"预览态=true、video 没在 PiP 也没在主页面控件里"的画面黑屏状态。
const pipActive = ref(false)
const onEnterPip = () => { pipActive.value = true }
const onLeavePip = () => { pipActive.value = false }

function onVideoEl(el) {
  // 函数式 ref：Vue 在元素 mount 时调 el=videoEl、unmount 时调 el=null。
  // 每次重新创建都要重新绑定 PiP 监听 + 同步当前倍速；卸载时按引用移除避免残留 listener。
  if (el) {
    videoElement.value = el
    el.addEventListener('enterpictureinpicture', onEnterPip)
    el.addEventListener('leavepictureinpicture', onLeavePip)
    el.playbackRate = currentRate.value
  } else if (videoElement.value) {
    videoElement.value.removeEventListener('enterpictureinpicture', onEnterPip)
    videoElement.value.removeEventListener('leavepictureinpicture', onLeavePip)
    videoElement.value = null
  }
}

// 组件销毁时主动退出 PiP，避免 video 元素被卸载后 PiP 窗口仍残留（部分浏览器实现）。
onBeforeUnmount(() => {
  if (document.pictureInPictureElement) {
    document.exitPictureInPicture().catch(() => {})
  }
})

// 推荐格式：复用 utils/format.js 的 pickBestFormat（有音频的最高分辨率），用于列表高亮
const recommendedId = computed(() => {
  const best = pickBestFormat(props.video.formats || [])
  return best ? best.format_id : ''
})

// 初始选中的格式：默认取推荐画质，与模板下方"推荐"标签语义一致，
// 避免出现 formats 顺序乱时（YouTube 等）首屏"已选择"指向最低画质但视觉上又"推荐"另一档的 UX 矛盾。
const selectedFormat = ref(recommendedId.value || props.video.formats?.[0]?.format_id || '')
watch(selectedFormat, (value) => emit('format-change', value), { immediate: true })

// 快捷预设
const presets = [
  { type: 'best', label: '最高画质' },
  { type: 'audio', label: '仅音频' },
  { type: '720', label: '720P' },
  { type: 'mini', label: '最小体积' },
]
const activePreset = ref('')

function applyPreset(type) {
  const fmts = props.video.formats || []
  if (!fmts.length) return
  let target
  if (type === 'best') {
    target = pickBestFormat(fmts, 'max')
  } else if (type === 'audio') {
    target = fmts.find(f => /audio|音/i.test(f.label) || f.ext === 'mp3' || f.ext === 'm4a')
      || fmts.find(f => f.has_audio) || fmts[0]
  } else if (type === '720') {
    target = fmts.find(f => /720/.test(f.label)) || pickBestFormat(fmts, 'max')
  } else if (type === 'mini') {
    target = pickBestFormat(fmts, 'min')
  }
  if (target) {
    selectedFormat.value = target.format_id
    activePreset.value = type
  }
}

// 手动选择格式的高亮清除已在模板点击处处理（@click 同时置 activePreset=''），
// 此处不再用 watch——watch 会在 applyPreset 同步设值后异步清空高亮，导致预设按钮一闪即灭。

const selectedLabel = computed(() => {
  const fmt = props.video.formats?.find(f => f.format_id === selectedFormat.value)
  return fmt?.label || ''
})

async function copyLink() {
  const target = props.videoUrl || props.video.url || props.video.webpage_url || ''
  if (!target) return
  const ok = await copyText(target)
  showToast(ok ? '链接已复制' : '复制失败，请手动复制', ok ? 'success' : 'error')
}
</script>
