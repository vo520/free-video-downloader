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
  - 打开时尝试 focus 容器内第一个 autofocus 元素或容器本身
-->
<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-[100] flex items-center justify-center"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        @click.self="onBackdropClick"
      >
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="onBackdropClick"></div>
        <div
          ref="containerRef"
          :class="['relative bg-white rounded-2xl shadow-2xl w-full mx-4 overflow-hidden animate-modal-in', maxWidthClass]"
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
                  class="p-1 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
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

const MAX_WIDTH = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
}
const maxWidthClass = computed(() => MAX_WIDTH[props.maxWidth] || MAX_WIDTH.md)

function close() {
  emit('update:modelValue', false)
  emit('close')
}
function onBackdropClick() {
  if (props.closeOnBackdrop) close()
}

function onKeyDown(e) {
  if (e.key === 'Escape' && props.closeOnEsc) {
    e.stopPropagation()
    close()
  }
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
    await nextTick()
    // 自动 focus 容器内第一个 autofocus 元素,或容器本身
    const target = containerRef.value?.querySelector('[autofocus]') || containerRef.value
    target?.focus()
  }
})

// 兜底：组件卸载时确保监听被移除（防止父组件在 modelValue=true 时突然卸载导致监听泄漏）
onBeforeUnmount(() => document.removeEventListener('keydown', onKeyDown))
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