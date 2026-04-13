<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { createEmptyPublicConfig, fetchPublicConfig, type FrontendPublicConfig } from '../api/publicConfig'
import { fetchUserInfo } from '../api/user'
import { useToast } from 'vue-toastification'

interface UserData {
  scope: 'standard' | 'traffic_limited'
  sub_is_active: boolean
  sub_link: string
  support_link?: string
  human_view_expiration_remaining?: string
  human_view_expiration_date?: string
  traffic_allocated_bytes?: number | null
  traffic_used_bytes?: number | null
  traffic_remaining_bytes?: number | null
  human_view_traffic_allocated?: string | null
  human_view_traffic_used?: string | null
  human_view_traffic_remaining?: string | null
}

type InstructionAction =
  | {
      type: 'link'
      icon: string
      label: string
      href: (user: UserData) => string
    }
  | {
      type: 'copy'
      icon: string
      label: string
    }

interface InstructionSection {
  key: string
  title: string
  icon: string
  appName?: string
  notes?: string[]
  actions: InstructionAction[]
  steps?: string[]
  detailsLink?: string
}

const toast = useToast()
const route = useRoute()

const userData = ref<UserData | null>(null)
const publicConfig = ref<FrontendPublicConfig>(createEmptyPublicConfig())
const error = ref<string | null>(null)
const isLoading = ref(true)
const currentDeviceKey = ref<string | null>(null)
const quickStartRef = ref<HTMLElement | null>(null)
const instructionRefs = ref<Record<string, HTMLDetailsElement | null>>({})
const instructionsListRef = ref<HTMLElement | null>(null)
const isTrafficLimitedScope = computed(() => route.path.includes('/subscription/traffic-limited/'))

const normalizeTelegramLink = (value?: string) => {
  const normalizedValue = value?.trim()
  if (!normalizedValue) {
    return ''
  }

  if (
    normalizedValue.startsWith('http://') ||
    normalizedValue.startsWith('https://') ||
    normalizedValue.startsWith('tg://')
  ) {
    return normalizedValue
  }

  return `https://t.me/${normalizedValue.replace(/^@+/, '').replace(/^\/+|\/+$/g, '')}`
}

const supportLink = computed(() =>
  normalizeTelegramLink(userData.value?.support_link || publicConfig.value?.support_link),
)

const normalizeOptionalUrl = (value?: string | null) => {
  const normalizedValue = value?.trim() || ''
  return normalizedValue === '#' ? '' : normalizedValue
}

const buildHappImportLink = (subLink?: string | null) => {
  const addLink = normalizeOptionalUrl(publicConfig.value?.subscription_add_links?.happ)
  const normalizedSubLink = normalizeOptionalUrl(subLink)

  if (!addLink || !normalizedSubLink) {
    return ''
  }

  return `${addLink}${normalizedSubLink}`
}

const setInstructionRef = (key: string) => (el: Element | null) => {
  instructionRefs.value[key] = el as HTMLDetailsElement | null
}

const instructionSections = computed<InstructionSection[]>(() => {
  const appLinks = publicConfig.value?.app_links || {}
  const instructionLinks = publicConfig.value?.instruction_links || {}

  return [
    {
      key: 'ios',
      title: 'iOS',
      icon: 'smartphone',
      appName: 'HAPP',
      actions: [
        {
          type: 'link',
          icon: 'download',
          label: 'Скачать в App Store',
          href: () => normalizeOptionalUrl(appLinks.happ_ios),
        },
        {
          type: 'link',
          icon: 'add_circle',
          label: 'Добавить подписку',
          href: (user) => buildHappImportLink(user.sub_link),
        },
      ],
      steps: [
        'Нажмите «Скачать в App Store», чтобы установить приложение.',
        'После установки нажмите «Добавить подписку».',
        'Убедитесь, что подписка появилась в приложении.',
      ],
      detailsLink: normalizeOptionalUrl(instructionLinks.ios),
    },
    {
      key: 'android',
      title: 'Android',
      icon: 'android',
      appName: 'HAPP',
      actions: [
        {
          type: 'link',
          icon: 'download',
          label: 'Скачать в Play Market',
          href: () => normalizeOptionalUrl(appLinks.happ_android),
        },
        {
          type: 'link',
          icon: 'add_circle',
          label: 'Добавить подписку',
          href: (user) => buildHappImportLink(user.sub_link),
        },
      ],
      steps: [
        'Нажмите «Скачать в Play Market», чтобы установить приложение.',
        'После установки нажмите «Добавить подписку».',
        'Убедитесь, что подписка появилась в приложении.',
      ],
      detailsLink: normalizeOptionalUrl(instructionLinks.android),
    },
    {
      key: 'windows',
      title: 'Windows',
      icon: 'laptop_windows',
      appName: 'HAPP',
      actions: [
        {
          type: 'link',
          icon: 'download',
          label: 'Скачать с оф. сайта',
          href: () => normalizeOptionalUrl(appLinks.happ_windows),
        },
        {
          type: 'link',
          icon: 'add_circle',
          label: 'Добавить подписку',
          href: (user) => buildHappImportLink(user.sub_link),
        },
      ],
      steps: [
        'Скачайте приложение с официального сайта.',
        'Установите его на устройство.',
        'Нажмите «Добавить подписку» после установки.',
      ],
      detailsLink: normalizeOptionalUrl(instructionLinks.windows),
    },
    {
      key: 'windows-nekoray',
      title: 'Windows Nekoray - Tunneling',
      icon: 'tv',
      actions: [
        {
          type: 'link',
          icon: 'arrow_outward',
          label: 'Подробная инструкция',
          href: () => normalizeOptionalUrl(instructionLinks.windows_nekoray),
        },
        {
          type: 'link',
          icon: 'download',
          label: 'Скачать с GitHub',
          href: () => normalizeOptionalUrl(appLinks.windows_nekoray),
        },
        {
          type: 'copy',
          icon: 'content_copy',
          label: 'Скопировать подписку',
        },
      ],
      notes: [
        'Инструкция для тех, кто хочет пропускать через VPN только выбранные приложения.',
        'Если это не требуется, лучше использовать обычную инструкцию для Windows.',
      ],
    },
    {
      key: 'macos',
      title: 'macOS',
      icon: 'laptop_mac',
      appName: 'HAPP',
      actions: [
        {
          type: 'link',
          icon: 'download',
          label: 'Скачать в App Store',
          href: () => normalizeOptionalUrl(appLinks.happ_macos),
        },
        {
          type: 'link',
          icon: 'add_circle',
          label: 'Добавить подписку',
          href: (user) => buildHappImportLink(user.sub_link),
        },
      ],
      steps: [
        'Нажмите «Скачать в App Store», чтобы установить приложение.',
        'После установки нажмите «Добавить подписку».',
        'Убедитесь, что подписка появилась в приложении.',
      ],
      detailsLink: normalizeOptionalUrl(instructionLinks.macos),
    },
    {
      key: 'linux',
      title: 'Linux',
      icon: 'terminal',
      appName: 'HAPP',
      actions: [
        {
          type: 'link',
          icon: 'download',
          label: 'Скачать с оф. сайта',
          href: () => normalizeOptionalUrl(appLinks.happ_linux),
        },
        {
          type: 'link',
          icon: 'add_circle',
          label: 'Добавить подписку',
          href: (user) => buildHappImportLink(user.sub_link),
        },
      ],
      steps: [
        'Скачайте приложение с официального сайта и установите его.',
        'При необходимости выберите подходящий пакет для вашей системы.',
        'Нажмите «Добавить подписку» после установки.',
      ],
      detailsLink: normalizeOptionalUrl(instructionLinks.linux),
    },
    {
      key: 'manual',
      title: 'Ручная установка',
      icon: 'back_hand',
      appName: 'Ручная установка',
      actions: [
        {
          type: 'copy',
          icon: 'content_copy',
          label: 'Скопировать подписку',
        },
      ],
      steps: [
        'Откройте приложение для вашего устройства.',
        'Добавьте подписку в приложение или импортируйте её из буфера обмена.',
      ],
    },
  ]
})

const getVisibleInstructionActions = (section: InstructionSection, user: UserData) =>
  section.actions.filter((action) => action.type !== 'link' || Boolean(action.href(user)))

const preferredDeviceSection = computed(
  () => instructionSections.value.find((section) => section.key === currentDeviceKey.value) ?? null,
)

const quickStartSection = computed(() => preferredDeviceSection.value ?? instructionSections.value[0])

const quickStartActions = computed(() => {
  const user = userData.value
  if (!user) {
    return []
  }
  return getVisibleInstructionActions(quickStartSection.value, user).slice(0, 2)
})

const productTag = computed(() =>
  isTrafficLimitedScope.value ? 'Доступ с лимитом трафика' : 'Доступ',
)

const statusTitle = computed(() => {
  if (isTrafficLimitedScope.value) {
    return userData.value?.sub_is_active
      ? 'Доступ с лимитом трафика активен и готов к подключению'
      : 'Доступ с лимитом трафика сейчас неактивен'
  }

  return userData.value?.sub_is_active
    ? 'Подписка активна и готова к подключению'
    : 'Подписка сейчас неактивна'
})

const statusLead = computed(() => {
  if (isTrafficLimitedScope.value) {
    return userData.value?.sub_is_active
      ? 'Импортируйте ссылку в приложение и следите за остатком трафика.'
      : 'Трафик закончился или срок действия истёк. Напишите в поддержку, если доступ должен быть активен.'
  }

  return userData.value?.sub_is_active
    ? 'Выберите приложение для своего устройства и добавьте ссылку в один клик.'
    : 'Проверьте срок действия и, если доступ должен быть активен, напишите в поддержку для быстрой проверки.'
})

const primaryStatusLabel = computed(() =>
  isTrafficLimitedScope.value ? 'Осталось трафика' : 'Осталось',
)

const primaryStatusValue = computed(() =>
  isTrafficLimitedScope.value
    ? userData.value?.human_view_traffic_remaining ?? '0 GB'
    : userData.value?.human_view_expiration_remaining ?? 'Неизвестно',
)

const secondaryStatusLabel = computed(() =>
  isTrafficLimitedScope.value ? 'Действует до' : 'До',
)

const secondaryStatusValue = computed(() =>
  isTrafficLimitedScope.value
    ? userData.value?.human_view_expiration_date ?? 'Без срока'
    : userData.value?.human_view_expiration_date ?? 'Неизвестно',
)

const quickStartTitle = computed(() =>
  isTrafficLimitedScope.value ? 'Подключение конфигурации с лимитом трафика' : 'Подключение за пару шагов',
)

const quickStartLead = computed(() =>
  isTrafficLimitedScope.value
    ? `Начните с ${quickStartSection.value.title} и импортируйте ссылку доступа без ручной настройки.`
    : `Начните с ${quickStartSection.value.title} и импортируйте подписку без ручной настройки.`,
)

const instructionsLeadText = computed(() =>
  isTrafficLimitedScope.value
    ? 'Откройте нужную платформу, скачайте приложение и импортируйте ссылку доступа.'
    : 'Откройте нужную платформу, скачайте приложение и импортируйте подписку.',
)

const detectDeviceKey = (): string | null => {
  const ua = navigator.userAgent.toLowerCase()
  if (/iphone|ipad/.test(ua)) return 'ios'
  if (/macintosh|mac os/.test(ua)) return 'macos'
  if (/android/.test(ua)) return 'android'
  if (/windows nt/.test(ua)) return 'windows'
  if (/linux/.test(ua)) return 'linux'
  return null
}

const openAndMoveDeviceTab = () => {
  const key = currentDeviceKey.value
  if (!key) return

  const tab = instructionRefs.value[key]
  const parent = instructionsListRef.value

  if (!tab || !parent) return
  tab.open = false
  parent.prepend(tab)
}

const focusQuickStart = async () => {
  const quickStart = quickStartRef.value
  if (!quickStart) return

  quickStart.scrollIntoView({ behavior: 'smooth', block: 'start' })

  await nextTick()
  quickStart.focus()
}

const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    toast.success('Скопировано!')
  } catch {
    toast.error('Ошибка при копировании')
  }
}

const loadUserData = async () => {
  isLoading.value = true
  error.value = null
  userData.value = null
  publicConfig.value = createEmptyPublicConfig()
  const token = route.params.token as string
  const scope = isTrafficLimitedScope.value ? 'traffic_limited' : 'standard'

  try {
    const [configResult, userInfoResult] = await Promise.allSettled([
      fetchPublicConfig(),
      fetchUserInfo(token, scope),
    ])

    if (configResult.status === 'fulfilled') {
      publicConfig.value = configResult.value
    }

    if (userInfoResult.status === 'rejected') {
      throw userInfoResult.reason
    }

    userData.value = userInfoResult.value
  } catch (err: any) {
    if (err?.response?.status === 404) {
      error.value = 'Подписка не найдена'
    } else if (err?.code === 'ERR_NETWORK') {
      error.value = 'Сервер недоступен'
    } else {
      error.value = 'Не удалось загрузить данные подписки'
    }
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  currentDeviceKey.value = detectDeviceKey()
  await loadUserData()
  await nextTick()
  openAndMoveDeviceTab()
})
</script>

<template>
  <main
    class="page-shell subscription-page"
    :class="{ 'subscription-page--traffic_limited': isTrafficLimitedScope }"
  >
    <div class="subscription-scene" aria-hidden="true">
      <div class="subscription-scene__orb subscription-scene__orb--one"></div>
      <div class="subscription-scene__orb subscription-scene__orb--two"></div>
      <div class="subscription-scene__ring subscription-scene__ring--one"></div>
      <div class="subscription-scene__ring subscription-scene__ring--two"></div>
      <span class="subscription-scene__dot subscription-scene__dot--1"></span>
      <span class="subscription-scene__dot subscription-scene__dot--2"></span>
      <span class="subscription-scene__dot subscription-scene__dot--3"></span>
      <span class="subscription-scene__dot subscription-scene__dot--4"></span>
    </div>

    <div class="layout">
      <section class="card-surface status-card" aria-live="polite">
        <div class="status-card__mesh" aria-hidden="true"></div>

        <div v-if="isLoading" class="loading-state">
          <div class="loading-spinner" aria-hidden="true"></div>
          <p>Загружаем данные подписки...</p>
        </div>

        <div v-else-if="error" class="error-banner">
          <h2>Не получилось загрузить подписку</h2>
          <p>{{ error }}</p>
        </div>

        <div v-else-if="userData" class="status-content">
          <div class="status-copy">
            <div>
              <p class="section-tag">Персональный доступ</p>
              <p class="scope-chip">{{ productTag }}</p>
              <h1 class="section-title">{{ statusTitle }}</h1>
              <p class="status-lead">{{ statusLead }}</p>
            </div>

            <div
              class="status-visual"
              :class="[
                userData.sub_is_active ? 'status-visual--active' : 'status-visual--inactive',
                isTrafficLimitedScope ? 'status-visual--traffic_limited' : 'status-visual--standard',
              ]"
            >
              <div class="status-visual__orbit status-visual__orbit--outer" aria-hidden="true"></div>
              <div class="status-visual__orbit status-visual__orbit--inner" aria-hidden="true"></div>
              <div class="status-visual__beam status-visual__beam--one" aria-hidden="true"></div>
              <div class="status-visual__beam status-visual__beam--two" aria-hidden="true"></div>
              <span class="status-visual__spark status-visual__spark--one" aria-hidden="true"></span>
              <span class="status-visual__spark status-visual__spark--two" aria-hidden="true"></span>
              <span class="status-visual__spark status-visual__spark--three" aria-hidden="true"></span>

              <div class="status-visual__card status-visual__card--one">
                <span class="material-symbols-outlined">schedule</span>
                <div>
                  <small>{{ primaryStatusLabel }}</small>
                  <strong>{{ primaryStatusValue }}</strong>
                </div>
              </div>

              <div class="status-visual__card status-visual__card--two">
                <span class="material-symbols-outlined">event</span>
                <div>
                  <small>{{ secondaryStatusLabel }}</small>
                  <strong>{{ secondaryStatusValue }}</strong>
                </div>
              </div>

              <button
                v-if="preferredDeviceSection"
                type="button"
                class="status-visual__card status-visual__card--three status-visual__card--interactive"
                @click="focusQuickStart"
              >
                <span class="material-symbols-outlined">rocket_launch</span>
                <div>
                  <small>Старт</small>
                  <strong>{{ preferredDeviceSection.title }}</strong>
                </div>
              </button>
            </div>

            <div class="status-actions">
              <button
                type="button"
                class="primary-btn primary-btn--ghost"
                @click="copyToClipboard(userData.sub_link)"
              >
                <span class="material-symbols-outlined" aria-hidden="true">content_copy</span>
                Скопировать ссылку
              </button>

              <a
                v-if="supportLink"
                :href="supportLink"
                target="_blank"
                rel="noopener noreferrer"
                class="primary-btn"
              >
                <span class="material-symbols-outlined" aria-hidden="true">support_agent</span>
                Чат поддержки
              </a>
            </div>

            <div v-if="isTrafficLimitedScope" class="traffic-summary">
              <div class="traffic-summary__item">
                <small>Выдано</small>
                <strong>{{ userData.human_view_traffic_allocated ?? '0 GB' }}</strong>
              </div>
              <div class="traffic-summary__item">
                <small>Использовано</small>
                <strong>{{ userData.human_view_traffic_used ?? '0 GB' }}</strong>
              </div>
              <div class="traffic-summary__item">
                <small>Осталось</small>
                <strong>{{ userData.human_view_traffic_remaining ?? '0 GB' }}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        v-if="!isLoading && userData"
        ref="quickStartRef"
        class="card-surface quick-start-card"
        tabindex="-1"
      >
        <div class="quick-start-card__glow" aria-hidden="true"></div>

        <div class="quick-start-head">
          <div>
            <p class="section-tag">Быстрый старт</p>
            <h2 class="section-title">{{ quickStartTitle }}</h2>
            <p class="instructions-lead">{{ quickStartLead }}</p>
          </div>

          <div class="quick-start-device">
            <span class="material-symbols-outlined" aria-hidden="true">{{ quickStartSection.icon }}</span>
            <div>
              <small>Устройство</small>
              <strong>{{ quickStartSection.title }}</strong>
            </div>
          </div>
        </div>

        <div class="quick-start-body">
          <ol class="quick-start-steps">
            <li v-for="step in quickStartSection.steps ?? []" :key="step">{{ step }}</li>
          </ol>

          <div class="quick-start-actions">
            <template v-for="action in quickStartActions" :key="action.label">
              <a
                v-if="action.type === 'link'"
                :href="action.href(userData)"
                target="_blank"
                rel="noopener noreferrer"
                class="primary-btn"
              >
                <span class="material-symbols-outlined" aria-hidden="true">{{ action.icon }}</span>
                {{ action.label }}
              </a>

              <button
                v-else
                type="button"
                class="primary-btn primary-btn--ghost"
                @click="copyToClipboard(userData.sub_link)"
              >
                <span class="material-symbols-outlined" aria-hidden="true">{{ action.icon }}</span>
                {{ action.label }}
              </button>
            </template>

          </div>
        </div>
      </section>

      <section v-if="!isLoading && userData" class="card-surface instructions-card">
        <div class="instructions-head">
          <div>
            <p class="section-tag">Платформы</p>
            <h2 class="section-title">Инструкции подключения</h2>
            <p class="instructions-lead">{{ instructionsLeadText }}</p>
          </div>

          <div class="instructions-head__chips">
            <span v-if="preferredDeviceSection" class="instructions-head__chip">
              Для этого устройства: {{ preferredDeviceSection.title }}
            </span>
            <span class="instructions-head__chip">
              {{ instructionSections.length }} вариантов подключения
            </span>
          </div>
        </div>

        <div ref="instructionsListRef" class="instructions-list">
          <details
            v-for="section in instructionSections"
            :key="section.key"
            :ref="setInstructionRef(section.key)"
            class="instruction-item"
            :class="{ 'instruction-item--recommended': section.key === preferredDeviceSection?.key }"
            tabindex="-1"
          >
            <summary>
              <span class="summary-left">
                <span class="material-symbols-outlined" aria-hidden="true">{{ section.icon }}</span>
                <span>
                  <span class="summary-title">{{ section.title }}</span>
                  <span v-if="section.appName" class="summary-app">{{ section.appName }}</span>
                </span>
              </span>
              <span class="summary-right">
                <span
                  v-if="section.key === preferredDeviceSection?.key"
                  class="summary-recommendation"
                >
                  Рекомендуем
                </span>
                <span class="material-symbols-outlined expand-icon" aria-hidden="true">expand_more</span>
              </span>
            </summary>

            <div class="instruction-body">
              <ul v-if="section.notes?.length" class="notes-list">
                <li v-for="note in section.notes" :key="note">{{ note }}</li>
              </ul>

              <ul class="action-list">
              <li v-for="action in getVisibleInstructionActions(section, userData)" :key="action.label">
                  <a
                    v-if="action.type === 'link'"
                    :href="action.href(userData)"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="action-link"
                  >
                    <span class="material-symbols-outlined" aria-hidden="true">{{ action.icon }}</span>
                    {{ action.label }}
                  </a>

                  <button
                    v-else
                    type="button"
                    class="action-link action-link--button"
                    @click="copyToClipboard(userData.sub_link)"
                  >
                    <span class="material-symbols-outlined" aria-hidden="true">{{ action.icon }}</span>
                    {{ action.label }}
                  </button>
                </li>
              </ul>

              <ol v-if="section.steps?.length" class="steps-list">
                <li v-for="step in section.steps" :key="step">{{ step }}</li>
              </ol>

              <a
                v-if="section.detailsLink"
                :href="section.detailsLink"
                target="_blank"
                rel="noopener noreferrer"
                class="details-link"
              >
                <span class="material-symbols-outlined" aria-hidden="true">arrow_outward</span>
                Подробная инструкция
              </a>
            </div>
          </details>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.subscription-page {
  padding-top: 24px;
  overflow: hidden;
}

.subscription-page--traffic_limited .subscription-scene__orb--one {
  background: radial-gradient(circle, rgba(94, 164, 232, 0.28), rgba(94, 164, 232, 0));
}

.subscription-page--traffic_limited .subscription-scene__orb--two {
  background: radial-gradient(circle, rgba(85, 203, 186, 0.2), rgba(85, 203, 186, 0));
}

.subscription-page--traffic_limited .subscription-scene__ring {
  border-color: rgba(95, 147, 210, 0.18);
}

.subscription-page--traffic_limited .subscription-scene__dot {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(114, 177, 232, 0.48));
}

.subscription-scene {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: -1;
}

.subscription-scene__orb,
.subscription-scene__ring,
.subscription-scene__dot {
  position: absolute;
}

.subscription-scene__orb {
  border-radius: 50%;
  filter: blur(10px);
  opacity: 0.8;
}

.subscription-scene__orb--one {
  top: 70px;
  right: min(8vw, 80px);
  width: min(28vw, 240px);
  height: min(28vw, 240px);
  background: radial-gradient(circle, rgba(255, 119, 92, 0.28), rgba(255, 119, 92, 0));
  animation: scene-float 14s ease-in-out infinite;
}

.subscription-scene__orb--two {
  left: min(4vw, 48px);
  bottom: 16%;
  width: min(24vw, 200px);
  height: min(24vw, 200px);
  background: radial-gradient(circle, rgba(255, 177, 88, 0.22), rgba(255, 177, 88, 0));
  animation: scene-float 12s ease-in-out infinite reverse;
}

.subscription-scene__ring {
  border-radius: 50%;
  border: 1px solid rgba(255, 142, 105, 0.16);
}

.subscription-scene__ring--one {
  top: 92px;
  left: 6%;
  width: min(32vw, 280px);
  height: min(32vw, 280px);
  animation: scene-spin 30s linear infinite;
}

.subscription-scene__ring--two {
  right: 10%;
  bottom: 10%;
  width: min(18vw, 160px);
  height: min(18vw, 160px);
  animation: scene-spin 22s linear infinite reverse;
}

.subscription-scene__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(255, 149, 102, 0.48));
  box-shadow: 0 0 0 8px rgba(255, 255, 255, 0.08);
  animation: scene-drift 10s linear infinite;
}

.subscription-scene__dot--1 {
  top: 18%;
  left: 18%;
}

.subscription-scene__dot--2 {
  top: 26%;
  right: 16%;
  width: 8px;
  height: 8px;
  animation-delay: -2s;
}

.subscription-scene__dot--3 {
  bottom: 23%;
  left: 12%;
  width: 12px;
  height: 12px;
  animation-delay: -4.4s;
}

.subscription-scene__dot--4 {
  bottom: 14%;
  right: 22%;
  width: 6px;
  height: 6px;
  animation-delay: -6.6s;
}

.layout {
  width: min(1120px, 100%);
  margin: 0 auto;
  display: grid;
  gap: 22px;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  align-items: start;
}

.card-surface {
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(255, 129, 95, 0.26);
  border-radius: 24px;
  box-shadow: 0 16px 42px rgba(149, 60, 39, 0.15);
  backdrop-filter: blur(8px);
  padding: clamp(18px, 3vw, 28px);
  min-width: 0;
}

.subscription-page--traffic_limited .card-surface {
  border-color: rgba(93, 139, 196, 0.24);
  box-shadow: 0 16px 42px rgba(53, 88, 128, 0.16);
}

.status-card,
.quick-start-card,
.instructions-card {
  position: relative;
  overflow: hidden;
}

.status-card {
  min-height: 420px;
  grid-column: 1;
}

.status-card__mesh {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 75% 28%, rgba(255, 141, 84, 0.18), transparent 26%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.24), rgba(255, 255, 255, 0));
  z-index: 0;
}

.subscription-page--traffic_limited .status-card__mesh {
  background:
    radial-gradient(circle at 75% 28%, rgba(98, 166, 228, 0.18), transparent 26%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.24), rgba(255, 255, 255, 0));
}

.loading-state {
  position: relative;
  z-index: 1;
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--muted);
}

.loading-spinner {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  border: 4px solid rgba(255, 138, 90, 0.24);
  border-top-color: var(--accent);
  animation: spin 0.85s linear infinite;
}

.error-banner {
  position: relative;
  z-index: 1;
  background: #fff1ef;
  border: 1px solid #f4b5ad;
  border-radius: 18px;
  padding: 16px;
}

.error-banner h2 {
  margin: 0 0 6px;
  font-family: 'Lato', sans-serif;
  color: #aa3121;
}

.error-banner p {
  margin: 0;
  color: #6d4040;
}

.status-content {
  position: relative;
  z-index: 1;
  min-height: 0;
}

.status-copy {
  display: grid;
  gap: 22px;
}

.section-tag {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-family: 'Lato', sans-serif;
  font-size: 12px;
  font-weight: 700;
  color: #936b68;
}

.scope-chip {
  display: inline-flex;
  margin: 12px 0 0;
  padding: 7px 12px;
  border-radius: 999px;
  font-size: 13px;
  line-height: 1;
  font-family: 'Lato', sans-serif;
  font-weight: 700;
  color: #9f4b35;
  background: rgba(255, 239, 231, 0.92);
  border: 1px solid rgba(226, 128, 97, 0.18);
}

.subscription-page--traffic_limited .section-tag {
  color: #6c7e9b;
}

.subscription-page--traffic_limited .section-title {
  color: #26415d;
}

.subscription-page--traffic_limited .scope-chip {
  color: #285e90;
  background: rgba(231, 243, 255, 0.95);
  border-color: rgba(95, 145, 201, 0.18);
}

.section-title {
  margin: 5px 0 0;
  font-family: 'Lato', sans-serif;
  font-size: clamp(25px, 4vw, 34px);
  line-height: 1.12;
  color: #4a2d2a;
}

.status-lead,
.instructions-lead {
  margin: 14px 0 0;
  max-width: 56ch;
  font-size: 16px;
  line-height: 1.65;
  color: #5f4745;
}

.pill {
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 14px;
  line-height: 1;
}

.pill--ok {
  color: #1a6b39;
  background: #def7e7;
}

.pill--bad {
  color: #9f2f2f;
  background: #fde7e7;
}

.status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-decoration: none;
  border-radius: 14px;
  padding: 12px 16px;
  width: fit-content;
  font-family: 'Lato', sans-serif;
  font-weight: 700;
  font-size: 16px;
  color: #fff;
  background: linear-gradient(120deg, var(--accent), var(--accent-2));
  box-shadow: 0 11px 20px rgba(184, 70, 43, 0.3);
  border: 1px solid rgba(255, 117, 87, 0.34);
  transition: transform 220ms ease, box-shadow 220ms ease, background-color 220ms ease;
  position: relative;
  overflow: hidden;
  max-width: 100%;
  white-space: normal;
  text-align: center;
}

.subscription-page--traffic_limited .primary-btn {
  background: linear-gradient(120deg, #2f77bd, #57b6c8);
  box-shadow: 0 11px 20px rgba(49, 98, 154, 0.28);
  border-color: rgba(87, 156, 202, 0.3);
}

.primary-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 24%, rgba(255, 255, 255, 0.28) 50%, transparent 76%);
  transform: translateX(-140%);
  animation: cta-sheen 5.4s ease-in-out infinite;
}

.primary-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 22px rgba(184, 70, 43, 0.38);
}

.primary-btn--ghost {
  color: #a1452d;
  background: rgba(255, 243, 236, 0.92);
  box-shadow: 0 11px 20px rgba(184, 70, 43, 0.12);
}

.subscription-page--traffic_limited .primary-btn--ghost {
  color: #2b6497;
  background: rgba(234, 244, 255, 0.95);
  box-shadow: 0 11px 20px rgba(64, 109, 171, 0.12);
}

.primary-btn--ghost:hover {
  background: rgba(255, 236, 227, 0.98);
}

.status-visual {
  --status-visual-ring: rgba(255, 147, 104, 0.22);
  --status-visual-glow: rgba(255, 148, 74, 0.12);
  --status-visual-spot: rgba(255, 198, 167, 0.32);
  --status-visual-spark: rgba(255, 148, 74, 0.45);
  --status-visual-panel-end: rgba(255, 241, 233, 0.74);
  position: relative;
  min-height: 320px;
  display: grid;
  place-items: center;
  width: 100%;
  overflow: hidden;
  margin-top: 4px;
  padding: 18px;
  border-radius: 28px;
  border: 1px solid rgba(255, 145, 102, 0.18);
  background:
    radial-gradient(circle at 20% 22%, rgba(255, 255, 255, 0.68), transparent 28%),
    radial-gradient(circle at 78% 28%, var(--status-visual-spot), transparent 26%),
    linear-gradient(145deg, rgba(255, 252, 249, 0.92), var(--status-visual-panel-end));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.74),
    0 14px 30px rgba(183, 84, 55, 0.08);
  isolation: isolate;
}

.status-visual--active {
  --status-visual-ring: rgba(74, 182, 112, 0.28);
  --status-visual-glow: rgba(93, 207, 127, 0.18);
  --status-visual-spot: rgba(132, 223, 161, 0.24);
  --status-visual-spark: rgba(93, 207, 127, 0.5);
  --status-visual-panel-end: rgba(237, 250, 240, 0.82);
}

.status-visual--inactive {
  --status-visual-ring: rgba(226, 96, 96, 0.26);
  --status-visual-glow: rgba(237, 96, 96, 0.18);
  --status-visual-spot: rgba(244, 162, 162, 0.22);
  --status-visual-spark: rgba(237, 96, 96, 0.48);
  --status-visual-panel-end: rgba(253, 239, 239, 0.82);
}

.status-visual--traffic_limited {
  border-color: rgba(97, 154, 214, 0.18);
  background:
    radial-gradient(circle at 20% 22%, rgba(255, 255, 255, 0.7), transparent 28%),
    radial-gradient(circle at 78% 28%, rgba(159, 212, 255, 0.22), transparent 26%),
    linear-gradient(145deg, rgba(246, 251, 255, 0.94), rgba(236, 246, 255, 0.82));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.76),
    0 14px 30px rgba(63, 102, 147, 0.08);
}

.traffic-summary {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.traffic-summary__item {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(237, 246, 255, 0.9);
  border: 1px solid rgba(96, 154, 211, 0.18);
}

.traffic-summary__item small {
  display: block;
  font-size: 12px;
  color: #62748f;
  margin-bottom: 6px;
}

.traffic-summary__item strong {
  color: #26415d;
  font-family: 'Lato', sans-serif;
  font-size: 16px;
}

.status-visual__orbit,
.status-visual__beam,
.status-visual__spark {
  position: absolute;
  border-radius: 50%;
  z-index: 0;
  pointer-events: none;
}

.status-visual__orbit {
  inset: auto;
  border: 1px solid var(--status-visual-ring);
  opacity: 0.9;
}

.status-visual__orbit--outer {
  width: min(32vw, 320px);
  height: min(32vw, 320px);
  animation: scene-spin 24s linear infinite;
}

.status-visual__orbit--inner {
  width: min(24vw, 240px);
  height: min(24vw, 240px);
  border-style: dashed;
  animation: scene-spin 18s linear infinite reverse;
}

.status-visual__beam {
  inset: 50% auto auto 50%;
  width: 220px;
  height: 220px;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle, var(--status-visual-glow), rgba(255, 148, 74, 0));
  filter: blur(12px);
  animation: pulse-glow 6.5s ease-in-out infinite;
}

.status-visual__beam--two {
  width: 150px;
  height: 150px;
  animation-delay: -2.4s;
}

.status-visual__spark {
  width: 14px;
  height: 14px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), var(--status-visual-spark));
  box-shadow: 0 0 0 8px rgba(255, 255, 255, 0.08);
  animation: scene-drift 8.5s linear infinite;
}

.status-visual__spark--one {
  top: 18%;
  left: 23%;
}

.status-visual__spark--two {
  top: 28%;
  right: 18%;
  width: 10px;
  height: 10px;
  animation-delay: -2.4s;
}

.status-visual__spark--three {
  right: 24%;
  bottom: 18%;
  width: 8px;
  height: 8px;
  animation-delay: -4.8s;
}

.status-visual__card small,
.status-visual__card strong {
  margin: 0;
}

.status-visual__card {
  position: absolute;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 160px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(255, 145, 102, 0.22);
  box-shadow: 0 14px 26px rgba(179, 82, 53, 0.12);
  backdrop-filter: blur(10px);
  animation: card-float 7.5s ease-in-out infinite;
  max-width: min(210px, calc(50% - 12px));
}

.status-visual__card .material-symbols-outlined {
  color: #dc5f42;
}

.status-visual__card small {
  display: block;
  color: #866361;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-visual__card strong {
  display: block;
  margin-top: 2px;
  color: #3a2422;
  font-family: 'Lato', sans-serif;
}

.status-visual__card--interactive {
  appearance: none;
  cursor: pointer;
  text-align: left;
  font: inherit;
}

.status-visual__card--interactive:hover {
  transform: translate3d(0, -3px, 0);
  box-shadow: 0 18px 30px rgba(179, 82, 53, 0.16);
}

.status-visual__card--interactive:focus-visible {
  outline: 2px solid rgba(211, 91, 58, 0.72);
  outline-offset: 3px;
}

.status-visual__card--one {
  top: 20px;
  left: 0;
}

.status-visual__card--two {
  right: 4px;
  bottom: 30px;
  animation-delay: -2.6s;
}

.status-visual__card--three {
  top: 54px;
  right: 14px;
  animation-delay: -4.7s;
}

.quick-start-card {
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.9), rgba(255, 244, 237, 0.82));
  grid-column: 2;
}

.quick-start-card:focus-visible {
  outline: 2px solid rgba(211, 91, 58, 0.72);
  outline-offset: 4px;
}

.quick-start-card__glow {
  position: absolute;
  inset: auto auto -80px -40px;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 148, 74, 0.18), rgba(255, 148, 74, 0));
  filter: blur(12px);
  pointer-events: none;
}

.quick-start-head {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 16px;
  margin-bottom: 18px;
}

.quick-start-device {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  min-width: 0;
  width: 100%;
  max-width: 100%;
  padding: 14px 16px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 145, 102, 0.22);
  box-shadow: 0 14px 28px rgba(183, 84, 55, 0.1);
  overflow: hidden;
}

.quick-start-device .material-symbols-outlined {
  color: #d55a3d;
  font-size: 28px;
}

.quick-start-device small,
.quick-start-device strong {
  display: block;
  margin: 0;
}

.quick-start-device small {
  color: #896662;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.quick-start-device strong {
  margin-top: 2px;
  font-family: 'Lato', sans-serif;
  color: #4a2d2a;
  overflow-wrap: anywhere;
}

.quick-start-device > div {
  min-width: 0;
}

.quick-start-body {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 16px;
  align-items: start;
}

.quick-start-steps {
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: quick-start;
  display: grid;
  gap: 12px;
}

.quick-start-steps li {
  counter-increment: quick-start;
  position: relative;
  padding: 14px 16px 14px 64px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 145, 102, 0.18);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  color: #513a37;
  line-height: 1.55;
}

.quick-start-steps li::before {
  content: counter(quick-start);
  position: absolute;
  top: 50%;
  left: 16px;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  transform: translateY(-50%);
  background: linear-gradient(135deg, rgba(255, 104, 72, 0.92), rgba(255, 146, 64, 0.9));
  box-shadow: 0 10px 18px rgba(185, 82, 49, 0.18);
  color: #fff;
  font-family: 'Lato', sans-serif;
  font-size: 16px;
  font-weight: 700;
}

.quick-start-actions {
  display: grid;
  gap: 12px;
  align-content: start;
}

.quick-start-actions .primary-btn {
  width: 100%;
}

.instructions-head {
  position: relative;
  z-index: 1;
  margin-bottom: 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.instructions-head__chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.instructions-head__chip {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(255, 248, 243, 0.9);
  border: 1px solid rgba(255, 145, 102, 0.24);
  color: #885a53;
  font-family: 'Lato', sans-serif;
  box-shadow: 0 8px 18px rgba(191, 94, 63, 0.08);
}

.instructions-card {
  grid-column: 1 / -1;
}

@media (max-width: 1120px) {
  .layout {
    grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
  }

  .status-content {
    min-height: 0;
  }

  .status-visual {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    place-items: stretch;
    min-height: auto;
    padding: 18px;
  }

  .status-visual__card {
    position: static;
    min-width: 0;
    max-width: none;
    width: 100%;
    animation-duration: 6.5s;
  }

  .status-visual__card--three {
    grid-column: 1 / -1;
  }

  .quick-start-head {
    margin-bottom: 16px;
  }
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .status-card,
  .quick-start-card,
  .instructions-card {
    grid-column: 1;
  }
}

.instructions-list {
  display: grid;
  gap: 12px;
}

.instruction-item {
  position: relative;
  border-radius: 16px;
  border: 1px solid rgba(255, 145, 102, 0.25);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(255, 245, 239, 0.78));
  overflow: hidden;
  transition: transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease;
}

.instruction-item::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 18%, rgba(255, 255, 255, 0.22) 50%, transparent 82%);
  transform: translateX(-140%);
  animation: card-sheen 9s ease-in-out infinite;
  pointer-events: none;
}

.instruction-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 24px rgba(182, 83, 54, 0.1);
}

.instruction-item--recommended {
  border-color: rgba(255, 120, 82, 0.42);
  box-shadow: 0 18px 34px rgba(182, 83, 54, 0.12);
}

.instruction-item summary {
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px;
  cursor: pointer;
  font-family: 'Lato', sans-serif;
  font-size: 18px;
  font-weight: 700;
  color: #422c2a;
  position: relative;
  z-index: 1;
}

.instruction-item summary:focus-visible {
  outline: 2px solid rgba(211, 91, 58, 0.68);
  outline-offset: -2px;
}

.instruction-item summary::-webkit-details-marker {
  display: none;
}

.summary-left {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.summary-left > span:last-child {
  display: grid;
  gap: 2px;
}

.summary-title {
  display: block;
}

.summary-app {
  display: block;
  font-size: 12px;
  color: #916966;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.summary-right {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.summary-recommendation {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(255, 236, 226, 0.92);
  color: #c35a3d;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.expand-icon {
  transition: transform 240ms ease;
  color: #795a57;
}

.instruction-item[open] .expand-icon {
  transform: rotate(180deg);
}

.instruction-body {
  border-top: 1px solid rgba(255, 145, 102, 0.2);
  padding: 14px;
  display: grid;
  gap: 12px;
  position: relative;
  z-index: 1;
}

.instruction-item[open] .instruction-body {
  animation: body-reveal 280ms ease;
}

.app-name {
  margin: 0;
  font-family: 'Lato', sans-serif;
  font-weight: 700;
  color: #563230;
}

.notes-list,
.action-list,
.steps-list {
  margin: 0;
  padding-left: 20px;
}

.notes-list {
  display: grid;
  gap: 6px;
}

.action-list {
  list-style: none;
  padding-left: 0;
  display: grid;
  gap: 8px;
}

.action-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  text-decoration: none;
  border-radius: 11px;
  padding: 11px 13px;
  width: fit-content;
  color: #b14628;
  border: 1px solid rgba(250, 129, 89, 0.28);
  background: rgba(255, 243, 236, 0.9);
  box-shadow: 0 10px 18px rgba(187, 82, 49, 0.08);
  transition: transform 200ms ease, background-color 200ms ease, box-shadow 200ms ease;
}

.action-link:hover {
  background: rgba(255, 231, 217, 0.95);
  transform: translateY(-1px);
  box-shadow: 0 12px 20px rgba(187, 82, 49, 0.12);
}

.action-link--button {
  font-family: inherit;
  font-size: 16px;
  cursor: pointer;
}

.steps-list {
  display: grid;
  gap: 7px;
  color: #513a37;
}

.details-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #934024;
  text-decoration: none;
  font-weight: 700;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes scene-float {
  0%, 100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(0, -18px, 0) scale(1.05);
  }
}

@keyframes scene-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes scene-drift {
  0% {
    transform: translate3d(0, 0, 0) scale(0.9);
    opacity: 0;
  }
  16% {
    opacity: 0.78;
  }
  50% {
    transform: translate3d(14px, -18px, 0) scale(1.08);
    opacity: 1;
  }
  100% {
    transform: translate3d(-12px, -36px, 0) scale(0.86);
    opacity: 0;
  }
}

@keyframes pulse-glow {
  0%, 100% {
    opacity: 0.45;
    transform: translate(-50%, -50%) scale(0.92);
  }
  50% {
    opacity: 0.9;
    transform: translate(-50%, -50%) scale(1.08);
  }
}

@keyframes core-bob {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@keyframes pulse-core {
  0%, 100% {
    transform: scale(0.94);
    opacity: 0.74;
  }
  50% {
    transform: scale(1.06);
    opacity: 1;
  }
}

@keyframes card-float {
  0%, 100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(0, -9px, 0);
  }
}

@keyframes cta-sheen {
  0%, 60%, 100% {
    transform: translateX(-140%);
  }
  78% {
    transform: translateX(140%);
  }
}

@keyframes card-sheen {
  0%, 75%, 100% {
    transform: translateX(-140%);
  }
  87% {
    transform: translateX(140%);
  }
}

@keyframes body-reveal {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 760px) {
  .subscription-page {
    padding-top: 18px;
  }

  .status-card {
    min-height: auto;
  }

  .status-visual__orbit--outer {
    width: min(74vw, 300px);
    height: min(74vw, 300px);
  }

  .status-visual__orbit--inner {
    width: min(58vw, 220px);
    height: min(58vw, 220px);
  }

  .status-visual {
    min-height: 280px;
    padding: 14px;
  }

  .instructions-head {
    flex-direction: column;
  }

  .quick-start-head,
  .quick-start-body {
    flex-direction: column;
  }

  .instructions-head__chips {
    justify-content: flex-start;
  }

  .primary-btn,
  .action-link {
    width: 100%;
    justify-content: center;
  }

  .traffic-summary {
    grid-template-columns: 1fr;
  }

  .instruction-item summary {
    font-size: 16px;
  }

  .summary-right {
    gap: 6px;
  }

  .summary-recommendation {
    display: none;
  }
}

@media (max-width: 520px) {
  .instructions-head__chip {
    width: 100%;
    justify-content: center;
  }

  .quick-start-device {
    width: 100%;
    padding: 12px 14px;
  }

  .status-visual {
    grid-template-columns: 1fr;
  }

  .status-visual__card--three {
    grid-column: 1;
  }
}
</style>
