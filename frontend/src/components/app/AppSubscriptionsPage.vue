<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import { fetchSubscriptions, type WebSubscriptions } from '../../api/account'
import {
  DEFAULT_FEATURE_FLAGS,
  createEmptyPublicConfig,
  fetchPublicConfig,
  type FrontendFeatureFlags,
  type FrontendPublicConfig,
} from '../../api/publicConfig'
import { formatDateTime } from '../../utils/format'

const toast = useToast()
const subscriptions = ref<WebSubscriptions | null>(null)
const publicConfig = ref<FrontendPublicConfig>(createEmptyPublicConfig())
const loading = ref(true)
const features = computed<FrontendFeatureFlags>(() => publicConfig.value.features || DEFAULT_FEATURE_FLAGS)
const webPurchaseEnabled = computed(() => features.value.commerce_enabled && features.value.web_purchase_enabled)

function buildHappImportLink(importUrl?: string | null) {
  const addLink = publicConfig.value?.subscription_add_links?.happ?.trim() || ''
  const normalizedImportUrl = importUrl?.trim() || ''

  if (!addLink || !normalizedImportUrl) {
    return ''
  }

  return `${addLink}${normalizedImportUrl}`
}

async function copyImportUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url)
    toast.success('Ссылка подписки скопирована')
  } catch {
    toast.error('Не удалось скопировать ссылку')
  }
}

const cards = computed(() => {
  if (!subscriptions.value) return []

  return [
    {
      key: 'standard',
      title: 'Базовая конфигурация',
      icon: 'vpn_key',
      accentClass: 'scope-card--warm',
      buttonClass: 'cabinet-btn--warm',
      active: subscriptions.value.standard.is_active,
      primaryLabel: 'Срок действия',
      primaryValue: subscriptions.value.standard.human_view_expiration_remaining || 'Нет активной подписки',
      secondaryLabel: 'Действует до',
      secondaryValue: formatDateTime(subscriptions.value.standard.expires_at),
      importUrl: subscriptions.value.standard.subscription_import_url,
      note: 'Повседневный защищённый удалённый доступ.',
      metrics: [],
    },
    {
      key: 'whitelist',
      title: 'Конфигурация с лимитом трафика',
      icon: 'shield',
      accentClass: 'scope-card--blue',
      buttonClass: 'cabinet-btn--primary',
      active: subscriptions.value.whitelist.is_active,
      primaryLabel: 'Остаток трафика',
      primaryValue: subscriptions.value.whitelist.human_view_traffic_remaining || 'Нет активного пакета',
      secondaryLabel: 'Действует до',
      secondaryValue: formatDateTime(subscriptions.value.whitelist.expires_at),
      importUrl: subscriptions.value.whitelist.subscription_import_url,
      note: 'Отдельный контур с учётом трафика и срока действия.',
      metrics: [
        { label: 'Использовано', value: subscriptions.value.whitelist.human_view_traffic_used || '0 B' },
        { label: 'Выдано', value: subscriptions.value.whitelist.human_view_traffic_allocated || '0 B' },
      ],
    },
  ]
})

onMounted(async () => {
  loading.value = true
  try {
    const [subscriptionsData, configData] = await Promise.all([fetchSubscriptions(), fetchPublicConfig()])
    subscriptions.value = subscriptionsData
    publicConfig.value = configData
  } catch {
    publicConfig.value = createEmptyPublicConfig()
    toast.error('Не удалось загрузить подписки')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="cabinet-section">
    <div class="cabinet-section__head">
      <p class="cabinet-kicker">Мои подписки</p>
      <h2 class="cabinet-title">Текущий доступ</h2>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="cabinet-loader">
      <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
      <p class="cabinet-loader__text">Загружаем подписки...</p>
    </div>

    <div v-else class="cabinet-grid cabinet-grid--2">
      <article v-for="card in cards" :key="card.key" class="glass-card cabinet-panel scope-card" :class="card.accentClass">
        <!-- Header -->
        <div class="scope-card__header">
          <div class="scope-card__icon-wrap" :class="`scope-card__icon-wrap--${card.key}`">
            <span class="material-symbols-outlined">{{ card.icon }}</span>
          </div>
          <div class="scope-card__title-area">
            <h3 class="scope-card__title">{{ card.title }}</h3>
            <span class="scope-card__status" :class="card.active ? 'scope-card__status--ok' : 'scope-card__status--off'">
              <span class="scope-card__dot"></span>
              {{ card.active ? 'Активен' : 'Не активен' }}
            </span>
          </div>
        </div>

        <!-- Active subscription content -->
        <template v-if="card.importUrl">
          <div class="scope-card__metrics">
            <div class="scope-metric">
              <p class="scope-metric__label">{{ card.primaryLabel }}</p>
              <p class="scope-metric__value">{{ card.primaryValue }}</p>
            </div>
            <div class="scope-metric">
              <p class="scope-metric__label">{{ card.secondaryLabel }}</p>
              <p class="scope-metric__value">{{ card.secondaryValue }}</p>
            </div>
            <template v-if="card.metrics.length">
              <div v-for="metric in card.metrics" :key="metric.label" class="scope-metric">
                <p class="scope-metric__label">{{ metric.label }}</p>
                <p class="scope-metric__value">{{ metric.value }}</p>
              </div>
            </template>
          </div>

          <p class="scope-card__note">{{ card.note }}</p>

          <div class="scope-card__actions">
            <a
              v-if="buildHappImportLink(card.importUrl)"
              class="cabinet-btn"
              :class="card.buttonClass"
              :href="buildHappImportLink(card.importUrl)"
              target="_blank"
              rel="noopener noreferrer"
            >
              <span class="material-symbols-outlined">add_link</span>
              Добавить в Happ
            </a>
            <button class="cabinet-btn cabinet-btn--ghost" type="button" @click="copyImportUrl(card.importUrl!)">
              <span class="material-symbols-outlined">content_copy</span>
              Скопировать
            </button>
          </div>

          <p class="scope-card__hint">
            Скачайте <RouterLink to="/app/help" class="scope-card__hint-link">Happ</RouterLink> и добавьте подписку одной кнопкой.
          </p>
        </template>

        <!-- Inactive subscription — cute animation -->
        <template v-else>
          <div class="scope-empty">
            <div class="scope-empty__visual">
              <div class="scope-empty__ring"></div>
              <span class="material-symbols-outlined scope-empty__icon">{{ card.icon }}</span>
              <span class="scope-empty__dot scope-empty__dot--1"></span>
              <span class="scope-empty__dot scope-empty__dot--2"></span>
              <span class="scope-empty__dot scope-empty__dot--3"></span>
            </div>
            <p class="scope-empty__text">Подписка пока не активна</p>
            <p class="scope-empty__hint">{{ card.note }}</p>
          </div>

          <div class="scope-card__actions">
            <RouterLink v-if="webPurchaseEnabled" class="cabinet-btn" :class="card.buttonClass" to="/app/purchase">
              <span class="material-symbols-outlined">shopping_cart</span>
              Получить доступ
            </RouterLink>
          </div>
        </template>
      </article>
    </div>

    <!-- Help banner -->
    <article v-if="!loading" class="glass-card cabinet-panel subs-help">
      <span class="material-symbols-outlined subs-help__icon">help_outline</span>
      <div class="subs-help__body">
        <p class="subs-help__title">Не знаете, как подключиться?</p>
        <p class="subs-help__desc">Скачайте приложение Happ, добавьте подписку — и VPN заработает. Подробная инструкция и ссылки на загрузку на странице помощи.</p>
      </div>
      <RouterLink class="cabinet-btn cabinet-btn--ghost" to="/app/help">
        <span class="material-symbols-outlined">arrow_forward</span>
        Помощь
      </RouterLink>
    </article>
  </section>
</template>

<style scoped>
/* ── Scope card ── */
.scope-card {
  display: grid;
  gap: 16px;
}

.scope-card--warm {
  background:
    radial-gradient(circle at 95% 5%, rgba(245, 160, 78, 0.12), transparent 35%),
    var(--cabinet-surface);
}

.scope-card--blue {
  background:
    radial-gradient(circle at 95% 5%, rgba(77, 143, 214, 0.1), transparent 35%),
    var(--cabinet-surface);
}

.scope-card__header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.scope-card__icon-wrap {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  flex-shrink: 0;
  font-size: 24px;
}

.scope-card__icon-wrap--standard {
  color: var(--cabinet-standard);
  background: linear-gradient(135deg, rgba(245, 160, 78, 0.18), rgba(255, 120, 60, 0.08));
}

.scope-card__icon-wrap--whitelist {
  color: var(--cabinet-whitelist);
  background: linear-gradient(135deg, rgba(77, 143, 214, 0.18), rgba(100, 180, 255, 0.08));
}

.scope-card__title-area {
  display: grid;
  gap: 4px;
  flex: 1;
}

.scope-card__title {
  margin: 0;
  font: 700 17px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.scope-card__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 600 12px/1 var(--font-ui);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.scope-card__status--ok {
  color: #267a48;
}

.scope-card__status--off {
  color: #a13c3c;
}

.scope-card__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.scope-card__status--ok .scope-card__dot {
  box-shadow: 0 0 8px rgba(61, 168, 102, 0.5);
  animation: pulse-soft 2s ease-in-out infinite;
}

/* Metrics */
.scope-card__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.scope-metric {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.06);
}

.scope-metric__label {
  margin: 0;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--cabinet-muted);
}

.scope-metric__value {
  margin: 2px 0 0;
  font: 600 14px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.scope-card__note {
  margin: 0;
  font: 400 13px/1.5 var(--font-text);
  color: var(--cabinet-muted);
}

.scope-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.scope-card__hint {
  margin: 0;
  font-size: 12px;
  color: var(--cabinet-muted);
}

.scope-card__hint-link {
  color: var(--cabinet-whitelist);
  text-decoration: none;
  font-weight: 600;
}

.scope-card__hint-link:hover {
  text-decoration: underline;
}

/* ── Help banner ── */
.subs-help {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
}

.subs-help__icon {
  font-size: 28px;
  color: var(--cabinet-whitelist);
  flex-shrink: 0;
}

.subs-help__body {
  flex: 1;
  min-width: 0;
}

.subs-help__title {
  margin: 0;
  font: 700 14px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.subs-help__desc {
  margin: 2px 0 0;
  font: 400 13px/1.5 var(--font-text);
  color: var(--cabinet-muted);
}

@media (max-width: 720px) {
  .subs-help {
    flex-direction: column;
    text-align: center;
  }
}

/* ── Empty / inactive animation ── */
.scope-empty {
  display: grid;
  place-items: center;
  gap: 12px;
  padding: 24px 8px;
  text-align: center;
}

.scope-empty__visual {
  position: relative;
  width: 96px;
  height: 96px;
  display: grid;
  place-items: center;
}

.scope-empty__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px dashed rgba(126, 170, 220, 0.2);
  animation: empty-spin 12s linear infinite;
}

.scope-empty__icon {
  font-size: 36px;
  color: var(--cabinet-muted);
  opacity: 0.45;
  animation: empty-float 3s ease-in-out infinite;
}

.scope-card--warm .scope-empty__icon {
  color: var(--cabinet-standard);
  opacity: 0.35;
}

.scope-card--blue .scope-empty__icon {
  color: var(--cabinet-whitelist);
  opacity: 0.35;
}

.scope-empty__dot {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  opacity: 0.5;
}

.scope-empty__dot--1 {
  top: 8px;
  right: 12px;
  background: var(--cabinet-standard);
  animation: empty-dot 3s ease-in-out infinite;
}

.scope-empty__dot--2 {
  bottom: 10px;
  left: 8px;
  background: var(--cabinet-whitelist);
  animation: empty-dot 3s ease-in-out 1s infinite;
}

.scope-empty__dot--3 {
  top: 50%;
  left: 2px;
  width: 6px;
  height: 6px;
  background: var(--cabinet-muted);
  animation: empty-dot 3s ease-in-out 2s infinite;
}

.scope-empty__text {
  margin: 0;
  font: 600 15px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.scope-empty__hint {
  margin: 0;
  max-width: 260px;
  font: 400 13px/1.5 var(--font-text);
  color: var(--cabinet-muted);
}

@keyframes empty-spin {
  to { transform: rotate(360deg); }
}

@keyframes empty-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

@keyframes empty-dot {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(1.3); }
}

@media (max-width: 720px) {
  .scope-card__metrics {
    grid-template-columns: 1fr;
  }
}
</style>
