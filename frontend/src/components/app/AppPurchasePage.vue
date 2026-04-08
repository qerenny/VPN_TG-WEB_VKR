<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import {
  createStandardCheckout,
  createWhitelistCheckout,
  fetchPlanCatalog,
  type WebCatalogPlan,
  type WebPlanCatalog,
} from '../../api/account'
import {
  DEFAULT_FEATURE_FLAGS,
  createEmptyPublicConfig,
  fetchPublicConfig,
  type FrontendFeatureFlags,
} from '../../api/publicConfig'
import { formatMoney } from '../../utils/format'

const toast = useToast()
const catalog = ref<WebPlanCatalog | null>(null)
const loading = ref(true)
const checkoutLoadingCode = ref<string | null>(null)
const selectedScope = ref<'standard' | 'whitelist' | null>(null)
const selectedPlanCode = ref<string | null>(null)
const showConfirmModal = ref(false)
const features = ref<FrontendFeatureFlags>({ ...DEFAULT_FEATURE_FLAGS })

const standardPlans = computed(() => catalog.value?.standard || [])
const whitelistPlans = computed(() => catalog.value?.whitelist || [])
const webPurchaseEnabled = computed(() => features.value.commerce_enabled && features.value.web_purchase_enabled)
const selectedPlan = computed(() => {
  if (!selectedScope.value || !selectedPlanCode.value) {
    return null
  }

  const plans = selectedScope.value === 'standard' ? standardPlans.value : whitelistPlans.value
  return plans.find((plan) => plan.code === selectedPlanCode.value) || null
})

async function openCheckout(scope: 'standard' | 'whitelist', planCode: string) {
  checkoutLoadingCode.value = planCode
  try {
    const result =
      scope === 'standard' ? await createStandardCheckout(planCode) : await createWhitelistCheckout(planCode)

    if (!result?.checkout_url) {
      throw new Error('Checkout URL is missing')
    }

    window.location.assign(String(result.checkout_url))
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось начать оплату'))
    } else {
      toast.error('Не удалось начать оплату')
    }
  } finally {
    checkoutLoadingCode.value = null
  }
}

const planNameRu: Record<string, string> = {
  '1 month access': 'Доступ на 1 месяц',
  '3 months access': 'Доступ на 3 месяца',
  '6 months access': 'Доступ на 6 месяцев',
  '12 months access': 'Доступ на 12 месяцев',
  'Trial 3 days': 'Пробный период 3 дня',
  'News bonus 4 days': 'Бонус за канал 4 дня',
  'Traffic-limited trial 2 GB': 'Пробная конфигурация 2 ГБ',
  'Traffic-limited access 15 GB': 'Лимит трафика 15 ГБ',
  'Traffic-limited access 35 GB': 'Лимит трафика 35 ГБ',
  'Traffic-limited access 80 GB': 'Лимит трафика 80 ГБ',
}

function localizePlanName(name: string) {
  return planNameRu[name] || name
}

function regularPlanSummary(plan: WebCatalogPlan) {
  return `${plan.duration_days} дней доступа`
}

function whitelistPlanSummary(plan: WebCatalogPlan) {
  return `${plan.human_view_traffic_quota || 'Пакет'} · ${plan.duration_days} дней`
}

function selectPlan(scope: 'standard' | 'whitelist', planCode: string) {
  selectedScope.value = scope
  selectedPlanCode.value = planCode
  showConfirmModal.value = true
}

function closeConfirmModal() {
  showConfirmModal.value = false
}

async function proceedToCheckout() {
  if (!selectedScope.value || !selectedPlanCode.value) {
    toast.info('Сначала выбери тариф')
    return
  }
  showConfirmModal.value = false
  await openCheckout(selectedScope.value, selectedPlanCode.value)
}

onMounted(async () => {
  loading.value = true
  try {
    features.value = (await fetchPublicConfig().catch(() => createEmptyPublicConfig())).features
    if (!webPurchaseEnabled.value) {
      catalog.value = null
      return
    }
    catalog.value = await fetchPlanCatalog()
  } catch {
    toast.error('Не удалось загрузить тарифы')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="cabinet-section">
    <div class="cabinet-section__head">
      <p class="cabinet-kicker">Доступ</p>
      <h2 class="cabinet-title">Выбери нужный тип доступа</h2>
      <p class="cabinet-copy">
        Базовая конфигурация для повседневного использования. Конфигурация с лимитом трафика для сетей с ограничениями.
      </p>
    </div>

    <article v-if="!webPurchaseEnabled" class="glass-card cabinet-panel cabinet-empty">
      <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">lock</span>
      <p class="cabinet-subtitle" style="font-size: 17px;">Получение доступа через оплату отключено</p>
      <p class="cabinet-note">Текущая сборка использует некоммерческий режим. Проверьте доступные конфигурации в разделе подписок.</p>
      <RouterLink class="cabinet-btn cabinet-btn--primary" to="/app/subscriptions">
        <span class="material-symbols-outlined">vpn_key</span>
        Перейти к подпискам
      </RouterLink>
    </article>

    <div v-else class="cabinet-grid cabinet-grid--2">
      <!-- Standard VPN first (same order as Subscriptions page) -->
      <article class="glass-card cabinet-panel purchase-card purchase-card--standard">
        <div class="purchase-card__head">
          <span class="material-symbols-outlined purchase-card__icon purchase-card__icon--warm">vpn_key</span>
          <div class="cabinet-section__head">
            <p class="cabinet-badge cabinet-badge--warm">Базовая конфигурация</p>
            <h3 class="cabinet-subtitle">Домашний интернет, стриминг и работа</h3>
            <p class="cabinet-copy">
              Базовый контур для повседневного использования без ограничений по трафику.
            </p>
          </div>
        </div>

        <div v-if="standardPlans.length" class="plan-list">
          <button
            v-for="plan in standardPlans"
            :key="plan.code"
            class="plan-item plan-item--warm"
            :class="{ 'plan-item--selected': selectedScope === 'standard' && selectedPlanCode === plan.code }"
            type="button"
            :disabled="checkoutLoadingCode !== null"
            @click="selectPlan('standard', plan.code)"
          >
            <div class="plan-item__copy">
              <p class="plan-item__title">{{ localizePlanName(plan.name) }}</p>
              <p class="plan-item__meta">{{ regularPlanSummary(plan) }}</p>
            </div>
            <span class="plan-item__price">{{ formatMoney(plan.price_amount, plan.currency) }}</span>
          </button>
        </div>
        <div v-else-if="loading" class="cabinet-loader">
          <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
          <p class="cabinet-loader__text">Загружаем тарифы...</p>
        </div>
        <div v-else class="cabinet-empty">
          <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">inventory_2</span>
          <p>Тарифы пока недоступны</p>
        </div>
      </article>

      <!-- Whitelist second -->
      <article class="glass-card cabinet-panel purchase-card purchase-card--whitelist">
        <div class="purchase-card__head">
          <span class="material-symbols-outlined purchase-card__icon purchase-card__icon--blue">shield</span>
          <div class="cabinet-section__head">
            <p class="cabinet-badge">Конфигурация с лимитом трафика</p>
            <h3 class="cabinet-subtitle">Отдельный контур и отдельный трафик</h3>
            <p class="cabinet-copy">
              Подходит для сетей с ограничениями. Пакеты суммируют трафик.
            </p>
          </div>
        </div>

        <div v-if="whitelistPlans.length" class="plan-list">
          <button
            v-for="plan in whitelistPlans"
            :key="plan.code"
            class="plan-item"
            :class="{ 'plan-item--selected': selectedScope === 'whitelist' && selectedPlanCode === plan.code }"
            type="button"
            :disabled="checkoutLoadingCode !== null"
            @click="selectPlan('whitelist', plan.code)"
          >
            <div class="plan-item__copy">
              <p class="plan-item__title">{{ plan.human_view_traffic_quota }}</p>
              <p class="plan-item__meta">{{ whitelistPlanSummary(plan) }}</p>
            </div>
            <span class="plan-item__price">{{ formatMoney(plan.price_amount, plan.currency) }}</span>
          </button>
        </div>
        <div v-else-if="loading" class="cabinet-loader">
          <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
          <p class="cabinet-loader__text">Загружаем тарифы...</p>
        </div>
        <div v-else class="cabinet-empty">
          <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">inventory_2</span>
          <p>Тарифы пока недоступны</p>
        </div>
      </article>
    </div>

    <!-- Confirmation modal -->
    <div v-if="showConfirmModal && selectedPlan" class="confirm-overlay" @click.self="closeConfirmModal">
      <article class="glass-card cabinet-panel confirm-modal">
        <div class="confirm-modal__head">
          <span class="material-symbols-outlined confirm-modal__icon">shopping_cart_checkout</span>
          <div class="cabinet-section__head">
            <p class="cabinet-badge" :class="selectedScope === 'whitelist' ? undefined : 'cabinet-badge--warm'">
              {{ selectedScope === 'whitelist' ? 'Лимит трафика' : 'Базовая конфигурация' }}
            </p>
            <h3 class="cabinet-subtitle">Подтвердить выбор</h3>
          </div>
        </div>

        <div class="confirm-modal__grid">
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Тариф</p>
            <p class="cabinet-fact__value">
              {{ selectedScope === 'whitelist' ? selectedPlan.human_view_traffic_quota : localizePlanName(selectedPlan.name) }}
            </p>
          </div>
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Параметры</p>
            <p class="cabinet-fact__value">
              {{ selectedScope === 'whitelist' ? whitelistPlanSummary(selectedPlan) : regularPlanSummary(selectedPlan) }}
            </p>
          </div>
          <div class="cabinet-fact confirm-modal__price-fact">
            <p class="cabinet-fact__label">К оплате</p>
            <p class="cabinet-fact__value confirm-modal__price">{{ formatMoney(selectedPlan.price_amount, selectedPlan.currency) }}</p>
          </div>
        </div>

        <div class="cabinet-actions">
          <button class="cabinet-btn cabinet-btn--ghost" type="button" @click="closeConfirmModal">
            Отмена
          </button>
          <button
            class="cabinet-btn"
            :class="selectedScope === 'whitelist' ? 'cabinet-btn--primary' : 'cabinet-btn--warm'"
            type="button"
            :disabled="checkoutLoadingCode !== null"
            @click="proceedToCheckout"
          >
            <span class="material-symbols-outlined">shopping_cart_checkout</span>
            {{ checkoutLoadingCode ? 'Переходим...' : 'Перейти к оплате' }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.purchase-card {
  display: grid;
  gap: 20px;
}

.purchase-card__head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.purchase-card__icon {
  font-size: 28px;
  padding: 10px;
  border-radius: 16px;
  flex-shrink: 0;
}

.purchase-card__icon--warm {
  color: var(--cabinet-standard);
  background: rgba(245, 160, 78, 0.1);
}

.purchase-card__icon--blue {
  color: var(--cabinet-whitelist);
  background: rgba(77, 143, 214, 0.1);
}

.purchase-card--standard {
  background:
    radial-gradient(circle at 90% 10%, rgba(245, 160, 78, 0.18), transparent 30%),
    linear-gradient(145deg, rgba(255, 252, 249, 0.96), rgba(255, 244, 237, 0.88));
  border-color: rgba(240, 126, 74, 0.16);
}

.purchase-card--whitelist {
  background:
    radial-gradient(circle at 90% 10%, rgba(77, 143, 214, 0.15), transparent 30%),
    linear-gradient(145deg, rgba(248, 252, 255, 0.96), rgba(238, 247, 255, 0.88));
  border-color: rgba(77, 143, 214, 0.16);
}

.plan-list {
  display: grid;
  gap: 10px;
}

.plan-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1.5px solid rgba(77, 143, 214, 0.16);
  background: rgba(255, 255, 255, 0.8);
  color: var(--cabinet-text);
  text-align: left;
  cursor: pointer;
  transition: transform 200ms ease, background-color 200ms ease, border-color 200ms ease, box-shadow 200ms ease;
}

.plan-item--warm {
  border-color: rgba(240, 126, 74, 0.16);
}

.plan-item:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 8px 22px rgba(90, 110, 140, 0.08);
}

.plan-item--selected {
  border-color: rgba(77, 143, 214, 0.35);
  background: #fff;
  box-shadow: 0 10px 28px rgba(59, 130, 212, 0.12);
}

.plan-item--warm.plan-item--selected {
  border-color: rgba(240, 126, 74, 0.35);
  box-shadow: 0 10px 28px rgba(240, 126, 74, 0.12);
}

.plan-item:disabled {
  opacity: 0.6;
  cursor: wait;
  transform: none;
}

.plan-item__copy {
  display: grid;
  gap: 4px;
}

.plan-item__title {
  margin: 0;
  font: 700 18px/1.2 var(--font-ui);
}

.plan-item__price {
  margin: 0;
  font: 700 20px/1.2 var(--font-ui);
  flex-shrink: 0;
}

.plan-item__meta {
  margin: 0;
  color: var(--cabinet-muted);
  font-size: 13px;
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgba(30, 42, 60, 0.3);
  backdrop-filter: blur(12px);
}

.confirm-modal {
  width: min(580px, 100%);
  display: grid;
  gap: 20px;
  background:
    radial-gradient(circle at 80% 15%, rgba(77, 143, 214, 0.1), transparent 30%),
    linear-gradient(145deg, rgba(255, 252, 249, 0.98), rgba(248, 250, 254, 0.96));
}

.confirm-modal__head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.confirm-modal__icon {
  font-size: 28px;
  color: var(--cabinet-whitelist);
  padding: 8px;
  border-radius: 14px;
  background: rgba(77, 143, 214, 0.08);
  flex-shrink: 0;
}

.confirm-modal__grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.confirm-modal__price {
  font: 700 22px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

@media (max-width: 720px) {
  .plan-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .purchase-card__head {
    flex-direction: column;
  }
}
</style>
