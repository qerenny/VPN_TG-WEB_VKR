<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import {
  createAccessRequest,
  createStandardCheckout,
  createTrafficLimitedCheckout,
  fetchAccessRequests,
  fetchPlanCatalog,
  fetchSubscriptions,
  repeatAccessRequest,
  type WebAccessRequestItem,
  type WebCatalogPlan,
  type WebPlanCatalog,
  type WebSubscriptions,
} from '../../api/account'
import {
  DEFAULT_FEATURE_FLAGS,
  createEmptyPublicConfig,
  fetchPublicConfig,
  type FrontendFeatureFlags,
  type FrontendPublicConfig,
} from '../../api/publicConfig'
import {
  buildAccessTemplateLabelFromPlan,
  localizePlanName,
  REQUESTABLE_ACCESS_TEMPLATE_CODES,
} from '../../utils/accessTemplates'
import { formatMoney } from '../../utils/format'

const toast = useToast()
const catalog = ref<WebPlanCatalog | null>(null)
const loading = ref(true)
const checkoutLoadingCode = ref<string | null>(null)
const requestSubmitting = ref(false)
const selectedScope = ref<'standard' | 'traffic_limited' | null>(null)
const selectedPlanCode = ref<string | null>(null)
const showConfirmModal = ref(false)
const accessRequests = ref<WebAccessRequestItem[]>([])
const subscriptions = ref<WebSubscriptions | null>(null)
const requestComment = ref('')
const requestKind = ref<'new_access' | 'renewal'>('new_access')
const requestTemplateCode = ref<string | null>(null)
const features = ref<FrontendFeatureFlags>({ ...DEFAULT_FEATURE_FLAGS })
const publicConfig = ref<FrontendPublicConfig>(createEmptyPublicConfig())
const nowMs = ref(Date.now())
let repeatTimerId: number | null = null

const accessRequestsEnabled = computed(() => features.value.access_requests_enabled)
const accessRegistryEnabled = computed(() => features.value.access_registry_enabled)
const standardConfigEnabled = computed(() => features.value.standard_config_enabled)
const trafficLimitedConfigEnabled = computed(() => features.value.traffic_limited_config_enabled)
const standardPlans = computed(() => (
  standardConfigEnabled.value ? catalog.value?.standard || [] : []
))
const traffic_limitedPlans = computed(() => (
  trafficLimitedConfigEnabled.value ? catalog.value?.traffic_limited || [] : []
))
const webPurchaseEnabled = computed(() => features.value.commerce_enabled && features.value.web_purchase_enabled)
const hasPurchasableScopes = computed(() => standardConfigEnabled.value || trafficLimitedConfigEnabled.value)
const hasAnyAccessFlow = computed(() => webPurchaseEnabled.value || accessRequestsEnabled.value)
const primaryPaymentMethod = computed(() => publicConfig.value.payment_methods?.primary || 'external_card')
const requestTemplateOptions = computed(() => {
  const standard = standardPlans.value
    .filter((plan) => REQUESTABLE_ACCESS_TEMPLATE_CODES.includes(plan.code as typeof REQUESTABLE_ACCESS_TEMPLATE_CODES[number]))
    .map((plan) => ({
      ...plan,
      label: buildAccessTemplateLabelFromPlan(plan),
    }))
  const trafficLimited = traffic_limitedPlans.value
    .filter((plan) => REQUESTABLE_ACCESS_TEMPLATE_CODES.includes(plan.code as typeof REQUESTABLE_ACCESS_TEMPLATE_CODES[number]))
    .map((plan) => ({
      ...plan,
      label: buildAccessTemplateLabelFromPlan(plan),
    }))
  return [...standard, ...trafficLimited]
})
const requestTemplateLabelByCode = computed(() => Object.fromEntries(
  requestTemplateOptions.value.map((plan) => [plan.code, plan.label]),
))
const latestRequest = computed(() => accessRequests.value[0] || null)
const hasPendingRequest = computed(() => accessRequests.value.some((item) => item.status === 'pending'))
const repeatablePendingRequest = computed(() => latestRequest.value?.status === 'pending' ? latestRequest.value : null)
const hasActiveAccess = computed(() => Boolean(
  subscriptions.value?.standard.is_active || subscriptions.value?.traffic_limited.is_active,
))
const registryManagedAccess = computed(() => Boolean(subscriptions.value?.access_policy?.registry_managed))
const canRequestRenewal = computed(() => hasActiveAccess.value)
const canRequestInitialAccess = computed(() => !hasActiveAccess.value)
const requestSubmitLabel = computed(() => {
  if (hasPendingRequest.value) return 'Заявка уже отправлена'
  if (requestSubmitting.value) return 'Отправляем...'
  if (registryManagedAccess.value) return 'Доступ управляется реестром'
  if (requestKind.value === 'renewal') return 'Запросить продление'
  if (hasActiveAccess.value) return 'Запросить перевыпуск'
  if (latestRequest.value && ['rejected', 'expired'].includes(latestRequest.value.status)) return 'Повторно запросить доступ'
  return 'Запросить доступ'
})
const renewalCurrentTemplateOptionLabel = computed(() => 'Продлить без смены шаблона')
const showRequestTemplateSelector = computed(() => requestKind.value !== 'renewal')
const repeatRequestCooldownMs = 10 * 60 * 1000
const repeatRequestRemainingMs = computed(() => {
  const item = repeatablePendingRequest.value
  if (!item) return 0
  const requestedAtMs = new Date(item.requested_at).getTime()
  if (Number.isNaN(requestedAtMs)) return 0
  return Math.max(0, requestedAtMs + repeatRequestCooldownMs - nowMs.value)
})
const canRepeatPendingRequest = computed(() => Boolean(repeatablePendingRequest.value) && repeatRequestRemainingMs.value <= 0)
const repeatRequestButtonLabel = computed(() => {
  if (!repeatablePendingRequest.value || canRepeatPendingRequest.value) return 'Повторно запросить доступ'
  const totalSeconds = Math.ceil(repeatRequestRemainingMs.value / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `Повторно запросить через ${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})
const requestTypeHint = computed(() => {
  if (requestKind.value === 'renewal') {
    return 'Используйте этот вариант, если нужно только продлить срок текущего доступа. Шаблон при продлении не меняется.'
  }
  if (registryManagedAccess.value) {
    return 'Доступ для этого аккаунта управляется реестром. Система выдаёт и продлевает его автоматически.'
  }
  if (hasActiveAccess.value) {
    return 'Используйте этот вариант, если нужно заменить текущий доступ: выбрать другой шаблон или перевыпустить его на новый срок. Дополнительный параллельный ключ этим сценарием не создаётся.'
  }
  return 'Используйте этот вариант для первичной выдачи доступа.'
})
const purchaseIntroCopy = computed(() => {
  if (registryManagedAccess.value) {
    return 'Для этого аккаунта доступ обслуживается через реестр. Новые заявки, продление и перевыпуск из кабинета недоступны.'
  }
  if (!webPurchaseEnabled.value && accessRequestsEnabled.value) {
    if (accessRegistryEnabled.value) {
      return 'Доступ выдается по заявке. Если аккаунт найден в реестре разрешённых пользователей, запрос может быть одобрен автоматически.'
    }
    return 'Доступ выдается по заявке. Оставьте комментарий, а администратор одобрит и активирует нужную конфигурацию.'
  }
  if (standardConfigEnabled.value && trafficLimitedConfigEnabled.value) {
    return 'Базовая конфигурация подходит для повседневного использования. Отдельно можно получить конфигурацию с лимитом трафика со своим сроком и квотой.'
  }
  if (trafficLimitedConfigEnabled.value) {
    return 'Доступна конфигурация с лимитом трафика со своим сроком действия и квотой.'
  }
  return 'Базовая конфигурация для повседневного защищённого удалённого доступа.'
})
const selectedPlan = computed(() => {
  if (!selectedScope.value || !selectedPlanCode.value) {
    return null
  }

  const plans = selectedScope.value === 'standard' ? standardPlans.value : traffic_limitedPlans.value
  return plans.find((plan) => plan.code === selectedPlanCode.value) || null
})

async function openCheckout(scope: 'standard' | 'traffic_limited', planCode: string) {
  checkoutLoadingCode.value = planCode
  try {
    const result =
      scope === 'standard'
        ? await createStandardCheckout(planCode, primaryPaymentMethod.value)
        : await createTrafficLimitedCheckout(planCode, primaryPaymentMethod.value)

    if (!result?.checkout_url) {
      throw new Error('Checkout URL is missing')
    }

    window.location.assign(String(result.checkout_url))
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось открыть оформление доступа'))
    } else {
      toast.error('Не удалось открыть оформление доступа')
    }
  } finally {
    checkoutLoadingCode.value = null
  }
}

async function submitAccessRequest() {
  if (hasPendingRequest.value) {
    toast.info('У вас уже есть активная заявка на доступ')
    return
  }
  if (registryManagedAccess.value) {
    toast.info('Доступ для этого аккаунта управляется реестром автоматически')
    return
  }
  requestSubmitting.value = true
  try {
    const created = await createAccessRequest({
      template_code: requestTemplateCode.value || null,
      request_kind: requestKind.value,
      comment: requestComment.value.trim() || null,
    })
    accessRequests.value = [created, ...accessRequests.value.filter((item) => item.id !== created.id)]
    if (requestWasAutoApproved(created)) {
      subscriptions.value = await fetchSubscriptions().catch(() => subscriptions.value)
      syncRequestKindWithAccess()
    }
    requestComment.value = ''
    requestTemplateCode.value = null
    toast.success(requestWasAutoApproved(created) ? 'Доступ активирован автоматически' : 'Заявка на доступ отправлена')
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось отправить заявку'))
    } else {
      toast.error('Не удалось отправить заявку')
    }
  } finally {
    requestSubmitting.value = false
  }
}

function regularPlanSummary(plan: WebCatalogPlan) {
  return `${plan.duration_days} дней доступа`
}

function traffic_limitedPlanSummary(plan: WebCatalogPlan) {
  return `${plan.human_view_traffic_quota || 'Пакет'} · ${plan.duration_days} дней`
}

function requestStatusLabel(status: string) {
  if (status === 'pending') return 'На рассмотрении'
  if (status === 'approved') return 'Одобрена'
  if (status === 'rejected') return 'Отклонена'
  if (status === 'expired') return 'Истекла'
  return status
}

function requestStatusBadgeClass(status: string) {
  if (status === 'approved') return 'cabinet-badge--ok'
  if (status === 'rejected') return 'cabinet-badge--danger'
  return 'cabinet-badge--warm'
}

function requestWasAutoApproved(item: WebAccessRequestItem) {
  return Boolean(item.metadata?.auto_approved)
}

function requestApprovedTemplateCode(item: WebAccessRequestItem) {
  const value = item.metadata?.approved_template_code
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function requestResolutionSourceLabel(item: WebAccessRequestItem) {
  if (requestWasAutoApproved(item)) return 'Решение принято автоматически'
  if (item.reviewed_by_actor) return 'Рассмотрено администратором'
  return null
}

function requestKindLabel(value: string) {
  return value === 'renewal' ? 'Продление доступа' : 'Запрос доступа'
}

function requestTemplateLabel(item: WebAccessRequestItem) {
  if (item.approved_template_label) return item.approved_template_label
  const approvedCode = requestApprovedTemplateCode(item)
  if (approvedCode) return requestTemplateLabelByCode.value[approvedCode] || approvedCode
  if (item.requested_template_label) return item.requested_template_label
  if (item.requested_template_code) return requestTemplateLabelByCode.value[item.requested_template_code] || item.requested_template_code
  if (item.request_kind === 'renewal') return renewalCurrentTemplateOptionLabel.value
  return 'Не указан'
}

function setRequestKind(kind: 'new_access' | 'renewal') {
  if (kind === 'renewal' && !canRequestRenewal.value) {
    toast.info('Сначала должен появиться активный доступ, чтобы отправить запрос на продление')
    requestKind.value = 'new_access'
    return
  }
  requestKind.value = kind
  if (kind === 'renewal') {
    requestTemplateCode.value = null
  }
}

function syncRequestKindWithAccess() {
  if (!hasActiveAccess.value && requestKind.value === 'renewal') {
    requestKind.value = 'new_access'
    requestTemplateCode.value = null
    return
  }
  if (hasActiveAccess.value && requestKind.value !== 'renewal') {
    requestKind.value = 'renewal'
  }
}

async function repeatLatestRequest() {
  const item = repeatablePendingRequest.value
  if (!item) return
  if (!canRepeatPendingRequest.value) {
    toast.info('Повторная отправка будет доступна через 10 минут после последнего запроса')
    return
  }
  requestSubmitting.value = true
  try {
    const repeated = await repeatAccessRequest(item.id)
    accessRequests.value = [repeated, ...accessRequests.value.filter((current) => current.id !== repeated.id)]
    toast.success('Заявка повторно отправлена')
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось повторно отправить заявку'))
    } else {
      toast.error('Не удалось повторно отправить заявку')
    }
  } finally {
    requestSubmitting.value = false
  }
}

function selectPlan(scope: 'standard' | 'traffic_limited', planCode: string) {
  selectedScope.value = scope
  selectedPlanCode.value = planCode
  showConfirmModal.value = true
}

function closeConfirmModal() {
  showConfirmModal.value = false
}

async function proceedToCheckout() {
    if (!selectedScope.value || !selectedPlanCode.value) {
    toast.info('Сначала выберите план доступа')
    return
  }
  showConfirmModal.value = false
  await openCheckout(selectedScope.value, selectedPlanCode.value)
}

onMounted(async () => {
  repeatTimerId = window.setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
  loading.value = true
  try {
    publicConfig.value = await fetchPublicConfig().catch(() => createEmptyPublicConfig())
    features.value = publicConfig.value.features
    subscriptions.value = await fetchSubscriptions().catch(() => null)
    if (accessRequestsEnabled.value) {
      accessRequests.value = await fetchAccessRequests().catch(() => [])
    }
    if (webPurchaseEnabled.value || accessRequestsEnabled.value) {
      catalog.value = await fetchPlanCatalog()
    } else {
      catalog.value = null
    }
    syncRequestKindWithAccess()
  } catch {
    toast.error('Не удалось загрузить данные о доступе')
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (repeatTimerId !== null) {
    window.clearInterval(repeatTimerId)
    repeatTimerId = null
  }
})
</script>

<template>
  <section class="cabinet-section">
    <div class="cabinet-section__head">
      <p class="cabinet-kicker">Доступ</p>
      <h2 class="cabinet-title">Получение доступа</h2>
      <p class="cabinet-copy">
        {{ purchaseIntroCopy }}
      </p>
    </div>

    <article v-if="!hasAnyAccessFlow" class="glass-card cabinet-panel cabinet-empty">
      <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">lock</span>
      <p class="cabinet-subtitle" style="font-size: 17px;">Получение доступа отключено</p>
      <p class="cabinet-note">В этой сборке не включены ни оформление доступа, ни подача заявок.</p>
      <RouterLink class="cabinet-btn cabinet-btn--primary" to="/app/subscriptions">
        <span class="material-symbols-outlined">vpn_key</span>
        Перейти к подпискам
      </RouterLink>
    </article>

    <article v-else-if="webPurchaseEnabled && !hasPurchasableScopes" class="glass-card cabinet-panel cabinet-empty">
      <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">inventory_2</span>
      <p class="cabinet-subtitle" style="font-size: 17px;">Планы доступа недоступны</p>
      <p class="cabinet-note">В этой сборке отключены оба типа конфигураций.</p>
    </article>

    <article v-else-if="registryManagedAccess" class="glass-card cabinet-panel cabinet-empty">
      <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">fact_check</span>
      <p class="cabinet-subtitle" style="font-size: 17px;">Доступ управляется через реестр</p>
      <p class="cabinet-note">
        Для этого аккаунта новые заявки, продление и перевыпуск из кабинета отключены.
        Система выдаёт доступ на 1 месяц и продлевает его автоматически, пока запись в реестре активна.
      </p>
      <RouterLink class="cabinet-btn cabinet-btn--primary" to="/app/subscriptions">
        <span class="material-symbols-outlined">vpn_key</span>
        Перейти к доступу
      </RouterLink>
    </article>

    <div v-else class="cabinet-stack">
      <article v-if="accessRequestsEnabled" class="glass-card cabinet-panel">
        <div class="purchase-card__head">
          <span class="material-symbols-outlined purchase-card__icon purchase-card__icon--blue">approval</span>
          <div class="cabinet-section__head">
            <p class="cabinet-badge">Заявка на доступ</p>
            <h3 class="cabinet-subtitle">Автоматизированная обработка запроса</h3>
            <p class="cabinet-copy">
              {{ requestTypeHint }}
            </p>
          </div>
        </div>

        <div class="request-form">
          <label class="cabinet-form-field">
            <span class="cabinet-form-label">Тип запроса</span>
            <div class="request-kind-toggle">
              <button
                class="cabinet-btn"
                :class="requestKind === 'new_access' ? 'cabinet-btn--primary' : 'cabinet-btn--ghost'"
                type="button"
                v-if="canRequestInitialAccess && !registryManagedAccess"
                @click="setRequestKind('new_access')"
              >
                <span class="material-symbols-outlined">add_circle</span>
                Запросить доступ
              </button>
              <button
                class="cabinet-btn"
                :class="requestKind === 'renewal' ? 'cabinet-btn--warm' : 'cabinet-btn--ghost'"
                type="button"
                v-if="canRequestRenewal && !registryManagedAccess"
                @click="setRequestKind('renewal')"
              >
                <span class="material-symbols-outlined">autorenew</span>
                Продлить доступ
              </button>
              <button
                class="cabinet-btn"
                :class="requestKind === 'new_access' ? 'cabinet-btn--primary' : 'cabinet-btn--ghost'"
                type="button"
                v-if="hasActiveAccess && !registryManagedAccess"
                @click="setRequestKind('new_access')"
              >
                <span class="material-symbols-outlined">refresh</span>
                Перевыпустить доступ
              </button>
            </div>
          </label>
          <label v-if="requestTemplateOptions.length && showRequestTemplateSelector" class="cabinet-form-field">
            <span class="cabinet-form-label">Желаемый шаблон доступа</span>
            <select v-model="requestTemplateCode" class="cabinet-input">
              <option :value="null">
                {{ hasActiveAccess ? 'Выберите новый шаблон доступа' : 'Не указывать шаблон' }}
              </option>
              <option v-for="plan in requestTemplateOptions" :key="plan.code" :value="plan.code">
                {{ plan.label }}
              </option>
            </select>
          </label>
          <label class="cabinet-form-field">
            <span class="cabinet-form-label">Комментарий</span>
            <textarea
              v-model="requestComment"
              class="cabinet-input"
              rows="3"
              placeholder="Например: нужен доступ для семьи, работы или тестирования"
            />
          </label>

          <div class="cabinet-actions">
            <button class="cabinet-btn cabinet-btn--primary" :disabled="requestSubmitting || hasPendingRequest || registryManagedAccess" @click="submitAccessRequest">
              <span class="material-symbols-outlined">{{ requestSubmitting ? 'hourglass_top' : 'send' }}</span>
              {{ requestSubmitLabel }}
            </button>
            <button
              v-if="repeatablePendingRequest"
              class="cabinet-btn cabinet-btn--ghost"
              type="button"
              :disabled="requestSubmitting || !canRepeatPendingRequest"
              @click="repeatLatestRequest"
            >
              <span class="material-symbols-outlined">replay</span>
              {{ repeatRequestButtonLabel }}
            </button>
          </div>
        </div>

        <p v-if="registryManagedAccess" class="request-registry-hint">
          <span class="material-symbols-outlined">info</span>
          Этот аккаунт обслуживается через реестр. Доступ выдаётся на 1 месяц и затем продлевается автоматически, пока запись остаётся активной.
        </p>

        <div v-if="accessRequests.length" class="request-history">
          <div class="request-history__head">
            <span class="material-symbols-outlined request-history__icon">history</span>
            <h4 class="request-history__title">История заявок</h4>
          </div>
          <div class="request-history__list">
            <article v-for="item in accessRequests" :key="item.id" class="request-card">
              <div class="request-card__head">
                <div class="request-card__head-left">
                  <span class="material-symbols-outlined request-card__type-icon">
                    {{ item.request_kind === 'renewal' ? 'autorenew' : 'add_circle' }}
                  </span>
                  <div>
                    <p class="request-card__title">{{ requestKindLabel(item.request_kind) }}</p>
                    <p class="cabinet-note">{{ new Date(item.requested_at).toLocaleString() }}</p>
                  </div>
                </div>
                <span class="cabinet-badge" :class="requestStatusBadgeClass(item.status)">
                  {{ requestStatusLabel(item.status) }}
                </span>
              </div>

              <p v-if="item.comment" class="request-card__comment">{{ item.comment }}</p>

              <dl class="request-card__props">
                <div>
                  <dt>Шаблон доступа</dt>
                  <dd>{{ requestTemplateLabel(item) }}</dd>
                </div>
                <div v-if="requestResolutionSourceLabel(item)">
                  <dt>Решение</dt>
                  <dd>{{ requestResolutionSourceLabel(item) }}</dd>
                </div>
                <div v-if="item.expires_at && item.status === 'pending'">
                  <dt>Истечёт без решения</dt>
                  <dd>{{ new Date(item.expires_at).toLocaleString() }}</dd>
                </div>
                <div v-if="item.reviewed_at">
                  <dt>Обработана</dt>
                  <dd>{{ new Date(item.reviewed_at).toLocaleString() }}</dd>
                </div>
                <div v-if="item.review_note">
                  <dt>Комментарий администратора</dt>
                  <dd>{{ item.review_note }}</dd>
                </div>
              </dl>
            </article>
          </div>
        </div>
      </article>

      <div v-if="webPurchaseEnabled" class="cabinet-grid cabinet-grid--2">
      <!-- Standard VPN first (same order as Subscriptions page) -->
      <article v-if="standardConfigEnabled" class="glass-card cabinet-panel purchase-card purchase-card--standard">
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
          <p class="cabinet-loader__text">Загружаем варианты доступа...</p>
        </div>
        <div v-else class="cabinet-empty">
          <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">inventory_2</span>
          <p>Планы доступа пока недоступны</p>
        </div>
      </article>

      <!-- TrafficLimited second -->
      <article v-if="trafficLimitedConfigEnabled" class="glass-card cabinet-panel purchase-card purchase-card--traffic_limited">
        <div class="purchase-card__head">
          <span class="material-symbols-outlined purchase-card__icon purchase-card__icon--blue">shield</span>
          <div class="cabinet-section__head">
            <p class="cabinet-badge">Конфигурация с лимитом трафика</p>
            <h3 class="cabinet-subtitle">Отдельный контур и отдельный трафик</h3>
            <p class="cabinet-copy">
              Отдельная конфигурация со своим сроком действия и собственной квотой трафика.
            </p>
          </div>
        </div>

        <div v-if="traffic_limitedPlans.length" class="plan-list">
          <button
            v-for="plan in traffic_limitedPlans"
            :key="plan.code"
            class="plan-item"
            :class="{ 'plan-item--selected': selectedScope === 'traffic_limited' && selectedPlanCode === plan.code }"
            type="button"
            :disabled="checkoutLoadingCode !== null"
            @click="selectPlan('traffic_limited', plan.code)"
          >
            <div class="plan-item__copy">
              <p class="plan-item__title">{{ plan.human_view_traffic_quota }}</p>
              <p class="plan-item__meta">{{ traffic_limitedPlanSummary(plan) }}</p>
            </div>
            <span class="plan-item__price">{{ formatMoney(plan.price_amount, plan.currency) }}</span>
          </button>
        </div>
        <div v-else-if="loading" class="cabinet-loader">
          <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
          <p class="cabinet-loader__text">Загружаем варианты доступа...</p>
        </div>
        <div v-else class="cabinet-empty">
          <span class="material-symbols-outlined" style="font-size: 44px; opacity: 0.3;">inventory_2</span>
          <p>Планы доступа пока недоступны</p>
        </div>
      </article>
      </div>
    </div>

    <!-- Confirmation modal -->
    <div v-if="showConfirmModal && selectedPlan" class="confirm-overlay" @click.self="closeConfirmModal">
      <article class="glass-card cabinet-panel confirm-modal">
        <div class="confirm-modal__head">
          <span class="material-symbols-outlined confirm-modal__icon">vpn_key</span>
          <div class="cabinet-section__head">
            <p class="cabinet-badge" :class="selectedScope === 'traffic_limited' ? undefined : 'cabinet-badge--warm'">
              {{ selectedScope === 'traffic_limited' ? 'Лимит трафика' : 'Базовая конфигурация' }}
            </p>
            <h3 class="cabinet-subtitle">Подтвердить выбор</h3>
          </div>
        </div>

        <div class="confirm-modal__grid">
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">План доступа</p>
            <p class="cabinet-fact__value">
              {{ selectedScope === 'traffic_limited' ? selectedPlan.human_view_traffic_quota : localizePlanName(selectedPlan.name) }}
            </p>
          </div>
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Параметры</p>
            <p class="cabinet-fact__value">
              {{ selectedScope === 'traffic_limited' ? traffic_limitedPlanSummary(selectedPlan) : regularPlanSummary(selectedPlan) }}
            </p>
          </div>
          <div class="cabinet-fact confirm-modal__price-fact">
            <p class="cabinet-fact__label">Стоимость</p>
            <p class="cabinet-fact__value confirm-modal__price">{{ formatMoney(selectedPlan.price_amount, selectedPlan.currency) }}</p>
          </div>
        </div>

        <div class="cabinet-actions">
          <button class="cabinet-btn cabinet-btn--ghost" type="button" @click="closeConfirmModal">
            Отмена
          </button>
          <button
            class="cabinet-btn"
            :class="selectedScope === 'traffic_limited' ? 'cabinet-btn--primary' : 'cabinet-btn--warm'"
            type="button"
            :disabled="checkoutLoadingCode !== null"
            @click="proceedToCheckout"
          >
            <span class="material-symbols-outlined">vpn_key</span>
            {{ checkoutLoadingCode ? 'Переходим...' : 'Перейти к оформлению' }}
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
  color: var(--cabinet-traffic_limited);
  background: rgba(77, 143, 214, 0.1);
}

.purchase-card--standard {
  background:
    radial-gradient(circle at 90% 10%, rgba(245, 160, 78, 0.18), transparent 30%),
    linear-gradient(145deg, rgba(255, 252, 249, 0.96), rgba(255, 244, 237, 0.88));
  border-color: rgba(240, 126, 74, 0.16);
}

.purchase-card--traffic_limited {
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

.cabinet-stack {
  display: grid;
  gap: 20px;
}

/* ── Request form ── */
.request-form {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.request-kind-toggle {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.request-registry-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(77, 143, 214, 0.06);
  border: 1px solid rgba(77, 143, 214, 0.1);
  color: var(--cabinet-muted);
  font-size: 13px;
  line-height: 1.45;
}

.request-registry-hint .material-symbols-outlined {
  font-size: 18px;
  color: var(--cabinet-traffic_limited);
  flex-shrink: 0;
}

/* ── Request history ── */
.request-history {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid rgba(126, 170, 220, 0.1);
}

.request-history__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.request-history__icon {
  font-size: 20px;
  color: var(--cabinet-traffic_limited);
}

.request-history__title {
  margin: 0;
  font: 700 15px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.request-history__list {
  display: grid;
  gap: 12px;
}

.request-card {
  display: grid;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(126, 170, 220, 0.1);
  transition: transform 180ms, box-shadow 180ms;
}

.request-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(100, 120, 150, 0.05);
}

.request-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.request-card__head-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.request-card__type-icon {
  font-size: 22px;
  color: var(--cabinet-traffic_limited);
  flex-shrink: 0;
}

.request-card__title {
  margin: 0;
  font: 700 15px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.request-card__comment {
  margin: 0;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(126, 170, 220, 0.06);
  color: var(--cabinet-text);
  font-size: 14px;
  line-height: 1.5;
}

.request-card__props {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px 16px;
  margin: 0;
}

.request-card__props div {
  display: grid;
  gap: 2px;
}

.request-card__props dt {
  color: var(--cabinet-muted);
  font: 600 11px/1.2 var(--font-ui);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.request-card__props dd {
  margin: 0;
  font: 400 13px/1.4 var(--font-ui);
  color: var(--cabinet-text);
  word-break: break-word;
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
  color: var(--cabinet-traffic_limited);
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

  .request-card__head {
    flex-direction: column;
    align-items: flex-start;
  }

  .request-card__props {
    grid-template-columns: 1fr;
  }
}
</style>
