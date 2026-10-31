import { ref } from 'vue'
import { parseVideo, saveVideoCache } from '../api/video.js'
import { getApiError, extractErrorMsg } from '../utils/error.js'
import { normalizeHistoryUrl } from './useHistory.js'

/**
 * 历史 snapshot 缺失时的统一兜底提示文案。
 * HistoryDrawer 在 emit view-history-record 前预检 snapshot（防止抽屉误关），
 * useVideo.handleShowHistoryRecord 内部兜底检查。两处共用同一句文案。
 */
export const MISSING_SNAPSHOT_TIP =
  '该历史无完整数据，请在主输入框粘贴链接重新解析'

// handleParse 版本号守卫：连续快速点击解析（HeroSection/AppHeader/HistoryDrawer 任一来源触发）时，
// 慢请求返回后不会覆盖快请求的最新结果（race condition）。
let parseSeq = 0

/**
 * 视频功能 composable（替换原 App.vue 内联 videoData/currentUrl/summaryParams/summarizing + 6 个函数）。
 * - summaryParams: Step 2 合并的双 ref 对象（key + fromHistory），所有赋值走 bumpSummary()。
 * - handleParse 内部根据宿主注入的界面登录态走 refreshHistory() 或 addLocalHistory()，
 *   避免 request 层懒创建 demo token 后把未登录界面误判为已登录。
 * - handleHistoryDeleted 不直接读 useVideo 外的状态,自包含 currentUrl 检查。
 */
export function useVideo({ showToast, refreshHistory, addLocalHistory, isAuthed } = {}) {
  const loading = ref(false)
  const videoData = ref(null)
  const currentUrl = ref('')
  // Step 2 合并的双 ref:key 作 :key 重建触发器,fromHistory 控制 autoTrigger
  const summaryParams = ref({ key: 0, fromHistory: false })
  const summarizing = ref(false)

  function bumpSummary(fromHistory) {
    summaryParams.value = {
      ...summaryParams.value,
      key: summaryParams.value.key + 1,
      fromHistory,
    }
  }

  function handleSummarizeLoadingChange(isLoading) {
    summarizing.value = isLoading
  }

  function handleSummarize() {
    bumpSummary(false)
  }

  async function handleParse(url) {
    const mySeq = ++parseSeq
    loading.value = true
    videoData.value = null
    currentUrl.value = url
    // 进入 parse 模式:先重置 fromHistory（无论成功失败都重置,确保 autoTrigger 正确）
    summaryParams.value = { ...summaryParams.value, fromHistory: false }
    try {
      const res = await parseVideo(url)
      // 版本号守卫：仅在本次调用仍是最新时才更新视频数据，避免慢请求覆盖快请求结果
      if (mySeq !== parseSeq) return
      if (res.success) {
        videoData.value = res.data
        // parse 成功才 bump 触发 VideoSummary 重建
        bumpSummary(false)
        if (isAuthed && isAuthed()) {
          if (refreshHistory) refreshHistory()
        } else {
          if (addLocalHistory) addLocalHistory(url, res.data)
        }
        // 解析结果 best-effort 归档到视频缓存,供后台管理查看（失败不影响体验）。
        // 补齐直链与格式清单：后台「播放/下载/复制」按钮依赖 direct_url/download_url，
        // 不做归档时这两列恒为空、按钮永远不显示。抖音解析结果在 formats[]._direct_url
        // 内携带直链；yt-dlp 侧解析阶段无直链（播放时才按需拉取），故有则带上、无则留空，
        // 由后台按字段是否为空自行隐藏按钮。
        const formats = Array.isArray(res.data.formats) ? res.data.formats : []
        const playable = formats.find((f) => f && f._direct_url)
        const mediaUrl = playable ? playable._direct_url : ''
        const fileSize = formats.reduce(
          (max, f) => Math.max(max, (f && (f.filesize || f.filesize_approx)) || 0),
          0
        )
        // 分辨率/编码取自最高质量的可用格式：后端 video_cache 有 width/height/fps/codec
        // 列，不传则恒为 0/NULL，后台缓存列表拿不到画质信息。
        const bestFormat = formats.reduce(
          (best, f) =>
            f && (!best || (f.height || 0) > (best.height || 0)) ? f : best,
          null
        )
        saveVideoCache({
          url,
          video_info: {
            platform: res.data.platform,
            video_id: res.data.id,
            title: res.data.title,
            description: res.data.description,
            uploader: res.data.uploader,
            thumbnail: res.data.thumbnail,
            direct_url: mediaUrl,
            download_url: mediaUrl,
            formats,
          },
          metadata: {
            duration: res.data.duration,
            file_size: fileSize || null,
            quality: playable && playable.height ? `${playable.height}p` : '',
            format: playable ? playable.format_id : '',
            width: (bestFormat && bestFormat.width) || 0,
            height: (bestFormat && bestFormat.height) || 0,
            fps: (bestFormat && bestFormat.fps) || 0,
            codec: (bestFormat && (bestFormat.vcodec || bestFormat.codec)) || null,
          },
          success: true,
        }).catch(() => {})
      } else {
        if (showToast) showToast('解析失败：' + extractErrorMsg(res.error), 'error')
      }
    } catch (err) {
      if (mySeq !== parseSeq) return
      if (showToast) showToast(getApiError(err, '解析失败'), 'error')
    } finally {
      // loading 仅由最新请求复位（旧的 finally 跳过）
      if (mySeq === parseSeq) loading.value = false
    }
  }

  /**
   * 从历史抽屉点解析记录进入：直接用数据库落库的 snapshot 还原 videoData 显示,
   * 不走 /api/parse 重跑 yt-dlp。硬约束：即便无 snapshot 也绝不降级重跑——按用户要求
   * 「应该从数据库中直接显示内容」。
   */
  function handleShowHistoryRecord(item) {
    const snapshot = item && item.snapshot
    if (!snapshot || typeof snapshot !== 'object') {
      if (showToast) showToast(MISSING_SNAPSHOT_TIP, 'info')
      return
    }
    // 作废仍在途的 parse 请求：否则慢请求返回时 mySeq === parseSeq 的守卫仍成立，
    // 会把刚还原的历史 snapshot 覆盖成慢请求结果（race condition）。
    parseSeq += 1
    loading.value = false
    videoData.value = snapshot
    // 兼容两种历史条目字段：服务端是 video_url，本地（addLocalHistory）是 url。
    currentUrl.value = item.video_url || item.url || ''
    // 点历史回看：不自动跑 AI 总结,避免对已总结过的视频重跑浪费配额,
    // 用户可手动点 VideoResult 顶部的「AI 总结」按钮触发。
    bumpSummary(true)
    // 抽屉由 HistoryDrawer 自己关闭；窗口滚到顶部让用户立即看到还原的视频结果。
    try { window.scrollTo({ top: 0, behavior: 'smooth' }) } catch {}
  }

  function clearCurrentVideo() {
    parseSeq += 1
    videoData.value = null
    currentUrl.value = ''
    loading.value = false
    bumpSummary(false)
  }

  /**
   * 抽屉删除/清空历史时的联动清理：若被删条目对应当前正在显示的视频（parse 类型且 url 一致）,
   * 同步清掉 videoData / currentUrl / 触发 VideoSummary 重建,避免用户看到陈旧内容。
   */
  function handleHistoryDeleted(item) {
    if (!item || item.type !== 'parse') return
    // 归一化比对：item.video_url 是后端入库前归一化后的形态，currentUrl 是用户原始输入；
    // 两侧不归一化直接 === 比较，用户粘贴带 www./http/fragment 的 URL 时会漏判，
    // 导致历史已删除但 videoData 仍残留陈旧内容。
    if (!currentUrl.value) return
    if (normalizeHistoryUrl(item.video_url) !== normalizeHistoryUrl(currentUrl.value)) return
    // 作废在途 parse：避免删除联动清空后又被慢请求重新填充陈旧内容。
    clearCurrentVideo()
    if (showToast) showToast('当前视频对应历史已删除', 'info')
  }

  function handleHistoryCleared() {
    if (!videoData.value && !currentUrl.value) return
    clearCurrentVideo()
  }

  return {
    loading,
    videoData,
    currentUrl,
    summaryParams,
    summarizing,
    bumpSummary,
    handleSummarize,
    handleSummarizeLoadingChange,
    handleParse,
    handleShowHistoryRecord,
    handleHistoryDeleted,
    handleHistoryCleared,
  }
}