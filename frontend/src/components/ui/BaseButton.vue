<!--
  BaseButton - 统一按钮基础
  variant:  primary | secondary | ghost | danger | outline
  size:     sm | md | lg | xl
  shape:    pill (默认胶囊) | square
  loading:  自动展示 Spinner + 禁用 click
  type:     button (默认) | submit | reset
  - 默认 slot: 按钮文案
  - #icon slot: 左侧图标 (loading 时自动忽略外部 icon,显示 Spinner)
  - #right slot: 右侧图标(可选)
-->
<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="[baseClass, sizeClass, shapeClass, variantClass, blockClass, $attrs.class]"
    @click="onClick"
  >
    <Spinner v-if="loading" :size="spinnerSize" :class="textSpacing" />
    <slot v-else name="icon" />
    <slot />
    <slot name="right" />
  </button>
</template>

<script setup>
import { computed } from 'vue'
import Spinner from './Spinner.vue'

const props = defineProps({
  variant: { type: String, default: 'primary' },
  size: { type: String, default: 'md' },
  shape: { type: String, default: 'pill' },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
  block: { type: Boolean, default: false },
})

const emit = defineEmits(['click'])
function onClick(e) {
  if (props.disabled || props.loading) {
    e.preventDefault()
    return
  }
  emit('click', e)
}

const baseClass = 'inline-flex items-center justify-center font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30'

const SIZE_MAP = {
  xs: { btn: 'h-7 px-2.5 text-xs', sp: 'xs', space: 'gap-1' },
  sm: { btn: 'h-8 px-3 text-xs', sp: 'xs', space: 'gap-1.5' },
  md: { btn: 'h-10 px-4 text-sm', sp: 'sm', space: 'gap-2' },
  lg: { btn: 'h-12 px-6 text-base', sp: 'sm', space: 'gap-2' },
  xl: { btn: 'h-14 px-8 text-base', sp: 'md', space: 'gap-2.5' },
}

const sizeClass = computed(() => (SIZE_MAP[props.size] || SIZE_MAP.md).btn)
const spinnerSize = computed(() => (SIZE_MAP[props.size] || SIZE_MAP.md).sp)
const textSpacing = computed(() => (SIZE_MAP[props.size] || SIZE_MAP.md).space)

const shapeClass = computed(() => ({
  pill: 'rounded-full',
  square: 'rounded-lg',
}[props.shape] || 'rounded-full'))

const variantClass = computed(() => ({
  primary:   'bg-gradient-to-r from-primary to-primary-dark hover:from-primary-dark hover:to-primary text-white shadow-sm shadow-primary/20',
  secondary: 'border border-primary/25 bg-primary-light/70 text-primary hover:bg-primary hover:text-white shadow-sm',
  ghost:     'text-primary hover:bg-primary-light/80',
  danger:    'bg-red-600 hover:bg-red-700 text-white shadow-sm',
  outline:   'bg-white/80 text-text-primary border border-border hover:border-primary hover:text-primary hover:bg-white shadow-sm',
}[props.variant] || 'bg-gradient-to-r from-primary to-primary-dark text-white'))

const blockClass = computed(() => (props.block ? 'w-full' : ''))
</script>