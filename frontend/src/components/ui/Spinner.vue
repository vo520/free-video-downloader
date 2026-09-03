<!--
  Spinner - 统一加载指示器
  variant=svg (默认): 按钮/行内用 SVG circle (小尺寸)
  variant=ring:       整页/卡片级加载用 div+border (大尺寸)
  size: xs(4) sm(5) md(6) lg(10) xl(12)
-->
<template>
  <svg
    v-if="variant === 'svg'"
    :class="['animate-spin', sizeClass]"
    fill="none"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
  </svg>
  <div
    v-else
    :class="['animate-spin rounded-full border-4 border-primary/20 border-t-primary', sizeClass]"
    aria-hidden="true"
  ></div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  size: { type: String, default: 'md' },           // xs|sm|md|lg|xl
  variant: { type: String, default: 'svg' }        // svg|ring
})

const sizeClass = computed(() => ({
  xs: 'w-4 h-4',
  sm: 'w-5 h-5',
  md: 'w-6 h-6',
  lg: 'w-10 h-10',
  xl: 'w-12 h-12'
}[props.size] || 'w-5 h-5'))
</script>