<script setup lang="ts">
import axios from 'axios'
import { computed, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'vue-toastification'

import { resendWebRegistration, startWebRegistration, verifyWebRegistration } from '../../api/auth'
import { consumePublicLink } from '../../api/linking'
import { refreshSession } from '../../stores/session'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const email = ref(String(route.query.email || ''))
const code = ref('')
const password = ref('')
const stage = ref<'request' | 'verify'>('request')
const loading = ref(false)
const verificationRequired = ref(true)

const RESEND_COOLDOWN = 60
const resendCountdown = ref(0)
let resendTimer: ReturnType<typeof setInterval> | null = null

function startResendCooldown() {
  resendCountdown.value = RESEND_COOLDOWN
  if (resendTimer) clearInterval(resendTimer)
  resendTimer = setInterval(() => {
    resendCountdown.value--
    if (resendCountdown.value <= 0) {
      resendCountdown.value = 0
      if (resendTimer) { clearInterval(resendTimer); resendTimer = null }
    }
  }, 1000)
}

onUnmounted(() => { if (resendTimer) clearInterval(resendTimer) })

const resendDisabled = computed(() => loading.value || resendCountdown.value > 0)

const linkToken = computed(() => {
  const raw = route.query.link_token
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null
})

async function consumeLinkIfNeeded() {
  if (!linkToken.value) {
    return
  }
  await consumePublicLink(linkToken.value)
}

async function startRegistration() {
  loading.value = true
  try {
    const result = await startWebRegistration(email.value.trim())
    verificationRequired.value = result.verification_required
    stage.value = 'verify'
    if (result.verification_required) startResendCooldown()
    toast.success(result.verification_required ? 'Код отправлен на почту' : 'Можно завершить регистрацию без кода')
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось отправить код'))
    } else {
      toast.error('Не удалось отправить код')
    }
  } finally {
    loading.value = false
  }
}

async function resendCode() {
  loading.value = true
  try {
    const result = await resendWebRegistration(email.value.trim())
    verificationRequired.value = result.verification_required
    if (result.verification_required) startResendCooldown()
    toast.success(result.verification_required ? 'Код отправлен повторно' : 'Подтверждение email временно отключено')
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось отправить код'))
    } else {
      toast.error('Не удалось отправить код')
    }
  } finally {
    loading.value = false
  }
}

async function verifyRegistration() {
  loading.value = true
  try {
    await verifyWebRegistration({
      email: email.value.trim(),
      code: verificationRequired.value ? code.value.trim() : '',
      password: password.value,
      device_name: 'web_panel',
    })
    await refreshSession()
    await consumeLinkIfNeeded()
    toast.success('Аккаунт создан')
    await router.replace('/app')
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось завершить регистрацию'))
    } else {
      toast.error('Не удалось завершить регистрацию')
    }
  } finally {
    loading.value = false
  }
}
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
        <p class="auth-card__subtitle">Создание аккаунта</p>
        <p class="cabinet-copy">
          {{ verificationRequired
            ? 'Отправим код подтверждения, затем откроем кабинет.'
            : 'Достаточно указать email и пароль.' }}
        </p>

        <form v-if="stage === 'request'" class="auth-form" @submit.prevent="startRegistration">
          <label class="auth-field">
            <span class="cabinet-form-label">Email</span>
            <input v-model.trim="email" class="cabinet-input" type="email" autocomplete="email" placeholder="you@example.com" required />
          </label>
          <button class="cabinet-btn cabinet-btn--warm auth-submit" type="submit" :disabled="loading">
            <span class="material-symbols-outlined">mail</span>
            {{ loading ? 'Отправляем...' : 'Получить код' }}
          </button>
        </form>

        <form v-else class="auth-form" @submit.prevent="verifyRegistration">
          <label class="auth-field">
            <span class="cabinet-form-label">Email</span>
            <input v-model.trim="email" class="cabinet-input" type="email" autocomplete="email" required />
          </label>
          <label v-if="verificationRequired" class="auth-field">
            <span class="cabinet-form-label">Код из письма</span>
            <input v-model.trim="code" class="cabinet-input" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="000000" required />
          </label>
          <label class="auth-field">
            <span class="cabinet-form-label">Пароль</span>
            <input v-model="password" class="cabinet-input" type="password" autocomplete="new-password" required />
          </label>
          <button class="cabinet-btn cabinet-btn--warm auth-submit" type="submit" :disabled="loading">
            <span class="material-symbols-outlined">check_circle</span>
            {{ loading ? 'Завершаем...' : 'Завершить регистрацию' }}
          </button>
          <button v-if="verificationRequired" class="cabinet-btn cabinet-btn--ghost auth-submit" type="button" :disabled="resendDisabled" @click="resendCode">
            <span v-if="resendCountdown > 0" class="auth-resend-timer">
              <span class="material-symbols-outlined">schedule</span>
              Отправить снова через {{ resendCountdown }}с
            </span>
            <span v-else>Отправить код снова</span>
          </button>
        </form>

        <div class="auth-footer">
          <RouterLink class="auth-footer__link" :to="{ path: '/auth/login', query: route.query }">
            <span class="material-symbols-outlined auth-footer__icon">login</span>
            Уже есть аккаунт
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

.auth-card { width: min(480px, 100%); text-align: center; }

.auth-logo-wrap { display: flex; justify-content: center; margin-bottom: 8px; }

.auth-logo {
  width: 80px; height: 80px;
  border-radius: 50%;
  border: 3px solid rgba(255, 90, 68, 0.3);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(151, 53, 34, 0.18);
  animation: float-soft 4s ease-in-out infinite;
}

.auth-card__body { display: grid; gap: 6px; }

.auth-card__title { margin: 0; font-size: clamp(32px, 6vw, 44px); color: var(--accent); }

.auth-card__subtitle {
  margin: 0;
  font: 700 14px/1.2 var(--font-ui);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.auth-form { display: grid; gap: 14px; margin-top: 18px; text-align: left; }
.auth-field { display: grid; gap: 6px; }
.auth-submit { width: 100%; margin-top: 2px; }

.auth-footer { display: flex; justify-content: center; gap: 20px; margin-top: 20px; }

.auth-footer__link {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--accent); font: 700 13px/1.2 var(--font-ui);
  text-decoration: none; transition: opacity 180ms ease;
}

.auth-footer__link:hover { opacity: 0.75; }
.auth-footer__icon { font-size: 18px; }

.auth-resend-timer {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.auth-resend-timer .material-symbols-outlined {
  font-size: 16px;
}

@media (max-width: 720px) {
  .auth-card { padding: 24px 18px; }
  .auth-logo { width: 64px; height: 64px; }
}
</style>
