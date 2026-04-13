<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'vue-toastification'

import { resetPassword, startPasswordReset } from '../../api/auth'
import { getAxiosErrorMessage } from '../../utils/httpErrors'
import AuthCardLayout from './AuthCardLayout.vue'
import AuthPasswordField from './AuthPasswordField.vue'

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
    toast.error(getAxiosErrorMessage(error, 'Не удалось отправить код'))
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
    toast.error(getAxiosErrorMessage(error, 'Не удалось обновить пароль'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthCardLayout subtitle="Сброс пароля">
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
      <AuthPasswordField v-model="newPassword" label="Новый пароль" autocomplete="new-password" />
      <button class="cabinet-btn cabinet-btn--warm auth-submit" type="submit" :disabled="loading">
        <span class="material-symbols-outlined">lock_reset</span>
        {{ loading ? 'Обновляем...' : 'Сохранить новый пароль' }}
      </button>
    </form>

    <template #footer>
      <RouterLink class="auth-footer__link" to="/auth/login">
        <span class="material-symbols-outlined auth-footer__icon">arrow_back</span>
        Назад ко входу
      </RouterLink>
    </template>
  </AuthCardLayout>
</template>
