<template>
  <header class="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-border-light">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <a href="/" class="flex items-center gap-3" title="SaveAny - 免费在线万能视频下载器">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center shadow-sm" role="img" aria-label="SaveAny Logo">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <span class="text-lg font-semibold text-text-primary tracking-tight">SaveAny</span>
        <span class="hidden sm:inline text-xs text-text-muted bg-primary-light px-2 py-0.5 rounded-full">万能视频下载</span>
      </a>
      <nav class="hidden md:flex items-center gap-2 text-sm text-text-secondary" aria-label="主导航">
        <!-- 最近解析：点击展开历史下拉，避免导航链接点击无效 -->
        <div class="relative" ref="historyRef">
          <button
            @click="historyOpen = !historyOpen"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full hover:bg-gray-50 transition-colors cursor-pointer"
            :class="{ 'text-primary bg-primary-light': historyOpen }"
            title="查看最近解析记录"
            aria-haspopup="menu"
            aria-controls="history-dropdown"
            :aria-expanded="historyOpen"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            最近解析
            <span v-if="history.length" class="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold bg-primary text-white">
              {{ history.length }}
            </span>
            <svg class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': historyOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <div
            v-if="historyOpen"
            id="history-dropdown"
            role="menu"
            class="absolute left-0 top-full mt-2 w-80 bg-white rounded-xl border border-border shadow-xl py-2 animate-menu-in"
          >
            <div class="px-4 py-2 flex items-center justify-between border-b border-border">
              <p class="text-xs font-semibold text-text-muted uppercase tracking-wider">最近解析</p>
              <BaseButton
                v-if="history.length"
                @click="$emit('clear-history')"
                variant="ghost"
                class="!text-xs !text-text-muted !hover:text-red-500"
                title="清空所有本地记录"
              >
                清空
              </BaseButton>
            </div>
            <div v-if="!history.length" class="px-4 py-2">
              <EmptyState size="sm" variant="empty" title="暂无记录" desc="解析一次视频试试" />
            </div>
            <ul v-else class="max-h-80 overflow-y-auto py-1">
              <li
                v-for="item in recentHistory"
                :key="(item.id != null ? item.id : item.url) + '-' + item.ts"
                class="group px-3"
              >
                <div
                  role="button"
                  tabindex="0"
                  @click="onPickHistory(item.url)"
                  @keydown.enter.prevent="onPickHistory(item.url)"
                  @keydown.space.prevent="onPickHistory(item.url)"
                  class="w-full text-left px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer flex items-start gap-2"
                  :title="item.url"
                >
                  <div class="flex-shrink-0 w-7 h-7 mt-0.5 rounded-md bg-primary-light text-primary flex items-center justify-center text-xs font-semibold">
                    {{ (item.platform || '?').slice(0, 2).toUpperCase() }}
                  </div>
                  <div class="min-w-0 flex-1">
                    <p class="text-sm font-medium text-text-primary truncate">{{ item.title || item.url }}</p>
                    <p class="text-xs text-text-muted truncate">
                      {{ item.platform || '未知平台' }} · {{ formatRelativeTime(item.ts) }}
                    </p>
                  </div>
                  <BaseButton
                    type="button"
                    @click.stop="onRemoveHistory(item)"
                    variant="ghost"
                    class="!opacity-0 group-hover:opacity-100 !text-text-muted !hover:text-red-500 !transition-opacity !p-1 !self-center"
                    title="删除这条"
                  >
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </BaseButton>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </nav>
      <div class="flex items-center gap-3">
        <!-- 未登录 -->
        <template v-if="!user">
          <BaseButton @click="$emit('login')" variant="ghost" class="!hidden !sm:inline-flex !items-center !px-4 !py-2 !rounded-full !text-sm !font-medium !text-text-secondary !hover:text-primary !hover:bg-gray-50">
            登录
          </BaseButton>
          <BaseButton @click="$emit('register')" variant="primary" class="!hidden !sm:inline-flex !items-center !gap-1.5 !px-4 !py-2 !rounded-full !text-sm !font-medium !shadow-sm">
            免费注册
          </BaseButton>
        </template>

        <!-- 已登录 -->
        <template v-else>
          <BaseButton v-if="!user.is_vip" @click="$emit('open-vip')" variant="ghost" class="!hidden !sm:inline-flex !items-center !gap-1.5 !px-4 !py-2 !rounded-full !text-sm !font-medium !text-primary !bg-primary-light !hover:bg-primary/15">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
            </svg>
            开通 VIP
          </BaseButton>
          <span v-else class="hidden sm:inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-yellow-400 to-orange-400 text-white shadow-sm">
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            VIP
          </span>

          <!-- 用户下拉菜单 -->
          <div class="relative" ref="menuRef">
            <BaseButton
              @click="menuOpen = !menuOpen"
              variant="ghost"
              class="!flex !items-center !gap-2 !px-3 !py-2 !rounded-full !hover:bg-gray-50"
              aria-haspopup="menu"
              aria-controls="user-menu"
              :aria-expanded="menuOpen"
            >
              <div class="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center text-white text-sm font-semibold">
                {{ (user?.email || '?')[0]?.toUpperCase() }}
              </div>
              <svg class="w-4 h-4 text-text-muted transition-transform" :class="{ 'rotate-180': menuOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </BaseButton>
            <div
            v-if="menuOpen"
            id="user-menu"
            role="menu"
            class="absolute right-0 top-full mt-2 w-56 bg-white rounded-xl border border-border shadow-xl py-2 animate-menu-in"
          >
              <div class="px-4 py-2 border-b border-border">
                <p class="text-sm font-medium text-text-primary truncate">{{ user.email }}</p>
                <p class="text-xs text-text-muted mt-0.5">
                  {{ user.is_vip ? 'VIP 会员' : '免费用户' }}
                  <span v-if="user.is_vip && user.vip_expire_at" class="ml-1">· 到期 {{ formatDate(user.vip_expire_at) }}</span>
                </p>
              </div>
              <BaseButton v-if="!user.is_vip" @click="menuOpen = false; $emit('open-vip')" variant="ghost" class="!w-full !text-left !px-4 !py-2.5 !text-sm !text-primary !hover:bg-primary-light !flex !items-center !gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                开通 VIP
              </BaseButton>
              <BaseButton @click="menuOpen = false; $emit('logout')" variant="ghost" class="!w-full !text-left !px-4 !py-2.5 !text-sm !text-text-secondary !hover:bg-gray-50 !flex !items-center !gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                退出登录
              </BaseButton>
            </div>
          </div>
        </template>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import EmptyState from './ui/EmptyState.vue'
import BaseButton from './ui/BaseButton.vue'
import { formatRelativeTime } from '../utils/relativeTime.js'
import { formatDate } from '../utils/format.js'

const props = defineProps({
  user: { type: Object, default: null },
  history: { type: Array, default: () => [] },
})

const emit = defineEmits(['login', 'register', 'logout', 'open-vip', 'reparse', 'remove-history', 'clear-history'])

const menuOpen = ref(false)
const menuRef = ref(null)
const historyOpen = ref(false)
const historyRef = ref(null)

const RECENT_HISTORY_LIMIT = 5
const recentHistory = computed(() => (props.history || []).slice(0, RECENT_HISTORY_LIMIT))

function onPickHistory(url) {
  historyOpen.value = false
  emit('reparse', url)
}

function onRemoveHistory(item) {
  // 登录态优先用 id 删（与服务端 DELETE /api/history/{id} 对齐），
  // 未登录态没有 id，回退到 url。
  emit('remove-history', item.id != null ? item.id : item.url)
}

function handleClickOutside(e) {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    menuOpen.value = false
  }
  if (historyRef.value && !historyRef.value.contains(e.target)) {
    historyOpen.value = false
  }
}

// Esc 键关闭任意打开的 dropdown（与 HistoryDrawer / SubtitlePanel 风格一致）
function handleKeydown(e) {
  if (e.key !== 'Escape') return
  if (menuOpen.value) menuOpen.value = false
  if (historyOpen.value) historyOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('keydown', handleKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
@keyframes menu-in {
  from { opacity: 0; transform: translateY(-4px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.animate-menu-in {
  animation: menu-in 0.15s ease-out;
}
</style>
