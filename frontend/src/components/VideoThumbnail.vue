<!--
  VideoThumbnail - 统一视频缩略图 + 加载失败降级占位
  复用于 App.vue / HistoryDrawer / VideoCacheAdmin（列表缩略图）与 VideoResult（大图预览），
  消除各处重复的 img + @error 兜底逻辑与各异的占位图标。
  props:
    url:   缩略图地址（可空）
    alt:   图片替代文本（默认空，调用方按需传标题）
    size:  sm (w-14 h-10, 历史列表) | md (w-16 h-12, 缓存表格) | lg (填满父容器, 视频结果大图)
           默认 sm。lg 不再自带尺寸/圆角/底色，由父容器（如 VideoResult 的 aspect-video 圆角容器）负责。
-->
<template>
  <div :class="[boxClass, 'overflow-hidden flex items-center justify-center shrink-0']">
    <img
      v-if="url && !failed"
      :src="url"
      :alt="alt"
      class="w-full h-full object-cover"
      @error="failed = true"
    />
    <svg v-else :class="[iconClass, 'text-text-muted']" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  url: { type: String, default: '' },
  alt: { type: String, default: '' },
  size: { type: String, default: 'sm' }, // sm | md | lg
})

const failed = ref(false)

// url 变化时重置失败态（防御同组件实例复用不同 url 的场景）
watch(() => props.url, () => { failed.value = false })

const SIZE_MAP = {
  sm: { box: 'w-14 h-10 rounded-lg bg-gray-100', icon: 'w-4 h-4' },
  md: { box: 'w-16 h-12 rounded-lg bg-gray-100', icon: 'w-6 h-6' },
  // lg：父容器已控制尺寸与裁切，这里只负责填满，避免圆角/底色与父容器叠加出现"灰色缺口"。
  lg: { box: 'w-full h-full', icon: 'w-12 h-12' },
}
const sizeClass = computed(() => SIZE_MAP[props.size] || SIZE_MAP.sm)
const boxClass = computed(() => sizeClass.value.box)
const iconClass = computed(() => sizeClass.value.icon)
</script>
