<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'vue-toastification'

import { loginViaTelegramLink, loginWeb } from '../../api/auth'
import { consumePublicLink, fetchPublicLinkPreview, type PublicLinkPreview } from '../../api/linking'
import { refreshSession } from '../../stores/session'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const email = ref(String(route.query.email || ''))
const password = ref('')
const loading = ref(false)
const linkPreview = ref<PublicLinkPreview | null>(null)

const linkToken = computed(() => {
  const raw = route.query.link_token
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null
})

const sessionErrorText = computed(() => {
  return route.query.session_error === '1'
    ? 'Не удалось проверить активную сессию. Попробуй войти заново.'
    : null
})

const nextPath = computed(() => {
  const raw = route.query.next
  return typeof raw === 'string' && raw.startsWith('/') ? raw : '/app'
})

const linkStatusText = computed(() => {
  if (linkPreview.value?.status === 'pending') {
    return 'После входа сайт свяжется с твоим Telegram-аккаунтом.'
  }
  if (linkToken.value) {
    return 'Ссылка привязки недействительна или уже использована.'
  }
  return null
})

async function consumeLinkIfNeeded() {
  if (!linkToken.value) {
    return
  }

  try {
    const result = await consumePublicLink(linkToken.value)
    if (result.status === 'linked' || result.status === 'already_linked') {
      toast.success('Аккаунты связаны')
    }
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось завершить привязку'))
      return
    }
    toast.error('Не удалось завершить привязку')
  }
}

async function submitLogin() {
  loading.value = true
  try {
    await loginWeb({
      email: email.value.trim(),
      password: password.value,
      device_name: 'web_panel',
    })
    await refreshSession()
    await consumeLinkIfNeeded()
    await router.replace(nextPath.value)
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось войти'))
    } else {
      toast.error('Не удалось войти')
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (!linkToken.value) {
    return
  }

  try {
    await loginViaTelegramLink({
      token: linkToken.value,
      device_name: 'telegram_link',
    })
    await refreshSession()
    toast.success('Кабинет открыт через Telegram')
    await router.replace('/app')
    return
  } catch {
    try {
      linkPreview.value = await fetchPublicLinkPreview(linkToken.value)
    } catch {
      linkPreview.value = { status: 'invalid', purpose: null, expires_at: null }
    }
  }
})
</script>

<template>
  <main class="page-shell auth-page">
    <div class="auth-scene" aria-hidden="true">
      <div class="auth-scene__orb auth-scene__orb--one"></div>
      <div class="auth-scene__orb auth-scene__orb--two"></div>
      <div class="auth-scene__ring auth-scene__ring--one"></div>
      <span class="auth-scene__dot auth-scene__dot--one"></span>
      <span class="auth-scene__dot auth-scene__dot--two"></span>
    </div>

    <section class="auth-card glass-card cabinet-panel">
      <div class="auth-logo-wrap">
        <img src="/favicon.svg" alt="Логотип сервиса" class="auth-logo" />
      </div>

      <div class="auth-card__body">
        <h1 class="auth-card__title brand-title">Remote Access</h1>
        <p class="auth-card__subtitle">Вход в кабинет</p>
        <p class="cabinet-copy">
          Один аккаунт для конфигураций доступа и профиля. Вход по email.
        </p>

        <div v-if="sessionErrorText" class="auth-notice auth-notice--warn">
          <span class="material-symbols-outlined auth-notice__icon">wifi_off</span>
          {{ sessionErrorText }}
        </div>

        <div v-if="linkStatusText" class="auth-notice" :class="{ 'auth-notice--warn': linkPreview?.status !== 'pending' }">
          <span class="material-symbols-outlined auth-notice__icon">{{ linkPreview?.status === 'pending' ? 'link' : 'link_off' }}</span>
          {{ linkStatusText }}
        </div>

        <form class="auth-form" @submit.prevent="submitLogin">
          <label class="auth-field">
            <span class="cabinet-form-label">Email</span>
            <input v-model.trim="email" class="cabinet-input" type="email" autocomplete="email" placeholder="you@example.com" required />
          </label>

          <label class="auth-field">
            <span class="cabinet-form-label">Пароль</span>
            <input v-model="password" class="cabinet-input" type="password" autocomplete="current-password" required />
          </label>

          <button class="cabinet-btn cabinet-btn--warm auth-submit" type="submit" :disabled="loading">
            <span class="material-symbols-outlined">login</span>
            {{ loading ? 'Входим...' : 'Войти' }}
          </button>
        </form>

        <div class="auth-footer">
          <RouterLink class="auth-footer__link" :to="{ path: '/auth/register', query: route.query }">
            <span class="material-symbols-outlined auth-footer__icon">person_add</span>
            Создать аккаунт
          </RouterLink>
          <RouterLink class="auth-footer__link" :to="{ path: '/auth/password', query: route.query }">
            <span class="material-symbols-outlined auth-footer__icon">lock_reset</span>
            Забыли пароль?
          </RouterLink>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-page {
  display: grid;
  place-items: center;
  padding-top: max(4vh, 24px);
  padding-bottom: max(4vh, 24px);
}

.auth-card {
  width: min(480px, 100%);
  text-align: center;
}

.auth-logo-wrap {
  display: flex;
  justify-content: center;
  margin-bottom: 8px;
}

.auth-logo {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  border: 3px solid rgba(255, 90, 68, 0.3);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(151, 53, 34, 0.18);
  animation: float-soft 4s ease-in-out infinite;
}

.auth-card__body {
  display: grid;
  gap: 6px;
}

.auth-card__title {
  margin: 0;
  font-size: clamp(32px, 6vw, 44px);
  color: var(--accent);
}

.auth-card__subtitle {
  margin: 0;
  font: 700 14px/1.2 var(--font-ui);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--cabinet-muted, var(--muted));
}

.auth-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 16px;
  border-radius: 14px;
  background: rgba(77, 143, 214, 0.08);
  border: 1px solid rgba(77, 143, 214, 0.16);
  color: #1a5a94;
  font: 400 14px/1.5 var(--font-text);
  text-align: left;
}

.auth-notice--warn {
  background: rgba(240, 126, 74, 0.08);
  border-color: rgba(240, 126, 74, 0.18);
  color: #8c3b20;
}

.auth-notice__icon {
  font-size: 20px;
  flex-shrink: 0;
}

.auth-form {
  display: grid;
  gap: 14px;
  margin-top: 18px;
  text-align: left;
}

.auth-field {
  display: grid;
  gap: 6px;
}

.auth-submit {
  width: 100%;
  margin-top: 4px;
}

.auth-footer {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 20px;
  margin-top: 20px;
}

.auth-footer__link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
  font: 700 13px/1.2 var(--font-ui);
  text-decoration: none;
  transition: opacity 180ms ease;
}

.auth-footer__link:hover {
  opacity: 0.75;
}

.auth-footer__icon {
  font-size: 18px;
}

@media (max-width: 720px) {
  .auth-card {
    padding: 24px 18px;
  }

  .auth-logo {
    width: 72px;
    height: 72px;
  }
}
</style>
