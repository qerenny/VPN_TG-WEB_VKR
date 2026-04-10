<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import {
  DEFAULT_FEATURE_FLAGS,
  createEmptyPublicConfig,
  fetchPublicConfig,
  type FrontendFeatureFlags,
  type FrontendPublicConfig,
} from '../../api/publicConfig'

const toast = useToast()
const publicConfig = ref<FrontendPublicConfig>(createEmptyPublicConfig())
const loading = ref(true)
const features = computed<FrontendFeatureFlags>(() => publicConfig.value.features || DEFAULT_FEATURE_FLAGS)
const webPurchaseEnabled = computed(() => features.value.commerce_enabled && features.value.web_purchase_enabled)
const accessRequestsEnabled = computed(() => features.value.access_requests_enabled)
const appLinks = computed(() => publicConfig.value.app_links || {})
const docsLinks = computed(() => publicConfig.value.product?.docs_links || {})
const subscriptionClientName = computed(() => publicConfig.value.subscription_client?.name || 'Happ')

onMounted(async () => {
  loading.value = true
  try {
    publicConfig.value = await fetchPublicConfig()
  } catch {
    publicConfig.value = createEmptyPublicConfig()
    toast.error('Не удалось загрузить данные')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="cabinet-section">
    <div class="cabinet-section__head">
      <p class="cabinet-kicker">Помощь</p>
      <h2 class="cabinet-title">Поддержка и установка</h2>
      <p class="cabinet-copy">Скачайте приложение {{ subscriptionClientName }} для вашего устройства, добавьте подписку — и всё заработает.</p>
    </div>

    <!-- ═══ How it works ═══ -->
    <article class="glass-card cabinet-panel help-card">
      <div class="help-card__head">
        <span class="material-symbols-outlined help-card__head-icon help-card__head-icon--warm">menu_book</span>
        <div class="cabinet-section__head">
          <p class="cabinet-kicker">Быстрый старт</p>
          <h3 class="cabinet-subtitle">Как подключиться</h3>
        </div>
      </div>
      <div class="steps">
        <div class="step">
          <span class="step__num">1</span>
          <div>
            <p class="step__title">Скачайте {{ subscriptionClientName }}</p>
            <p class="step__desc">Выберите версию для вашего устройства ниже.</p>
          </div>
        </div>
        <div class="step">
          <span class="step__num">2</span>
          <div>
            <p class="step__title">{{ webPurchaseEnabled ? 'Получите доступ' : accessRequestsEnabled ? 'Отправьте заявку' : 'Проверьте доступ' }}</p>
            <p v-if="webPurchaseEnabled" class="step__desc">Перейдите в раздел <RouterLink to="/app/purchase" class="step__link">Доступ</RouterLink> и выберите конфигурацию.</p>
            <p v-else-if="accessRequestsEnabled" class="step__desc">Перейдите в раздел <RouterLink to="/app/purchase" class="step__link">Доступ</RouterLink> и отправьте заявку на получение доступа.</p>
            <p v-else class="step__desc">Откройте раздел <RouterLink to="/app/subscriptions" class="step__link">Подписки</RouterLink> и проверьте доступные конфигурации.</p>
          </div>
        </div>
        <div class="step">
          <span class="step__num">3</span>
          <div>
            <p class="step__title">Добавьте подписку в {{ subscriptionClientName }}</p>
            <p class="step__desc">На странице <RouterLink to="/app/subscriptions" class="step__link">Подписки</RouterLink> нажмите кнопку импорта или скопируйте ссылку вручную.</p>
          </div>
        </div>
      </div>
    </article>

    <!-- ═══ Happ downloads — grouped ═══ -->
    <article class="glass-card cabinet-panel help-card">
      <div class="help-card__head">
        <span class="material-symbols-outlined help-card__head-icon">download</span>
        <div class="cabinet-section__head">
          <p class="cabinet-kicker">Установка</p>
          <h3 class="cabinet-subtitle">Скачать {{ subscriptionClientName }}</h3>
        </div>
      </div>

      <!-- iPhone -->
      <div class="happ-group">
        <div class="happ-group__head">
          <span class="material-symbols-outlined happ-group__icon">phone_iphone</span>
          <h4 class="happ-group__title">iPhone / iPad</h4>
        </div>
        <div class="happ-row">
          <a class="happ-tile" :href="appLinks.happ_ios_global || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">storefront</span>
            <strong class="happ-tile__title">App Store</strong>
            <span class="happ-tile__label">World</span>
          </a>
          <a class="happ-tile" :href="appLinks.happ_ios || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">storefront</span>
            <strong class="happ-tile__title">App Store</strong>
            <span class="happ-tile__label">Россия</span>
          </a>
        </div>
      </div>

      <!-- Android -->
      <div class="happ-group">
        <div class="happ-group__head">
          <span class="material-symbols-outlined happ-group__icon">phone_android</span>
          <h4 class="happ-group__title">Android</h4>
        </div>
        <div class="happ-row">
          <a class="happ-tile" :href="appLinks.happ_android || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">storefront</span>
            <strong class="happ-tile__title">Google Play</strong>
            <span class="happ-tile__label">Play Market</span>
          </a>
          <a class="happ-tile" :href="appLinks.happ_android_apk || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">apk_install</span>
            <strong class="happ-tile__title">APK</strong>
            <span class="happ-tile__label">Прямая загрузка</span>
          </a>
        </div>
      </div>

      <!-- Desktop -->
      <div class="happ-group">
        <div class="happ-group__head">
          <span class="material-symbols-outlined happ-group__icon">computer</span>
          <h4 class="happ-group__title">Компьютеры</h4>
        </div>
        <div class="happ-row">
          <a class="happ-tile" :href="appLinks.happ_windows || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">desktop_windows</span>
            <strong class="happ-tile__title">Windows</strong>
            <span class="happ-tile__label">x64 .exe</span>
          </a>
          <a class="happ-tile" :href="appLinks.happ_macos_dmg || appLinks.happ_macos || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">laptop_mac</span>
            <strong class="happ-tile__title">macOS</strong>
            <span class="happ-tile__label">DMG Universal</span>
          </a>
          <a class="happ-tile" :href="appLinks.happ_linux || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">terminal</span>
            <strong class="happ-tile__title">Linux DEB</strong>
            <span class="happ-tile__label">Ubuntu / Debian</span>
          </a>
          <a class="happ-tile" :href="appLinks.happ_linux_rpm || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">terminal</span>
            <strong class="happ-tile__title">Linux RPM</strong>
            <span class="happ-tile__label">Fedora / RHEL</span>
          </a>
        </div>
      </div>

      <!-- TV -->
      <div class="happ-group">
        <div class="happ-group__head">
          <span class="material-symbols-outlined happ-group__icon">tv</span>
          <h4 class="happ-group__title">TV</h4>
        </div>
        <div class="happ-row">
          <a class="happ-tile" :href="appLinks.happ_apple_tv || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">storefront</span>
            <strong class="happ-tile__title">Apple TV</strong>
            <span class="happ-tile__label">tvOS</span>
          </a>
          <a class="happ-tile" :href="appLinks.happ_android_tv || appLinks.happ_android || '#'" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined happ-tile__icon">storefront</span>
            <strong class="happ-tile__title">Android TV</strong>
            <span class="happ-tile__label">Google Play</span>
          </a>
        </div>
      </div>
    </article>

    <!-- ═══ Quick links ═══ -->
    <article class="glass-card cabinet-panel help-card help-card--compact">
      <div class="help-card__head">
        <span class="material-symbols-outlined help-card__head-icon help-card__head-icon--warm">bolt</span>
        <div class="cabinet-section__head">
          <p class="cabinet-kicker">Полезное</p>
          <h3 class="cabinet-subtitle">Ссылки</h3>
        </div>
      </div>

      <div class="help-links">
        <a
          v-if="publicConfig?.support_link"
          class="help-link"
          :href="publicConfig.support_link"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="material-symbols-outlined help-link__icon">support_agent</span>
          <div>
            <p class="help-link__title">Поддержка в Telegram</p>
            <p class="help-link__desc">Напиши, если есть вопросы</p>
          </div>
        </a>
        <RouterLink class="help-link" to="/app/subscriptions">
          <span class="material-symbols-outlined help-link__icon help-link__icon--accent">vpn_key</span>
          <div>
            <p class="help-link__title">Мой доступ</p>
            <p class="help-link__desc">Статус, срок, трафик и ссылки</p>
          </div>
        </RouterLink>
        <RouterLink v-if="webPurchaseEnabled || accessRequestsEnabled" class="help-link" to="/app/purchase">
          <span class="material-symbols-outlined help-link__icon">vpn_key</span>
          <div>
            <p class="help-link__title">{{ webPurchaseEnabled ? 'Получить доступ' : 'Запросить доступ' }}</p>
            <p class="help-link__desc">{{ webPurchaseEnabled ? 'Варианты доступа и условия' : 'Заявка и статус обработки' }}</p>
          </div>
        </RouterLink>
        <a
          v-if="docsLinks.faq"
          class="help-link"
          :href="docsLinks.faq"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="material-symbols-outlined help-link__icon">quiz</span>
          <div>
            <p class="help-link__title">FAQ</p>
            <p class="help-link__desc">Частые вопросы и ответы</p>
          </div>
        </a>
        <a
          v-if="docsLinks.devices"
          class="help-link"
          :href="docsLinks.devices"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="material-symbols-outlined help-link__icon">devices</span>
          <div>
            <p class="help-link__title">Устройства</p>
            <p class="help-link__desc">Инструкции по платформам</p>
          </div>
        </a>
        <a
          v-if="docsLinks.about"
          class="help-link"
          :href="docsLinks.about"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="material-symbols-outlined help-link__icon">info</span>
          <div>
            <p class="help-link__title">О сервисе</p>
            <p class="help-link__desc">Общее описание и справка</p>
          </div>
        </a>
      </div>

      <div v-if="loading" class="cabinet-loader">
        <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
        <p class="cabinet-loader__text">Загружаем...</p>
      </div>
    </article>
  </section>
</template>

<style scoped>
.help-card {
  display: grid;
  gap: 20px;
}

.help-card--compact {
  max-width: 640px;
}

.help-card__head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.help-card__head-icon {
  font-size: 28px;
  color: var(--cabinet-traffic_limited);
  padding: 10px;
  border-radius: 16px;
  background: rgba(77, 143, 214, 0.08);
  flex-shrink: 0;
}

.help-card__head-icon--warm {
  color: var(--cabinet-standard);
  background: rgba(245, 160, 78, 0.08);
}

/* ═══ Steps ═══ */
.steps {
  display: grid;
  gap: 12px;
}

.step {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 18px;
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.55), rgba(255, 250, 246, 0.35));
  border: 1px solid rgba(126, 170, 220, 0.06);
}

.step__num {
  display: grid;
  place-items: center;
  min-width: 32px;
  height: 32px;
  border-radius: 10px;
  font: 700 15px/1 var(--font-ui);
  color: #fff;
  background: linear-gradient(135deg, var(--cabinet-standard), #e08a3a);
  flex-shrink: 0;
}

.step__title {
  margin: 0;
  font: 700 14px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.step__desc {
  margin: 2px 0 0;
  font: 400 13px/1.5 var(--font-text);
  color: var(--cabinet-muted);
}

.step__link {
  color: var(--cabinet-traffic_limited);
  text-decoration: none;
  font-weight: 600;
}

.step__link:hover {
  text-decoration: underline;
}

/* ═══ Happ groups ═══ */
.happ-group {
  display: grid;
  gap: 10px;
}

.happ-group__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.happ-group__icon {
  font-size: 22px;
  color: var(--cabinet-traffic_limited);
}

.happ-group__title {
  margin: 0;
  font: 700 15px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.happ-row {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.happ-tile {
  display: grid;
  place-items: center;
  gap: 6px;
  min-width: 130px;
  padding: 18px 16px;
  border-radius: 18px;
  text-decoration: none;
  text-align: center;
  color: var(--cabinet-text);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.6), rgba(255, 250, 246, 0.35));
  border: 1.5px solid rgba(126, 170, 220, 0.08);
  transition: transform 200ms ease, box-shadow 200ms ease, border-color 200ms ease;
  flex-shrink: 0;
}

.happ-tile:hover {
  transform: translateY(-3px);
  border-color: rgba(77, 143, 214, 0.2);
  box-shadow: 0 8px 24px rgba(90, 110, 140, 0.1);
}

.happ-tile__icon {
  font-size: 30px;
  color: var(--cabinet-traffic_limited);
}

.happ-tile__title {
  font: 700 13px/1.2 var(--font-ui);
}

.happ-tile__label {
  font-size: 11px;
  color: var(--cabinet-muted);
  line-height: 1.3;
}

/* ═══ Help links ═══ */
.help-links {
  display: grid;
  gap: 8px;
}

.help-link {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  border-radius: 16px;
  text-decoration: none;
  color: var(--cabinet-text);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.55), rgba(255, 250, 246, 0.35));
  border: 1px solid rgba(126, 170, 220, 0.06);
  transition: transform 200ms ease, box-shadow 200ms ease, background-color 200ms ease;
}

.help-link:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 6px 18px rgba(90, 110, 140, 0.08);
}

.help-link__icon {
  font-size: 24px;
  color: var(--cabinet-traffic_limited);
  flex-shrink: 0;
}

.help-link__icon--accent {
  color: var(--cabinet-standard);
}

.help-link__title {
  margin: 0;
  font: 700 14px/1.3 var(--font-ui);
}

.help-link__desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--cabinet-muted);
}

/* ═══ Responsive ═══ */
@media (max-width: 600px) {
  .happ-tile {
    min-width: 110px;
    padding: 14px 12px;
  }

  .happ-tile__icon {
    font-size: 26px;
  }

  .step {
    padding: 12px 14px;
  }
}
</style>
