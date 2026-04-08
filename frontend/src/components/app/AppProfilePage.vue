<script setup lang="ts">
import axios from 'axios'
import { onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'

import {
  fetchLinks,
  fetchProfile,
  startTelegramLink,
  updateProfile,
  type TelegramLinkStartResult,
  type WebLinks,
  type WebProfile,
} from '../../api/account'
import { formatDateTime } from '../../utils/format'

const toast = useToast()

const profile = ref<WebProfile | null>(null)
const links = ref<WebLinks | null>(null)
const loading = ref(true)
const saving = ref(false)
const pendingTelegramLink = ref<TelegramLinkStartResult | null>(null)

onMounted(async () => {
  loading.value = true
  try {
    const [profileData, linksData] = await Promise.all([fetchProfile(), fetchLinks()])
    profile.value = profileData
    links.value = linksData
  } catch {
    toast.error('Не удалось загрузить профиль')
  } finally {
    loading.value = false
  }
})

async function saveProfile() {
  if (!profile.value) {
    return
  }

  saving.value = true
  try {
    const payload = {
      display_name: profile.value.display_name,
      marketing_opt_in: profile.value.marketing_opt_in,
      preferred_contact_email: profile.value.auth_email ? null : profile.value.preferred_contact_email,
    }
    profile.value = await updateProfile({
      ...payload,
    })
    toast.success('Профиль сохранен')
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось сохранить профиль'))
    } else {
      toast.error('Не удалось сохранить профиль')
    }
  } finally {
    saving.value = false
  }
}

async function beginTelegramLink() {
  try {
    pendingTelegramLink.value = await startTelegramLink()
    if (pendingTelegramLink.value.status === 'already_linked') {
      toast.info('Telegram уже привязан')
      return
    }
    toast.success('Ссылка для привязки Telegram создана')
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      toast.error(String(error.response?.data?.detail || 'Не удалось начать привязку'))
    } else {
      toast.error('Не удалось начать привязку')
    }
  }
}
</script>

<template>
  <section class="cabinet-section">
    <div class="cabinet-section__head">
      <p class="cabinet-kicker">Профиль</p>
      <h2 class="cabinet-title">Данные аккаунта и привязки</h2>
      <p class="cabinet-copy">Личные настройки, email и интеграции с внешними сервисами.</p>
    </div>

    <div class="cabinet-grid cabinet-grid--2">
      <!-- Personal data card -->
      <article class="glass-card cabinet-panel profile-card">
        <div class="profile-card__head">
          <span class="material-symbols-outlined profile-card__head-icon profile-card__head-icon--warm">person</span>
          <div class="cabinet-section__head">
            <p class="cabinet-kicker">Личные данные</p>
            <h3 class="cabinet-subtitle">Настройки кабинета</h3>
          </div>
        </div>

        <div v-if="profile && !profile.auth_email" class="profile-notice">
          <span class="material-symbols-outlined profile-notice__icon">mail</span>
          <span>Email еще не добавлен — укажи ниже для входа на сайт</span>
        </div>

        <form v-if="profile" class="profile-form" @submit.prevent="saveProfile">
          <div class="profile-group">
            <label class="profile-field">
              <span class="cabinet-form-label">Имя</span>
              <input v-model.trim="profile.display_name" class="cabinet-input" type="text" />
            </label>
          </div>

          <hr class="profile-divider" />

          <div class="profile-group">
            <div v-if="profile.auth_email" class="profile-field">
              <span class="cabinet-form-label">Email аккаунта</span>
              <div class="profile-readonly">
                <span class="material-symbols-outlined profile-readonly__icon">lock</span>
                {{ profile.auth_email }}
              </div>
            </div>
            <label v-if="!profile.auth_email" class="profile-field">
              <span class="cabinet-form-label">Email для входа</span>
              <input
                v-model.trim="profile.preferred_contact_email"
                class="cabinet-input"
                type="email"
                placeholder="you@example.com"
              />
            </label>
            <label class="profile-toggle-row">
              <span class="cabinet-toggle">
                <input v-model="profile.marketing_opt_in" type="checkbox" />
                <span class="cabinet-toggle__track"></span>
              </span>
              <span class="cabinet-note">Можно присылать обновления</span>
            </label>
          </div>

          <button class="cabinet-btn cabinet-btn--primary" type="submit" :disabled="saving">
            <span class="material-symbols-outlined">save</span>
            {{ saving ? 'Сохраняем...' : 'Сохранить профиль' }}
          </button>
        </form>

        <div v-else-if="loading" class="cabinet-loader">
          <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
          <p class="cabinet-loader__text">Загружаем профиль...</p>
        </div>
      </article>

      <!-- Linking card -->
      <article class="glass-card cabinet-panel profile-card">
        <div class="profile-card__head">
          <span class="material-symbols-outlined profile-card__head-icon profile-card__head-icon--blue">link</span>
          <div class="cabinet-section__head">
            <p class="cabinet-kicker">Привязки</p>
            <h3 class="cabinet-subtitle">Telegram и web-account</h3>
          </div>
        </div>

        <div class="cabinet-facts">
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Web email</p>
            <p class="cabinet-fact__value">{{ profile?.auth_email || 'Пока не создан' }}</p>
          </div>
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Почта</p>
            <p class="cabinet-fact__value">
              {{ profile?.auth_email ? (profile.email_verified ? 'Подтверждена' : 'Не подтверждена') : 'Еще не настроена' }}
            </p>
          </div>
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Telegram</p>
            <p class="cabinet-fact__value">{{ links?.telegram.linked ? `@${links.telegram.username || 'без username'}` : 'Не привязан' }}</p>
          </div>
          <div class="cabinet-fact">
            <p class="cabinet-fact__label">Связан с</p>
            <p class="cabinet-fact__value">{{ formatDateTime(links?.telegram.linked_at || links?.web.linked_at) }}</p>
          </div>
        </div>

        <button
          class="cabinet-btn"
          :class="links?.telegram.linked ? 'cabinet-btn--ghost' : 'cabinet-btn--primary'"
          type="button"
          @click="beginTelegramLink"
        >
          <span class="material-symbols-outlined">{{ links?.telegram.linked ? 'check_circle' : 'add_link' }}</span>
          {{ links?.telegram.linked ? 'Статус привязки' : 'Привязать Telegram' }}
        </button>

        <div v-if="pendingTelegramLink?.deep_link" class="glass-card cabinet-panel telegram-link-card">
          <div class="telegram-link-card__head">
            <span class="material-symbols-outlined telegram-link-card__icon">send</span>
            <p class="cabinet-note">Открой Telegram и заверши привязку через start-ссылку.</p>
          </div>
          <a class="cabinet-btn cabinet-btn--primary" :href="pendingTelegramLink.deep_link" target="_blank" rel="noopener noreferrer">
            <span class="material-symbols-outlined">open_in_new</span>
            Перейти в Telegram
          </a>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.profile-card {
  display: grid;
  gap: 18px;
  align-content: start;
}

.profile-card__head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.profile-card__head-icon {
  font-size: 28px;
  padding: 10px;
  border-radius: 16px;
  flex-shrink: 0;
}

.profile-card__head-icon--warm {
  color: var(--cabinet-standard);
  background: rgba(245, 160, 78, 0.1);
}

.profile-card__head-icon--blue {
  color: var(--cabinet-whitelist);
  background: rgba(77, 143, 214, 0.1);
}

.profile-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 14px;
  background: rgba(77, 143, 214, 0.06);
  border: 1px solid rgba(77, 143, 214, 0.14);
  color: var(--cabinet-text);
  font: 400 13px/1.5 var(--font-text);
}

.profile-notice__icon {
  font-size: 20px;
  color: var(--cabinet-whitelist);
  flex-shrink: 0;
}

.profile-form {
  display: grid;
  gap: 16px;
}

.profile-group {
  display: grid;
  gap: 12px;
}

.profile-divider {
  border: none;
  border-top: 1px solid rgba(126, 170, 220, 0.1);
  margin: 0;
}

.profile-field {
  display: grid;
  gap: 6px;
}

.profile-readonly {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.08);
  font: 600 14px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.profile-readonly__icon {
  font-size: 16px;
  color: var(--cabinet-muted);
}

.profile-toggle-row {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
}

.telegram-link-card {
  margin-top: 4px;
  display: grid;
  gap: 14px;
  background:
    radial-gradient(circle at 80% 15%, rgba(77, 143, 214, 0.1), transparent 30%),
    rgba(255, 252, 249, 0.96);
}

.telegram-link-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.telegram-link-card__icon {
  font-size: 22px;
  color: var(--cabinet-whitelist);
  flex-shrink: 0;
}

@media (max-width: 720px) {
  .profile-toggle-row {
    align-items: flex-start;
  }

  .profile-card__head {
    flex-direction: column;
  }
}
</style>
