<!--
  EmptyState - 统一空/加载/错误态展示
  variant: loading | empty | error | info
  layout:   vertical (默认) | horizontal
  提供默认 slot(自定义主体) + #action slot(下方按钮/链接)
  图标默认用灰色占位 svg,可通过 #icon slot 自定义
-->
<template>
  <div
    class="flex items-center justify-center text-text-muted"
    :class="containerClass"
  >
    <div class="flex flex-col items-center text-center max-w-md mx-auto px-4">
      <slot name="icon">
        <Spinner
          v-if="variant === 'loading'"
          variant="ring"
          :size="loadingSize"
          :class="iconSpacing"
        />
        <svg
          v-else-if="defaultIcon"
          class="opacity-40"
          :class="[iconSize, iconSpacing]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            v-for="(p, i) in defaultIcon"
            :key="i"
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="1.5"
            :d="p"
          />
        </svg>
      </slot>
      <p v-if="title" class="text-sm">{{ title }}</p>
      <p v-if="desc" class="text-xs mt-1">{{ desc }}</p>
      <slot name="action" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Spinner from './Spinner.vue'

const props = defineProps({
  variant: { type: String, default: 'empty' }, // loading|empty|error|info
  title: { type: String, default: '' },
  desc: { type: String, default: '' },
  size: { type: String, default: 'md' },        // sm|md|lg (图标 + 容器 padding)
})

// 默认图标路径：每个 variant 对应一个常用场景图标
const ICONS = {
  empty: [
    'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
  ],
  error: [
    'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z'
  ],
  info: [
    'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
  ],
}

const SIZE_MAP = {
  sm: { pad: 'py-4', icon: 'w-8 h-8', spinner: 'md' },
  md: { pad: 'py-12', icon: 'w-12 h-12', spinner: 'lg' },
  lg: { pad: 'py-16', icon: 'w-16 h-16', spinner: 'xl' },
}

const containerClass = computed(() => (SIZE_MAP[props.size] || SIZE_MAP.md).pad)
const iconSize = computed(() => (SIZE_MAP[props.size] || SIZE_MAP.md).icon)
const loadingSize = computed(() => (SIZE_MAP[props.size] || SIZE_MAP.md).spinner)

const iconSpacing = computed(() => (props.variant === 'loading' ? 'mb-4' : 'mb-3'))

const defaultIcon = computed(() => {
  if (props.variant === 'loading') return null
  return ICONS[props.variant] || ICONS.empty
})
</script>