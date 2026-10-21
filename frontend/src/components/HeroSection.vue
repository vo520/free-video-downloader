<template>
  <section class="relative overflow-hidden transition-all"
    :class="compact ? 'pt-6 pb-4 sm:pt-8 sm:pb-6' : 'pt-16 pb-12 sm:pt-24 sm:pb-16'"
  >
    <!-- 装饰背景 -->
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute left-1/2 top-8 h-64 w-[42rem] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl"></div>
      <div class="absolute -right-28 top-10 h-72 w-72 rounded-full bg-success/10 blur-3xl"></div>
      <div class="absolute left-8 top-1/3 hidden h-28 w-28 rounded-[2rem] border border-primary/10 bg-white/30 rotate-12 sm:block"></div>
      <div class="absolute right-16 bottom-12 hidden h-20 w-20 rounded-full border border-success/20 bg-white/40 sm:block"></div>
    </div>

    <div class="relative max-w-4xl mx-auto px-4 sm:px-6 text-center">
      <template v-if="showSlogan">
        <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/75 shadow-sm shadow-primary/5 border border-white/80 backdrop-blur text-sm text-text-secondary"
          :class="compact ? 'mb-3' : 'mb-6'"
        >
          <span class="w-2 h-2 rounded-full bg-success animate-pulse shadow-[0_0_0_5px_rgba(19,185,129,0.12)]"></span>
          支持 1800+ 平台，永久免费使用
        </div>

        <h1 :class="compact ? 'text-2xl sm:text-3xl mb-2' : 'text-4xl sm:text-6xl mb-5'" class="font-black tracking-[-0.045em] text-text-primary leading-[1.02]">
          免费在线视频下载器
          <span class="block bg-gradient-to-r from-primary via-primary-dark to-success bg-clip-text text-transparent sm:inline">一键保存</span>
        </h1>
        <p :class="compact ? 'mb-4 text-sm sm:text-base' : 'mb-10 text-base sm:text-lg'" class="text-text-secondary max-w-2xl mx-auto leading-relaxed">
          粘贴链接即可解析下载，支持 YouTube、Bilibili、抖音、TikTok 等 1800+ 平台，并可生成 AI 摘要、字幕与思维导图。
        </p>
      </template>

      <!-- 搜索输入框 -->
      <div class="max-w-2xl mx-auto">
        <form
          @submit.prevent="onSubmit"
          @dragenter.prevent="dragActive = true"
          @dragover.prevent="dragActive = true"
          @dragleave.prevent="onDragLeave"
          @drop.prevent="onDrop"
          class="relative flex items-center rounded-[1.75rem] bg-white/75 p-1.5 shadow-2xl shadow-primary/10 ring-1 ring-white/80 backdrop-blur-xl transition-all"
          :class="dragActive ? 'ring-2 ring-primary/30 scale-[1.01]' : ''"
          role="search"
          aria-label="视频链接解析"
        >
          <div class="relative flex-1">
            <label for="video-url-input" class="sr-only">粘贴视频链接进行解析下载</label>
            <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            <input
              id="video-url-input"
              ref="inputRef"
              v-model="url"
              type="url"
              :placeholder="placeholder"
              class="w-full h-13 sm:h-14 pl-12 pr-14 sm:pr-4 rounded-full sm:rounded-r-none border border-transparent bg-white/80 text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/25 focus:bg-white transition-all"
              :disabled="loading"
              autocomplete="url"
              @paste="onPaste"
              @input="pasteHint = 0"
            />
          </div>
          <BaseButton
            type="submit"
            :disabled="loading || !url.trim()"
            variant="primary"
            size="xl"
            class="hidden sm:inline-flex !items-center !gap-2 !h-14 !px-8 !rounded-r-[1.35rem] !rounded-l-none !text-white !font-semibold !text-base !shadow-lg !shadow-primary/25 hover:!shadow-xl hover:!shadow-primary/30"
          >
            <Spinner v-if="loading" size="sm" />
            <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {{ loading ? '解析中...' : '解析视频' }}
          </BaseButton>
          <!-- 移动端按钮 -->
          <BaseButton
            type="submit"
            :disabled="loading || !url.trim()"
            variant="primary"
            class="!sm:hidden !absolute !right-2 !top-1/2 !-translate-y-1/2 !w-9 !h-9 !flex !items-center !justify-center !rounded-full !text-white"
          >
            <Spinner v-if="loading" size="xs" />
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </BaseButton>
        </form>

        <div v-if="showSlogan" class="flex flex-wrap items-center justify-center gap-3 mt-5 text-xs text-text-muted">
          <span>试试：</span>
          <BaseButton
            v-for="example in examples"
            :key="example.label"
            @click="url = example.url"
            variant="outline"
            class="!px-3 !py-1 !rounded-full !text-text-muted"
          >
            {{ example.label }}
          </BaseButton>
          <span class="text-border">·</span>
          <BaseButton
            @click="$emit('open-batch')"
            variant="outline"
            class="!inline-flex !items-center !gap-1 !px-3 !py-1 !rounded-full !text-text-muted"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            批量下载
          </BaseButton>
        </div>

        <!-- 拖拽提示 -->
        <transition name="fade">
          <div
            v-if="dragActive"
            class="mt-4 mx-auto max-w-2xl px-4 py-3 rounded-2xl border-2 border-dashed border-primary bg-primary-light text-sm text-primary font-medium"
          >
            松开后自动识别单条或批量链接
          </div>
        </transition>

        <!-- 粘贴多链接快捷入口 -->
        <transition name="fade">
          <BaseButton
            v-if="pasteHint > 0"
            @click="$emit('open-batch', pastedText); pasteHint = 0"
            variant="ghost"
            class="!mt-4 !inline-flex !items-center !gap-1.5 !px-4 !py-2 !rounded-full !text-sm !font-medium !text-primary !bg-primary-light !hover:bg-primary/15"
          >
            检测到 {{ pasteHint }} 个链接，去批量解析
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5-5 5M6 12h12" />
            </svg>
          </BaseButton>
        </transition>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { splitUrls } from '../utils/splitUrls.js'
import Spinner from './ui/Spinner.vue'
import BaseButton from './ui/BaseButton.vue'

const props = defineProps({
  loading: Boolean,
  compact: Boolean,
  showSlogan: { type: Boolean, default: true },
})
const emit = defineEmits(['parse', 'open-batch'])

const url = ref('')
const placeholder = 'https://www.youtube.com/watch?v=... 粘贴视频链接'
const inputRef = ref(null)
const dragActive = ref(false)
const pasteHint = ref(0)
const pastedText = ref('')

const examples = [
  { label: 'YouTube', url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' },
  { label: 'Bilibili', url: 'https://www.bilibili.com/video/BV1GJ411x7h7' },
  { label: 'Twitter/X', url: 'https://x.com/elonmusk/status/1234567890' },
]

function normalizeUrl(raw) {
  let u = raw
  if (u.includes('bilibili.com') && !u.includes('www.bilibili.com')) {
    u = u.replace('bilibili.com', 'www.bilibili.com')
  }
  return u
}

function onSubmit() {
  const trimmed = url.value.trim()
  if (!trimmed) return
  const urls = splitUrls(trimmed)
  if (urls.length > 1) {
    emit('open-batch', trimmed)
    return
  }
  emit('parse', normalizeUrl(urls[0] || trimmed))
}

// 拖拽离开：仅在真正移出容器（relatedTarget 不在容器内）时才取消高亮，
// 避免子元素间移动误触发 dragleave 导致高亮闪烁。
function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    dragActive.value = false
  }
}

// 拖拽文本/链接到输入框：批量填入
function onDrop(e) {
  dragActive.value = false
  const text = e.dataTransfer?.getData('text') || e.dataTransfer?.getData('text/plain') || ''
  if (!text) return
  const cur = url.value.trim()
  const next = (cur ? cur + '\n' : '') + text.trim()
  const urls = splitUrls(next)
  if (urls.length > 1) {
    emit('open-batch', next)
    return
  }
  url.value = urls[0] || next
}

// 粘贴时若检测到多个链接，给出快捷批量入口（不自动跳转，避免打断单条输入）
// 关键：@input="pasteHint = 0" 与 @paste 同步触发（事件顺序：paste → input），
// 同步赋值会被 @input 立刻清零，所以用 nextTick 延后到 @input 之后再设。
function onPaste(e) {
  const text = e.clipboardData?.getData('text') || ''
  const urls = splitUrls(text)
  // 先同步清零，让 @input 触发时 pasteHint 已是 0，nextTick 之后再设新值
  pasteHint.value = 0
  if (urls.length > 1) {
    pastedText.value = text.trim()
    nextTick(() => {
      pasteHint.value = urls.length
    })
  }
}

// 快捷键：Cmd/Ctrl+K 聚焦输入框
function onKeyDown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    inputRef.value?.focus()
    inputRef.value?.select()
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
