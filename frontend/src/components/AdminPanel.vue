<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useToast } from 'vue-toastification'
import {
  createAdminPromo,
  fetchAdminAudit,
  fetchAdminOverview,
  fetchAdminPromos,
  fetchAdminUser,
  loginAdmin,
  logoutAdmin,
  runAdminAction,
  searchAdminUsers,
  toggleAdminPromo,
  type AdminActionPayload,
  type AdminPromoCode,
  type AdminPromoCreatePayload,
} from '../api/admin'

const toast = useToast()

const token = ref('')
const actor = ref('superadmin')
const searchQuery = ref('')
const isBootstrapping = ref(false)
const isSearching = ref(false)
const isLoadingUser = ref(false)
const isRunningAction = ref(false)
const overview = ref<any | null>(null)
const users = ref<any[]>([])
const selectedUser = ref<any | null>(null)
const auditItems = ref<any[]>([])
const selectedUserId = ref<number | null>(null)
const actionReason = ref('')
const dryRun = ref(false)

// Promo management
const promoList = ref<AdminPromoCode[]>([])
const isLoadingPromos = ref(false)
const showPromoForm = ref(false)
const newPromo = ref<AdminPromoCreatePayload>({
  code: '',
  duration_days_override: 30,
  max_redemptions: null,
  per_user_limit: 1,
})

// Per-action inline params
const extendPeriod = ref('month1')
const compensationDays = ref(7)
const referralBonusDays = ref(7)
const unlinkEntityType = ref('referrer')
const paymentDlqLimit = ref(100)
const whitelistPlanCode = ref('whitelist_15gb')

// Tab state for user 360
const activeUserTab = ref('overview')
const userTabs = [
  { key: 'overview', label: 'Обзор', icon: 'person' },
  { key: 'subscriptions', label: 'Подписки', icon: 'vpn_key' },
  { key: 'diagnostics', label: 'Диагностика', icon: 'troubleshoot' },
  { key: 'payments', label: 'Платежи', icon: 'receipt_long' },
  { key: 'growth', label: 'Рост', icon: 'trending_up' },
  { key: 'audit', label: 'Журнал', icon: 'history' },
]

// Confirmation modal
const pendingConfirmation = ref<{
  actionType: AdminActionType
  globalAction: boolean
} | null>(null)

type AdminActionType =
  | 'extend_subscription'
  | 'grant_trial'
  | 'rebuild_subscription_link'
  | 'clear_cache'
  | 'recreate_client'
  | 'grant_compensation_days'
  | 'retry_payment_dlq'
  | 'grant_referral_bonus'
  | 'unlink_problem_entity'
  | 'grant_whitelist_package'
  | 'sync_whitelist_traffic'
  | 'block_user'
  | 'unblock_user'
  | 'delete_user'

interface ActionMeta {
  label: string
  help: string
  icon: string
  scope: 'user' | 'global'
  destructive?: boolean
  requiresPopup?: boolean
  confirmationTitle?: string
  confirmationText?: string
  uses?: string[]
}

const overviewMetrics = [
  { key: 'total_users', label: 'Всего', icon: 'group' },
  { key: 'active_users', label: 'Активных', icon: 'check_circle' },
  { key: 'blocked_users', label: 'Заблокировано', icon: 'block' },
  { key: 'pending_payments', label: 'Ожидают оплаты', icon: 'pending' },
  { key: 'audit_records', label: 'Действий за 24ч', icon: 'history' },
]

const actionCatalog: Record<AdminActionType, ActionMeta> = {
  extend_subscription: {
    label: 'Продлить подписку',
    help: 'Увеличивает срок подписки на заданный период.',
    icon: 'add_circle',
    scope: 'user',
    uses: ['extendPeriod'],
  },
  grant_trial: {
    label: 'Выдать пробный период',
    help: 'Включает trial, если он ещё не использован.',
    icon: 'star',
    scope: 'user',
  },
  rebuild_subscription_link: {
    label: 'Обновить ссылку',
    help: 'Пересобирает subscription link и сбрасывает кэш.',
    icon: 'refresh',
    scope: 'user',
  },
  clear_cache: {
    label: 'Очистить кэш',
    help: 'Сбрасывает серверный кэш подписки.',
    icon: 'delete_sweep',
    scope: 'user',
  },
  recreate_client: {
    label: 'Пересоздать VPN-клиента',
    help: 'Удаляет и создаёт заново VPN-клиента в 3x-ui с сохранением срока.',
    icon: 'build',
    scope: 'user',
    requiresPopup: true,
    confirmationTitle: 'Пересоздать VPN-клиента?',
    confirmationText: 'Используйте только если клиент на сервере пропал или рассинхронизирован.',
  },
  grant_compensation_days: {
    label: 'Начислить компенсацию',
    help: 'Добавляет указанное количество дней как компенсацию.',
    icon: 'volunteer_activism',
    scope: 'user',
    uses: ['compensationDays'],
  },
  retry_payment_dlq: {
    label: 'Повторить зависшие платежи',
    help: 'Повторно обрабатывает задачи из dead letter queue.',
    icon: 'replay',
    scope: 'global',
    requiresPopup: true,
    confirmationTitle: 'Повторить зависшие платежи?',
    confirmationText: 'Массовое действие. Убедитесь, что причина сбоя устранена.',
    uses: ['paymentDlqLimit'],
  },
  grant_referral_bonus: {
    label: 'Реферальный бонус',
    help: 'Ручное начисление реферальных дней.',
    icon: 'group_add',
    scope: 'user',
    uses: ['referralBonusDays'],
  },
  unlink_problem_entity: {
    label: 'Отвязать сущность',
    help: 'Разрывает проблемную связь (referrer, TG, web).',
    icon: 'link_off',
    scope: 'user',
    requiresPopup: true,
    confirmationTitle: 'Отвязать сущность?',
    confirmationText: 'После отвязки часть автоматической логики может перестать работать.',
    uses: ['unlinkEntityType'],
  },
  grant_whitelist_package: {
    label: 'Выдать трафик',
    help: 'Начисляет выбранный пакет конфигурации с лимитом трафика.',
    icon: 'shield',
    scope: 'user',
    uses: ['whitelistPlanCode'],
  },
  sync_whitelist_traffic: {
    label: 'Синхронизировать трафик',
    help: 'Подтягивает текущий трафик из панели и обновляет остаток.',
    icon: 'sync',
    scope: 'user',
  },
  block_user: {
    label: 'Заблокировать',
    help: 'Запрещает пользователю доступ.',
    icon: 'block',
    scope: 'user',
    destructive: true,
    requiresPopup: true,
    confirmationTitle: 'Заблокировать пользователя?',
    confirmationText: 'Пользователь потеряет доступ до ручной разблокировки.',
  },
  unblock_user: {
    label: 'Разблокировать',
    help: 'Снимает блокировку.',
    icon: 'lock_open',
    scope: 'user',
  },
  delete_user: {
    label: 'Удалить полностью',
    help: 'Безвозвратное удаление из БД и 3x-ui.',
    icon: 'delete_forever',
    scope: 'user',
    destructive: true,
    requiresPopup: true,
    confirmationTitle: 'Удалить пользователя безвозвратно?',
    confirmationText: 'Это необратимое действие. Все данные будут потеряны.',
  },
}

const actionGroups = computed(() => [
  {
    title: 'Подписка и доступ',
    icon: 'vpn_key',
    actions: ['extend_subscription', 'grant_trial', 'rebuild_subscription_link', 'clear_cache'] as AdminActionType[],
  },
  {
    title: 'Восстановление',
    icon: 'build',
    actions: ['recreate_client', 'grant_compensation_days', 'retry_payment_dlq'] as AdminActionType[],
  },
  {
    title: 'Рефералка и связи',
    icon: 'group_add',
    actions: ['grant_referral_bonus', 'unlink_problem_entity'] as AdminActionType[],
  },
  {
    title: 'Лимит трафика',
    icon: 'shield',
    actions: ['grant_whitelist_package', 'sync_whitelist_traffic'] as AdminActionType[],
  },
  {
    title: 'Опасные действия',
    icon: 'warning',
    actions: ['block_user', 'unblock_user', 'delete_user'] as AdminActionType[],
  },
])

const canLoad = computed(() => token.value.trim().length > 0)
const isAuthorized = computed(() => !!overview.value)
const selectedSummary = computed(() => selectedUser.value?.summary || null)
const pendingConfirmationMeta = computed(() =>
  pendingConfirmation.value ? actionCatalog[pendingConfirmation.value.actionType] : null,
)
const pendingConfirmationTarget = computed(() => {
  if (!pendingConfirmation.value) return ''
  if (pendingConfirmation.value.globalAction) return 'всю систему'
  if (selectedSummary.value) return `${selectedSummary.value.email} (user #${selectedSummary.value.user_id})`
  return 'выбранного пользователя'
})
const userAudit = computed(() => {
  if (!selectedSummary.value?.tg_id) return []
  return auditItems.value.filter((item) => item.target_tg_id === selectedSummary.value.tg_id)
})

function getActionMeta(actionType: string) {
  return actionCatalog[actionType as AdminActionType]
}

function identityLabel(value?: string) {
  if (value === 'linked') return 'Telegram + Email'
  if (value === 'web') return 'Только web'
  if (value === 'telegram') return 'Только Telegram'
  return 'Внутренний'
}

function identityIcon(value?: string) {
  if (value === 'linked') return 'link'
  if (value === 'web') return 'mail'
  if (value === 'telegram') return 'send'
  return 'person'
}

function formatTrafficBytes(value?: number | null) {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let current = bytes
  let unitIndex = 0
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024
    unitIndex += 1
  }
  const digits = current >= 100 || unitIndex === 0 ? 0 : current >= 10 ? 1 : 2
  return `${current.toFixed(digits)} ${units[unitIndex]}`
}

function playbookSeverityClass(value?: string) {
  if (value === 'high') return 'cabinet-badge--danger'
  if (value === 'medium') return 'cabinet-badge--warm'
  return 'cabinet-badge--muted'
}

function playbookSeverityLabel(value?: string) {
  if (value === 'high') return 'срочно'
  if (value === 'medium') return 'важно'
  return 'низкий'
}

function paymentBadgeClass(status?: string) {
  const n = String(status || '').toLowerCase()
  if (['paid', 'succeeded', 'fulfilled'].includes(n)) return 'cabinet-badge--ok'
  if (['failed', 'canceled', 'cancelled', 'expired'].includes(n)) return 'cabinet-badge--danger'
  return 'cabinet-badge--muted'
}

function auditStatusClass(status?: string) {
  if (status === 'failed') return 'cabinet-badge--danger'
  if (status === 'dry_run') return 'cabinet-badge--warm'
  return 'cabinet-badge--ok'
}

function getErrorMessage(error: any, fallback: string) {
  return error?.response?.data?.detail?.message || error?.response?.data?.detail || error?.message || fallback
}

function resetAdminState() {
  overview.value = null
  users.value = []
  selectedUser.value = null
  auditItems.value = []
  selectedUserId.value = null
}

async function bootstrapAdmin(silent = false) {
  isBootstrapping.value = true
  try {
    const overviewPayload = await fetchAdminOverview()
    overview.value = overviewPayload
    actor.value = overviewPayload.actor || actor.value

    const [usersResult, auditResult] = await Promise.allSettled([searchAdminUsers(''), fetchAdminAudit(), loadPromos()])
    if (usersResult.status === 'fulfilled') {
      users.value = usersResult.value
      if (!selectedUserId.value && usersResult.value.length) await selectUser(usersResult.value[0].user_id)
    } else {
      users.value = []
      if (!silent) toast.error(getErrorMessage(usersResult.reason, 'Не удалось загрузить пользователей'))
    }
    if (auditResult.status === 'fulfilled') auditItems.value = auditResult.value
    else { auditItems.value = []; if (!silent) toast.error(getErrorMessage(auditResult.reason, 'Не удалось загрузить audit')) }
    return true
  } catch (error: any) {
    resetAdminState()
    if (!silent) {
      const retryAfter = error?.response?.data?.detail?.retry_after_seconds
      if (retryAfter) toast.error(`Слишком много попыток. Повтор через ${retryAfter} сек.`)
      else toast.error(getErrorMessage(error, 'Доступ закрыт'))
    }
    return false
  } finally {
    isBootstrapping.value = false
  }
}

async function performSearch() {
  if (!isAuthorized.value) return
  isSearching.value = true
  try {
    users.value = await searchAdminUsers(searchQuery.value)
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || 'Поиск не выполнился')
  } finally {
    isSearching.value = false
  }
}

async function selectUser(userId: number) {
  if (!isAuthorized.value) return
  selectedUserId.value = userId
  isLoadingUser.value = true
  activeUserTab.value = 'overview'
  try {
    selectedUser.value = await fetchAdminUser(userId)
    auditItems.value = await fetchAdminAudit(selectedUser.value?.summary?.tg_id || undefined)
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || 'Не удалось загрузить пользователя')
  } finally {
    isLoadingUser.value = false
  }
}

function buildActionPayload(actionType: string, globalAction: boolean): AdminActionPayload {
  const payload: AdminActionPayload = {
    action_type: actionType,
    target_user_id: globalAction ? null : selectedUserId.value,
    target_tg_id: globalAction ? null : selectedSummary.value?.tg_id ?? null,
    reason: actionReason.value.trim() || undefined,
    dry_run: dryRun.value,
    params: {},
  }
  if (actionType === 'extend_subscription') payload.params = { period: extendPeriod.value.trim() }
  else if (actionType === 'grant_compensation_days') payload.params = { days: compensationDays.value }
  else if (actionType === 'grant_referral_bonus') payload.params = { days: referralBonusDays.value }
  else if (actionType === 'unlink_problem_entity') payload.params = { entity_type: unlinkEntityType.value }
  else if (actionType === 'retry_payment_dlq') payload.params = { limit: paymentDlqLimit.value }
  else if (actionType === 'grant_whitelist_package') payload.params = { plan_code: whitelistPlanCode.value }
  return payload
}

function closeConfirmationModal() { pendingConfirmation.value = null }

async function runActionNow(actionType: string, globalAction: boolean) {
  if (!isAuthorized.value) { toast.error('Сессия не активна'); return }
  if (!globalAction && !selectedUserId.value) { toast.error('Сначала выберите пользователя'); return }
  const payload = buildActionPayload(actionType, globalAction)
  isRunningAction.value = true
  try {
    const result = await runAdminAction(payload)
    toast.success(result.summary || 'Действие выполнено')
    await bootstrapAdmin(true)
    if (selectedUserId.value && !globalAction) await selectUser(selectedUserId.value)
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || 'Ошибка выполнения')
  } finally {
    isRunningAction.value = false
    closeConfirmationModal()
  }
}

function executeAction(actionType: string) {
  const meta = getActionMeta(actionType)
  const globalAction = meta?.scope === 'global'
  if (!isAuthorized.value) { toast.error('Сначала войдите'); return }
  if (!globalAction && !selectedUserId.value) { toast.error('Выберите пользователя'); return }
  if (meta?.requiresPopup) { pendingConfirmation.value = { actionType: actionType as AdminActionType, globalAction }; return }
  void runActionNow(actionType, globalAction)
}

async function confirmPendingAction() {
  if (!pendingConfirmation.value) return
  await runActionNow(pendingConfirmation.value.actionType, pendingConfirmation.value.globalAction)
}

async function signInAdmin() {
  if (!canLoad.value) { toast.error('Введите access token'); return }
  isBootstrapping.value = true
  try {
    await loginAdmin(token.value.trim(), actor.value.trim() || 'superadmin')
    token.value = ''
    const isReady = await bootstrapAdmin(true)
    if (!isReady) { toast.error('Сессия создана, но данные не загрузились'); return }
    toast.success('Сессия открыта')
  } catch (error: any) {
    resetAdminState()
    const retryAfter = error?.response?.data?.detail?.retry_after_seconds
    if (retryAfter) toast.error(`Слишком много попыток. Повтор через ${retryAfter} сек.`)
    else toast.error('Доступ закрыт')
  } finally {
    isBootstrapping.value = false
  }
}

async function signOutAdmin() {
  try { await logoutAdmin() } finally {
    resetAdminState()
    pendingConfirmation.value = null
    toast.info('Сессия закрыта')
  }
}

async function loadPromos() {
  isLoadingPromos.value = true
  try {
    promoList.value = await fetchAdminPromos()
  } catch {
    toast.error('Не удалось загрузить промокоды')
  } finally {
    isLoadingPromos.value = false
  }
}

async function submitCreatePromo() {
  if (!newPromo.value.code.trim()) { toast.error('Введите код'); return }
  try {
    await createAdminPromo(newPromo.value)
    toast.success(`Промокод "${newPromo.value.code}" создан`)
    newPromo.value = { code: '', duration_days_override: 30, max_redemptions: null, per_user_limit: 1 }
    showPromoForm.value = false
    await loadPromos()
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || 'Не удалось создать промокод')
  }
}

async function handleTogglePromo(promo: AdminPromoCode) {
  try {
    await toggleAdminPromo(promo.id, !promo.is_active)
    toast.success(`Промокод "${promo.code}" ${promo.is_active ? 'деактивирован' : 'активирован'}`)
    await loadPromos()
  } catch (error: any) {
    toast.error(error?.response?.data?.detail || 'Не удалось обновить промокод')
  }
}

onMounted(() => {
  actor.value = 'superadmin'
  void bootstrapAdmin(true)
})
</script>

<template>
  <main class="cabinet-shell page-shell adm">
    <!-- ══════ Confirmation Modal ══════ -->
    <div v-if="pendingConfirmation" class="adm-backdrop" @click.self="closeConfirmationModal">
      <section class="glass-card cabinet-panel adm-modal" role="dialog" aria-modal="true">
        <p class="cabinet-kicker">Подтверждение</p>
        <h2 class="adm-modal__title">{{ pendingConfirmationMeta?.confirmationTitle || 'Подтвердите действие' }}</h2>
        <p class="cabinet-note">{{ pendingConfirmationMeta?.confirmationText || 'Это действие может повлиять на данные.' }}</p>

        <div class="adm-modal__facts">
          <div class="adm-modal__fact"><span class="cabinet-form-label">Действие</span><strong>{{ pendingConfirmationMeta?.label }}</strong></div>
          <div class="adm-modal__fact"><span class="cabinet-form-label">Цель</span><strong>{{ pendingConfirmationTarget }}</strong></div>
          <div class="adm-modal__fact"><span class="cabinet-form-label">Причина</span><strong>{{ actionReason.trim() || 'не указана' }}</strong></div>
          <div class="adm-modal__fact"><span class="cabinet-form-label">Режим</span><strong>{{ dryRun ? 'dry run' : 'боевое' }}</strong></div>
        </div>

        <p v-if="!actionReason.trim()" class="adm-modal__warn">
          <span class="material-symbols-outlined">warning</span>
          Лучше указать причину для audit log.
        </p>

        <div class="cabinet-actions">
          <button class="cabinet-btn cabinet-btn--ghost" :disabled="isRunningAction" @click="closeConfirmationModal">Отмена</button>
          <button
            class="cabinet-btn"
            :class="pendingConfirmationMeta?.destructive ? 'adm-btn--danger' : 'cabinet-btn--primary'"
            :disabled="isRunningAction"
            @click="confirmPendingAction"
          >
            <span class="material-symbols-outlined">{{ isRunningAction ? 'hourglass_top' : pendingConfirmationMeta?.destructive ? 'warning' : 'check' }}</span>
            {{ isRunningAction ? 'Выполняю...' : dryRun ? 'Dry run' : 'Подтвердить' }}
          </button>
        </div>
      </section>
    </div>

    <!-- ══════ Top Bar ══════ -->
    <header class="glass-card cabinet-panel adm-header">
      <div class="adm-header__left">
        <p class="cabinet-kicker">Admin Panel</p>
        <h1 class="adm-header__title brand-title">Remote Access</h1>
        <p class="cabinet-note">Служебный интерфейс управления.</p>
      </div>
      <div class="adm-header__right">
        <template v-if="!isAuthorized">
          <label class="adm-field">
            <span class="cabinet-form-label">Access token</span>
            <input v-model="token" class="cabinet-input" type="password" placeholder="Токен для входа" @keydown.enter="signInAdmin" />
          </label>
          <label class="adm-field">
            <span class="cabinet-form-label">Оператор</span>
            <input v-model="actor" class="cabinet-input" type="text" placeholder="superadmin" @keydown.enter="signInAdmin" />
          </label>
          <button class="cabinet-btn cabinet-btn--warm" :disabled="isBootstrapping || !canLoad" @click="signInAdmin">
            <span class="material-symbols-outlined">login</span>
            {{ isBootstrapping ? 'Проверка...' : 'Войти' }}
          </button>
        </template>
        <template v-else>
          <span class="cabinet-badge">{{ overview?.actor || actor }} • {{ overview?.role || 'superadmin' }}</span>
          <button class="cabinet-btn cabinet-btn--ghost" :disabled="isBootstrapping" @click="signOutAdmin">
            <span class="material-symbols-outlined">logout</span>
            Выйти
          </button>
        </template>
      </div>
    </header>

    <!-- ══════ Authorized content ══════ -->
    <template v-if="isAuthorized">
      <!-- Stats -->
      <div class="cabinet-metrics adm-stats">
        <article v-for="m in overviewMetrics" :key="m.key" class="cabinet-metric">
          <div class="adm-stat-head">
            <span class="material-symbols-outlined adm-stat-icon">{{ m.icon }}</span>
            <p class="cabinet-metric__label">{{ m.label }}</p>
          </div>
          <p class="cabinet-metric__value">{{ overview?.stats?.[m.key] ?? '—' }}</p>
        </article>
      </div>

      <!-- Common controls -->
      <div class="glass-card cabinet-panel adm-controls">
        <div class="adm-controls__row">
          <label class="adm-field adm-field--grow">
            <span class="cabinet-form-label">Причина действия</span>
            <input v-model="actionReason" class="cabinet-input" type="text" placeholder="Причина для audit log" />
          </label>
          <label class="adm-toggle-field">
            <span class="cabinet-toggle">
              <input v-model="dryRun" type="checkbox" />
              <span class="cabinet-toggle__track"></span>
            </span>
            <span class="cabinet-form-label">Dry run</span>
          </label>
        </div>
      </div>

      <!-- Main workspace -->
      <div class="adm-workspace">
        <!-- Sidebar: Search + User list -->
        <aside class="glass-card cabinet-panel adm-sidebar">
          <div class="adm-sidebar__head">
            <div>
              <p class="cabinet-kicker">Поиск</p>
              <h2 class="adm-sidebar__title">Пользователи</h2>
            </div>
          </div>
          <form class="adm-search-form" @submit.prevent="performSearch">
            <input v-model="searchQuery" class="cabinet-input" type="text" placeholder="ID, email, tg_id, uuid..." />
            <button class="cabinet-btn cabinet-btn--primary" type="submit" :disabled="isSearching">
              <span class="material-symbols-outlined">search</span>
            </button>
          </form>

          <div class="adm-user-list">
            <button
              v-for="item in users"
              :key="item.user_id"
              class="adm-user-card"
              :class="{ 'adm-user-card--active': item.user_id === selectedUserId }"
              @click="selectUser(item.user_id)"
            >
              <div class="adm-user-card__top">
                <strong class="adm-user-card__email">{{ item.email || `user #${item.user_id}` }}</strong>
                <span class="cabinet-badge" :class="item.is_blocked ? 'cabinet-badge--danger' : item.is_active ? 'cabinet-badge--ok' : 'cabinet-badge--muted'">
                  {{ item.is_blocked ? 'блок' : item.is_active ? 'актив' : 'нет' }}
                </span>
              </div>
              <p class="adm-user-card__meta">
                <span class="material-symbols-outlined adm-user-card__meta-icon">{{ identityIcon(item.identity_kind) }}</span>
                #{{ item.user_id }}
                <span v-if="item.tg_id"> • TG {{ item.tg_id }}</span>
                <span v-if="item.username"> • @{{ item.username }}</span>
              </p>
            </button>
            <p v-if="!users.length" class="cabinet-note" style="text-align:center;padding:20px 0">Нет результатов</p>
          </div>
        </aside>

        <!-- Main content -->
        <div class="adm-main">
          <!-- Action groups -->
          <section class="glass-card cabinet-panel adm-actions-panel">
            <div class="adm-actions-panel__head">
              <span class="material-symbols-outlined adm-actions-panel__icon">tune</span>
              <div>
                <p class="cabinet-kicker">Действия</p>
                <h2 class="adm-section-title">Управление{{ selectedSummary ? `: ${selectedSummary.email || 'user #' + selectedSummary.user_id}` : '' }}</h2>
              </div>
            </div>

            <div v-for="group in actionGroups" :key="group.title" class="adm-action-group">
              <div class="adm-action-group__head">
                <span class="material-symbols-outlined adm-action-group__icon">{{ group.icon }}</span>
                <h3 class="adm-action-group__title">{{ group.title }}</h3>
              </div>
              <div class="adm-action-cards">
                <article
                  v-for="aType in group.actions"
                  :key="aType"
                  class="adm-action-card"
                  :class="{ 'adm-action-card--danger': actionCatalog[aType]?.destructive }"
                >
                  <div class="adm-action-card__head">
                    <span class="material-symbols-outlined adm-action-card__icon">{{ actionCatalog[aType].icon }}</span>
                    <div>
                      <strong>{{ actionCatalog[aType].label }}</strong>
                      <p class="adm-action-card__help">{{ actionCatalog[aType].help }}</p>
                    </div>
                  </div>

                  <!-- Inline parameters -->
                  <div v-if="actionCatalog[aType].uses?.length" class="adm-action-card__params">
                    <label v-if="actionCatalog[aType].uses?.includes('extendPeriod')" class="adm-field">
                      <span class="cabinet-form-label">Период</span>
                      <input v-model="extendPeriod" class="cabinet-input" type="text" placeholder="month1" />
                    </label>
                    <label v-if="actionCatalog[aType].uses?.includes('compensationDays')" class="adm-field">
                      <span class="cabinet-form-label">Дней</span>
                      <input v-model.number="compensationDays" class="cabinet-input" type="number" min="1" />
                    </label>
                    <label v-if="actionCatalog[aType].uses?.includes('referralBonusDays')" class="adm-field">
                      <span class="cabinet-form-label">Дней</span>
                      <input v-model.number="referralBonusDays" class="cabinet-input" type="number" min="1" />
                    </label>
                    <label v-if="actionCatalog[aType].uses?.includes('unlinkEntityType')" class="adm-field">
                      <span class="cabinet-form-label">Что отвязывать</span>
                      <select v-model="unlinkEntityType" class="cabinet-input">
                        <option value="referrer">referrer</option>
                        <option value="telegram_account">telegram_account</option>
                        <option value="web_account">web_account</option>
                      </select>
                    </label>
                    <label v-if="actionCatalog[aType].uses?.includes('paymentDlqLimit')" class="adm-field">
                      <span class="cabinet-form-label">Лимит задач</span>
                      <input v-model.number="paymentDlqLimit" class="cabinet-input" type="number" min="1" />
                    </label>
                    <label v-if="actionCatalog[aType].uses?.includes('whitelistPlanCode')" class="adm-field">
                      <span class="cabinet-form-label">Пакет</span>
                      <select v-model="whitelistPlanCode" class="cabinet-input">
                        <option value="whitelist_15gb">15 GB</option>
                        <option value="whitelist_35gb">35 GB</option>
                        <option value="whitelist_80gb">80 GB</option>
                      </select>
                    </label>
                  </div>

                  <button
                    class="cabinet-btn"
                    :class="actionCatalog[aType].destructive ? 'adm-btn--danger' : 'cabinet-btn--ghost'"
                    :disabled="isRunningAction"
                    @click="executeAction(aType)"
                  >
                    <span class="material-symbols-outlined">{{ actionCatalog[aType].icon }}</span>
                    {{ actionCatalog[aType].label }}
                  </button>
                </article>
              </div>
            </div>
          </section>

          <!-- Promo Management -->
          <section class="glass-card cabinet-panel adm-promo-panel">
            <div class="adm-promo-panel__head">
              <div class="adm-promo-panel__head-left">
                <span class="material-symbols-outlined adm-actions-panel__icon">confirmation_number</span>
                <div>
                  <p class="cabinet-kicker">Управление</p>
                  <h2 class="adm-section-title">Промокоды</h2>
                </div>
              </div>
              <div class="adm-promo-panel__head-right">
                <button class="cabinet-btn cabinet-btn--primary" @click="showPromoForm = !showPromoForm">
                  <span class="material-symbols-outlined">{{ showPromoForm ? 'close' : 'add' }}</span>
                  {{ showPromoForm ? 'Отмена' : 'Создать' }}
                </button>
                <button class="cabinet-btn cabinet-btn--ghost" :disabled="isLoadingPromos" @click="loadPromos">
                  <span class="material-symbols-outlined">refresh</span>
                </button>
              </div>
            </div>

            <!-- Create form -->
            <div v-if="showPromoForm" class="adm-promo-form">
              <div class="adm-promo-form__grid">
                <label class="adm-field">
                  <span class="cabinet-form-label">Код</span>
                  <input v-model="newPromo.code" class="cabinet-input" type="text" placeholder="PROMO2026" />
                </label>
                <label class="adm-field">
                  <span class="cabinet-form-label">Дней (override)</span>
                  <input v-model.number="newPromo.duration_days_override" class="cabinet-input" type="number" min="1" placeholder="30" />
                </label>
                <label class="adm-field">
                  <span class="cabinet-form-label">Макс. активаций</span>
                  <input v-model.number="newPromo.max_redemptions" class="cabinet-input" type="number" min="1" placeholder="∞" />
                </label>
                <label class="adm-field">
                  <span class="cabinet-form-label">Лимит на юзера</span>
                  <input v-model.number="newPromo.per_user_limit" class="cabinet-input" type="number" min="1" />
                </label>
                <label class="adm-field">
                  <span class="cabinet-form-label">Действует с</span>
                  <input v-model="newPromo.valid_from" class="cabinet-input" type="datetime-local" />
                </label>
                <label class="adm-field">
                  <span class="cabinet-form-label">Действует до</span>
                  <input v-model="newPromo.valid_until" class="cabinet-input" type="datetime-local" />
                </label>
              </div>
              <button class="cabinet-btn cabinet-btn--warm" @click="submitCreatePromo">
                <span class="material-symbols-outlined">check</span>
                Создать промокод
              </button>
            </div>

            <!-- Promo list -->
            <div v-if="isLoadingPromos" class="cabinet-loader" style="padding:24px 0">
              <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
              <p class="cabinet-loader__text">Загрузка...</p>
            </div>
            <div v-else-if="promoList.length" class="adm-promo-list">
              <article v-for="promo in promoList" :key="promo.id" class="adm-promo-item" :class="{ 'adm-promo-item--inactive': !promo.is_active }">
                <div class="adm-promo-item__main">
                  <div class="adm-promo-item__info">
                    <strong class="adm-promo-item__code">{{ promo.code }}</strong>
                    <span class="cabinet-badge" :class="promo.is_active ? 'cabinet-badge--ok' : 'cabinet-badge--muted'">
                      {{ promo.is_active ? 'активен' : 'неактивен' }}
                    </span>
                  </div>
                  <div class="adm-promo-item__meta">
                    <span v-if="promo.duration_days_override">{{ promo.duration_days_override }}д</span>
                    <span v-if="promo.plan_name">• {{ promo.plan_name }}</span>
                    <span>• {{ promo.redemptions_count }}{{ promo.max_redemptions ? `/${promo.max_redemptions}` : '' }} использований</span>
                    <span v-if="promo.valid_until">• до {{ promo.valid_until?.slice(0, 10) }}</span>
                  </div>
                </div>
                <button
                  class="cabinet-btn"
                  :class="promo.is_active ? 'cabinet-btn--ghost' : 'cabinet-btn--primary'"
                  @click="handleTogglePromo(promo)"
                >
                  <span class="material-symbols-outlined">{{ promo.is_active ? 'pause' : 'play_arrow' }}</span>
                  {{ promo.is_active ? 'Выкл' : 'Вкл' }}
                </button>
              </article>
            </div>
            <p v-else class="cabinet-note" style="text-align:center;padding:24px 0">Промокодов пока нет</p>
          </section>

          <!-- User 360 -->
          <section v-if="selectedSummary" class="glass-card cabinet-panel adm-user360">
            <div class="adm-user360__hero">
              <div>
                <p class="cabinet-kicker">User 360</p>
                <h2 class="adm-section-title">{{ selectedSummary.email || `user #${selectedSummary.user_id}` }}</h2>
                <p class="cabinet-note">
                  #{{ selectedSummary.user_id }}
                  <span v-if="selectedSummary.tg_id"> • TG {{ selectedSummary.tg_id }}</span>
                  <span v-if="selectedSummary.username"> • @{{ selectedSummary.username }}</span>
                  <span v-if="selectedSummary.uuid"> • {{ selectedSummary.uuid.slice(0, 8) }}...</span>
                </p>
              </div>
              <div class="adm-user360__badges">
                <span class="cabinet-badge" :class="selectedSummary.is_active ? 'cabinet-badge--ok' : 'cabinet-badge--muted'">
                  {{ selectedSummary.is_active ? 'активен' : 'неактивен' }}
                </span>
                <span v-if="selectedSummary.is_blocked" class="cabinet-badge cabinet-badge--danger">заблокирован</span>
                <span class="cabinet-badge">{{ identityLabel(selectedSummary.identity_kind) }}</span>
              </div>
            </div>

            <!-- Tabs -->
            <nav class="adm-tabs">
              <button
                v-for="tab in userTabs"
                :key="tab.key"
                class="adm-tab"
                :class="{ 'adm-tab--active': activeUserTab === tab.key }"
                @click="activeUserTab = tab.key"
              >
                <span class="material-symbols-outlined">{{ tab.icon }}</span>
                {{ tab.label }}
              </button>
            </nav>

            <!-- Loading -->
            <div v-if="isLoadingUser" class="cabinet-loader">
              <img src="/favicon.svg" alt="" class="cabinet-loader__img" />
              <p class="cabinet-loader__text">Загружаем данные...</p>
            </div>

            <template v-else>
              <!-- TAB: Overview -->
              <div v-show="activeUserTab === 'overview'" class="adm-tab-content">
                <div class="adm-kv-grid">
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">person</span> Профиль</h3>
                    <dl class="adm-kv">
                      <div><dt>user_id</dt><dd>{{ selectedUser.profile.user_id }}</dd></div>
                      <div><dt>auth email</dt><dd>{{ selectedUser.profile.auth_email || '—' }}</dd></div>
                      <div><dt>contact email</dt><dd>{{ selectedUser.profile.preferred_contact_email || '—' }}</dd></div>
                      <div><dt>sub_id</dt><dd>{{ selectedUser.profile.sub_id || '—' }}</dd></div>
                      <div><dt>зарегистрирован</dt><dd>{{ selectedUser.profile.login_date || '—' }}</dd></div>
                      <div><dt>подписка до</dt><dd>{{ selectedUser.profile.expiration_date || '—' }}</dd></div>
                      <div><dt>trial</dt><dd>{{ selectedUser.profile.trial_date || 'не использован' }}</dd></div>
                      <div><dt>news бонус</dt><dd>{{ selectedUser.profile.news_channel_date || '—' }}</dd></div>
                    </dl>
                    <div v-if="selectedUser.profile.subscription_link" class="adm-link-row">
                      <a :href="selectedUser.profile.subscription_link" target="_blank" rel="noreferrer" class="cabinet-btn cabinet-btn--ghost">
                        <span class="material-symbols-outlined">link</span> Ссылка подписки
                      </a>
                    </div>
                  </article>
                  <article v-if="selectedUser.telegram_account" class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">send</span> Telegram</h3>
                    <dl class="adm-kv">
                      <div><dt>telegram_id</dt><dd>{{ selectedUser.telegram_account.telegram_id }}</dd></div>
                      <div><dt>username</dt><dd>{{ selectedUser.telegram_account.username || '—' }}</dd></div>
                      <div><dt>привязан</dt><dd>{{ selectedUser.telegram_account.linked_at || '—' }}</dd></div>
                      <div><dt>первый визит</dt><dd>{{ selectedUser.telegram_account.first_seen_at || '—' }}</dd></div>
                      <div><dt>последний визит</dt><dd>{{ selectedUser.telegram_account.last_seen_at || '—' }}</dd></div>
                    </dl>
                  </article>
                  <article v-if="selectedUser.web_account" class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">mail</span> Web-аккаунт</h3>
                    <dl class="adm-kv">
                      <div><dt>email</dt><dd>{{ selectedUser.web_account.email }}</dd></div>
                      <div><dt>подтверждён</dt><dd>{{ selectedUser.web_account.email_verified_at || 'нет' }}</dd></div>
                      <div><dt>последний вход</dt><dd>{{ selectedUser.web_account.last_login_at || '—' }}</dd></div>
                    </dl>
                  </article>
                </div>

                <!-- Playbooks -->
                <div v-if="selectedUser.playbooks?.length" class="adm-playbooks">
                  <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">auto_fix_high</span> Сценарии решения</h3>
                  <article v-for="pb in selectedUser.playbooks" :key="pb.id" class="adm-playbook">
                    <div class="adm-playbook__head">
                      <strong>{{ pb.title }}</strong>
                      <span class="cabinet-badge" :class="playbookSeverityClass(pb.severity)">{{ playbookSeverityLabel(pb.severity) }}</span>
                    </div>
                    <p class="cabinet-note">{{ pb.summary }}</p>
                    <div v-if="pb.checks?.length" class="adm-playbook__checks">
                      <span v-for="check in pb.checks" :key="check" class="cabinet-badge cabinet-badge--muted">{{ check }}</span>
                    </div>
                    <div v-if="pb.suggested_actions?.length" class="adm-playbook__actions">
                      <span v-for="a in pb.suggested_actions" :key="a" class="cabinet-badge cabinet-badge--warm">{{ getActionMeta(a)?.label || a }}</span>
                    </div>
                  </article>
                </div>
              </div>

              <!-- TAB: Subscriptions -->
              <div v-show="activeUserTab === 'subscriptions'" class="adm-tab-content">
                <div class="adm-kv-grid">
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">vpn_key</span> Standard</h3>
                    <dl class="adm-kv">
                      <div><dt>подписка до</dt><dd>{{ selectedUser.profile.expiration_date || '—' }}</dd></div>
                      <div><dt>uuid</dt><dd class="adm-kv__mono">{{ selectedUser.profile.uuid || '—' }}</dd></div>
                      <div><dt>sub_id</dt><dd class="adm-kv__mono">{{ selectedUser.profile.sub_id || '—' }}</dd></div>
                    </dl>
                  </article>
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">shield</span> Лимит трафика</h3>
                    <dl class="adm-kv">
                      <div><dt>статус</dt><dd>
                        <span class="cabinet-badge" :class="selectedUser.profile.whitelist?.is_enabled ? 'cabinet-badge--ok' : 'cabinet-badge--muted'">
                          {{ selectedUser.profile.whitelist?.is_enabled ? 'подключен' : 'нет' }}
                        </span>
                      </dd></div>
                      <div><dt>email</dt><dd class="adm-kv__mono">{{ selectedUser.profile.whitelist?.email || '—' }}</dd></div>
                      <div><dt>uuid</dt><dd class="adm-kv__mono">{{ selectedUser.profile.whitelist?.uuid || '—' }}</dd></div>
                      <div><dt>выделено</dt><dd>{{ formatTrafficBytes(selectedUser.profile.whitelist?.allocated_bytes) }}</dd></div>
                      <div><dt>использовано</dt><dd>{{ formatTrafficBytes(selectedUser.profile.whitelist?.used_bytes) }}</dd></div>
                      <div><dt>остаток</dt><dd>{{ formatTrafficBytes(selectedUser.profile.whitelist?.remaining_bytes) }}</dd></div>
                      <div><dt>действует до</dt><dd>{{ selectedUser.profile.whitelist?.expires_at || '—' }}</dd></div>
                    </dl>
                  </article>
                </div>
              </div>

              <!-- TAB: Diagnostics -->
              <div v-show="activeUserTab === 'diagnostics'" class="adm-tab-content">
                <div class="adm-kv-grid">
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">dns</span> Клиент 3x-ui</h3>
                    <dl class="adm-kv">
                      <div><dt>статус</dt><dd>
                        <span class="cabinet-badge" :class="selectedUser.diagnostics.client.status === 'present' ? 'cabinet-badge--ok' : 'cabinet-badge--danger'">
                          {{ selectedUser.diagnostics.client.status }}
                        </span>
                      </dd></div>
                      <div v-if="selectedUser.diagnostics.client.details"><dt>детали</dt><dd>{{ selectedUser.diagnostics.client.details }}</dd></div>
                    </dl>
                  </article>
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">cached</span> Кэш</h3>
                    <dl class="adm-kv">
                      <div><dt>local build</dt><dd>{{ selectedUser.diagnostics.cache.local.build ? 'да' : 'нет' }}</dd></div>
                      <div><dt>local info</dt><dd>{{ selectedUser.diagnostics.cache.local.info ? 'да' : 'нет' }}</dd></div>
                      <div><dt>redis build</dt><dd>{{ selectedUser.diagnostics.cache.redis.build ? 'да' : 'нет' }}</dd></div>
                      <div><dt>redis info</dt><dd>{{ selectedUser.diagnostics.cache.redis.info ? 'да' : 'нет' }}</dd></div>
                    </dl>
                  </article>
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">compare_arrows</span> Parity</h3>
                    <dl class="adm-kv">
                      <div><dt>расхождение</dt><dd>
                        <span class="cabinet-badge" :class="selectedUser.diagnostics.parity.has_mismatch ? 'cabinet-badge--danger' : 'cabinet-badge--ok'">
                          {{ selectedUser.diagnostics.parity.has_mismatch ? 'есть' : 'нет' }}
                        </span>
                      </dd></div>
                    </dl>
                  </article>
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">shield</span> Лимит трафика</h3>
                    <dl class="adm-kv">
                      <div><dt>статус</dt><dd>{{ selectedUser.diagnostics.whitelist.status }}</dd></div>
                      <div><dt>остаток</dt><dd>{{ formatTrafficBytes(selectedUser.diagnostics.whitelist.remaining_bytes) }}</dd></div>
                      <div><dt>sync</dt><dd>{{ selectedUser.diagnostics.whitelist.last_provider_sync_at || '—' }}</dd></div>
                    </dl>
                  </article>
                </div>

                <!-- Timeline -->
                <div v-if="selectedUser.diagnostics.timeline?.length" class="adm-timeline">
                  <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">timeline</span> Временная шкала</h3>
                  <div class="adm-timeline__items">
                    <div v-for="item in selectedUser.diagnostics.timeline" :key="item.label" class="adm-timeline__item">
                      <span class="cabinet-form-label">{{ item.label }}</span>
                      <span>{{ item.value || '—' }}</span>
                    </div>
                  </div>
                </div>

                <!-- DLQ -->
                <div v-if="selectedUser.diagnostics.queues?.recent_dead_letters?.length" class="adm-dlq">
                  <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">error</span> Dead Letter Queue</h3>
                  <article v-for="item in selectedUser.diagnostics.queues.recent_dead_letters" :key="`${item.payment_id}-${item.failed_at}`" class="adm-dlq__item">
                    <strong>{{ item.payment_id || 'неизвестный' }}</strong>
                    <p class="cabinet-note">{{ item.error }}</p>
                    <small class="cabinet-note">{{ item.failed_at || '' }}</small>
                  </article>
                </div>
              </div>

              <!-- TAB: Payments -->
              <div v-show="activeUserTab === 'payments'" class="adm-tab-content">
                <div v-if="selectedUser.payments?.legacy?.length || selectedUser.payments?.current?.length" class="adm-payments">
                  <div v-if="selectedUser.payments.current?.length" class="adm-payment-list">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">receipt_long</span> Текущие</h3>
                    <div class="adm-table-wrap">
                      <table class="adm-table">
                        <thead><tr><th>ID</th><th>Статус</th><th>Сумма</th><th>Создан</th><th>Оплачен</th></tr></thead>
                        <tbody>
                          <tr v-for="p in selectedUser.payments.current" :key="p.id">
                            <td>{{ p.id }}</td>
                            <td><span class="cabinet-badge" :class="paymentBadgeClass(p.status)">{{ p.status }}</span></td>
                            <td>{{ p.amount }} {{ p.currency }}</td>
                            <td>{{ p.created_at || '—' }}</td>
                            <td>{{ p.paid_at || '—' }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div v-if="selectedUser.payments.legacy?.length" class="adm-payment-list">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">history</span> Legacy</h3>
                    <div class="adm-table-wrap">
                      <table class="adm-table">
                        <thead><tr><th>payment_id</th><th>Статус</th><th>Создан</th><th>Подтверждён</th><th>Метод</th></tr></thead>
                        <tbody>
                          <tr v-for="p in selectedUser.payments.legacy" :key="p.payment_id">
                            <td>{{ p.payment_id }}</td>
                            <td><span class="cabinet-badge" :class="paymentBadgeClass(p.status)">{{ p.status }}</span></td>
                            <td>{{ p.created_at || '—' }}</td>
                            <td>{{ p.confirmed }}</td>
                            <td>{{ p.method || '—' }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
                <p v-else class="cabinet-note" style="text-align:center;padding:32px 0">Платежей нет</p>
              </div>

              <!-- TAB: Growth -->
              <div v-show="activeUserTab === 'growth'" class="adm-tab-content">
                <div class="adm-kv-grid">
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">group_add</span> Рефералка</h3>
                    <dl class="adm-kv">
                      <div><dt>реферер tg_id</dt><dd>{{ selectedUser.referral?.referrer_tg_id || '—' }}</dd></div>
                      <div><dt>приглашено</dt><dd>{{ selectedUser.referral?.invited_count || 0 }}</dd></div>
                      <div><dt>оплатили</dt><dd>{{ selectedUser.referral?.paid_count || 0 }}</dd></div>
                      <div><dt>бонус получен</dt><dd>{{ selectedUser.referral?.bonus_is_received || false }}</dd></div>
                      <div><dt>дней в ожидании</dt><dd>{{ selectedUser.referral?.days_pending || 0 }}</dd></div>
                    </dl>
                  </article>
                  <article class="adm-kv-card">
                    <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">confirmation_number</span> Промокоды</h3>
                    <div v-if="selectedUser.promo?.current?.length || selectedUser.promo?.legacy?.length" class="adm-chip-list">
                      <span v-for="p in selectedUser.promo.current" :key="`c-${p.code}-${p.redeemed_at}`" class="cabinet-badge cabinet-badge--ok">
                        {{ p.code }}
                      </span>
                      <span v-for="p in selectedUser.promo.legacy" :key="`l-${p.id}`" class="cabinet-badge cabinet-badge--muted">
                        legacy: {{ p.code }}
                      </span>
                    </div>
                    <p v-else class="cabinet-note">Промокоды не использовались</p>
                  </article>
                </div>

                <!-- Referral Rewards -->
                <div v-if="selectedUser.referral_rewards?.length" class="adm-rewards">
                  <h3 class="adm-kv-card__title"><span class="material-symbols-outlined">card_giftcard</span> Реферальные награды</h3>
                  <div class="adm-table-wrap">
                    <table class="adm-table">
                      <thead><tr><th>Триггер</th><th>Дней</th><th>Создан</th><th>Применён</th><th>Отменён</th></tr></thead>
                      <tbody>
                        <tr v-for="(r, i) in selectedUser.referral_rewards" :key="i">
                          <td>{{ r.trigger_type }}</td>
                          <td>{{ r.reward_days }}</td>
                          <td>{{ r.created_at || '—' }}</td>
                          <td>{{ r.applied_at || '—' }}</td>
                          <td>{{ r.canceled_at || '—' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <!-- TAB: Audit -->
              <div v-show="activeUserTab === 'audit'" class="adm-tab-content">
                <div class="adm-audit-list">
                  <article v-for="item in (userAudit.length ? userAudit : auditItems)" :key="item.id" class="adm-audit-item">
                    <div class="adm-audit-item__head">
                      <div class="adm-audit-item__info">
                        <span class="material-symbols-outlined adm-audit-item__icon">{{ getActionMeta(item.action_type)?.icon || 'settings' }}</span>
                        <strong>{{ getActionMeta(item.action_type)?.label || item.action_type }}</strong>
                      </div>
                      <span class="cabinet-badge" :class="auditStatusClass(item.status)">{{ item.status }}</span>
                    </div>
                    <p class="cabinet-note">{{ item.summary || 'без описания' }}</p>
                    <p class="adm-audit-item__meta">{{ item.created_at }} • {{ item.actor }} • target {{ item.target_tg_id || 'global' }}</p>
                  </article>
                  <p v-if="!userAudit.length && !auditItems.length" class="cabinet-note" style="text-align:center;padding:20px 0">Нет записей</p>
                </div>
              </div>
            </template>
          </section>
        </div>
      </div>
    </template>

    <!-- Not authorized -->
    <section v-else class="glass-card cabinet-panel adm-locked">
      <span class="material-symbols-outlined adm-locked__icon">lock</span>
      <h2 class="adm-section-title">Консоль скрыта</h2>
      <p class="cabinet-note">Без активной сессии разделы недоступны.</p>
    </section>
  </main>
</template>

<style scoped>
/* ══════ Layout ══════ */
.adm { max-width: 1440px; }

.adm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.adm-header__title {
  margin: 0;
  font-size: clamp(32px, 5vw, 48px);
  color: var(--accent);
}

.adm-header__right {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.adm-field {
  display: grid;
  gap: 6px;
}

.adm-field--grow { flex: 1; min-width: 200px; }

/* ══════ Stats ══════ */
.adm-stats {
  margin-top: 20px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.adm-stat-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.adm-stat-icon {
  font-size: 18px;
  color: var(--cabinet-muted);
}

/* ══════ Controls ══════ */
.adm-controls { margin-top: 16px; }

.adm-controls__row {
  display: flex;
  align-items: flex-end;
  gap: 20px;
  flex-wrap: wrap;
}

.adm-toggle-field {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  cursor: pointer;
}

/* ══════ Workspace ══════ */
.adm-workspace {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 20px;
  margin-top: 20px;
  align-items: start;
}

/* ══════ Sidebar ══════ */
.adm-sidebar { position: sticky; top: 20px; }

.adm-sidebar__head {
  display: flex;
  justify-content: space-between;
  align-items: start;
  margin-bottom: 14px;
}

.adm-sidebar__title {
  margin: 0;
  font: 700 18px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.adm-search-form {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  margin-bottom: 16px;
}

.adm-user-list {
  display: grid;
  gap: 8px;
  max-height: 60vh;
  overflow-y: auto;
}

.adm-user-card {
  width: 100%;
  padding: 14px 16px;
  text-align: left;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.5);
  border: 1.5px solid transparent;
  cursor: pointer;
  transition: border-color 180ms, background 180ms, transform 180ms;
}

.adm-user-card:hover {
  background: rgba(255, 255, 255, 0.8);
  transform: translateY(-1px);
}

.adm-user-card--active {
  border-color: var(--cabinet-whitelist);
  background: rgba(77, 143, 214, 0.06);
}

.adm-user-card__top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.adm-user-card__email {
  font: 600 14px/1.3 var(--font-ui);
  color: var(--cabinet-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.adm-user-card__meta {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--cabinet-muted);
}

.adm-user-card__meta-icon {
  font-size: 14px;
}

/* ══════ Main ══════ */
.adm-main { display: grid; gap: 20px; }

/* ══════ Actions Panel ══════ */
.adm-actions-panel__head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 20px;
}

.adm-actions-panel__icon {
  font-size: 28px;
  color: var(--cabinet-whitelist);
}

.adm-section-title {
  margin: 0;
  font: 700 clamp(18px, 2.5vw, 22px)/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.adm-action-group + .adm-action-group { margin-top: 20px; }

.adm-action-group__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.adm-action-group__icon {
  font-size: 20px;
  color: var(--cabinet-muted);
}

.adm-action-group__title {
  margin: 0;
  font: 700 15px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.adm-action-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.adm-action-card {
  display: grid;
  gap: 12px;
  align-content: start;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.1);
  transition: transform 180ms, box-shadow 180ms;
}

.adm-action-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(100, 120, 150, 0.06);
}

.adm-action-card--danger {
  background: rgba(214, 88, 88, 0.04);
  border-color: rgba(214, 88, 88, 0.12);
}

.adm-action-card__head {
  display: flex;
  gap: 12px;
}

.adm-action-card__icon {
  font-size: 22px;
  color: var(--cabinet-whitelist);
  flex-shrink: 0;
  margin-top: 2px;
}

.adm-action-card--danger .adm-action-card__icon {
  color: var(--cabinet-danger);
}

.adm-action-card__help {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--cabinet-muted);
  line-height: 1.45;
}

.adm-action-card__params {
  display: grid;
  gap: 10px;
}

/* ══════ Promo Panel ══════ */
.adm-promo-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.adm-promo-panel__head-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.adm-promo-panel__head-right {
  display: flex;
  gap: 8px;
}

.adm-promo-form {
  padding: 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.1);
  margin-bottom: 20px;
}

.adm-promo-form__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.adm-promo-list {
  display: grid;
  gap: 8px;
}

.adm-promo-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 18px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.08);
  transition: transform 180ms, box-shadow 180ms;
}

.adm-promo-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(100, 120, 150, 0.05);
}

.adm-promo-item--inactive {
  opacity: 0.6;
}

.adm-promo-item__main {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.adm-promo-item__info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.adm-promo-item__code {
  font: 700 15px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--cabinet-text);
}

.adm-promo-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 12px;
  color: var(--cabinet-muted);
}

/* ══════ Danger button ══════ */
.adm-btn--danger {
  overflow: hidden;
  border-color: rgba(214, 88, 88, 0.3);
  background: linear-gradient(135deg, #d65858, #c44444);
  box-shadow: 0 12px 32px rgba(214, 88, 88, 0.25);
  color: #fff;
}

.adm-btn--danger:hover {
  box-shadow: 0 16px 36px rgba(214, 88, 88, 0.32);
  background: linear-gradient(135deg, #e06565, #d05050);
}

/* ══════ User 360 ══════ */
.adm-user360__hero {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.adm-user360__badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ══════ Tabs ══════ */
.adm-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 16px;
  background: rgba(126, 170, 220, 0.06);
  margin-bottom: 20px;
  overflow-x: auto;
}

.adm-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-radius: 12px;
  border: none;
  background: transparent;
  color: var(--cabinet-muted);
  font: 600 13px/1.2 var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: background 180ms, color 180ms;
}

.adm-tab .material-symbols-outlined { font-size: 18px; }

.adm-tab:hover { background: rgba(255, 255, 255, 0.6); }

.adm-tab--active {
  background: rgba(255, 255, 255, 0.9);
  color: var(--cabinet-text);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.adm-tab-content { min-height: 200px; }

/* ══════ KV Grid / Cards ══════ */
.adm-kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.adm-kv-card {
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.08);
}

.adm-kv-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  font: 700 15px/1.2 var(--font-ui);
  color: var(--cabinet-text);
}

.adm-kv-card__title .material-symbols-outlined {
  font-size: 20px;
  color: var(--cabinet-whitelist);
}

.adm-kv {
  display: grid;
  gap: 8px;
}

.adm-kv div {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 8px;
  font-size: 13px;
}

.adm-kv dt {
  color: var(--cabinet-muted);
  font-weight: 600;
}

.adm-kv dd {
  margin: 0;
  word-break: break-all;
  color: var(--cabinet-text);
}

.adm-kv__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.adm-link-row {
  margin-top: 14px;
}

.adm-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* ══════ Playbooks ══════ */
.adm-playbooks { margin-top: 20px; }

.adm-playbook {
  padding: 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.08);
  margin-top: 10px;
}

.adm-playbook__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.adm-playbook__checks,
.adm-playbook__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

/* ══════ Timeline ══════ */
.adm-timeline { margin-top: 20px; }

.adm-timeline__items {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.adm-timeline__item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  font-size: 13px;
}

/* ══════ DLQ ══════ */
.adm-dlq { margin-top: 20px; }

.adm-dlq__item {
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(214, 88, 88, 0.04);
  border: 1px solid rgba(214, 88, 88, 0.1);
  margin-top: 8px;
}

/* ══════ Payments ══════ */
.adm-payment-list + .adm-payment-list { margin-top: 24px; }

.adm-table-wrap {
  overflow-x: auto;
  margin-top: 12px;
}

.adm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.adm-table th,
.adm-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(126, 170, 220, 0.1);
}

.adm-table th {
  color: var(--cabinet-muted);
  font: 700 11px/1.2 var(--font-ui);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* ══════ Audit ══════ */
.adm-audit-list {
  display: grid;
  gap: 10px;
}

.adm-audit-item {
  padding: 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(126, 170, 220, 0.08);
}

.adm-audit-item__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.adm-audit-item__info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.adm-audit-item__icon {
  font-size: 18px;
  color: var(--cabinet-muted);
}

.adm-audit-item__meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--cabinet-muted);
}

/* ══════ Locked ══════ */
.adm-locked {
  display: grid;
  place-items: center;
  gap: 12px;
  text-align: center;
  max-width: 480px;
  margin: 40px auto 0;
}

.adm-locked__icon {
  font-size: 48px;
  color: var(--cabinet-muted);
  opacity: 0.4;
}

/* ══════ Modal ══════ */
.adm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(30, 51, 82, 0.3);
  backdrop-filter: blur(10px);
}

.adm-modal {
  width: min(560px, 100%);
}

.adm-modal__title {
  margin: 0 0 10px;
  font: 700 20px/1.3 var(--font-ui);
  color: var(--cabinet-text);
}

.adm-modal__facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 16px 0;
}

.adm-modal__fact {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(126, 170, 220, 0.1);
}

.adm-modal__warn {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 16px;
  padding: 10px 14px;
  border-radius: 14px;
  background: rgba(245, 160, 78, 0.08);
  border: 1px solid rgba(245, 160, 78, 0.15);
  color: #964520;
  font-size: 13px;
}

.adm-modal__warn .material-symbols-outlined {
  font-size: 18px;
  flex-shrink: 0;
}

/* ══════ Responsive ══════ */
@media (max-width: 1200px) {
  .adm-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .adm-workspace { grid-template-columns: 1fr; }
  .adm-sidebar { position: static; }
}

@media (max-width: 768px) {
  .adm-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .adm-header { flex-direction: column; align-items: stretch; }
  .adm-header__right { flex-direction: column; }
  .adm-action-cards { grid-template-columns: 1fr; }
  .adm-kv-grid { grid-template-columns: 1fr; }
  .adm-kv div { grid-template-columns: 1fr; }
  .adm-modal__facts { grid-template-columns: 1fr; }
  .adm-user360__hero { flex-direction: column; }
}
</style>
