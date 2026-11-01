<!--
  BaseModal - 统一模态框基座
  - Teleport 到 body,fixed 全屏遮罩 + 居中容器
  - 默认 ARIA: role=dialog + aria-modal=true + aria-labelledby (绑定 title id)
  - Esc 键关闭,点击遮罩关闭(closeOnBackdrop=false 可禁用)
  - max-width: sm|md|lg|xl
  - 自带打开动画 (animate-modal-in)
  - 提供 #header slot (默认渲染 title + 关闭按钮)
  - 提供默认 slot (主体)
  - 提供 #footer slot
  - 焦点管理:打开时聚焦首个可聚焦元素,Tab 循环限制在弹窗内,关闭后焦点归还触发元素
  - 打开期间锁定 body 滚动(避免背景页面跟着滚动)
-->
<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-modal flex items-center justify-center"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        @click.self="onBackdropClick"
      >
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="onBackdropClick"></div>
        <div
          ref="containerRef"
          :class="['relative bg-white rounded-2xl shadow-2xl w-full mx-4 max-h-[90dvh] overflow-y-auto overscroll-contain animate-modal-in', maxWidthClass]"
          tabindex="-1"
        >
          <slot name="header">
            <div class="px-8 pt-8 pb-4">
              <div class="flex items-center justify-between mb-1">
                <h2 :id="titleId" class="text-xl font-bold text-text-primary">
                  {{ title }}
                </h2>
                <button
                  @click="close"
                  aria-label="关闭弹窗"
                  class="-mr-2 w-11 h-11 flex items-center justify-center rounded-lg hover:bg-surface-muted transition-colors cursor-pointer"
                >
                  <svg class="w-5 h-5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <p v-if="subtitle" class="text-sm text-text-secondary">{{ subtitle }}</p>
            </div>
          </slot>

          <slot />

          <slot name="footer" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  maxWidth: { type: String, default: 'md' },  // sm|md|lg|xl
  closeOnBackdrop: { type: Boolean, default: true },
  closeOnEsc: { type: Boolean, default: true },
  // 用于 aria-labelledby 关联,留空则自动生成 uid
  titleId: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'close'])

const uid = `modal-${Math.random().toString(36).slice(2, 9)}`
const titleId = computed(() => props.titleId || uid)

const containerRef = ref(null)
// 打开弹窗前的激活元素：关闭后把焦点还回去，
// 否则键盘用户的焦点会掉回 body，Tab 从页面顶部重新开始。
let openerEl = null
// body 滚动锁定的原始样式（用于还原）
let prevBodyOverflow = ''

const MAX_WIDTH = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
  '5xl': 'max-w-5xl',
  '6xl': 'max-w-6xl',
  '7xl': 'max-w-7xl',
}
const maxWidthClass = computed(() => MAX_WIDTH[props.maxWidth] || MAX_WIDTH.md)

function close() {
  emit('update:modelValue', false)
  emit('close')
}
function onBackdropClick() {
  if (props.closeOnBackdrop) close()
}

// 弹窗内可聚焦元素：用于 Tab 循环
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function getFocusable() {
  const root = containerRef.value
  if (!root) return []
  return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
    // 排除不可见元素（display:none / hidden），否则 Tab 会聚焦到看不见的东西
    (el) => el.offsetParent !== null || el === document.activeElement
  )
}

function onKeyDown(e) {
  if (e.key === 'Escape' && props.closeOnEsc) {
    e.stopPropagation()
    close()
    return
  }
  if (e.key !== 'Tab') return

  // 焦点陷阱：Tab / Shift+Tab 在弹窗内循环，不会跑到背后的页面去
  const focusables = getFocusable()
  if (focusables.length === 0) {
    e.preventDefault()
    containerRef.value?.focus()
    return
  }
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement

  if (e.shiftKey) {
    if (active === first || active === containerRef.value) {
      e.preventDefault()
      last.focus()
    }
  } else if (active === last) {
    e.preventDefault()
    first.focus()
  }
}

function lockBodyScroll() {
  prevBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
}

function unlockBodyScroll() {
  document.body.style.overflow = prevBodyOverflow
  prevBodyOverflow = ''
}

// Esc 监听跟随 modelValue 动态挂卸：弹窗关闭时不占用全局 keydown 事件，
// 避免页面其他位置（HeroSection 等）的 Esc 监听被噪声处理。
watch(() => props.modelValue, (open) => {
  if (open) {
    document.addEventListener('keydown', onKeyDown)
  } else {
    document.removeEventListener('keydown', onKeyDown)
  }
})

watch(() => props.modelValue, async (open) => {
  if (open) {
    // 记录触发元素（关闭后归还焦点）
    openerEl = document.activeElement instanceof HTMLElement ? document.activeElement : null
    lockBodyScroll()
    await nextTick()
    // 自动 focus 容器内第一个 autofocus 元素,否则第一个可聚焦元素,最后才是容器本身
    const target =
      containerRef.value?.querySelector('[autofocus]') ||
      getFocusable()[0] ||
      containerRef.value
    target?.focus()
  } else {
    unlockBodyScroll()
    // 焦点归还触发元素
    if (openerEl && document.contains(openerEl)) {
      openerEl.focus()
    }
    openerEl = null
  }
})

// 兜底：组件卸载时确保监听被移除（防止父组件在 modelValue=true 时突然卸载导致监听泄漏）
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
  unlockBodyScroll()
})
</script>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
