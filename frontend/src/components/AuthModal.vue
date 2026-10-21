<!--
  AuthModal - 登录/注册弹窗（基于 BaseModal）
  - 复用 BaseModal 的 ARIA 容器、Esc 关闭、点击遮罩关闭、打开自动聚焦
  - email input 用 autofocus 让 BaseModal 自动聚焦第一个表单字段
  - 提密码 toggle 按钮带 aria-label / aria-pressed
-->
<template>
  <BaseModal
    :model-value="visible"
    @update:model-value="(v) => !v && $emit('close')"
    :title="isLogin ? '登录账号' : '注册账号'"
    :subtitle="isLogin ? '登录以使用 AI 视频总结和 VIP 功能' : '创建账号，开始使用全部功能'"
    max-width="md"
  >
    <form @submit.prevent="handleSubmit" class="px-8 pb-8">
      <div class="space-y-4">
        <div>
          <label for="auth-email" class="block text-sm font-medium text-text-primary mb-1.5">邮箱地址</label>
          <input
            id="auth-email"
            ref="emailInput"
            v-model="email"
            type="email"
            required
            autofocus
            placeholder="your@email.com"
            autocomplete="email"
            class="w-full h-11 px-4 rounded-xl border border-border bg-white text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
            :disabled="submitting"
          />
        </div>
        <div>
          <label for="auth-password" class="block text-sm font-medium text-text-primary mb-1.5">密码</label>
          <div class="relative">
            <input
              id="auth-password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              required
              minlength="6"
              placeholder="至少 6 位密码"
              autocomplete="current-password"
              class="w-full h-11 px-4 pr-11 rounded-xl border border-border bg-white text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
              :disabled="submitting"
            />
            <BaseButton
              type="button"
              @click="showPassword = !showPassword"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              :aria-pressed="showPassword"
              variant="ghost"
              class="!absolute !right-3 !top-1/2 !-translate-y-1/2 !text-text-muted !hover:text-text-secondary"
            >
              <svg v-if="showPassword" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              </svg>
              <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              </svg>
            </BaseButton>
          </div>
        </div>
      </div>

      <div v-if="error" class="mt-4 p-3 rounded-xl bg-red-50 border border-red-200">
        <p class="text-sm text-red-800">{{ error }}</p>
      </div>

      <BaseButton
        type="submit"
        :disabled="!canSubmit"
        :loading="submitting"
        variant="primary"
        block
        class="mt-6"
      >
        {{ submitting ? '请稍候...' : (isLogin ? '登录' : '注册') }}
      </BaseButton>

      <p class="mt-4 text-center text-sm text-text-secondary">
        {{ isLogin ? '还没有账号？' : '已有账号？' }}
        <BaseButton type="button" @click="toggleMode" variant="ghost" class="!text-primary !font-medium !hover:underline">
          {{ isLogin ? '立即注册' : '去登录' }}
        </BaseButton>
      </p>
    </form>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { register, login } from '../api/auth'
import BaseModal from './ui/BaseModal.vue'
import BaseButton from './ui/BaseButton.vue'
import { getApiError } from '../utils/error.js'

const props = defineProps({
  visible: Boolean,
  initialMode: { type: String, default: 'login' },
})

const emit = defineEmits(['close', 'success'])

const isLogin = ref(props.initialMode === 'login')
const email = ref('')
const password = ref('')
const showPassword = ref(false)
const submitting = ref(false)
const error = ref('')
const emailInput = ref(null)

// AuthModal 常驻挂载（App.vue 未用 v-if），initialMode 由父组件在每次 open 前更新。
// 若不监听 prop 变化，isLogin 只在首次初始化一次，导致点「免费注册」仍显示登录表单。
watch(
  () => props.initialMode,
  (mode) => {
    isLogin.value = mode === 'login'
    error.value = ''
  }
)

// 修复模式残留：用户在弹窗内手动切换过模式后关闭，父组件下次以相同 initialMode 再次打开时
// initialMode watch 不会触发（值未变），isLogin 会停留在上次手动切换的结果，
// 例如「点登录 → 手动切到注册 → 关闭 → 再点登录」仍显示注册表单。
// 打开时强制按 initialMode 重置，保证每次打开的模式与入口意图一致。
watch(
  () => props.visible,
  (v) => {
    if (v) {
      isLogin.value = props.initialMode === 'login'
      error.value = ''
    }
  }
)

// 提交按钮可用性：邮箱与密码任一为空时禁用，避免用户点击后被 HTML5 required 静默拦截造成「点了没反应」的错觉。
// 计算时同步 trim 邮箱，与 handleSubmit 真实提交值保持一致（防止用户输入 "  test@x.com  " 时按钮仍可点）。
const canSubmit = computed(() => !submitting.value && email.value.trim() && password.value)

function toggleMode() {
  isLogin.value = !isLogin.value
  error.value = ''
}

async function handleSubmit() {
  error.value = ''
  // 提交前 trim email：避免用户从其他地方粘贴邮箱带入前后空白导致后端格式校验失败。
  const trimmedEmail = email.value.trim()
  email.value = trimmedEmail
  submitting.value = true
  try {
    const user = isLogin.value
      ? await login(trimmedEmail, password.value)
      : await register(trimmedEmail, password.value)
    emit('success', user)
    emit('close')
    email.value = ''
    password.value = ''
  } catch (err) {
    error.value = getApiError(err, '', '操作失败')
  } finally {
    submitting.value = false
  }
}
</script>