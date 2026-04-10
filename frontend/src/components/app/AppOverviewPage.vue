<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import axios from 'axios'
import {
  applyPromoCode,
  fetchAccessGrants,
  fetchLinks,
  fetchReferralStats,
  fetchSubscriptions,
  type WebAccessGrantItem,
  type WebLinks,
  type WebReferralStats,
  type WebSubscriptions,
} from '../../api/account'
import {
  DEFAULT_FEATURE_FLAGS,
  createEmptyPublicConfig,
  fetchPublicConfig,
  type FrontendFeatureFlags,
  type FrontendPublicConfig,
} from '../../api/publicConfig'
import { useSessionState } from '../../stores/session'
import { formatAccessTemplateLabel } from '../../utils/accessTemplates'

const toast = useToast()
const session = useSessionState()

const links = ref<WebLinks | null>(null)
const subscriptions = ref<WebSubscriptions | null>(null)
const accessGrants = ref<WebAccessGrantItem[]>([])
const referrals = ref<WebReferralStats | null>(null)
const publicConfig = ref<FrontendPublicConfig>(createEmptyPublicConfig())
const loading = ref(true)

const promoCode = ref('')
const promoLoading = ref(false)
const promoSuccess = ref('')

async function submitPromoCode() {
  const code = promoCode.value.trim()
  if (!code) return
  promoLoading.value = true
  promoSuccess.value = ''
  try {
    const result = await applyPromoCode(code)
    promoSuccess.value = result.message
    promoCode.value = ''
    toast.success(result.message)
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось активировать промокод'))
    } else {
      toast.error('Не удалось активировать промокод')
    }
  } finally {
    promoLoading.value = false
  }
}

const needsTelegramLink = computed(() => {
  const hasEmail = Boolean(session.me?.email || session.me?.preferred_contact_email)
  const telegramLinked = Boolean(session.me?.telegram_linked)
  return hasEmail && !telegramLinked
})

const needsEmailLink = computed(() => {
  const hasEmail = Boolean(session.me?.email || session.me?.preferred_contact_email)
  const telegramLinked = Boolean(session.me?.telegram_linked)
  return telegramLinked && !hasEmail
})

const features = computed<FrontendFeatureFlags>(() => publicConfig.value.features || DEFAULT_FEATURE_FLAGS)
const accountDisplayName = computed(() => (
  session.me?.display_name
  || (session.me?.telegram_username ? `@${session.me.telegram_username}` : null)
  || 'Пользователь'
))
const loginMethod = computed(() => (
  session.me?.email ? 'Email и пароль' : 'Telegram'
))
const showEmailFact = computed(() => true)
const webPurchaseEnabled = computed(() => features.value.commerce_enabled && features.value.web_purchase_enabled)
const accessRequestsEnabled = computed(() => features.value.access_requests_enabled)
const referralsEnabled = computed(() => features.value.referrals_enabled)
const promosEnabled = computed(() => features.value.promos_enabled && features.value.commerce_enabled)
const standardConfigEnabled = computed(() => features.value.standard_config_enabled)
const trafficLimitedConfigEnabled = computed(() => features.value.traffic_limited_config_enabled)
const registryManagedAccess = computed(() => Boolean(subscriptions.value?.access_policy?.registry_managed))
const visibleSubscriptionRows = computed(() => {
  if (!subscriptions.value) return []

  const rows = [
    { key: 'standard', label: 'Базовая конфигурация', active: subscriptions.value.standard.is_active },
    { key: 'traffic_limited', label: 'Лимит трафика', active: subscriptions.value.traffic_limited.is_active },
  ]
  return rows.filter((row) => {
    if (row.key === 'standard') return standardConfigEnabled.value
    if (row.key === 'traffic_limited') return trafficLimitedConfigEnabled.value
    return true
  })
})
const activeCount = computed(() => visibleSubscriptionRows.value.filter((row) => row.active).length)
const accessActionLabel = computed(() => (
  webPurchaseEnabled.value ? 'Получить доступ' : 'Запросить доступ'
))
const recentAccessGrants = computed(() => accessGrants.value.slice(0, 3))
const activeAccessGrant = computed(() => accessGrants.value.find((item) => item.status === 'active') || null)

function accessGrantSourceLabel(sourceType: string) {
  const normalized = String(sourceType || '').trim().toLowerCase()
  if (normalized === 'payment') return 'Оформление доступа'
  if (normalized === 'request_approval') return 'Заявка'
  if (normalized === 'access_registry') return 'Реестр доступа'
  if (normalized === 'access_registry_auto_renew') return 'Автопродление по реестру'
  if (normalized === 'admin_override') return 'Административная выдача'
  return normalized || 'Источник не указан'
}

function accessGrantScopeLabel(scope: string) {
  return String(scope || '').trim().toLowerCase() === 'traffic_limited'
    ? 'Лимит трафика'
    : 'Базовая конфигурация'
}

function accessGrantStatusLabel(status: string) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'active') return 'Активен'
  if (normalized === 'expired') return 'Истёк'
  if (normalized === 'revoked') return 'Отозван'
  return status || '—'
}

function activeAccessReasonTitle() {
  const grant = activeAccessGrant.value
  if (!grant) return 'Доступ сейчас не активирован'
  return `Доступ активен через: ${accessGrantSourceLabel(grant.source_type)}`
}

function activeAccessReasonFacts() {
  const grant = activeAccessGrant.value
  if (!grant) return []
  const facts: { label: string; value: string; icon: string }[] = [
    { label: 'Шаблон', value: grant.template_label || formatAccessTemplateLabel(grant.template_code), icon: 'description' },
    { label: 'Контур', value: accessGrantScopeLabel(grant.scope), icon: 'layers' },
  ]
  if (grant.expires_at) {
    facts.push({ label: 'Действует до', value: new Date(grant.expires_at).toLocaleString(), icon: 'schedule' })
  }
  if (grant.quota_bytes) {
    facts.push({ label: 'Лимит трафика', value: `${Math.round(grant.quota_bytes / (1024 * 1024 * 1024))} GB`, icon: 'data_usage' })
  }
  return facts
}

function accessGrantSourceIcon(sourceType: string) {
  const normalized = String(sourceType || '').trim().toLowerCase()
  if (normalized === 'payment') return 'credit_card'
  if (normalized === 'request_approval') return 'approval'
  if (normalized === 'access_registry') return 'badge'
  if (normalized === 'access_registry_auto_renew') return 'autorenew'
  if (normalized === 'admin_override') return 'admin_panel_settings'
  return 'vpn_key'
}

async function copyReferralLink() {
  if (!referrals.value?.referral_link) return
  try {
    await navigator.clipboard.writeText(referrals.value.referral_link)
    toast.success('Ссылка приглашения скопирована')
  } catch {
    toast.error('Не удалось скопировать ссылку')
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const [configData, linksData, subscriptionsData] = await Promise.all([
      fetchPublicConfig().catch(() => createEmptyPublicConfig()),
      fetchLinks(),
      fetchSubscriptions(),
    ])
    publicConfig.value = configData
    links.value = linksData
    subscriptions.value = subscriptionsData
    referrals.value = referralsEnabled.value
      ? await fetchReferralStats().catch(() => null)
      : null
    accessGrants.value = await fetchAccessGrants().catch(() => [])
  } catch {
    toast.error('Не удалось загрузить кабинет')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="cabinet-section">
    <!-- Loading state -->
    <div v-if="loading" class="cabinet-loader">
      <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
      <p class="cabinet-loader__text">Загружаем кабинет...</p>
    </div>

    <template v-else>
      <!-- TG linking banner (prominent for email-only users) -->
      <div v-if="needsTelegramLink" class="tg-banner glass-card cabinet-panel">
        <div class="tg-banner__content">
          <div class="tg-banner__icon-wrap">
            <span class="material-symbols-outlined tg-banner__icon">link</span>
          </div>
          <div class="tg-banner__text">
            <h2 class="tg-banner__title">Привяжи Telegram</h2>
            <p class="tg-banner__desc">
              Без привязки бот создаст отдельный аккаунт. Свяжи Telegram, чтобы доступ и уведомления были в одном месте.
            </p>
          </div>
        </div>
        <RouterLink class="cabinet-btn cabinet-btn--primary tg-banner__btn" to="/app/profile">
          <span class="material-symbols-outlined">add_link</span>
          Привязать в профиле
        </RouterLink>
      </div>

      <!-- Email linking banner (prominent for Telegram-only users) -->
      <div v-if="needsEmailLink" class="tg-banner tg-banner--blue glass-card cabinet-panel">
        <div class="tg-banner__content">
          <div class="tg-banner__icon-wrap tg-banner__icon-wrap--blue">
            <span class="material-symbols-outlined tg-banner__icon tg-banner__icon--blue">mail</span>
          </div>
          <div class="tg-banner__text">
            <h2 class="tg-banner__title">Добавь email</h2>
            <p class="tg-banner__desc">
              Ты зашёл через Telegram — добавь email, чтобы заходить на сайт без бота,
              восстанавливать доступ и получать важные уведомления.
            </p>
          </div>
        </div>
        <RouterLink class="cabinet-btn cabinet-btn--primary tg-banner__btn" to="/app/profile">
          <span class="material-symbols-outlined">mail</span>
          Добавить в профиле
        </RouterLink>
      </div>

      <!-- Main cards -->
      <div class="cabinet-grid cabinet-grid--2">
        <!-- Account card -->
        <article class="glass-card cabinet-panel ov-card ov-card--account">
          <div class="ov-card__header">
            <div class="ov-card__icon-circle ov-card__icon-circle--warm">
              <span class="material-symbols-outlined">person</span>
            </div>
            <div>
              <p class="cabinet-kicker">Аккаунт</p>
              <h2 class="ov-card__name">{{ accountDisplayName }}</h2>
            </div>
          </div>

          <div class="ov-card__facts">
            <div v-if="showEmailFact" class="ov-fact">
              <span class="material-symbols-outlined ov-fact__icon">mail</span>
              <div>
                <p class="ov-fact__label">Email</p>
                <p class="ov-fact__value">{{ session.me?.email || session.me?.preferred_contact_email || 'Нужно привязать' }}</p>
              </div>
            </div>
            <div class="ov-fact">
              <span class="material-symbols-outlined ov-fact__icon">send</span>
              <div>
                <p class="ov-fact__label">Telegram</p>
                <p class="ov-fact__value">
                  {{ links?.telegram.linked ? `@${links.telegram.username || 'привязан'}` : 'Не привязан' }}
                </p>
              </div>
            </div>
            <div class="ov-fact">
              <span class="material-symbols-outlined ov-fact__icon">login</span>
              <div>
                <p class="ov-fact__label">Способ входа</p>
                <p class="ov-fact__value">{{ loginMethod }}</p>
              </div>
            </div>
          </div>

          <RouterLink class="cabinet-btn cabinet-btn--ghost" to="/app/profile">
            <span class="material-symbols-outlined">settings</span>
            Настройки
          </RouterLink>
        </article>

        <!-- Subscriptions card -->
        <article class="glass-card cabinet-panel ov-card ov-card--subs">
          <div class="ov-card__header">
            <div class="ov-card__icon-circle ov-card__icon-circle--blue">
              <span class="material-symbols-outlined">vpn_key</span>
            </div>
            <div>
              <p class="cabinet-kicker">Доступ</p>
              <h2 class="ov-card__name">{{ activeCount > 0 ? `${activeCount} активных` : 'Нет активных' }}</h2>
            </div>
          </div>

          <div class="ov-subs-grid">
            <div v-for="row in visibleSubscriptionRows" :key="row.key" class="ov-sub-row">
              <span class="ov-sub-row__dot" :class="row.active ? 'ov-sub-row__dot--ok' : ''"></span>
              <span class="ov-sub-row__label">{{ row.label }}</span>
              <span class="ov-sub-row__status">{{ row.active ? 'Активен' : 'Нет' }}</span>
            </div>
          </div>

          <div class="cabinet-actions">
            <RouterLink class="cabinet-btn cabinet-btn--primary" to="/app/subscriptions">
              <span class="material-symbols-outlined">vpn_key</span>
              Мой доступ
            </RouterLink>
            <RouterLink
              v-if="!registryManagedAccess && (webPurchaseEnabled || accessRequestsEnabled)"
              class="cabinet-btn cabinet-btn--warm"
              to="/app/purchase"
            >
              <span class="material-symbols-outlined">vpn_key</span>
              {{ accessActionLabel }}
            </RouterLink>
          </div>
          <p v-if="registryManagedAccess" class="cabinet-note">
            Доступ для этого аккаунта управляется через реестр и продлевается автоматически.
          </p>
        </article>
      </div>

      <article class="glass-card cabinet-panel ov-card ov-card--access-history">
        <div class="ov-card__header">
          <div class="ov-card__icon-circle ov-card__icon-circle--blue">
            <span class="material-symbols-outlined">history</span>
          </div>
          <div>
            <p class="cabinet-kicker">История доступа</p>
            <h2 class="ov-card__name">{{ recentAccessGrants.length ? 'Последние выдачи' : 'Выдач пока нет' }}</h2>
          </div>
        </div>

        <div v-if="recentAccessGrants.length" class="ov-grants-list">
          <div v-for="grant in recentAccessGrants" :key="grant.id" class="ov-grant-row">
            <div class="ov-grant-row__left">
              <span class="material-symbols-outlined ov-grant-row__icon">{{ accessGrantSourceIcon(grant.source_type) }}</span>
              <div>
                <p class="ov-grant-row__title">{{ accessGrantSourceLabel(grant.source_type) }}</p>
                <p class="cabinet-note">
                  {{ accessGrantScopeLabel(grant.scope) }}
                  <span v-if="grant.template_code"> · {{ grant.template_label || formatAccessTemplateLabel(grant.template_code) }}</span>
                </p>
              </div>
            </div>
            <div class="ov-grant-row__side">
              <span class="cabinet-badge" :class="grant.status === 'active' ? 'cabinet-badge--ok' : 'cabinet-badge--muted'">
                {{ accessGrantStatusLabel(grant.status) }}
              </span>
              <small class="cabinet-note">{{ new Date(grant.created_at).toLocaleString() }}</small>
            </div>
          </div>
        </div>
        <p v-else class="cabinet-note">История выдачи доступа появится после первой активации.</p>
      </article>

      <article class="glass-card cabinet-panel ov-card ov-card--access-reason">
        <div class="ov-card__header">
          <div class="ov-card__icon-circle ov-card__icon-circle--green">
            <span class="material-symbols-outlined">fact_check</span>
          </div>
          <div>
            <p class="cabinet-kicker">Почему доступ активен</p>
            <h2 class="ov-card__name">{{ activeAccessReasonTitle() }}</h2>
          </div>
        </div>

        <div v-if="activeAccessReasonFacts().length" class="ov-reason-facts">
          <div v-for="fact in activeAccessReasonFacts()" :key="fact.label" class="ov-reason-fact">
            <span class="material-symbols-outlined ov-reason-fact__icon">{{ fact.icon }}</span>
            <div>
              <p class="ov-reason-fact__label">{{ fact.label }}</p>
              <p class="ov-reason-fact__value">{{ fact.value }}</p>
            </div>
          </div>
        </div>
        <p v-else class="cabinet-note">
          Когда заявка будет одобрена или доступ будет оформлен, здесь появится объяснение, почему доступ активен и на каких условиях он выдан.
        </p>

        <div class="cabinet-actions">
          <RouterLink
            v-if="!registryManagedAccess && (webPurchaseEnabled || accessRequestsEnabled)"
            class="cabinet-btn cabinet-btn--ghost"
            to="/app/purchase"
          >
            <span class="material-symbols-outlined">vpn_key</span>
            Запросить продление
          </RouterLink>
        </div>
      </article>

      <!-- Referral stats + Promo code row -->
      <div v-if="referralsEnabled || promosEnabled" class="cabinet-grid cabinet-grid--2">
        <!-- Referral card -->
        <article v-if="referralsEnabled" class="glass-card cabinet-panel ov-card ov-card--referral">
          <div class="ov-card__header">
            <div class="ov-card__icon-circle ov-card__icon-circle--green">
              <span class="material-symbols-outlined">group_add</span>
            </div>
            <div>
              <p class="cabinet-kicker">Приглашения</p>
              <h2 class="ov-card__name">Доступ по ссылке</h2>
            </div>
          </div>

          <div class="ov-ref-stats">
            <div class="ov-ref-stat">
              <p class="ov-ref-stat__value">{{ referrals?.invited_count ?? 0 }}</p>
              <p class="ov-ref-stat__label">Приглашено</p>
            </div>
            <div class="ov-ref-stat">
              <p class="ov-ref-stat__value">{{ referrals?.paid_count ?? 0 }}</p>
              <p class="ov-ref-stat__label">Активировали</p>
            </div>
            <div class="ov-ref-stat">
              <p class="ov-ref-stat__value">{{ referrals?.pending_days ?? 0 }}д</p>
              <p class="ov-ref-stat__label">Бонус</p>
            </div>
          </div>

          <div v-if="referrals?.referral_link" class="ov-ref-link">
            <p class="ov-ref-link__url">{{ referrals.referral_link }}</p>
            <button class="cabinet-btn cabinet-btn--ghost" type="button" @click="copyReferralLink">
              <span class="material-symbols-outlined">content_copy</span>
              Скопировать
            </button>
          </div>
          <p v-else class="cabinet-note">Привяжи Telegram для получения реферальной ссылки.</p>
        </article>

        <!-- Promo code card -->
        <article v-if="promosEnabled" class="glass-card cabinet-panel ov-card ov-card--promo">
          <div class="ov-card__header">
            <div class="ov-card__icon-circle ov-card__icon-circle--purple">
              <span class="material-symbols-outlined">confirmation_number</span>
            </div>
            <div>
              <p class="cabinet-kicker">Промокод</p>
              <h2 class="ov-card__name">Активировать</h2>
            </div>
          </div>

          <p class="cabinet-note">Введи промокод, чтобы получить дополнительные дни доступа.</p>

          <form class="ov-promo-form" @submit.prevent="submitPromoCode">
            <input
              v-model.trim="promoCode"
              class="cabinet-input"
              type="text"
              placeholder="Введи промокод"
              :disabled="promoLoading"
            />
            <button class="cabinet-btn cabinet-btn--primary" type="submit" :disabled="promoLoading || !promoCode">
              <span class="material-symbols-outlined">{{ promoLoading ? 'hourglass_top' : 'redeem' }}</span>
              {{ promoLoading ? 'Применяем...' : 'Применить' }}
            </button>
          </form>

          <p v-if="promoSuccess" class="ov-promo-success">
            <span class="material-symbols-outlined ov-promo-success__icon">check_circle</span>
            {{ promoSuccess }}
          </p>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* ── Card base ── */
.ov-card {
  display: grid;
  gap: 18px;
  align-content: start;
}

.ov-card__header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.ov-card__icon-circle {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  flex-shrink: 0;
  font-size: 26px;
}

.ov-card__icon-circle--warm {
  color: var(--cabinet-standard);
  background: linear-gradient(135deg, rgba(245, 160, 78, 0.15), rgba(255, 120, 60, 0.08));
}

.ov-card__icon-circle--blue {
  color: var(--cabinet-traffic_limited);
  background: linear-gradient(135deg, rgba(77, 143, 214, 0.15), rgba(100, 180, 255, 0.08));
}

.ov-card__icon-circle--green {
  color: #3da866;
  background: linear-gradient(135deg, rgba(61, 168, 102, 0.12), rgba(80, 200, 120, 0.06));
}

.ov-card__icon-circle--purple {
  color: #8b5cf6;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.12), rgba(160, 120, 255, 0.06));
}

.ov-card__name {
  margin: 0;
  font: 700 clamp(17px, 3vw, 20px)/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

/* ── Account card ── */
.ov-card--account {
  background:
    radial-gradient(circle at 95% 5%, rgba(245, 160, 78, 0.1), transparent 40%),
    var(--cabinet-surface);
}

.ov-card__facts {
  display: grid;
  gap: 12px;
}

.ov-fact {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.06);
}

.ov-fact__icon {
  font-size: 20px;
  color: var(--cabinet-muted);
  flex-shrink: 0;
}

.ov-fact__label {
  margin: 0;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--cabinet-muted);
}

.ov-fact__value {
  margin: 0;
  font: 600 14px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

/* ── Subscriptions card ── */
.ov-card--subs {
  background:
    radial-gradient(circle at 95% 5%, rgba(77, 143, 214, 0.08), transparent 40%),
    var(--cabinet-surface);
}

.ov-card--access-history {
  background:
    radial-gradient(circle at 95% 5%, rgba(77, 143, 214, 0.06), transparent 40%),
    var(--cabinet-surface);
}

.ov-grants-list {
  display: grid;
  gap: 10px;
}

.ov-grant-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.08);
  transition: transform 180ms, box-shadow 180ms;
}

.ov-grant-row:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(100, 120, 150, 0.06);
}

.ov-grant-row__left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.ov-grant-row__icon {
  font-size: 22px;
  color: var(--cabinet-traffic_limited);
  flex-shrink: 0;
}

.ov-grant-row__title {
  margin: 0 0 4px;
  font: 600 14px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.ov-grant-row__side {
  display: grid;
  justify-items: end;
  gap: 6px;
  text-align: right;
  flex-shrink: 0;
}

/* ── Access reason facts ── */
.ov-card--access-reason {
  background:
    radial-gradient(circle at 95% 5%, rgba(61, 168, 102, 0.06), transparent 40%),
    var(--cabinet-surface);
}

.ov-reason-facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.ov-reason-fact {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.06);
}

.ov-reason-fact__icon {
  font-size: 20px;
  color: #3da866;
  flex-shrink: 0;
  margin-top: 1px;
}

.ov-reason-fact__label {
  margin: 0;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--cabinet-muted);
}

.ov-reason-fact__value {
  margin: 2px 0 0;
  font: 600 14px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.ov-subs-grid {
  display: grid;
  gap: 10px;
}

.ov-sub-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.06);
}

.ov-sub-row__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--cabinet-muted);
  opacity: 0.3;
  flex-shrink: 0;
}

.ov-sub-row__dot--ok {
  background: var(--cabinet-ok);
  opacity: 1;
  box-shadow: 0 0 8px rgba(61, 168, 102, 0.45);
  animation: pulse-soft 2s ease-in-out infinite;
}

.ov-sub-row__label {
  flex: 1;
  font: 600 14px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.ov-sub-row__status {
  font: 400 13px/1.2 var(--font-text);
  color: var(--cabinet-muted);
}

/* ── Referral card ── */
.ov-card--referral {
  background:
    radial-gradient(circle at 95% 5%, rgba(61, 168, 102, 0.08), transparent 40%),
    var(--cabinet-surface);
}

.ov-ref-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.ov-ref-stat {
  text-align: center;
  padding: 14px 8px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.06);
}

.ov-ref-stat__value {
  margin: 0;
  font: 700 22px/1.1 var(--font-ui);
  color: var(--cabinet-text);
}

.ov-ref-stat__label {
  margin: 4px 0 0;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--cabinet-muted);
}

.ov-ref-link {
  display: grid;
  gap: 8px;
}

.ov-ref-link__url {
  margin: 0;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(126, 170, 220, 0.1);
  font: 400 13px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--cabinet-text);
  word-break: break-all;
}

/* ── Promo card ── */
.ov-card--promo {
  background:
    radial-gradient(circle at 95% 5%, rgba(139, 92, 246, 0.06), transparent 40%),
    var(--cabinet-surface);
}

.ov-promo-form {
  display: grid;
  gap: 10px;
}

.ov-promo-success {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(61, 168, 102, 0.08);
  border: 1px solid rgba(61, 168, 102, 0.15);
  font: 500 13px/1.4 var(--font-text);
  color: #267a48;
}

.ov-promo-success__icon {
  font-size: 18px;
  flex-shrink: 0;
}

/* ── TG linking banner ── */
.tg-banner {
  display: grid;
  gap: 16px;
  border-left: 4px solid var(--accent);
  background:
    radial-gradient(circle at top right, rgba(255, 100, 70, 0.08), transparent 40%),
    rgba(255, 252, 249, 0.96);
}

.tg-banner__content {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.tg-banner__icon-wrap {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(255, 100, 70, 0.12), rgba(255, 140, 50, 0.06));
  flex-shrink: 0;
}

.tg-banner__icon {
  font-size: 26px;
  color: var(--accent);
}

.tg-banner__text {
  display: grid;
  gap: 6px;
}

.tg-banner__title {
  margin: 0;
  font: 700 18px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.tg-banner__desc {
  margin: 0;
  font: 400 14px/1.5 var(--font-text);
  color: var(--cabinet-muted);
}

.tg-banner__btn {
  justify-self: start;
}

/* ── Blue variant (email linking) ── */
.tg-banner--blue {
  border-left-color: var(--cabinet-traffic_limited);
  background:
    radial-gradient(circle at top right, rgba(77, 143, 214, 0.1), transparent 40%),
    rgba(248, 252, 255, 0.96);
}

.tg-banner__icon-wrap--blue {
  background: linear-gradient(135deg, rgba(77, 143, 214, 0.15), rgba(100, 180, 255, 0.06));
}

.tg-banner__icon--blue {
  color: var(--cabinet-traffic_limited);
}

@media (max-width: 720px) {
  .tg-banner__content {
    flex-direction: column;
    gap: 10px;
  }

  .ov-ref-stats {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
