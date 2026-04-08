<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'vue-toastification'

import {
  DEFAULT_FEATURE_FLAGS,
  DEFAULT_PRODUCT_CONFIG,
  fetchPublicConfig,
  type FrontendFeatureFlags,
  type FrontendProductConfig,
} from '../../api/publicConfig'
import { clearSession, useSessionState } from '../../stores/session'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const session = useSessionState()
const features = ref<FrontendFeatureFlags>({ ...DEFAULT_FEATURE_FLAGS })
const product = ref<FrontendProductConfig>({ ...DEFAULT_PRODUCT_CONFIG, docs_links: {} })

const commerceEnabled = computed(() => features.value.commerce_enabled)
const webPurchaseEnabled = computed(() => features.value.commerce_enabled && features.value.web_purchase_enabled)

const sections = computed(() => {
  const items = [
  { label: 'Обзор', to: '/app', icon: 'dashboard' },
  { label: 'Подписки', to: '/app/subscriptions', icon: 'vpn_key' },
  ]
  if (webPurchaseEnabled.value) {
    items.push({ label: 'Покупка', to: '/app/purchase', icon: 'shopping_cart' })
  }
  items.push({ label: 'Помощь', to: '/app/help', icon: 'help' })
  if (commerceEnabled.value) {
    items.push({ label: 'Транзакции', to: '/app/payments', icon: 'receipt_long' })
  }
  return items
})

const displayName = computed(() => session.me?.display_name || session.me?.email || 'Кабинет')

async function logout() {
  await clearSession()
  toast.success('Сессия завершена')
  await router.replace('/auth/login')
}

onMounted(async () => {
  try {
    const publicConfig = await fetchPublicConfig()
    features.value = publicConfig.features
    product.value = publicConfig.product
    document.title = publicConfig.product.name
  } catch {
    features.value = { ...DEFAULT_FEATURE_FLAGS }
  }
})
</script>

<template>
  <div class="cabinet-shell page-shell">
    <div class="cabinet-scene" aria-hidden="true">
      <div class="cabinet-scene__orb cabinet-scene__orb--one"></div>
      <div class="cabinet-scene__orb cabinet-scene__orb--two"></div>
      <div class="cabinet-scene__orb cabinet-scene__orb--three"></div>
      <div class="cabinet-scene__ring cabinet-scene__ring--one"></div>
      <div class="cabinet-scene__ring cabinet-scene__ring--two"></div>
      <span class="cabinet-scene__dot cabinet-scene__dot--one"></span>
      <span class="cabinet-scene__dot cabinet-scene__dot--two"></span>
      <span class="cabinet-scene__dot cabinet-scene__dot--three"></span>
    </div>

    <header class="cabinet-header glass-card cabinet-panel">
      <div class="cabinet-header__top">
        <div class="cabinet-header__brand">
          <img src="/favicon.svg" alt="Логотип сервиса" class="cabinet-header__logo" />
          <div class="cabinet-header__intro">
            <h1 class="cabinet-header__title">
              <span class="brand-title cabinet-header__brand-text">{{ product.short_name }}</span>
              <span class="cabinet-header__name">{{ displayName }}</span>
            </h1>
            <p class="cabinet-header__lead">Конфигурации доступа, подключение и профиль</p>
          </div>
        </div>
        <div class="cabinet-header__actions">
          <div class="cabinet-header__meta">
            <span class="cabinet-badge" :class="session.me?.telegram_linked ? 'cabinet-badge--ok' : ''">
              {{ session.me?.telegram_linked ? 'TG привязан' : 'TG не привязан' }}
            </span>
          </div>
          <div class="cabinet-header__buttons">
            <RouterLink class="cabinet-btn cabinet-btn--ghost cabinet-header__icon-btn" to="/app/profile" title="Профиль">
              <span class="material-symbols-outlined">person</span>
            </RouterLink>
            <button class="cabinet-btn cabinet-btn--ghost cabinet-header__icon-btn" type="button" @click="logout" title="Выйти">
              <span class="material-symbols-outlined">logout</span>
            </button>
          </div>
        </div>
      </div>
    </header>

    <nav class="cabinet-nav glass-card cabinet-panel" aria-label="Разделы кабинета">
      <RouterLink
        v-for="section in sections"
        :key="section.to"
        :to="section.to"
        class="cabinet-nav__link"
        :class="{ 'cabinet-nav__link--active': route.path === section.to }"
      >
        <span class="material-symbols-outlined cabinet-nav__icon">{{ section.icon }}</span>
        <span class="cabinet-nav__label">{{ section.label }}</span>
      </RouterLink>
    </nav>

    <router-view />
  </div>
</template>

<style scoped>
/* ── Scene ── */
.cabinet-scene {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: -1;
  overflow: hidden;
}

.cabinet-scene__orb,
.cabinet-scene__ring,
.cabinet-scene__dot {
  position: absolute;
}

.cabinet-scene__orb {
  border-radius: 50%;
  filter: blur(14px);
}

.cabinet-scene__orb--one {
  top: 50px;
  right: min(6vw, 70px);
  width: min(28vw, 260px);
  height: min(28vw, 260px);
  background: radial-gradient(circle, rgba(255, 100, 70, 0.22), transparent 65%);
  animation: scene-float 14s ease-in-out infinite;
}

.cabinet-scene__orb--two {
  left: min(4vw, 40px);
  bottom: 10%;
  width: min(24vw, 200px);
  height: min(24vw, 200px);
  background: radial-gradient(circle, rgba(77, 143, 214, 0.2), transparent 64%);
  animation: scene-float 12s ease-in-out infinite reverse;
}

.cabinet-scene__orb--three {
  top: 40%;
  left: 50%;
  transform: translateX(-50%);
  width: min(20vw, 180px);
  height: min(20vw, 180px);
  background: radial-gradient(circle, rgba(62, 191, 176, 0.14), transparent 65%);
  animation: scene-float 16s ease-in-out infinite;
  animation-delay: -4s;
}

.cabinet-scene__ring {
  border-radius: 50%;
  border: 1.5px solid rgba(126, 170, 220, 0.14);
}

.cabinet-scene__ring--one {
  top: 70px;
  left: 6%;
  width: min(32vw, 280px);
  height: min(32vw, 280px);
  animation: slow-spin 40s linear infinite;
}

.cabinet-scene__ring--two {
  right: 10%;
  bottom: 8%;
  width: min(20vw, 170px);
  height: min(20vw, 170px);
  animation: slow-spin 30s linear infinite reverse;
}

.cabinet-scene__dot {
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(77, 143, 214, 0.4));
  box-shadow: 0 0 0 8px rgba(255, 255, 255, 0.06);
  animation: float-ambient 10s ease-in-out infinite;
}

.cabinet-scene__dot--one {
  top: 16%;
  left: 16%;
  width: 10px;
  height: 10px;
}

.cabinet-scene__dot--two {
  bottom: 14%;
  right: 18%;
  width: 8px;
  height: 8px;
  animation-delay: -4s;
}

.cabinet-scene__dot--three {
  top: 50%;
  right: 30%;
  width: 6px;
  height: 6px;
  animation-delay: -8s;
}

/* ── Header ── */
.cabinet-header {
  border-radius: 28px;
}

.cabinet-header__top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}

.cabinet-header__brand {
  display: flex;
  align-items: center;
  gap: 16px;
}

.cabinet-header__logo {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: 2.5px solid rgba(255, 90, 68, 0.28);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 6px 18px rgba(151, 53, 34, 0.15);
  flex-shrink: 0;
  animation: float-soft 4s ease-in-out infinite;
}

.cabinet-header__intro {
  display: grid;
  gap: 4px;
}

.cabinet-header__title {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.cabinet-header__brand-text {
  font-size: clamp(22px, 4vw, 30px);
  color: var(--accent);
}

.cabinet-header__name {
  font: 700 clamp(18px, 3vw, 24px)/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.cabinet-header__lead {
  margin: 0;
  color: var(--cabinet-muted);
  font-size: 14px;
}

.cabinet-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.cabinet-header__buttons {
  display: flex;
  gap: 6px;
}

.cabinet-header__icon-btn {
  padding: 0 12px;
  min-height: 42px;
}

/* ── Nav ── */
.cabinet-nav {
  display: flex;
  gap: 4px;
  margin-top: 14px;
  padding: 8px;
  flex-wrap: wrap;
  border-radius: 20px;
}

.cabinet-nav__link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 14px;
  text-decoration: none;
  font: 700 13px/1.2 var(--font-ui);
  color: var(--cabinet-muted);
  transition: background-color 200ms ease, color 200ms ease, box-shadow 200ms ease, transform 200ms ease;
}

.cabinet-nav__link:hover {
  background: rgba(255, 255, 255, 0.6);
  color: var(--cabinet-text);
  transform: translateY(-1px);
}

.cabinet-nav__icon {
  font-size: 18px;
}

.cabinet-nav__link--active {
  background: rgba(255, 255, 255, 0.92);
  color: var(--cabinet-text);
  box-shadow: 0 6px 16px rgba(90, 110, 140, 0.1);
}

@keyframes scene-float {
  0%, 100% {
    transform: translateY(0) translateX(0);
  }
  50% {
    transform: translateY(-16px) translateX(12px);
  }
}

@keyframes slow-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ── Responsive ── */
@media (max-width: 720px) {
  .cabinet-header__top {
    flex-direction: column;
    align-items: flex-start;
  }

  .cabinet-header__logo {
    width: 44px;
    height: 44px;
  }

  .cabinet-header__actions {
    width: 100%;
    justify-content: space-between;
  }

  .cabinet-nav__label {
    display: none;
  }

  .cabinet-nav__link {
    padding: 10px 14px;
  }

  .cabinet-nav__icon {
    font-size: 20px;
  }

  .cabinet-nav {
    justify-content: space-between;
  }
}
</style>
