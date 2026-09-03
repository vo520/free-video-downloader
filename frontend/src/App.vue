<template>
  <div class="min-h-[100dvh] flex flex-col bg-bg-main">
    <AppHeader
      :user="currentUser"
      :history="history"
      @login="showAuthModal('login')"
      @register="showAuthModal('register')"
      @logout="handleLogout"
      @open-vip="handleOpenVip"
      @reparse="handleParse"
      @remove-history="removeHistory"
      @clear-history="clearHistory"
    />
    <main class="flex-1">
      <HeroSection
        @parse="handleParse"
        @open-batch="openBatch"
        :loading="loading"
        :compact="!!videoData"
        :showSlogan="!videoData"
      />
      <!-- 解析中骨架屏 -->
      <section v-if="loading && !videoData" class="py-4 sm:py-6 bg-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6">
          <div class="flex flex-col lg:flex-row gap-6">
            <div class="w-full lg:w-2/5 lg:flex-shrink-0">
              <div class="bg-white rounded-2xl border border-border shadow-lg p-5 sm:p-6">
                <div class="w-full aspect-video rounded-xl bg-gray-100 animate-pulse mb-5"></div>
                <div class="h-5 bg-gray-100 rounded animate-pulse w-3/4 mb-3"></div>
                <div class="h-4 bg-gray-100 rounded animate-pulse w-1/2 mb-4"></div>
                <div class="h-10 bg-gray-100 rounded-xl animate-pulse mb-3"></div>
                <div class="h-10 bg-gray-100 rounded-xl animate-pulse"></div>
              </div>
            </div>
            <div class="w-full lg:w-3/5 min-w-0">
              <div class="bg-white rounded-2xl border border-border shadow-lg p-6">
                <div class="h-4 bg-gray-100 rounded animate-pulse w-1/3 mb-5"></div>
                <div class="space-y-3">
                  <div class="h-4 bg-gray-100 rounded animate-pulse"></div>
                  <div class="h-4 bg-gray-100 rounded animate-pulse w-5/6"></div>
                  <div class="h-4 bg-gray-100 rounded animate-pulse w-4/6"></div>
                  <div class="h-4 bg-gray-100 rounded animate-pulse w-3/4"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      <!-- 最近解析历史 / 批量解析（本地存储，无需登录） -->
      <section v-if="!videoData && !loading" class="py-6 bg-white">
        <BatchPanel
          v-if="batchMode"
          :seed="batchSeed"
          @download="onBatchDownload"
          @close="batchMode = false"
        />
        <template v-else-if="history.length">
          <div class="max-w-3xl mx-auto px-4 sm:px-6">
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-base font-semibold text-text-primary flex items-center gap-2">
                <svg class="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                最近解析
              </h3>
              <BaseButton @click="clearHistory" variant="ghost" class="!text-xs !text-text-muted !hover:text-red-500">清空记录</BaseButton>
            </div>
            <ul class="space-y-2">
              <li
                v-for="item in history"
                :key="item.url"
                class="group flex items-center gap-3 px-4 py-3 rounded-xl border border-border-light hover:border-primary/40 hover:bg-gray-50 transition-all cursor-pointer"
                @click="handleShowHistoryRecord(item)"
              >
                <!-- 缩略图：有图用图，无图/加载失败统一降级占位（尺寸 w-14 h-10 与 HistoryDrawer 一致） -->
                <VideoThumbnail :url="item.thumbnail" size="sm" />
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium text-text-primary truncate">{{ item.title || item.url }}</p>
                  <p class="text-xs text-text-muted truncate">{{ item.platform }} · {{ formatRelativeTime(item.ts) }}</p>
                </div>
                <BaseButton
                  variant="ghost"
                  size="xs"
                  shape="square"
                  class="opacity-0 group-hover:opacity-100"
                  title="复制链接"
                  @click.stop="copyUrl(item.url, $event)"
                >
                  <template #icon>
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </template>
                </BaseButton>
                <BaseButton
                  variant="ghost"
                  size="xs"
                  shape="square"
                  class="opacity-0 group-hover:opacity-100 hover:text-red-500"
                  title="删除"
                  @click.stop="removeHistory(item.url)"
                >
                  <template #icon>
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </template>
                </BaseButton>
              </li>
            </ul>
          </div>
        </template>
        <!-- 空状态：无历史时展示友好提示（复用全站 EmptyState，与 HistoryDrawer 文案一致） -->
        <div v-else class="max-w-3xl mx-auto px-4 sm:px-6">
          <EmptyState size="md" variant="empty" title="暂无记录" desc="解析一次视频，这里会留下历史" />
        </div>
      </section>
      <!-- 视频信息 + AI 总结：左右双栏同屏布局 -->
      <section v-if="videoData" class="py-4 sm:py-6 bg-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6">
          <div class="flex flex-col lg:flex-row gap-6">
            <!-- 左栏：视频信息 -->
            <div class="w-full lg:w-2/5 lg:flex-shrink-0">
              <VideoResult
                :key="currentUrl"
                :video="videoData"
                :videoUrl="currentUrl"
                :downloading="downloading"
                :downloadProgress="downloadProgress"
                :downloadError="downloadError"
                :summarizing="summarizing"
                @download="onDownload"
                @summarize="handleSummarize"
              />
            </div>
            <!-- 右栏：AI 总结 -->
            <div class="w-full lg:w-3/5 min-w-0">
              <VideoSummary
                :videoUrl="currentUrl"
                :videoTitle="videoData.title"
                :user="currentUser"
                :auto-trigger="!summaryParams.fromHistory"
                :key="summaryParams.key"
                @loading-change="handleSummarizeLoadingChange"
                @need-login="showAuthModal('login')"
                @need-vip="handleOpenVip"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- 视频缓存管理入口 -->
      <section class="py-8 bg-gradient-to-b from-gray-50 to-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6">
          <VideoCacheAdmin />
        </div>
      </section>
    </main>
    <AppFooter />

    <!-- 支付成功/取消提示 -->
    <Teleport to="body">
      <div v-if="paymentToast" class="fixed top-20 left-1/2 -translate-x-1/2 z-[200] animate-toast-in">
        <div :class="[
          'flex items-center gap-3 px-6 py-4 rounded-2xl shadow-xl border',
          paymentToast === 'success' ? 'bg-green-50 border-green-200 text-green-800' : 'bg-orange-50 border-orange-200 text-orange-800'
        ]">
          <svg v-if="paymentToast === 'success'" class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <svg v-else class="w-5 h-5 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <span class="font-medium text-sm">
            {{ paymentToast === 'success' ? 'VIP 开通成功！已为你激活全部高级功能' : '支付已取消，你可以随时再次开通' }}
          </span>
        </div>
      </div>
    </Teleport>

    <!-- 全局轻提示（成功/错误/信息），复用既有 toast 动画 -->
    <Teleport to="body">
      <div v-if="appToast" class="fixed top-32 left-1/2 -translate-x-1/2 z-[200] animate-toast-in">
        <div :class="[
          'flex items-center gap-3 px-6 py-4 rounded-2xl shadow-xl border max-w-sm',
          appToast.type === 'success' ? 'bg-green-50 border-green-200 text-green-800' :
          appToast.type === 'error' ? 'bg-red-50 border-red-200 text-red-800' :
          'bg-primary-light border-primary/20 text-primary'
        ]">
          <svg v-if="appToast.type === 'success'" class="w-5 h-5 text-green-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <svg v-else-if="appToast.type === 'error'" class="w-5 h-5 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <svg v-else class="w-5 h-5 text-primary shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span class="font-medium text-sm">{{ appToast.message }}</span>
        </div>
      </div>
    </Teleport>

    <AuthModal
      :visible="authModalVisible"
      :initialMode="authModalMode"
      @close="authModalVisible = false"
      @success="onAuthSuccess"
    />

    <!-- 下载任务中心（浮动入口 + 抽屉面板） -->
    <DownloadTaskCenter />

    <!-- 登录用户云端历史（抽屉形态，仅在已登录时挂载；
         @reparse 走原解析流程，@view-history-record 从数据库 snapshot 直接还原显示；
         @history-deleted 联动清掉当前 videoData 避免陈旧显示） -->
    <HistoryDrawer
      v-if="currentUser"
      @reparse="handleParse"
      @view-history-record="handleShowHistoryRecord"
      @history-deleted="handleHistoryDeleted"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import AppHeader from './components/AppHeader.vue'
import HeroSection from './components/HeroSection.vue'
import VideoResult from './components/VideoResult.vue'
import VideoSummary from './components/VideoSummary.vue'
import AppFooter from './components/AppFooter.vue'
import AuthModal from './components/AuthModal.vue'
// VideoCacheAdmin (644 行) 改异步加载：首屏不渲染其模板与 onMounted 副作用；
// 用户滚到页面底部才触发加载，完全不影响首屏 FCP/LCP。
const VideoCacheAdmin = defineAsyncComponent({
  loader: () => import('./components/VideoCacheAdmin.vue'),
  loadingComponent: { template: '<div class="min-h-[120px] rounded-xl border border-border-light bg-white animate-pulse" />' },
  delay: 150,
})
import BatchPanel from './components/BatchPanel.vue'
import DownloadTaskCenter from './components/DownloadTaskCenter.vue'
import HistoryDrawer from './components/HistoryDrawer.vue'
import VideoThumbnail from './components/VideoThumbnail.vue'
import BaseButton from './components/ui/BaseButton.vue'
import EmptyState from './components/ui/EmptyState.vue'
import { createCheckoutSession } from './api/payment.js'
import { isLoggedIn, fetchMe } from './api/auth.js'
import { useDownloadManager } from './composables/useDownloadManager.js'
import { useToast } from './composables/useToast.js'
import { useAuth } from './composables/useAuth.js'
import { useAuthModal } from './composables/useAuthModal.js'
import { useHistory } from './composables/useHistory.js'
import { useVideo } from './composables/useVideo.js'
import { copyText } from './utils/clipboard.js'
import { formatRelativeTime } from './utils/relativeTime.js'
import { getApiError } from './utils/error.js'

// ===== 5 个 composable（按依赖顺序实例化）=====
// 顺序：toast → history（依赖 toast）→ auth（依赖 history.clearLocal）→ authModal → video（依赖 toast/history）
const { appToast, showToast } = useToast()
// 把 showToast 挂到 window，让 utils/request.js 的 axios 拦截器和 SSE 错误归一化工具
// 能不依赖 Vue runtime 直接调用（util 文件不在 setup context 中）。
window.__appToast = showToast
const {
  history, loadHistory, refreshHistory, removeHistory, clearHistory,
  addLocalHistory, clearLocal,
} = useHistory({ showToast })
const { currentUser, restoreUser, handleAuthSuccess, handleLogout } = useAuth({
  // 退出登录：自动清掉本地历史，避免下次未登录看到前任账号残留。
  onLogout: () => clearLocal(),
})
const { authModalVisible, authModalMode, showAuthModal } = useAuthModal()
const {
  loading, videoData, currentUrl, summaryParams, summarizing,
  handleSummarize, handleSummarizeLoadingChange,
  handleParse, handleShowHistoryRecord, handleHistoryDeleted,
} = useVideo({ showToast, refreshHistory, addLocalHistory })

// ===== 鉴权协调：登录成功清本地历史 + 拉服务端历史 =====
// useAuth.handleAuthSuccess 只更新 currentUser，宿主协调历史刷新（与 useHistory 隔离）。
function onAuthSuccess(user) {
  handleAuthSuccess(user)
  clearLocal()
  loadHistory()
}

// ===== 下载任务中心（单例，统一管理并发/进度/取消）=====
const downloadManager = useDownloadManager()

// 主流程按钮联动：根据当前视频 URL 关联的最新任务反映下载状态与进度
const currentTask = computed(() => downloadManager.latestTaskForUrl(currentUrl.value))
const downloading = computed(
  () =>
    !!currentTask.value &&
    (currentTask.value.status === 'downloading' || currentTask.value.status === 'queued')
)
const downloadProgress = computed(() => currentTask.value?.progress || 0)
// 下载失败联动：当前视频最新任务处于 error 态时把失败原因透传给 VideoResult，
// 用户不必打开任务中心也能在主流程看到下载失败原因（复用 downloadManager 既有状态）。
const downloadError = computed(() =>
  currentTask.value?.status === 'error' ? (currentTask.value.error || '下载失败，请重试') : ''
)

// 下载按钮：直接走统一下载任务中心（enqueue + 打开面板）
function onDownload(formatId) {
  downloadManager.enqueue(currentUrl.value, formatId, videoData.value?.title)
  downloadManager.openPanel()
}

// ===== 批量解析面板（与 downloadManager 耦合，留在 App.vue）=====
const batchMode = ref(false)
const batchSeed = ref('')

function openBatch(text) {
  batchSeed.value = text || ''
  batchMode.value = true
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function onBatchDownload({ url, formatId, title }) {
  downloadManager.enqueue(url, formatId, title)
  downloadManager.openPanel()
}

// ===== VIP 购买（耦合 window.location，留在 App.vue）=====
async function handleOpenVip() {
  if (!isLoggedIn()) {
    showAuthModal('login')
    return
  }
  try {
    const { checkout_url } = await createCheckoutSession('monthly')
    window.location.href = checkout_url
  } catch (err) {
    showToast(getApiError(err, '', '创建支付失败'), 'error')
  }
}

// ===== 支付结果处理（耦合 window.location，留在 App.vue）=====
const paymentToast = ref(null)
// 支付 toast 自动消失 + Stripe 回调后延迟刷新当前用户；保留 timerId 便于
// 多个回调同时抵达清理上一个 timer，避免 5s 后多个 timer 叠加关闭 toast。
let paymentToastTimer = null
let paymentMeRefreshTimer = null

function checkPaymentResult() {
  const params = new URLSearchParams(window.location.search)
  const payment = params.get('payment')
  if (payment === 'success' || payment === 'cancel') {
    paymentToast.value = payment
    window.history.replaceState({}, '', window.location.pathname)
    if (payment === 'success' && isLoggedIn()) {
      // 直接刷新当前用户（套餐变更后 VIP 状态同步），失败忽略下次 fetchMe 自然处理。
      clearTimeout(paymentMeRefreshTimer)
      paymentMeRefreshTimer = setTimeout(async () => {
        try { currentUser.value = await fetchMe() } catch {}
      }, 1000)
    }
    clearTimeout(paymentToastTimer)
    paymentToastTimer = setTimeout(() => { paymentToast.value = null }, 5000)
  }
}

// ===== 复制链接到剪贴板，带轻提示反馈（与 composable 隔离，留在 App.vue）=====
async function copyUrl(url, e) {
  if (e) e.stopPropagation()
  const ok = await copyText(url)
  showToast(ok ? '链接已复制' : '复制失败，请手动复制', ok ? 'success' : 'error')
}

onMounted(async () => {
  // restoreUser 失败会自动 handleLogout（清 currentUser + clearLocal）；成功后无论登录与否
  // 都调 loadHistory（登录走服务端 / 未登录走 localStorage）。
  await restoreUser()
  checkPaymentResult()
  loadHistory()
  downloadManager.initDownloadManager()
})
onBeforeUnmount(() => {
  delete window.__appToast
  // 支付回调相关的两个 timer 均需清理，避免组件销毁后仍触发（修改已卸载的 ref）
  if (paymentToastTimer) clearTimeout(paymentToastTimer)
  if (paymentMeRefreshTimer) clearTimeout(paymentMeRefreshTimer)
})
</script>

<style>
@keyframes toast-in {
  from { opacity: 0; transform: translate(-50%, -10px); }
  to { opacity: 1; transform: translate(-50%, 0); }
}
.animate-toast-in {
  animation: toast-in 0.3s ease-out;
}
</style>