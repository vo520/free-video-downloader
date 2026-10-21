<template>
  <!-- 浮动入口按钮（位置错开下载任务中心，避免重叠） -->
  <BaseButton
    @click="togglePanel"
    variant="ghost"
    class="!fixed !bottom-24 !right-6 !z-[150] !flex !items-center !gap-2 !h-12 !pl-4 !pr-5 !rounded-full !bg-primary !hover:bg-primary-dark !text-white !shadow-xl"
    title="历史记录"
  >
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
    <span class="text-sm font-medium">历史</span>
  </BaseButton>

  <!-- 抽屉面板 -->
  <Teleport to="body">
    <transition name="task-slide">
      <div
        v-if="open"
        @keydown.esc.window="closePanel"
        class="fixed bottom-0 right-0 z-[160] w-full sm:w-[420px] max-h-[82vh] bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl border border-border flex flex-col"
        role="region"
        aria-label="历史记录抽屉"
      >
        <!-- 头部 -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-light">
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 class="text-base font-semibold text-text-primary">历史记录</h3>
          </div>
          <div class="flex items-center gap-3">
            <BaseButton
              v-if="items.length"
              @click="clearAll"
              :disabled="clearing"
              variant="ghost"
              class="!text-xs !text-text-muted !hover:text-red-500 !disabled:opacity-50 !disabled:cursor-not-allowed"
              :aria-label="clearing ? '正在清空历史记录' : '清空全部历史记录'"
            >{{ clearing ? '清空中…' : '清空' }}</BaseButton>
            <BaseButton
              @click="closePanel"
              variant="ghost"
              class="!p-1 !text-text-muted !hover:text-text-primary"
              title="收起"
              aria-label="收起历史记录抽屉"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </BaseButton>
          </div>
        </div>

        <!-- 搜索（按标题/平台/链接前端模糊过滤，复用已拉全量的 items，无需打后端） -->
        <div class="px-5 py-2 border-b border-border-light">
          <div class="relative">
            <input
              ref="searchInput"
              v-model="search"
              type="text"
              placeholder="搜索标题 / 平台 / 链接"
              aria-label="搜索历史记录"
              class="w-full pl-3 pr-8 py-1.5 text-sm rounded-lg bg-gray-100 border border-transparent focus:border-primary focus:bg-white outline-none transition-colors"
            />
            <BaseButton
              v-if="search"
              @click="search = ''; searchInput?.focus()"
              variant="ghost"
              class="!absolute !right-2 !top-1/2 !-translate-y-1/2 !text-text-muted !hover:text-text-primary !p-1"
              title="清除搜索"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </BaseButton>
          </div>
        </div>

        <!-- 类型筛选 -->
        <div
          class="flex gap-2 px-5 py-3 border-b border-border-light"
          role="tablist"
          aria-label="历史记录类型筛选"
        >
          <button
            v-for="t in tabs"
            :key="t.key"
            @click="setTab(t.key)"
            :class="[
              'px-3 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer',
              activeTab === t.key ? 'bg-primary text-white' : 'bg-gray-100 text-text-secondary hover:bg-gray-200'
            ]"
            role="tab"
            :aria-selected="activeTab === t.key"
            :aria-controls="`history-tabpanel`"
          >{{ t.label }}<span v-if="tabCounts[t.key] > 0" class="ml-1 text-[10px] opacity-70">({{ tabCounts[t.key] }})</span></button>
        </div>

        <!-- 列表 -->
        <div
          id="history-tabpanel"
          role="tabpanel"
          :aria-label="`当前显示：${tabs.find(t => t.key === activeTab)?.label || '全部'}历史`"
          class="flex-1 overflow-y-auto px-4 py-3 space-y-2"
        >
          <p v-if="loading" class="text-center text-sm text-text-muted py-12">加载中…</p>
          <template v-else-if="errorMsg">
            <p class="text-center text-sm text-red-600 py-8">{{ errorMsg }}</p>
            <div class="text-center pb-8">
              <BaseButton
                @click="loadItems"
                variant="ghost"
                class="!text-xs !text-primary !hover:underline !disabled:opacity-50"
                :disabled="loading"
              >重试</BaseButton>
            </div>
          </template>
          <!-- 操作失败横幅：仅覆盖自身，不影响下方历史列表展示（列表仍可见） -->
          <div
            v-if="actionError"
            class="flex items-center justify-between gap-2 px-3 py-2 mb-2 rounded-lg bg-red-50 text-red-600 text-xs"
            role="alert"
            aria-live="polite"
          >
            <span class="min-w-0 flex-1">{{ actionError }}</span>
              <BaseButton
                @click="actionError = ''"
                variant="ghost"
                class="!shrink-0 !p-1 !hover:text-red-700"
                title="关闭"
                aria-label="关闭错误提示"
              >×</BaseButton>
          </div>
          <EmptyState
            v-else-if="filteredItems.length === 0"
            size="md"
            variant="empty"
            :title="items.length === 0 ? '暂无记录' : '没有匹配的搜索结果'"
            :desc="items.length === 0 ? '解析一次视频试试' : (search.trim() && hasMore ? '仅搜索已加载部分，可加载更多后重试' : '')"
          />

          <div
            v-for="it in filteredItems"
            :key="it.id"
            class="rounded-xl border border-border-light p-3"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="flex items-start gap-3 min-w-0 flex-1 cursor-pointer" @click="onItemClick(it)">
                <!-- 解析历史带缩略图（已落库），无图/加载失败统一降级占位 -->
                <VideoThumbnail :url="it.thumbnail" size="sm" />
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium text-text-primary truncate">{{ it.title || it.video_url }}</p>
                  <p class="text-xs text-text-muted truncate mt-0.5">
                    <span :class="typeTagClass(it.type)">{{ typeLabel(it.type) }}</span>
                    <span v-if="it.platform"> · {{ it.platform }}</span>
                    · {{ formatRelativeTime(it.created_at) }}
                  </p>
                </div>
              </div>
              <BaseButton
                @click="remove(it)"
                :disabled="deletingId === it.id"
                variant="ghost"
                class="!shrink-0 !text-text-muted !hover:text-red-500 !transition-opacity !p-1 !disabled:opacity-40 !disabled:cursor-not-allowed"
                title="删除"
                :aria-label="`删除历史记录：${it.title || it.video_url}`"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </BaseButton>
            </div>

            <!-- 总结回看（只读，使用与线上一致的消毒 Markdown 渲染，结果走 cache Map） -->
            <div v-if="expandedId === it.id && it.type === 'summary'" class="mt-3 border-t border-border-light pt-3 space-y-3">
              <div v-if="getExtra(it).summary">
                <p class="text-xs font-semibold text-text-secondary mb-1">总结</p>
                <div class="text-sm text-text-primary leading-relaxed max-h-60 overflow-y-auto history-md" v-html="getRenderedMarkdown(it, 'summary')"></div>
              </div>
              <div v-if="getExtra(it).mindmap">
                <p class="text-xs font-semibold text-text-secondary mb-1">思维导图</p>
                <div class="text-sm text-text-primary leading-relaxed max-h-40 overflow-y-auto history-md" v-html="getRenderedMarkdown(it, 'mindmap')"></div>
              </div>
            </div>
          </div>

          <!-- 加载更多：仅当后端 total 大于已加载条数且未搜索时出现 -->
          <div v-if="hasMore && !search.trim()" class="pt-1 pb-2 text-center">
            <BaseButton
              @click="loadMore"
              :disabled="loadingMore"
              variant="ghost"
              class="!text-xs !text-primary !hover:underline !disabled:opacity-50 !disabled:cursor-not-allowed"
            >{{ loadingMore ? '加载中…' : '加载更多（已显示 ' + items.length + '/' + total + '）' }}</BaseButton>
          </div>
        </div>

        <p class="px-5 py-2 text-xs text-text-muted border-t border-border-light">
          仅显示当前账号的历史，换设备登录也可查看
        </p>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, computed, onMounted, onBeforeUnmount, nextTick, inject } from 'vue'
import { renderMarkdown } from '../utils/markdown.js'
import { formatRelativeTime } from '../utils/relativeTime.js'
import { getApiError } from '../utils/error.js'
import { useDownloadManager } from '../composables/useDownloadManager.js'
import { fetchHistory, deleteHistoryItem, clearMyHistory } from '../api/history.js'
import { MISSING_SNAPSHOT_TIP } from '../composables/useVideo.js'
import EmptyState from './ui/EmptyState.vue'
import VideoThumbnail from './VideoThumbnail.vue'
import BaseButton from './ui/BaseButton.vue'

const emit = defineEmits(['reparse', 'view-history-record', 'history-deleted', 'history-cleared'])
const downloadManager = useDownloadManager()
// 复用 App.vue 已 provide 的全局轻提示（与首页删除/清空已有 toast 风格统一）。
// 父组件未 provide 时回退到 console.warn 而非抛错，避免单测/沙箱场景崩溃。
const showToast = inject('showToast', (msg, type = 'info') => {
  if (type === 'error') console.warn('[history toast]', msg)
})

const open = ref(false)
const items = ref([])
const loading = ref(false)
const errorMsg = ref('')
const activeTab = ref('all')
const expandedId = ref(null)
const search = ref('')
const searchInput = ref(null)
const deletingId = ref(null)
const clearing = ref(false)
// 操作失败横幅：删除/清空失败时单独提示，绝不覆盖整个列表（errorMsg 仅用于加载失败的整体替换态）。
const actionError = ref('')
let actionErrorTimer = null
// 分页：后端 list_history 原生支持 offset/limit/total，前端初始拉一页、按需「加载更多」追加，
// 降低大历史量首屏负载与 DOM 节点数；小数据量用户（<PAGE_SIZE）体验与全量拉取一致。
const PAGE_SIZE = 100
const total = ref(0)
const loadingMore = ref(false)

const tabs = [
  { key: 'all', label: '全部' },
  { key: 'parse', label: '解析' },
  { key: 'download', label: '下载' },
  { key: 'summary', label: '总结' },
]

// 各分类数量，用于 tab 上的计数徽标，无需额外请求。
// 「全部」直接用后端真实 total（分页后已加载数 < 总记录数，用 loaded 会少算）；
// 分类计数基于已加载 items（分页下为近似值，与「加载更多」提示一致，已在 UI 诚实标注）。
const tabCounts = computed(() => {
  const c = { all: total.value, parse: 0, download: 0, summary: 0 }
  for (const it of items.value) {
    if (c[it.type] !== undefined) c[it.type] += 1
  }
  return c
})

// 打开时一次性拉全量，按 tab + 关键词在前端过滤，避免每次切 tab/搜索都打后端（切换即时、省请求）。
const filteredItems = computed(() => {
  const kw = search.value.trim().toLowerCase()
  let list = items.value
  if (activeTab.value !== 'all') list = list.filter((x) => x.type === activeTab.value)
  if (kw) {
    list = list.filter((x) =>
      (x.title && x.title.toLowerCase().includes(kw)) ||
      (x.platform && x.platform.toLowerCase().includes(kw)) ||
      (x.video_url && x.video_url.toLowerCase().includes(kw))
    )
  }
  return list
})

// 是否还有未加载的历史（后端 total 与已加载条数比较）。搜索态下「加载更多」无意义（搜索仅覆盖已加载部分）。
const hasMore = computed(() => items.value.length < total.value)

// 操作失败提示：列表仍可见，4 秒后自动消失，可手动关闭（×）。
function showActionError(msg) {
  actionError.value = msg
  if (actionErrorTimer) clearTimeout(actionErrorTimer)
  actionErrorTimer = setTimeout(() => { actionError.value = '' }, 4000)
}

function togglePanel() { open.value = !open.value }
function closePanel() { open.value = false; search.value = ''; actionError.value = '' }
// 切 tab 时重置展开态，避免跨分类残留无效展开
function setTab(k) {
  activeTab.value = k
  expandedId.value = null
}

function typeLabel(t) {
  return { parse: '解析', download: '下载', summary: '总结' }[t] || t
}
function typeTagClass(t) {
  return {
    parse: 'text-primary',
    download: 'text-green-600',
    summary: 'text-purple-600',
  }[t] || 'text-text-secondary'
}

function parsedExtra(it) {
  if (!it.extra) return {}
  try { return typeof it.extra === 'string' ? JSON.parse(it.extra) : it.extra } catch { return {} }
}

// 列表频繁重渲染（搜索/切 tab/展开总结），每项模板调用 parsedExtra 2 次 → 2N 次 JSON.parse。
// 一次性按 id 预解析到 Map：N 项 × 2 次 → 1 次，且 summary/mindmap 的 marked + DOMPurify
// 重操作也只在 items 变化时跑一次，不再每帧重渲染。
const parsedExtrasById = computed(() => {
  const map = new Map()
  for (const it of items.value) {
    if (!it.extra) continue
    try {
      map.set(it.id, typeof it.extra === 'string' ? JSON.parse(it.extra) : it.extra)
    } catch { /* 单条损坏不阻塞列表渲染 */ }
  }
  return map
})

const renderedMarkdownCache = computed(() => {
  const map = new Map()
  for (const [id, extra] of parsedExtrasById.value) {
    if (!extra) continue
    if (extra.summary) map.set('summary:' + id, renderMarkdown(extra.summary))
    if (extra.mindmap) map.set('mindmap:' + id, renderMarkdown(extra.mindmap))
  }
  return map
})

function getExtra(it) { return parsedExtrasById.value.get(it.id) || {} }
function getRenderedMarkdown(it, kind) {
  return renderedMarkdownCache.value.get(kind + ':' + it.id) || ''
}

// 后端错误文案统一走 utils/error.js 的 getApiError（见下方调用）

async function loadItems() {
  loading.value = true
  errorMsg.value = ''
  try {
    // 初始按页拉取（后端已按 extra 解析、去重）；tab/搜索均前端过滤，无需每次切 tab 打后端。
    const { items: list, total: t } = await fetchHistory({ limit: PAGE_SIZE, offset: 0 })
    items.value = list
    total.value = t ?? list.length
  } catch (e) {
    errorMsg.value = getApiError(e, '加载失败')
  } finally {
    loading.value = false
  }
}

// 按页追加更多历史（后端 list_history 原生支持 offset/limit/total），避免一次性拉取全部造成首屏卡顿。
async function loadMore() {
  // 三重守卫：初始加载中 / 加载更多中 / 已加载完。避免初始未加载完成时用户点「加载更多」导致 offset 偏移错乱。
  if (loading.value || loadingMore.value || items.value.length >= total.value) return
  loadingMore.value = true
  try {
    const { items: list, total: t } = await fetchHistory({ limit: PAGE_SIZE, offset: items.value.length })
    items.value = items.value.concat(list)
    total.value = t ?? total.value
  } catch (e) {
    showActionError(getApiError(e, '加载更多失败'))
  } finally {
    loadingMore.value = false
  }
}

function onItemClick(it) {
  if (it.type === 'parse') {
    // 点击解析历史：直接用数据库落库的 snapshot 还原 videoData 显示，
    // 不再走 /api/parse 重新跑 yt-dlp（避免视频失效/慢/超时导致无法显示）。
    // 无 snapshot 时（早期未存快照的存量历史）也绝不自动重跑——按用户要求
    // 「应该从数据库中直接显示内容」是硬约束；提示其手动删除或重新粘贴解析。
    if (it.snapshot) {
      emit('view-history-record', it)
      closePanel()
    } else {
      showToast(MISSING_SNAPSHOT_TIP, 'info')
    }
  } else if (it.type === 'download') {
    const extra = getExtra(it)
    downloadManager.enqueue(it.video_url, extra?.format_id || '', it.title)
    downloadManager.openPanel()
    closePanel()
  } else if (it.type === 'summary') {
    expandedId.value = expandedId.value === it.id ? null : it.id
  }
}

async function remove(it) {
  if (deletingId.value) return
  if (!confirm('确定删除这条记录吗？')) return
  deletingId.value = it.id
  try {
    await deleteHistoryItem(it.id)
    items.value = items.value.filter((x) => x.id !== it.id)
    total.value = Math.max(0, total.value - 1)
    // 与 App.vue 删除最近解析的 toast 风格统一：成功反馈而非静默过滤
    showToast('已删除', 'success')
    // 通知 App.vue：若被删条目对应当前正在显示的视频，同步清掉 videoData，
    // 避免用户看到陈旧内容。
    emit('history-deleted', it)
  } catch (e) {
    showActionError(getApiError(e, '删除失败'))
  } finally {
    deletingId.value = null
  }
}

async function clearAll() {
  if (clearing.value) return
  if (!confirm('确定清空全部历史记录吗？')) return
  clearing.value = true
  try {
    await clearMyHistory()
    const n = total.value
    // 快照待删的全部条目：让 App.vue 检查其中是否有 parse 类型对应当前显示视频
    const deletedItems = items.value.slice()
    items.value = []
    total.value = 0
    search.value = ''
    // 给出明确数量反馈，避免用户怀疑"是否真的清完了"
    showToast(n > 0 ? `已清空 ${n} 条记录` : '已清空', 'success')
    emit('history-cleared')
    for (const it of deletedItems) emit('history-deleted', it)
  } catch (e) {
    showActionError(getApiError(e, '清空失败'))
  } finally {
    clearing.value = false
  }
}

onMounted(() => { if (open.value) loadItems() })
// 打开时即拉取（首次挂载时 open=false，由父组件 v-if 控制挂载时机）；切 tab 无需再请求，前端过滤即可。
// 修复：原写法每次 open 切回 true 都无条件 reload，用户关开抽屉会触发不必要的请求。
// 加 items.length 守卫：已有数据时不重拉，避免重复请求浪费。
watch(open, (v) => {
  if (!v) return
  expandedId.value = null
  if (items.value.length === 0) loadItems()
  nextTick(() => searchInput.value?.focus())
})

// 卸载时清理未触发的 timer，避免组件已销毁 timer 才触发 ref 操作报错
onBeforeUnmount(() => {
  if (actionErrorTimer) clearTimeout(actionErrorTimer)
})
</script>

<style scoped>
.task-slide-enter-active,
.task-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.task-slide-enter-from,
.task-slide-leave-to {
  transform: translateY(20px);
  opacity: 0;
}
/* 总结/mindmap 回看渲染的 Markdown 排版（v-html 注入内容需用 :deep 命中） */
.history-md :deep(h1),
.history-md :deep(h2),
.history-md :deep(h3) {
  font-weight: 600;
  margin: 0.45em 0 0.2em;
}
.history-md :deep(h1) { font-size: 1rem; }
.history-md :deep(h2) { font-size: 0.95rem; }
.history-md :deep(h3) { font-size: 0.9rem; }
.history-md :deep(p) { margin: 0.35em 0; }
.history-md :deep(ul),
.history-md :deep(ol) {
  padding-left: 1.25em;
  margin: 0.35em 0;
  list-style: revert;
}
.history-md :deep(li) { margin: 0.15em 0; }
.history-md :deep(pre) {
  white-space: pre-wrap;
  background: #f8fafc;
  padding: 0.5em;
  border-radius: 0.375rem;
  overflow-x: auto;
}
.history-md :deep(a) {
  color: #2563eb;
  text-decoration: underline;
}
.history-md :deep(code) {
  background: #f1f5f9;
  padding: 0.1em 0.3em;
  border-radius: 0.25rem;
  font-size: 0.85em;
}
</style>
