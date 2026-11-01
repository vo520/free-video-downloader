<template>
  <BaseModal
    :modelValue="modelValue"
    title="我的订单"
    subtitle="VIP 购买记录与支付状态"
    maxWidth="3xl"
    @update:modelValue="$emit('update:modelValue', $event)"
  >
    <!-- 加载中 -->
    <div v-if="loading" class="py-12">
      <EmptyState variant="loading" title="加载中…" />
    </div>

    <!-- 加载失败 -->
    <div v-else-if="errorMsg" class="py-12">
      <EmptyState variant="error" :title="errorMsg">
        <template #action>
          <BaseButton variant="primary" size="sm" shape="square" @click="loadOrders">重试</BaseButton>
        </template>
      </EmptyState>
    </div>

    <!-- 空态 -->
    <div v-else-if="orders.length === 0" class="py-12">
      <EmptyState
        variant="empty"
        title="暂无订单"
        desc="购买 VIP 后，订单与支付状态会显示在这里"
      >
        <template #action>
          <BaseButton variant="primary" size="sm" shape="square" @click="$emit('open-vip')">
            开通 VIP
          </BaseButton>
        </template>
      </EmptyState>
    </div>

    <!-- 订单列表 -->
    <ul v-else class="divide-y divide-border-light">
      <li
        v-for="order in orders"
        :key="order.order_no"
        class="flex flex-wrap items-center gap-x-4 gap-y-2 px-1 py-4"
      >
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-text-primary font-mono">{{ order.order_no }}</span>
            <span
              class="px-2 py-0.5 text-xs font-medium rounded-full"
              :class="statusClass(order.status)"
            >{{ statusLabel(order.status) }}</span>
          </div>
          <p class="mt-1 text-xs text-text-muted">
            {{ planLabel(order.plan_type) }} ·
            创建于 {{ formatDateTime(order.created_at) }}
            <template v-if="order.paid_at"> · 支付于 {{ formatDateTime(order.paid_at) }}</template>
          </p>
        </div>
        <div class="text-right">
          <p class="text-base font-semibold text-text-primary">{{ formatAmount(order) }}</p>
        </div>
      </li>
    </ul>
  </BaseModal>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { getOrders } from '../api/payment.js'
import { formatDateTime } from '../utils/format.js'
import { getApiError } from '../utils/error.js'
import BaseModal from './ui/BaseModal.vue'
import BaseButton from './ui/BaseButton.vue'
import EmptyState from './ui/EmptyState.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'open-vip'])

const orders = ref([])
const loading = ref(false)
const errorMsg = ref('')

const STATUS_LABEL = {
  paid: '已支付',
  pending: '待支付',
  failed: '已失败',
}

const PLAN_LABEL = {
  monthly: 'VIP 月卡',
  yearly: 'VIP 年卡',
}

function statusLabel(status) {
  return STATUS_LABEL[status] || status || '未知'
}

function statusClass(status) {
  if (status === 'paid') return 'bg-success-bg text-success-text'
  if (status === 'failed') return 'bg-error-bg text-error-text'
  return 'bg-warning-bg text-warning-text'
}

function planLabel(plan) {
  return PLAN_LABEL[plan] || plan || '未知套餐'
}

// 金额以「分」存储（后端 create_order 传入 990 表示 ¥9.90）
function formatAmount(order) {
  const amount = Number(order.amount)
  if (!Number.isFinite(amount)) return '—'
  const currency = (order.currency || 'cny').toUpperCase()
  const symbol = currency === 'CNY' ? '¥' : `${currency} `
  return `${symbol}${(amount / 100).toFixed(2)}`
}

async function loadOrders() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await getOrders()
    if (res?.success) {
      orders.value = res.data || []
    } else {
      errorMsg.value = '加载订单失败'
    }
  } catch (error) {
    errorMsg.value = getApiError(error, '加载订单失败')
  } finally {
    loading.value = false
  }
}

// 每次打开弹窗都拉一次最新状态（支付刚完成时列表需要立刻反映结果）
watch(
  () => props.modelValue,
  (open) => {
    if (open) loadOrders()
  }
)

onMounted(() => {
  if (props.modelValue) loadOrders()
})
</script>
