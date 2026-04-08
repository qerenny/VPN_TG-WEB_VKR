<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import { fetchPayments, type WebPaymentItem } from '../../api/account'
import {
  DEFAULT_FEATURE_FLAGS,
  createEmptyPublicConfig,
  fetchPublicConfig,
  type FrontendFeatureFlags,
} from '../../api/publicConfig'
import { formatDateTime, formatMoney } from '../../utils/format'

const toast = useToast()
const payments = ref<WebPaymentItem[]>([])
const loading = ref(true)
const features = ref<FrontendFeatureFlags>({ ...DEFAULT_FEATURE_FLAGS })
const PAYMENT_POLL_INTERVAL_MS = 3000
let paymentPollTimer: number | null = null

const commerceEnabled = computed(() => features.value.commerce_enabled)
const webPurchaseEnabled = computed(() => features.value.commerce_enabled && features.value.web_purchase_enabled)
const hasPendingPayments = computed(() =>
  payments.value.some((payment) => payment.runtime_status === 'pending'),
)

function clearPaymentPollTimer() {
  if (paymentPollTimer !== null) {
    window.clearTimeout(paymentPollTimer)
    paymentPollTimer = null
  }
}

function schedulePaymentRefresh() {
  clearPaymentPollTimer()
  if (!hasPendingPayments.value) {
    return
  }

  paymentPollTimer = window.setTimeout(() => {
    void loadPayments({ silent: true })
  }, PAYMENT_POLL_INTERVAL_MS)
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'paid': return 'cabinet-badge--ok'
    case 'pending': return 'cabinet-badge--warm'
    case 'canceled': return 'cabinet-badge--muted'
    case 'failed': return 'cabinet-badge--danger'
    default: return ''
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'paid': return 'Оплачено'
    case 'pending': return 'Ожидает'
    case 'canceled': return 'Отменено'
    case 'failed': return 'Ошибка'
    default: return status
  }
}

function statusBorderClass(status: string): string {
  switch (status) {
    case 'paid': return 'payment-row--paid'
    case 'pending': return 'payment-row--pending'
    case 'failed': return 'payment-row--failed'
    case 'canceled': return 'payment-row--canceled'
    default: return ''
  }
}

function localizePlanName(name: string): string {
  const names: Record<string, string> = {
    '1 month access': 'Доступ на 1 месяц',
    '3 months access': 'Доступ на 3 месяца',
    '6 months access': 'Доступ на 6 месяцев',
    '12 months access': 'Доступ на 12 месяцев',
    'Traffic-limited access 15 GB': 'Лимит трафика 15 ГБ',
    'Traffic-limited access 35 GB': 'Лимит трафика 35 ГБ',
    'Traffic-limited access 80 GB': 'Лимит трафика 80 ГБ',
  }
  return names[name] || name
}

async function loadPayments(options: { silent?: boolean } = {}) {
  const { silent = false } = options
  try {
    payments.value = await fetchPayments()
  } catch {
    if (!silent) {
      toast.error('Не удалось загрузить историю платежей')
    }
  } finally {
    loading.value = false
    schedulePaymentRefresh()
  }
}

onMounted(async () => {
  loading.value = true
  features.value = (await fetchPublicConfig().catch(() => createEmptyPublicConfig())).features
  if (!commerceEnabled.value) {
    payments.value = []
    loading.value = false
    return
  }
  await loadPayments()
})

onBeforeUnmount(() => {
  clearPaymentPollTimer()
})
</script>

<template>
  <section class="cabinet-section">
    <div class="cabinet-section__head">
      <p class="cabinet-kicker">Транзакции</p>
      <h2 class="cabinet-title">История операций</h2>
      <p class="cabinet-copy">Последние операции и их текущий статус.</p>
    </div>

    <article class="glass-card cabinet-panel">
      <div v-if="loading" class="cabinet-loader">
        <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
        <p class="cabinet-loader__text">Загружаем платежи...</p>
      </div>
      <div v-else-if="!commerceEnabled" class="cabinet-empty">
        <span class="material-symbols-outlined payments-icon">lock</span>
        <p class="cabinet-subtitle" style="font-size: 17px;">Коммерческий модуль отключён</p>
        <p class="cabinet-note">В этой сборке история платежей не используется.</p>
      </div>
      <div v-else-if="payments.length === 0" class="cabinet-empty">
        <span class="material-symbols-outlined payments-icon">receipt_long</span>
        <p class="cabinet-subtitle" style="font-size: 17px;">Операций пока нет</p>
        <p class="cabinet-note">После первой операции здесь появится история.</p>
        <RouterLink v-if="webPurchaseEnabled" class="cabinet-btn cabinet-btn--warm" to="/app/purchase">
          <span class="material-symbols-outlined">shopping_cart</span>
          Получить доступ
        </RouterLink>
      </div>
      <div v-else class="cabinet-table">
        <p v-if="hasPendingPayments" class="cabinet-note payment-polling-note">
          Обновляем статус оплаты автоматически...
        </p>
        <article
          v-for="payment in payments"
          :key="payment.order_id"
          class="cabinet-row payment-row"
          :class="statusBorderClass(payment.runtime_status)"
        >
          <div class="payment-row__main">
            <div class="payment-row__badges">
              <span class="cabinet-badge" :class="payment.scope === 'whitelist' ? '' : 'cabinet-badge--warm'">
                {{ payment.scope === 'whitelist' ? 'Лимит трафика' : 'Базовая конфигурация' }}
              </span>
              <span class="cabinet-badge" :class="statusBadgeClass(payment.runtime_status)">
                {{ statusLabel(payment.runtime_status) }}
              </span>
            </div>
            <p class="payment-row__title">{{ localizePlanName(payment.plan_name) }}</p>
            <p class="payment-row__meta">{{ formatDateTime(payment.created_at) }}</p>
          </div>
          <div class="payment-row__amount">
            <p class="payment-row__price">{{ formatMoney(payment.amount, payment.currency) }}</p>
          </div>
        </article>
      </div>
    </article>

  </section>
</template>

<style scoped>
.payments-icon {
  font-size: 48px;
  opacity: 0.3;
  color: var(--cabinet-muted);
}

.payments-empty-logo {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 3px solid rgba(255, 90, 68, 0.25);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 6px 18px rgba(151, 53, 34, 0.12);
  opacity: 0.7;
  animation: float-soft 4s ease-in-out infinite;
}

.payment-row {
  border-left: 3px solid transparent;
}

.payment-row--paid { border-left-color: var(--cabinet-ok); }
.payment-row--pending { border-left-color: var(--cabinet-standard); }
.payment-row--failed { border-left-color: var(--cabinet-danger); }
.payment-row--canceled { border-left-color: var(--cabinet-muted); }

.payment-row__main {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.payment-row__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.payment-row__title {
  margin: 0;
  font: 700 17px/1.24 var(--font-ui);
  color: var(--cabinet-text);
}

.payment-row__meta {
  margin: 0;
  color: var(--cabinet-muted);
  font-size: 13px;
}

.payment-row__amount {
  display: grid;
  justify-items: end;
  flex-shrink: 0;
}

.payment-row__price {
  margin: 0;
  font: 700 20px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.payment-polling-note {
  margin: 0 0 12px;
}

@media (max-width: 720px) {
  .payment-row__amount {
    justify-items: start;
  }
}
</style>
