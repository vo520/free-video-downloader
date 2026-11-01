<template>
  <header class="sticky top-0 z-dropdown border-b border-white/70 bg-white/70 backdrop-blur-xl supports-[backdrop-filter]:bg-white/60">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <a href="/" class="flex items-center gap-3" title="SaveAny - 免费在线万能视频下载器">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center shadow-lg shadow-primary/20 ring-1 ring-white/40" role="img" aria-label="SaveAny Logo">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <span class="text-lg font-black text-text-primary tracking-[-0.03em]">SaveAny</span>
        <span class="hidden sm:inline text-xs text-primary bg-primary-light/80 px-2.5 py-1 rounded-full font-medium">万能视频下载</span>
      </a>
      <nav class="hidden md:flex items-center gap-2 text-sm text-text-secondary" aria-label="主导航">
        <!-- 桌面端导航内容（移动端由下方汉堡菜单承载） -->
        <!-- 最近解析：点击展开历史下拉，避免导航链接点击无效 -->
        <div class="relative" ref="historyRef">
          <button
            @click="historyOpen = !historyOpen"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full hover:bg-white hover:shadow-sm transition-all cursor-pointer"
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
            class="absolute left-0 top-full mt-2 w-80 bg-white/95 rounded-2xl border border-white/80 shadow-2xl shadow-slate-900/10 py-2 backdrop-blur animate-menu-in"
          >
            <div class="px-4 py-2 flex items-center justify-between border-b border-border">
              <p class="text-xs font-semibold text-text-muted uppercase tracking-wider">最近解析</p>
              <BaseButton
                v-if="history.length"
                @click="$emit('clear-history')"
                variant="ghost"
                class="text-xs! text-text-muted! hover:text-error-text!"
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
                  class="w-full text-left px-3 py-2 rounded-lg hover:bg-surface-muted transition-colors cursor-pointer flex items-start gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
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
                    class="text-text-muted! hover:text-error-text! transition-opacity! p-1! self-center! w-9! h-9! opacity-100! sm:opacity-0! sm:group-hover:opacity-100!"
                    title="删除这条"
                    aria-label="删除这条记录"
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
          <!-- 访客模式徽标：明确告知「当前借用公共演示账号」，避免用户误以为自己是已登录的个人账号 -->
          <div v-if="guest" class="relative" ref="guestRef">
            <BaseButton
              @click="guestOpen = !guestOpen"
              variant="ghost"
              class="hidden! sm:inline-flex! items-center! gap-1.5! px-3! py-2! rounded-full! text-sm! font-medium! text-text-secondary! hover:bg-surface-muted!"
              aria-haspopup="menu"
              :aria-expanded="guestOpen"
            >
              <span class="w-2 h-2 rounded-full bg-warning" aria-hidden="true"></span>
              访客模式
              <svg class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': guestOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </BaseButton>
            <div
              v-if="guestOpen"
              id="guest-menu"
              role="menu"
              class="absolute right-0 top-full mt-2 w-64 bg-white/95 rounded-2xl border border-white/80 shadow-2xl shadow-slate-900/10 py-2 backdrop-blur animate-menu-in"
            >
              <div class="px-4 py-2.5 border-b border-border">
                <p class="text-sm font-medium text-text-primary">访客模式</p>
                <p class="text-xs text-text-muted mt-1 leading-relaxed">
                  当前使用公共演示账号，解析历史只保存在本机，不会同步到云端。
                </p>
              </div>
              <BaseButton @click="guestOpen = false; $emit('end-guest')" variant="ghost" class="w-full! text-left! px-4! py-2.5! text-sm! text-text-secondary! hover:bg-surface-muted! flex! items-center! gap-2!">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                结束访客会话
              </BaseButton>
            </div>
          </div>
          <BaseButton @click="$emit('login')" variant="ghost" class="hidden! sm:inline-flex! items-center! px-4! py-2! rounded-full! text-sm! font-medium! text-text-secondary! hover:text-primary! hover:bg-surface-muted!">
            登录
          </BaseButton>
          <BaseButton @click="$emit('register')" variant="primary" class="hidden! sm:inline-flex! items-center! gap-1.5! px-4! py-2! rounded-full! text-sm! font-medium! shadow-sm!">
            免费注册
          </BaseButton>
        </template>

        <!-- 已登录 -->
        <template v-else>
          <BaseButton v-if="!user.is_vip" @click="$emit('open-vip')" :loading="vipLoading" variant="ghost" class="hidden! sm:inline-flex! items-center! gap-1.5! px-4! py-2! rounded-full! text-sm! font-medium! text-primary! bg-primary-light! hover:bg-primary/15!">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
            </svg>
            开通 VIP
          </BaseButton>
          <span v-else class="hidden sm:inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-warning to-warning-text text-white shadow-sm">
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
              class="flex! items-center! gap-2! px-3! py-2! rounded-full! hover:bg-surface-muted!"
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
            class="absolute right-0 top-full mt-2 w-56 bg-white/95 rounded-2xl border border-white/80 shadow-2xl shadow-slate-900/10 py-2 backdrop-blur animate-menu-in"
          >
              <div class="px-4 py-2 border-b border-border">
                <!-- 访客：显示「访客模式」而不是 demo@local.com，
                     避免用户把公共演示账号误当成自己的个人账号。 -->
                <p class="text-sm font-medium text-text-primary truncate">
                  {{ guest ? '访客模式' : user.email }}
                </p>
                <p class="text-xs text-text-muted mt-0.5">
                  <template v-if="guest">使用公共演示账号 · 历史仅保存在本机</template>
                  <template v-else>
                    {{ user.is_vip ? 'VIP 会员' : '免费用户' }}
                    <span v-if="user.is_vip && user.vip_expire_at" class="ml-1">· 到期 {{ formatDate(user.vip_expire_at) }}</span>
                  </template>
                </p>
              </div>
              <BaseButton v-if="!user.is_vip && !guest" @click="menuOpen = false; $emit('open-vip')" :loading="vipLoading" variant="ghost" class="w-full! text-left! px-4! py-2.5! text-sm! text-primary! hover:bg-primary-light! flex! items-center! gap-2!">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                开通 VIP
              </BaseButton>
              <BaseButton @click="menuOpen = false; $emit('open-orders')" variant="ghost" class="w-full! text-left! px-4! py-2.5! text-sm! text-text-secondary! hover:bg-surface-muted! flex! items-center! gap-2!">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012 2h2a2 2 0 012 2M9 10h6m-6 4h6" />
                </svg>
                我的订单
              </BaseButton>
              <!-- 视频缓存管理是运维级后台（服务端仅管理员可访问），非管理员不展示入口 -->
              <BaseButton v-if="user.is_admin" @click="menuOpen = false; $emit('open-cache-admin')" variant="ghost" class="w-full! text-left! px-4! py-2.5! text-sm! text-text-secondary! hover:bg-surface-muted! flex! items-center! gap-2!">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2 3.6 3.5 8 3.5s8-1.5 8-3.5V7M4 7c0 2 3.6 3.5 8 3.5S20 9 20 7m-16 0c0-2 3.6-3.5 8-3.5S20 5 20 7m-16 5c0 2 3.6 3.5 8 3.5s8-1.5 8-3.5" />
                </svg>
                视频缓存管理
              </BaseButton>
              <BaseButton @click="menuOpen = false; $emit(guest ? 'end-guest' : 'logout')" variant="ghost" class="w-full! text-left! px-4! py-2.5! text-sm! text-text-secondary! hover:bg-surface-muted! flex! items-center! gap-2!">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                {{ guest ? '结束访客会话' : '退出登录' }}
              </BaseButton>
            </div>
          </div>
        </template>

        <!-- 移动端菜单：<md 时承载「最近解析」与账号操作，
             否则这些入口在窄屏完全不可达（桌面导航 hidden md:flex、
             登录/注册按钮 hidden sm:inline-flex）。 -->
        <button
          @click="mobileOpen = !mobileOpen"
          class="md:hidden w-11 h-11 flex items-center justify-center rounded-xl hover:bg-surface-muted transition-colors cursor-pointer"
          :aria-expanded="mobileOpen"
          aria-controls="mobile-menu"
          aria-label="打开菜单"
        >
          <svg class="w-5 h-5 text-text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path v-if="!mobileOpen" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
            <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 移动端下拉面板 -->
    <Transition name="menu">
      <div
        v-if="mobileOpen"
        id="mobile-menu"
        class="md:hidden border-t border-border bg-white/95 backdrop-blur-xl shadow-lg"
      >
        <div class="max-w-7xl mx-auto px-4 py-3 space-y-1">
          <!-- 最近解析：只切换内嵌列表，不能顺手把 mobileOpen 置 false。
               面板由 v-if="mobileOpen" 控制，一旦关闭会立刻卸载，
               用户永远看不到刚展开的历史列表（等于该入口点了没反应）。 -->
          <button
            @click="mobileHistoryOpen = !mobileHistoryOpen"
            class="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm text-text-secondary hover:bg-surface-muted transition-colors cursor-pointer"
            :aria-expanded="mobileHistoryOpen"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            最近解析
            <span v-if="history.length" class="ml-auto inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold bg-primary text-white">
              {{ history.length }}
            </span>
          </button>
          <ul v-if="mobileHistoryOpen && recentHistory.length" class="pl-6 pb-1 space-y-0.5">
            <li v-for="item in recentHistory" :key="(item.id != null ? item.id : item.url) + '-' + item.ts">
              <button
                @click="mobileOpen = false; mobileHistoryOpen = false; onPickHistory(item.url)"
                class="w-full text-left px-3 py-2 rounded-lg text-sm text-text-primary hover:bg-surface-muted transition-colors cursor-pointer truncate"
              >
                {{ item.title || item.url }}
              </button>
            </li>
          </ul>
          <p v-else-if="mobileHistoryOpen" class="pl-6 py-2 text-sm text-text-muted">暂无记录</p>

          <div class="border-t border-border-light my-2"></div>

          <!-- 账号操作 -->
          <template v-if="!user">
            <BaseButton @click="mobileOpen = false; $emit('login')" variant="ghost" class="w-full! justify-start! px-3! py-2.5! text-sm! text-text-secondary!">
              登录
            </BaseButton>
            <BaseButton @click="mobileOpen = false; $emit('register')" variant="primary" class="w-full! px-3! py-2.5! text-sm!">
              免费注册
            </BaseButton>
            <template v-if="guest">
              <div class="px-3 py-2 rounded-xl bg-surface-muted/70">
                <p class="text-sm font-medium text-text-primary">访客模式</p>
                <p class="text-xs text-text-muted mt-0.5 leading-relaxed">
                  当前使用公共演示账号，解析历史只保存在本机。
                </p>
              </div>
              <BaseButton @click="mobileOpen = false; $emit('end-guest')" variant="ghost" class="w-full! justify-start! px-3! py-2.5! text-sm! text-text-secondary!">
                结束访客会话
              </BaseButton>
            </template>
          </template>
          <template v-else>
            <div class="px-3 py-2">
              <p class="text-sm font-medium text-text-primary truncate">
                {{ guest ? '访客模式' : user.email }}
              </p>
              <p class="text-xs text-text-muted mt-0.5">
                <template v-if="guest">使用公共演示账号 · 历史仅保存在本机</template>
                <template v-else>
                  {{ user.is_vip ? 'VIP 会员' : '免费用户' }}
                  <span v-if="user.is_vip && user.vip_expire_at" class="ml-1">· 到期 {{ formatDate(user.vip_expire_at) }}</span>
                </template>
              </p>
            </div>
            <BaseButton v-if="!user.is_vip && !guest" @click="mobileOpen = false; $emit('open-vip')" :loading="vipLoading" variant="ghost" class="w-full! justify-start! px-3! py-2.5! text-sm! text-primary!">
              开通 VIP
            </BaseButton>
            <BaseButton @click="mobileOpen = false; $emit('open-orders')" variant="ghost" class="w-full! justify-start! px-3! py-2.5! text-sm! text-text-secondary!">
              我的订单
            </BaseButton>
            <BaseButton v-if="user.is_admin" @click="mobileOpen = false; $emit('open-cache-admin')" variant="ghost" class="w-full! justify-start! px-3! py-2.5! text-sm! text-text-secondary!">
              视频缓存管理
            </BaseButton>
            <BaseButton @click="mobileOpen = false; $emit(guest ? 'end-guest' : 'logout')" variant="ghost" class="w-full! justify-start! px-3! py-2.5! text-sm! text-text-secondary!">
              {{ guest ? '结束访客会话' : '退出登录' }}
            </BaseButton>
          </template>
        </div>
      </div>
    </Transition>
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
  vipLoading: { type: Boolean, default: false },
  // 是否处于访客会话（借用公共演示账号的匿名状态）
  guest: { type: Boolean, default: false },
})

const emit = defineEmits(['login', 'register', 'logout', 'end-guest', 'open-vip', 'reparse', 'remove-history', 'clear-history', 'open-cache-admin', 'open-orders'])

const menuOpen = ref(false)
const menuRef = ref(null)
const historyOpen = ref(false)
const historyRef = ref(null)
// 访客徽标下拉（未登录分支）
const guestOpen = ref(false)
const guestRef = ref(null)
// 移动端菜单（<md 承载导航与账号操作）
const mobileOpen = ref(false)
const mobileHistoryOpen = ref(false)

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
  if (guestRef.value && !guestRef.value.contains(e.target)) {
    guestOpen.value = false
  }
}

// Esc 键关闭任意打开的 dropdown（与 HistoryDrawer / SubtitlePanel 风格一致）
function handleKeydown(e) {
  if (e.key !== 'Escape') return
  if (menuOpen.value) menuOpen.value = false
  if (historyOpen.value) historyOpen.value = false
  if (guestOpen.value) guestOpen.value = false
  if (mobileOpen.value) mobileOpen.value = false
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

/* 移动端下拉面板的展开/收起 */
.menu-enter-active,
.menu-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.menu-enter-from,
.menu-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
