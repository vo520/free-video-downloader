<template>
  <div class="mindmap-panel">
    <div v-if="mindmapMarkdown" class="relative">
      <!-- 工具栏 -->
      <div class="flex items-center justify-end gap-2 mb-3">
        <BaseButton
          @click="downloadMindmapPng"
          variant="ghost"
          class="!flex !items-center !gap-1.5 !text-xs !px-3 !py-1.5 !rounded-lg !text-primary !hover:bg-primary-light"
          title="下载 PNG 图片"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          PNG
        </BaseButton>
        <BaseButton
          @click="downloadMindmapSvg"
          variant="ghost"
          class="!flex !items-center !gap-1.5 !text-xs !px-3 !py-1.5 !rounded-lg !text-primary !hover:bg-primary-light"
          title="下载 SVG 矢量图"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          SVG
        </BaseButton>
        <BaseButton
          @click="toggleFullscreen"
          variant="ghost"
          class="!flex !items-center !gap-1.5 !text-xs !px-3 !py-1.5 !rounded-lg !text-primary !hover:bg-primary-light"
          :title="isFullscreen ? '退出全屏' : '全屏展示'"
        >
          <svg v-if="!isFullscreen" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
          </svg>
          <svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
          </svg>
          {{ isFullscreen ? '退出全屏' : '全屏' }}
        </BaseButton>
      </div>
      <div
        ref="mindmapContainer"
        class="mindmap-wrapper w-full border border-border-light rounded-xl bg-white overflow-hidden"
        :class="isFullscreen ? 'mindmap-fullscreen' : 'min-h-[500px]'"
      >
        <svg
          ref="mindmapSvg"
          class="w-full h-full"
          :style="isFullscreen ? 'height: 100%' : 'min-height: 500px'"
        ></svg>
        <!-- 全屏模式下的退出按钮 -->
        <BaseButton
          v-if="isFullscreen"
          @click="toggleFullscreen"
          variant="ghost"
          class="!fixed !top-4 !right-4 !z-50 !flex !items-center !gap-1.5 !px-4 !py-2 !rounded-lg !bg-white/90 !backdrop-blur !shadow-lg !text-sm !text-text-primary !hover:bg-white !border !border-border-light"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          退出全屏
        </BaseButton>
      </div>
    </div>
    <div v-else-if="loading" class="flex flex-col items-center justify-center py-16">
      <Spinner variant="ring" size="lg" class="mb-3" />
      <p class="text-text-muted text-sm">正在生成思维导图...</p>
    </div>
    <EmptyState v-else size="md" variant="info">
      <template #icon>
        <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      </template>
      <template #default>请先生成总结以查看思维导图</template>
    </EmptyState>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount, inject } from 'vue'
import Spinner from '../ui/Spinner.vue'
import EmptyState from '../ui/EmptyState.vue'
import BaseButton from '../ui/BaseButton.vue'
import { sanitizeFilename, downloadBlob } from '../../utils/file.js'

  const props = defineProps({
    mindmapMarkdown: { type: String, default: '' },
    videoTitle: { type: String, default: '' },
    loading: { type: Boolean, default: false },
  })

  const mindmapSvg = ref(null)
  const mindmapContainer = ref(null)
  const isFullscreen = ref(false)
  let markmapInstance = null

  // markmap 库按需加载：仅在真正生成思维导图时才动态拉取，
  // 避免 markmap-lib / markmap-view（含 d3 等）进入首屏包，显著减小初始体积。
  let markmapModules = null
  async function loadMarkmap() {
    if (!markmapModules) {
      const [lib, view] = await Promise.all([
import('markmap-lib'),
import('markmap-view'),
      ])
      markmapModules = { Transformer: lib.Transformer, Markmap: view.Markmap }
    }
    return markmapModules
  }

  async function renderMindmap(md) {
    if (!mindmapSvg.value) return
    try {
      const { Transformer, Markmap } = await loadMarkmap()
      mindmapSvg.value.innerHTML = ''
      const transformer = new Transformer()
      const { root } = transformer.transform(md)
      markmapInstance = Markmap.create(mindmapSvg.value, { autoFit: true }, root)
    } catch (e) {
      console.warn('思维导图渲染失败:', e)
    }
  }

  // 流式渲染防抖：SSE 每个 chunk 都会更新 mindmapMarkdown，若每次同步重建 markmap 实例，
  // 长视频会产生大量整图重排。改为短延迟合并渲染（仅在 chunk 停止 ~120ms 后真正重建），
  // 既保留流式可见性，又大幅降低重排开销。
  let renderTimer = null
  function scheduleRender(md) {
    if (renderTimer) clearTimeout(renderTimer)
    renderTimer = setTimeout(() => {
      renderTimer = null
      renderMindmap(md)
    }, 120)
  }

  watch(
    () => props.mindmapMarkdown,
    async (val) => {
      if (val) {
        await nextTick()
        scheduleRender(val)
      }
    }
  )

  // ===== 全屏切换 =====
  function toggleFullscreen() {
    if (!mindmapContainer.value) return
    if (!isFullscreen.value) {
      // 修复：原写法 silent fail（iframe 跨域 / permission-policy 拒绝时无反馈）。
      // 改为 try/catch + toast 提示，让用户知道"当前环境不支持全屏"。
      try {
        if (mindmapContainer.value.requestFullscreen) {
          mindmapContainer.value.requestFullscreen()
        } else if (mindmapContainer.value.webkitRequestFullscreen) {
          mindmapContainer.value.webkitRequestFullscreen()
        } else {
          showToast('当前浏览器不支持全屏', 'info')
        }
      } catch (e) {
        showToast('当前环境无法全屏，请检查浏览器权限', 'info')
      }
    } else {
      try {
        if (document.exitFullscreen) document.exitFullscreen()
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen()
      } catch (e) {
        /* 退出全屏失败通常无影响 */
      }
    }
  }

  function onFullscreenChange() {
    // 兼容 WebKit：Safari 用 document.webkitFullscreenElement 而非标准属性，
    // 否则全屏状态下 isFullscreen 不更新、思维导图不重新适配。
    isFullscreen.value =
      !!document.fullscreenElement || !!document.webkitFullscreenElement
    nextTick(() => {
      if (markmapInstance) markmapInstance.fit()
    })
  }

  // ===== 构建可导出的纯 SVG（将 foreignObject 替换为 text） =====
  function buildExportableSvg() {
    if (!mindmapSvg.value) return null
    const cloned = mindmapSvg.value.cloneNode(true)
    cloned.querySelectorAll('[transform]').forEach((el) => {
      const t = el.getAttribute('transform')
      if (t && t.includes('NaN')) {
        el.setAttribute('transform', 'translate(0,0) scale(1)')
      }
    })
    cloned.querySelectorAll('foreignObject').forEach((fo) => {
      const textContent = fo.textContent?.trim() || ''
      if (!textContent) { fo.remove(); return }
      const x = parseFloat(fo.getAttribute('x')) || 0
      const y = parseFloat(fo.getAttribute('y')) || 0
      const h = parseFloat(fo.getAttribute('height')) || 20
      const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text')
      textEl.setAttribute('x', String(x + 4))
      textEl.setAttribute('y', String(y + h / 2 + 5))
      textEl.setAttribute('font-size', '14')
      textEl.setAttribute('font-family', 'sans-serif')
      textEl.setAttribute('fill', '#333')
      textEl.setAttribute('dominant-baseline', 'middle')
      textEl.textContent = textContent
      fo.parentNode.replaceChild(textEl, fo)
    })
    return cloned
  }

  function serializeSvg(svgEl) {
    const serializer = new XMLSerializer()
    let svgString = serializer.serializeToString(svgEl)
    if (!svgString.includes('xmlns=')) {
      svgString = svgString.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
    }
    const styles = document.querySelectorAll('style')
    let markmapCss = ''
    styles.forEach((s) => {
      if (s.textContent.includes('.markmap')) {
        markmapCss += s.textContent
      }
    })
    if (markmapCss) {
      svgString = svgString.replace('>', `><defs><style>${markmapCss}</style></defs>`)
    }
    return svgString
  }

  // ===== 获取思维导图完整内容边界（不受用户缩放/平移影响） =====
  function getContentBBox() {
    const svgEl = mindmapSvg.value
    const gRoot = svgEl.querySelector('g')
    if (gRoot) {
      try {
        const bbox = gRoot.getBBox()
        if (bbox.width > 0 && bbox.height > 0) {
          const transform = gRoot.getAttribute('transform') || ''
          const translateMatch = transform.match(/translate\(\s*([-\d.e]+)\s*[,\s]\s*([-\d.e]+)\s*\)/)
          const scaleMatch = transform.match(/scale\(\s*([-\d.e]+)/)
          const tx = translateMatch ? parseFloat(translateMatch[1]) : 0
          const ty = translateMatch ? parseFloat(translateMatch[2]) : 0
          const sc = scaleMatch ? parseFloat(scaleMatch[1]) : 1
          return {
            x: bbox.x * sc + tx,
            y: bbox.y * sc + ty,
            width: bbox.width * sc,
            height: bbox.height * sc,
          }
        }
      } catch {}
    }
    try {
      const bbox = svgEl.getBBox()
      if (bbox.width > 0 && bbox.height > 0) return bbox
    } catch {}
    return { x: 0, y: 0, width: 800, height: 600 }
  }

  // ===== 为导出 SVG 设置完整内容的 viewBox =====
  function setFullViewBox(svgClone) {
    const dims = getContentBBox()
    const padding = 60
    const vx = dims.x - padding
    const vy = dims.y - padding
    const vw = dims.width + padding * 2
    const vh = dims.height + padding * 2
    svgClone.setAttribute('viewBox', `${vx} ${vy} ${vw} ${vh}`)
    svgClone.setAttribute('width', String(vw))
    svgClone.setAttribute('height', String(vh))
    return { vw, vh }
  }

  // ===== 思维导图下载 PNG（4K 超清，完整内容） =====
  async function downloadMindmapPng() {
    if (!checkMindmapReady()) return
    const exportSvg = buildExportableSvg()
    if (!exportSvg) return
    const { vw, vh } = setFullViewBox(exportSvg)
    const scale = Math.max(4, Math.ceil(3840 / vw))
    const svgString = serializeSvg(exportSvg)
    const canvas = document.createElement('canvas')
    canvas.width = vw * scale
    canvas.height = vh * scale
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    const img = new Image()
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    return new Promise((resolve) => {
      img.onload = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        URL.revokeObjectURL(url)
        canvas.toBlob((pngBlob) => {
          if (pngBlob) {
            downloadBlob(pngBlob, sanitizeFilename(props.videoTitle) + ' - 思维导图.png')
          }
          resolve()
        }, 'image/png')
      }
      img.onerror = () => {
        URL.revokeObjectURL(url)
        showToast('PNG 导出失败，请使用 SVG 下载', 'error')
        resolve()
      }
      img.src = url
    })
  }

  // ===== 思维导图下载 SVG（完整内容，不受视口影响） =====
  function downloadMindmapSvg() {
    if (!checkMindmapReady()) return
    const cloned = mindmapSvg.value.cloneNode(true)
    cloned.querySelectorAll('[transform]').forEach((el) => {
      const t = el.getAttribute('transform')
      if (t && t.includes('NaN')) {
        el.setAttribute('transform', 'translate(0,0) scale(1)')
      }
    })
    setFullViewBox(cloned)
    const svgString = serializeSvg(cloned)
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    downloadBlob(blob, sanitizeFilename(props.videoTitle) + ' - 思维导图.svg')
  }

  // showToast 由父组件通过 provide/inject 注入
  const showToast = inject('showToast', (msg, type) => { console.warn('[toast]', msg) })

  // 思维导图导出前置检查（PNG/SVG 下载复用）：markmap 实例未就绪（生成中/失败）
  // → 提示并阻止导出，避免重复前置检查 + 重复 toast 文案。
  const MINDMAP_NOT_READY_TIP = '思维导图生成中，请稍后重试'
  function checkMindmapReady() {
    if (!mindmapSvg.value || !markmapInstance || !mindmapSvg.value.querySelector('g')) {
      showToast(MINDMAP_NOT_READY_TIP, 'info')
      return false
    }
    return true
  }

  onMounted(() => {
    document.addEventListener('fullscreenchange', onFullscreenChange)
    document.addEventListener('webkitfullscreenchange', onFullscreenChange)
    // 本组件由 VideoSummary 以 v-if 按 tab 按需挂载：若挂载时 mindmapMarkdown 已有值
    // （常见于「总结已完成 → 用户才切到思维导图 tab」），上面的 watch 只在值**变化**时触发，
    // 不会补渲染，导致思维导图区域永久空白。此处补一次首帧渲染（与 watch 共用 debounce 不冲突）。
    if (props.mindmapMarkdown) scheduleRender(props.mindmapMarkdown)
  })
  onBeforeUnmount(() => {
    document.removeEventListener('fullscreenchange', onFullscreenChange)
    document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
    // 清理 pending 的流式渲染防抖 timer，避免已销毁组件上重建 markmap
    if (renderTimer) {
      clearTimeout(renderTimer)
      renderTimer = null
    }
    // 释放 markmap 实例持有的 d3 zoom + window resize 等 listener，避免组件卸载后残留
    if (markmapInstance) {
      try { markmapInstance.destroy() } catch (e) { /* markmap 销毁已兜底 */ }
      markmapInstance = null
    }
  })
</script>

<style scoped>
  /* 思维导图：确保 markmap 的 foreignObject 文字正常显示 */
  .mindmap-wrapper :deep(.markmap-foreign) {
    display: inline-block !important;
  }
  .mindmap-wrapper :deep(foreignObject) {
    overflow: visible !important;
  }
  .mindmap-wrapper :deep(foreignObject div) {
    font: 300 16px/20px sans-serif;
    color: #333;
  }

  /* 思维导图全屏样式 */
  .mindmap-fullscreen {
    position: fixed !important;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 40;
    border-radius: 0 !important;
    border: none !important;
    background: #ffffff;
  }
</style>