<template>
  <div class="video-cache-admin">
    <!-- 头部统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">总缓存数</p>
            <p class="text-2xl font-bold text-text-primary">{{ stats.total_videos || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-primary-light rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">活跃缓存</p>
            <p class="text-2xl font-bold text-success">{{ stats.active_cache || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">热门缓存</p>
            <p class="text-2xl font-bold text-orange-600">{{ stats.hot_cache || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-border shadow-sm p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-text-muted">总访问次数</p>
            <p class="text-2xl font-bold text-purple-600">{{ stats.total_cache_hits || 0 }}</p>
          </div>
          <div class="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center">
            <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- 筛选和操作栏 -->
    <div class="bg-white rounded-xl border border-border shadow-sm p-4 mb-6">
      <div class="flex flex-col md:flex-row gap-4">
        <!-- 搜索框 -->
        <div class="flex-1">
          <input
            v-model="filters.search"
            type="text"
            placeholder="搜索视频标题、URL或UP主..."
            class="w-full h-10 px-4 border border-border rounded-xl bg-white text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
            @keyup.enter="searchVideos"
          />
        </div>

        <!-- 平台筛选 -->
        <select
          v-model="filters.platform"
          class="h-10 px-4 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          @change="loadVideos"
        >
          <option value="">全部平台</option>
          <option value="youtube">YouTube</option>
          <option value="bilibili">哔哩哔哩</option>
          <option value="douyin">抖音</option>
          <option value="twitter">Twitter</option>
        </select>

        <!-- 状态筛选 -->
        <select
          v-model="filters.cacheStatus"
          class="h-10 px-4 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          @change="loadVideos"
        >
          <option value="">全部状态</option>
          <option value="active">活跃</option>
          <option value="expired">已过期</option>
        </select>

        <!-- 仅热门 -->
        <label class="flex items-center gap-2">
          <input
            v-model="filters.hotOnly"
            type="checkbox"
            class="w-4 h-4 text-primary border-border rounded focus:ring-primary/20"
            @change="loadVideos"
          />
          <span class="text-sm text-text-secondary">仅热门</span>
        </label>

        <!-- 操作按钮 -->
        <BaseButton variant="primary" size="md" shape="square" @click="searchVideos">搜索</BaseButton>
        <BaseButton variant="outline" size="md" shape="square" @click="showExportDialog = true">导出数据</BaseButton>
        <BaseButton variant="danger" size="md" shape="square" @click="cleanupExpired">清理过期</BaseButton>
      </div>
    </div>

    <!-- 视频列表 -->
    <div class="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-border">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">视频信息</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">平台</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">时长/大小</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">缓存状态</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">访问统计</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-border">
            <tr v-if="loading">
              <td colspan="6">
                <EmptyState variant="loading" title="加载中…" />
              </td>
            </tr>
            <tr v-else-if="errorMsg">
              <td colspan="6">
                <EmptyState variant="error" :title="errorMsg">
                  <template #action>
                    <BaseButton variant="primary" size="sm" shape="square" @click="loadVideos">重试</BaseButton>
                  </template>
                </EmptyState>
              </td>
            </tr>
            <tr v-else-if="videos.length === 0">
              <td colspan="6">
                <EmptyState variant="empty" title="暂无缓存数据" desc="在首页解析视频后，结果会自动归档到这里。" />
              </td>
            </tr>
            <template v-else>
              <tr v-for="video in videos" :key="video.id" class="hover:bg-gray-50">
                <td class="px-6 py-4">
                  <div class="flex items-center gap-3">
                    <VideoThumbnail :url="video.thumbnail_url" size="md" />
                    <div class="min-w-0">
                      <p class="text-sm font-medium text-text-primary truncate max-w-xs">{{ video.title || '无标题' }}</p>
                      <p class="text-xs text-text-muted truncate max-w-xs">{{ video.video_url }}</p>
                    </div>
                  </div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span class="px-2 py-1 text-xs font-medium rounded-full" :class="getPlatformClass(video.platform)">
                    {{ video.platform || 'unknown' }}
                  </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-text-muted">
                  <div>{{ formatDuration(video.duration) }}</div>
                  <div>{{ formatFileSize(video.file_size) }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span
                    class="px-2 py-1 text-xs font-medium rounded-full"
                    :class="getStatusClass(video.cache_status)"
                  >
                    {{ video.cache_status || 'active' }}
                  </span>
                  <span v-if="video.is_hot" class="ml-2 px-2 py-1 text-xs font-medium bg-orange-100 text-orange-600 rounded-full">
                    热门
                  </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-text-muted">
                  <div>访问 {{ video.cache_hit_count || 0 }} 次</div>
                  <div class="text-xs text-text-muted">{{ formatDate(video.last_access_at) }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm">
                  <div class="flex flex-wrap gap-2">
                    <!-- 播放按钮 -->
                    <BaseButton
                      v-if="video.direct_url || (video.download_url && isPlayableUrl(video.download_url))"
                      variant="ghost"
                      size="xs"
                      shape="square"
                      @click="playVideo(video)"
                    >
                      播放
                    </BaseButton>
                    <!-- 下载按钮 -->
                    <BaseButton
                      v-if="video.download_url"
                      variant="ghost"
                      size="xs"
                      shape="square"
                      @click="downloadVideo(video)"
                    >
                      下载
                    </BaseButton>
                    <!-- 复制链接 -->
                    <BaseButton
                      v-if="video.download_url"
                      variant="ghost"
                      size="xs"
                      shape="square"
                      @click="copyUrl(video.download_url)"
                    >
                      复制
                    </BaseButton>
                    <!-- 标记为热门 -->
                    <BaseButton
                      variant="ghost"
                      size="xs"
                      shape="square"
                      @click="markHot(video)"
                    >
                      标热门
                    </BaseButton>
                    <!-- 删除 -->
                    <BaseButton
                      variant="danger"
                      size="xs"
                      shape="square"
                      @click="deleteVideo(video)"
                    >
                      删除
                    </BaseButton>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <div class="px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-border-light">
        <div class="text-sm text-text-muted">
          显示 {{ videos.length }} 条，共 {{ total }} 条
        </div>
        <div class="flex gap-2">
          <BaseButton
            variant="outline"
            size="xs"
            shape="square"
            :disabled="currentPage === 1"
            @click="prevPage"
          >
            上一页
          </BaseButton>
          <BaseButton
            variant="outline"
            size="xs"
            shape="square"
            :disabled="loading || currentPage * pageSize >= total"
            @click="nextPage"
          >
            下一页
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- 视频播放模态框 -->
    <BaseModal v-model="showPlayerModal" title="视频播放" max-width="4xl">
      <video
        ref="playerRef"
        :src="currentVideo?.direct_url || currentVideo?.download_url"
        controls
        autoplay
        class="w-full rounded-lg"
      >
        您的浏览器不支持视频播放
      </video>
      <div class="mt-4">
        <p class="font-medium">{{ currentVideo?.title }}</p>
        <p class="text-sm text-text-muted">{{ currentVideo?.platform }}</p>
      </div>
    </BaseModal>

    <!-- 导出对话框 -->
    <BaseModal v-model="showExportDialog" title="导出数据" max-width="md">
      <div class="px-6 py-2 space-y-4">
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1">导出格式</label>
          <select v-model="exportFormat" class="w-full h-10 px-3 border border-border rounded-xl bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all">
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-text-primary mb-1">筛选条件</label>
          <div class="space-y-2">
            <label class="flex items-center gap-2">
              <input v-model="exportFilters.platform" type="checkbox" class="rounded border-border text-primary focus:ring-primary/20" />
              <span class="text-sm text-text-secondary">按平台筛选</span>
            </label>
            <label class="flex items-center gap-2">
              <input v-model="exportFilters.cacheStatus" type="checkbox" class="rounded border-border text-primary focus:ring-primary/20" />
              <span class="text-sm text-text-secondary">按状态筛选</span>
            </label>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-3 px-6 pb-6">
          <BaseButton variant="outline" size="sm" shape="square" @click="showExportDialog = false">取消</BaseButton>
          <BaseButton variant="primary" size="sm" shape="square" @click="exportData">导出</BaseButton>
        </div>
      </template>
    </BaseModal>

  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import request from '../utils/request.js'
import { copyText } from '../utils/clipboard.js'
import { downloadBlob } from '../utils/file.js'
import { formatBytes, formatTime, formatDateTime } from '../utils/format.js'
import { getApiError } from '../utils/error.js'
import Spinner from './ui/Spinner.vue'
import EmptyState from './ui/EmptyState.vue'
import BaseButton from './ui/BaseButton.vue'
import BaseModal from './ui/BaseModal.vue'
import VideoThumbnail from './VideoThumbnail.vue'

// 业务 success:false 与异常 catch 分支的兜底文案（统一提取，避免 4 处重复）。
const OPERATION_FAILED_TIP = '操作失败，请重试'
const DELETE_FAILED_TIP = '删除失败'
const CLEANUP_FAILED_TIP = '清理失败'

const videos = ref([])
const stats = ref({})
const total = ref(0)
const currentPage = ref(1)
const pageSize = 50

const filters = ref({
  search: '',
  platform: '',
  cacheStatus: '',
  hotOnly: false
})

const showPlayerModal = ref(false)
const currentVideo = ref(null)
const playerRef = ref(null)

const showExportDialog = ref(false)
const exportFormat = ref('json')
const exportFilters = ref({
  platform: false,
  cacheStatus: false
})

// 加载 / 错误状态；轻提示统一走全局 showToast（provide 于 App.vue）
const loading = ref(false)
const errorMsg = ref('')
const showToast = inject('showToast', () => {})

onMounted(() => {
  loadStats()
  loadVideos()
})

async function loadStats() {
  try {
    const response = await request.get('/video-cache/stats', { __silent: true })
    if (response.data.success) {
      stats.value = response.data.data
    }
  } catch (error) {
    // 修复：原写法仅 console.error，用户看不到统计卡为何一直空白。
    // __silent 抑制 axios 自动 toast，这里手动补一条让用户知道。
    console.error('加载统计信息失败:', error)
    showToast(getApiError(error, '加载统计失败'), 'error')
  }
}

async function loadVideos() {
  loading.value = true
  errorMsg.value = ''
  try {
    const params = {
      limit: pageSize,
      offset: (currentPage.value - 1) * pageSize
    }
    
    if (filters.value.search) {
      params.search = filters.value.search
    }
    if (filters.value.platform) {
      params.platform = filters.value.platform
    }
    if (filters.value.cacheStatus) {
      params.cache_status = filters.value.cacheStatus
    }
    if (filters.value.hotOnly) {
      params.hot_only = true
    }
    
    const response = await request.get('/video-cache/videos', { params, __silent: true })
    if (response.data.success) {
      videos.value = response.data.data
      total.value = response.data.total
    } else {
      errorMsg.value = getApiError({ response }, '加载失败', '未知错误')
    }
  } catch (error) {
    errorMsg.value = getApiError(error, '加载失败')
  } finally {
    loading.value = false
  }
}

function searchVideos() {
  currentPage.value = 1
  loadVideos()
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
    loadVideos()
  }
}

function nextPage() {
  currentPage.value++
  loadVideos()
}

function playVideo(video) {
  currentVideo.value = video
  showPlayerModal.value = true
}

function downloadVideo(video) {
  if (video.download_url) {
    // 修复：原 `_blank` 在老浏览器（IE / 旧 Safari）下会暴露 window.opener 引用，可能被目标页面反向操控。
    // 显式 noopener,noreferrer 是现代安全标准。
    window.open(video.download_url, '_blank', 'noopener,noreferrer')
  }
}

async function copyUrl(url) {
  const ok = await copyText(url)
  showToast(ok ? '链接已复制到剪贴板' : '复制失败', ok ? 'success' : 'error')
}

async function markHot(video) {
  try {
    const response = await request.put(`/video-cache/videos/${encodeURIComponent(video.video_url)}/hot`, {}, { __silent: true })
    if (response.data.success) {
      showToast('已标记为热门', 'success')
      loadVideos()
      loadStats()
    } else {
      showToast(OPERATION_FAILED_TIP, 'error')
    }
  } catch (error) {
    console.error('标记热门失败:', error)
    showToast(getApiError(error, '', OPERATION_FAILED_TIP), 'error')
  }
}

async function deleteVideo(video) {
  if (!confirm(`确定要删除 "${video.title}" 的缓存吗？`)) {
    return
  }
  
  try {
    const response = await request.delete(`/video-cache/videos/${encodeURIComponent(video.video_url)}`, { __silent: true })
    if (response.data.success) {
      showToast('删除成功', 'success')
      loadVideos()
      loadStats()
    } else {
      showToast(DELETE_FAILED_TIP, 'error')
    }
  } catch (error) {
    console.error('删除失败:', error)
    showToast(getApiError(error, '', DELETE_FAILED_TIP), 'error')
  }
}

async function cleanupExpired() {
  if (!confirm('确定要清理所有过期缓存吗？')) {
    return
  }

  try {
    const response = await request.post('/video-cache/cleanup', {}, { __silent: true })
    if (response.data.success) {
      showToast(response.data.message || '清理完成', 'success')
      loadVideos()
      loadStats()
    } else {
      showToast(CLEANUP_FAILED_TIP, 'error')
    }
  } catch (error) {
    console.error('清理失败:', error)
    showToast(getApiError(error, '', CLEANUP_FAILED_TIP), 'error')
  }
}

async function exportData() {
  try {
    const params = {}

    if (exportFilters.value.platform && filters.value.platform) {
      params.platform = filters.value.platform
    }
    if (exportFilters.value.cacheStatus && filters.value.cacheStatus) {
      params.cache_status = filters.value.cacheStatus
    }

    const response = await request.get(`/video-cache/export?format=${exportFormat.value}`, {
      params,
      responseType: 'blob',
      __silent: true
    })

    // 复用 utils/file.js#downloadBlob（自动延迟 1s revoke，避免 Firefox 大文件下载失败）
    const blob = new Blob([response.data])
    downloadBlob(blob, `video_cache_export.${exportFormat.value}`)

    showExportDialog.value = false
    showToast('导出成功', 'success')
  } catch (error) {
    console.error('导出失败:', error)
    showToast('导出失败', 'error')
  }
}

function isPlayableUrl(url) {
  if (!url) return false
  return url.endsWith('.mp4') || url.endsWith('.webm') || url.includes('.m3u8')
}

function getPlatformClass(platform) {
  const classes = {
    youtube: 'bg-red-100 text-red-600',
    bilibili: 'bg-pink-100 text-pink-600',
    douyin: 'bg-black text-white',
    twitter: 'bg-blue-400 text-white'
  }
  return classes[platform?.toLowerCase()] || 'bg-gray-100 text-text-secondary'
}

function getStatusClass(status) {
  return status === 'active' ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-text-secondary'
}

function formatDuration(seconds) {
  // 复用 utils/format.js#formatTime（mm:ss / hh:mm:ss），空值用 '-' 兜底（统一后台展示口径）
  return seconds ? formatTime(seconds) : '-'
}

function formatFileSize(bytes) {
  return bytes ? formatBytes(bytes, 2) : '-'
}

function formatDate(dateStr) {
  // 复用 utils/format.js#formatDateTime（本地化日期+时间），空值用 '-' 兜底
  return dateStr ? formatDateTime(dateStr) : '-'
}
</script>

<style scoped>
.video-cache-admin {
  padding: 1rem;
}
</style>
