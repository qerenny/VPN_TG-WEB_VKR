type LabelMap = Record<string, string>

function normalizeAccessValue(value?: string | null) {
  return String(value || '').trim().toLowerCase()
}

function lookupAccessValue(value: string | null | undefined, labels: LabelMap, fallback = '—') {
  const normalized = normalizeAccessValue(value)
  return labels[normalized] || normalized || fallback
}

function lookupMappedValue(value: string | null | undefined, labels: LabelMap, fallback = '') {
  const normalized = normalizeAccessValue(value)
  return labels[normalized] || fallback
}

const ACCESS_GRANT_SOURCE_LABELS: LabelMap = {
  payment: 'Оплата',
  request_approval: 'Заявка',
  access_registry: 'Реестр',
  access_registry_auto_renew: 'Автопродление',
  admin_override: 'Администратор',
}

const ACCESS_GRANT_SOURCE_ICONS: LabelMap = {
  payment: 'credit_card',
  request_approval: 'approval',
  access_registry: 'badge',
  access_registry_auto_renew: 'autorenew',
  admin_override: 'admin_panel_settings',
}

const ACCESS_GRANT_STATUS_LABELS: LabelMap = {
  active: 'Активен',
  expired: 'Истёк',
  revoked: 'Отозван',
}

const ACCESS_GRANT_STATUS_BADGE_CLASSES: LabelMap = {
  active: 'cabinet-badge--ok',
  expired: 'cabinet-badge--muted',
  revoked: 'cabinet-badge--muted',
}

const ACCESS_REQUEST_STATUS_LABELS: LabelMap = {
  pending: 'На рассмотрении',
  approved: 'Одобрена',
  rejected: 'Отклонена',
  expired: 'Истекла',
}

const ACCESS_REQUEST_STATUS_BADGE_CLASSES: LabelMap = {
  approved: 'cabinet-badge--ok',
  rejected: 'cabinet-badge--danger',
}

const PAYMENT_STATUS_LABELS: LabelMap = {
  paid: 'Оплачено',
  pending: 'Ожидает',
  canceled: 'Отменено',
  cancelled: 'Отменено',
  failed: 'Ошибка',
}

const PAYMENT_STATUS_BADGE_CLASSES: LabelMap = {
  paid: 'cabinet-badge--ok',
  succeeded: 'cabinet-badge--ok',
  fulfilled: 'cabinet-badge--ok',
  pending: 'cabinet-badge--warm',
  canceled: 'cabinet-badge--danger',
  cancelled: 'cabinet-badge--danger',
  failed: 'cabinet-badge--danger',
  expired: 'cabinet-badge--danger',
}

const PAYMENT_STATUS_ROW_CLASSES: LabelMap = {
  paid: 'payment-row--paid',
  pending: 'payment-row--pending',
  failed: 'payment-row--failed',
  canceled: 'payment-row--canceled',
  cancelled: 'payment-row--canceled',
}

export function formatAccessGrantSourceLabel(sourceType?: string | null) {
  return lookupAccessValue(sourceType, ACCESS_GRANT_SOURCE_LABELS)
}

export function formatAccessGrantSourceIcon(sourceType?: string | null) {
  return lookupMappedValue(sourceType, ACCESS_GRANT_SOURCE_ICONS, 'vpn_key')
}

export function formatAccessScopeLabel(scope?: string | null) {
  return normalizeAccessValue(scope) === 'traffic_limited'
    ? 'Доступ с лимитом трафика'
    : 'Базовая'
}

export function formatAccessGrantStatusLabel(status?: string | null) {
  return lookupAccessValue(status, ACCESS_GRANT_STATUS_LABELS)
}

export function formatAccessGrantStatusBadgeClass(status?: string | null) {
  return lookupMappedValue(status, ACCESS_GRANT_STATUS_BADGE_CLASSES, 'cabinet-badge--muted')
}

export function formatAccessRequestStatusLabel(status?: string | null) {
  return lookupAccessValue(status, ACCESS_REQUEST_STATUS_LABELS)
}

export function formatAccessRequestStatusBadgeClass(status?: string | null) {
  return lookupMappedValue(status, ACCESS_REQUEST_STATUS_BADGE_CLASSES, 'cabinet-badge--warm')
}

export function formatAccessRequestKindLabel(
  value?: string | null,
  options: { includeAccessNoun?: boolean } = {},
) {
  const normalized = normalizeAccessValue(value)
  const includeAccessNoun = options.includeAccessNoun ?? false
  if (normalized === 'renewal') {
    return includeAccessNoun ? 'Продление доступа' : 'Продление'
  }
  return 'Новый доступ'
}

export function formatPaymentStatusLabel(status?: string | null) {
  return lookupAccessValue(status, PAYMENT_STATUS_LABELS)
}

export function formatPaymentStatusBadgeClass(
  status?: string | null,
  options: { fallback?: string; canceledClass?: string } = {},
) {
  const normalized = normalizeAccessValue(status)
  if ((normalized === 'canceled' || normalized === 'cancelled') && options.canceledClass) {
    return options.canceledClass
  }
  return lookupMappedValue(status, PAYMENT_STATUS_BADGE_CLASSES, options.fallback ?? 'cabinet-badge--muted')
}

export function formatPaymentStatusRowClass(status?: string | null) {
  return lookupMappedValue(status, PAYMENT_STATUS_ROW_CLASSES)
}
