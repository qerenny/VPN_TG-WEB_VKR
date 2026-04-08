<script setup lang="ts">
import axios from 'axios'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'vue-toastification'

import { resetPassword, startPasswordReset } from '../../api/auth'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const email = ref(String(route.query.email || ''))
const code = ref('')
const newPassword = ref('')
const stage = ref<'request' | 'reset'>('request')
const loading = ref(false)

async function requestReset() {
  loading.value = true
  try {
    await startPasswordReset(email.value.trim())
    stage.value = 'reset'
    toast.success('Код отправлен на почту')
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

async function submitReset() {
  loading.value = true
  try {
    await resetPassword({
      email: email.value.trim(),
      code: code.value.trim(),
      new_password: newPassword.value,
    })
    toast.success('Пароль обновлен')
    await router.replace({ path: '/auth/login', query: { email: email.value.trim() } })
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось обновить пароль'))
    } else {
      toast.error('Не удалось обновить пароль')
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
        <p class="auth-card__subtitle">Сброс пароля</p>
        <p class="cabinet-copy">Отправим код на email для восстановления доступа.</p>

        <form v-if="stage === 'request'" class="auth-form" @submit.prevent="requestReset">
          <label class="auth-field">
            <span class="cabinet-form-label">Email</span>
            <input v-model.trim="email" class="cabinet-input" type="email" autocomplete="email" placeholder="you@example.com" required />
          </label>
          <button class="cabinet-btn cabinet-btn--warm auth-submit" type="submit" :disabled="loading">
            <span class="material-symbols-outlined">mail</span>
            {{ loading ? 'Отправляем...' : 'Получить код' }}
          </button>
        </form>

        <form v-else class="auth-form" @submit.prevent="submitReset">
          <label class="auth-field">
            <span class="cabinet-form-label">Email</span>
            <input v-model.trim="email" class="cabinet-input" type="email" autocomplete="email" required />
          </label>
          <label class="auth-field">
            <span class="cabinet-form-label">Код из письма</span>
            <input v-model.trim="code" class="cabinet-input" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="000000" required />
          </label>
          <label class="auth-field">
            <span class="cabinet-form-label">Новый пароль</span>
            <input v-model="newPassword" class="cabinet-input" type="password" autocomplete="new-password" required />
          </label>
          <button class="cabinet-btn cabinet-btn--warm auth-submit" type="submit" :disabled="loading">
            <span class="material-symbols-outlined">lock_reset</span>
            {{ loading ? 'Обновляем...' : 'Сохранить новый пароль' }}
          </button>
        </form>

        <div class="auth-footer">
          <RouterLink class="auth-footer__link" to="/auth/login">
            <span class="material-symbols-outlined auth-footer__icon">arrow_back</span>
            Назад ко входу
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

@media (max-width: 720px) {
  .auth-card { padding: 24px 18px; }
  .auth-logo { width: 64px; height: 64px; }
}
</style>
