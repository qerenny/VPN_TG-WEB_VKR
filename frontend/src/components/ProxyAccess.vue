<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import { createEmptyPublicConfig, fetchPublicConfig, type FrontendPublicConfig } from '../api/publicConfig'

const toast = useToast()
const publicConfig = ref<FrontendPublicConfig>(createEmptyPublicConfig())

const rawProxyUrl = computed(() => {
  if (!publicConfig.value?.features.telegram_proxy_enabled) {
    return ''
  }
  return String(publicConfig.value?.telegram_proxy_url || '').trim()
})

const buildWebProxyUrl = (value: string) => {
  if (!value) {
    return ''
  }

  if (value.startsWith('https://t.me/proxy?')) {
    return value
  }

  if (value.startsWith('http://t.me/proxy?')) {
    return `https://${value.slice('http://'.length)}`
  }

  if (value.startsWith('tg://proxy?')) {
    return `https://t.me/proxy?${value.slice('tg://proxy?'.length)}`
  }

  return ''
}

const buildDirectProxyUrl = (value: string) => {
  if (!value) {
    return ''
  }

  if (value.startsWith('tg://proxy?')) {
    return value
  }

  if (value.startsWith('https://t.me/proxy?') || value.startsWith('http://t.me/proxy?')) {
    const query = value.split('?')[1] || ''
    return query ? `tg://proxy?${query}` : ''
  }

  return ''
}

const telegramProxyDirectUrl = computed(() => buildDirectProxyUrl(rawProxyUrl.value))
const telegramProxyWebUrl = computed(() => buildWebProxyUrl(rawProxyUrl.value))

const copyProxyLink = async () => {
  if (!telegramProxyDirectUrl.value) {
    toast.error('Ссылка на прокси не настроена')
    return
  }

  try {
    await navigator.clipboard.writeText(telegramProxyDirectUrl.value)
    toast.success('Ссылка на прокси скопирована')
  } catch {
    toast.error('Не удалось скопировать ссылку')
  }
}

onMounted(async () => {
  try {
    publicConfig.value = await fetchPublicConfig()
  } catch {
    publicConfig.value = createEmptyPublicConfig()
  }
})
</script>

<template>
  <main class="page-shell">
    <section class="hero glass-card">
      <div class="hero__halo" aria-hidden="true"></div>
      <div class="hero__spark hero__spark--one"></div>
      <div class="hero__spark hero__spark--two"></div>
      <div class="hero__particles" aria-hidden="true">
        <span class="hero__particle hero__particle--1"></span>
        <span class="hero__particle hero__particle--2"></span>
        <span class="hero__particle hero__particle--3"></span>
        <span class="hero__particle hero__particle--4"></span>
      </div>
      <div class="hero__badge hero__badge--one" aria-hidden="true">telegram access</div>
      <div class="hero__badge hero__badge--two" aria-hidden="true">быстрый вход</div>

      <div class="hero__brand">
        <img src="/favicon.svg" alt="Логотип сервиса" class="hero__logo" />
        <p class="hero__chip">Резервный вход в Telegram для доступа к боту</p>
      </div>

      <h1 class="brand-title hero__title">Telegram Proxy</h1>
      <p class="hero__lead">
        Если Telegram не открывается без VPN, подключите прокси в один клик,
        затем вернитесь в бот или веб-панель.
      </p>

      <div class="hero__actions">
        <a
          class="hero__cta"
          :href="telegramProxyDirectUrl || undefined"
        >
          <span class="material-symbols-outlined" aria-hidden="true">send</span>
          Подключить в Telegram
        </a>

        <button class="hero__ghost" type="button" @click="copyProxyLink">
          <span class="material-symbols-outlined" aria-hidden="true">content_copy</span>
          Скопировать ссылку
        </button>
      </div>

      <div class="proxy-card">
        <p class="proxy-card__label">Ссылка прокси</p>
        <p class="proxy-card__value">{{ telegramProxyDirectUrl || 'Ссылка не настроена' }}</p>
      </div>

      <p class="hero__hint">
        Основная кнопка открывает прямую ссылку <code>tg://proxy</code>.
        Если устройство не перехватывает эту схему, можно скопировать ссылку вручную.
      </p>

      <div class="hero__purchase">
        <p class="hero__purchase-label">Нужен доступ?</p>
        <div class="hero__purchase-links">
          <RouterLink to="/auth/login" class="hero__purchase-btn">
            <span class="material-symbols-outlined">login</span>
            Войти в кабинет
          </RouterLink>
          <RouterLink to="/app/subscriptions" class="hero__purchase-btn hero__purchase-btn--web">
            <span class="material-symbols-outlined">vpn_key</span>
            Открыть конфигурации
          </RouterLink>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.hero {
  position: relative;
  overflow: hidden;
  margin: min(10vh, 88px) auto 0;
  width: min(760px, 100%);
  padding: clamp(24px, 5vw, 48px);
  text-align: center;
  animation: card-rise 700ms cubic-bezier(0.19, 1, 0.22, 1);
}

.hero__halo {
  position: absolute;
  inset: 16% 24% auto;
  height: 220px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(255, 156, 95, 0.2), rgba(255, 156, 95, 0));
  filter: blur(10px);
  z-index: -1;
  animation: halo-breathe 7s ease-in-out infinite;
}

.hero__spark {
  position: absolute;
  z-index: -1;
  border-radius: 999px;
  filter: blur(2px);
  animation: orbit 9s ease-in-out infinite;
}

.hero__spark--one {
  width: min(34vw, 220px);
  height: min(34vw, 220px);
  top: -80px;
  right: -70px;
  background: radial-gradient(circle, rgba(255, 116, 87, 0.32), transparent 70%);
}

.hero__spark--two {
  width: min(32vw, 190px);
  height: min(32vw, 190px);
  bottom: -80px;
  left: -60px;
  background: radial-gradient(circle, rgba(255, 163, 75, 0.3), transparent 70%);
  animation-delay: -4.5s;
}

.hero__particles {
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
}

.hero__particle {
  position: absolute;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(255, 173, 95, 0.4));
  box-shadow: 0 0 0 7px rgba(255, 255, 255, 0.08);
  opacity: 0.72;
  animation: particle-drift 11s linear infinite;
}

.hero__particle--1 {
  top: 18%;
  left: 16%;
}

.hero__particle--2 {
  top: 28%;
  right: 18%;
  width: 8px;
  height: 8px;
  animation-delay: -2.2s;
}

.hero__particle--3 {
  bottom: 22%;
  left: 20%;
  width: 10px;
  height: 10px;
  animation-delay: -5.4s;
}

.hero__particle--4 {
  right: 24%;
  bottom: 18%;
  width: 14px;
  height: 14px;
  animation-delay: -7.1s;
}

.hero__badge {
  position: absolute;
  z-index: 1;
  padding: 9px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 129, 91, 0.24);
  box-shadow: 0 14px 22px rgba(194, 92, 52, 0.12);
  color: #9a4b3a;
  font-family: 'Lato', sans-serif;
  font-size: 13px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  backdrop-filter: blur(10px);
  animation: badge-float 8.5s ease-in-out infinite;
}

.hero__badge--one {
  top: 24px;
  left: 24px;
}

.hero__badge--two {
  top: 92px;
  right: 28px;
  animation-delay: -2.8s;
}

.hero__brand {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  gap: 12px;
}

.hero__logo {
  width: clamp(86px, 18vw, 124px);
  height: clamp(86px, 18vw, 124px);
  border-radius: 50%;
  border: 4px solid rgba(255, 90, 68, 0.35);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 34px rgba(151, 53, 34, 0.22);
  animation: logo-bob 6s ease-in-out infinite;
}

.hero__chip {
  margin: 0;
  font-size: clamp(13px, 2.4vw, 15px);
  color: var(--muted);
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(255, 122, 81, 0.26);
  border-radius: 999px;
  padding: 7px 14px;
}

.hero__title {
  margin: 14px 0 8px;
  font-size: clamp(42px, 8vw, 74px);
  line-height: 1;
  color: #de4c38;
}

.hero__lead {
  margin: 0 auto;
  max-width: 560px;
  font-family: 'Lato', sans-serif;
  font-size: clamp(17px, 3.3vw, 22px);
  line-height: 1.55;
  color: #513636;
}

.hero__actions {
  display: grid;
  gap: 12px;
  margin-top: clamp(22px, 4vw, 32px);
}

.hero__cta,
.hero__ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-width: min(350px, 100%);
  padding: 14px 26px;
  border-radius: 16px;
  font-size: clamp(18px, 3.2vw, 22px);
  font-family: 'Lato', sans-serif;
  font-weight: 700;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition: transform 240ms ease, box-shadow 240ms ease, filter 240ms ease;
}

.hero__cta {
  border: 1px solid rgba(255, 92, 66, 0.44);
  background: linear-gradient(120deg, var(--accent), var(--accent-2));
  color: white;
  box-shadow: 0 14px 24px rgba(197, 70, 42, 0.34);
}

.hero__ghost {
  border: 1px solid rgba(255, 122, 81, 0.26);
  background: rgba(255, 255, 255, 0.68);
  color: #9a4b3a;
  box-shadow: 0 10px 18px rgba(194, 92, 52, 0.1);
}

.hero__cta:hover,
.hero__ghost:hover {
  transform: translateY(-3px) scale(1.02);
  filter: saturate(1.05);
}

.proxy-card {
  margin-top: 20px;
  padding: 18px 18px 16px;
  border-radius: 18px;
  border: 1px solid rgba(255, 122, 81, 0.2);
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
}

.proxy-card__label {
  margin: 0 0 8px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.proxy-card__value {
  margin: 0;
  color: #513636;
  font-family: 'Lato', sans-serif;
  line-height: 1.6;
  word-break: break-all;
}

.hero__hint {
  margin: 16px auto 0;
  max-width: 560px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.55;
}

.hero__hint code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.95em;
}

.hero__purchase {
  margin-top: 24px;
  padding: 20px;
  border-radius: 18px;
  border: 1px solid rgba(255, 122, 81, 0.18);
  background: rgba(255, 255, 255, 0.6);
  text-align: center;
}

.hero__purchase-label {
  margin: 0 0 12px;
  font: 700 14px/1.2 'Lato', sans-serif;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.hero__purchase-links {
  display: grid;
  gap: 10px;
  grid-template-columns: 1fr 1fr;
}

.hero__purchase-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 18px;
  border-radius: 14px;
  border: 1px solid rgba(255, 92, 66, 0.35);
  background: linear-gradient(120deg, var(--accent), var(--accent-2));
  color: white;
  text-decoration: none;
  font: 700 15px/1.2 'Lato', sans-serif;
  transition: transform 200ms ease, box-shadow 200ms ease;
  box-shadow: 0 8px 18px rgba(197, 70, 42, 0.2);
}

.hero__purchase-btn--web {
  background: rgba(255, 255, 255, 0.8);
  color: #9a4b3a;
  border-color: rgba(255, 122, 81, 0.24);
  box-shadow: 0 6px 14px rgba(194, 92, 52, 0.08);
}

.hero__purchase-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 22px rgba(197, 70, 42, 0.28);
}

.hero__purchase-btn--web:hover {
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 10px 18px rgba(194, 92, 52, 0.12);
}

.hero__purchase-btn .material-symbols-outlined {
  font-size: 18px;
}

@keyframes card-rise {
  from {
    opacity: 0;
    transform: translateY(28px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes halo-breathe {
  0%, 100% {
    transform: scale(1);
    opacity: 0.95;
  }
  50% {
    transform: scale(1.08);
    opacity: 0.6;
  }
}

@keyframes orbit {
  0%, 100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(14px, -10px, 0);
  }
}

@keyframes particle-drift {
  0% {
    transform: translateY(0);
    opacity: 0;
  }
  12% {
    opacity: 0.78;
  }
  50% {
    transform: translateY(-18px);
  }
  100% {
    transform: translateY(-34px);
    opacity: 0;
  }
}

@keyframes badge-float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-9px);
  }
}

@keyframes logo-bob {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

@media (max-width: 720px) {
  .hero {
    margin-top: 20px;
    padding-top: 80px;
  }

  .hero__badge {
    position: static;
    display: inline-flex;
    margin: 0 6px 8px;
  }

  .hero__purchase-links {
    grid-template-columns: 1fr;
  }
}
</style>
