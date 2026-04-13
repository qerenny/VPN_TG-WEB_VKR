<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'vue-toastification'

import { resendWebRegistration, startWebRegistration, verifyWebRegistration } from '../../api/auth'
import { consumePublicLink } from '../../api/linking'
import { refreshSession } from '../../stores/session'
import { getAxiosErrorMessage } from '../../utils/httpErrors'
import AuthCardLayout from './AuthCardLayout.vue'
import AuthPasswordField from './AuthPasswordField.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const email = ref(String(route.query.email || ''))
const code = ref('')
const password = ref('')
const passwordConfirmation = ref('')
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
const passwordConfirmationError = computed(() => {
  return passwordConfirmation.value && password.value !== passwordConfirmation.value
    ? 'Пароли не совпадают'
    : ''
})

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
    toast.error(getAxiosErrorMessage(error, 'Не удалось отправить код'))
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
    toast.error(getAxiosErrorMessage(error, 'Не удалось отправить код'))
  } finally {
    loading.value = false
  }
}

async function verifyRegistration() {
  if (password.value !== passwordConfirmation.value) {
    toast.error('Пароли не совпадают')
    return
  }

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
    toast.error(getAxiosErrorMessage(error, 'Не удалось завершить регистрацию'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthCardLayout subtitle="Создание аккаунта">
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
      <AuthPasswordField v-model="password" label="Пароль" autocomplete="new-password" />
      <AuthPasswordField v-model="passwordConfirmation" label="Подтвердите пароль" autocomplete="new-password" />
      <p v-if="passwordConfirmationError" class="auth-field-error">{{ passwordConfirmationError }}</p>
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

    <template #footer>
      <RouterLink class="auth-footer__link" :to="{ path: '/auth/login', query: route.query }">
        <span class="material-symbols-outlined auth-footer__icon">login</span>
        Уже есть аккаунт
      </RouterLink>
    </template>
  </AuthCardLayout>
</template>

<style scoped>
.auth-resend-timer {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

:deep(.auth-resend-timer .material-symbols-outlined) {
  font-size: 16px;
}
</style>
