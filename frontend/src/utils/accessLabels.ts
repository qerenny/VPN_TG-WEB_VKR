export function formatAccessGrantSourceLabel(sourceType?: string | null) {
  const normalized = String(sourceType || '').trim().toLowerCase()
  if (normalized === 'payment') return 'Оплата'
  if (normalized === 'request_approval') return 'Заявка'
  if (normalized === 'access_registry') return 'Реестр'
  if (normalized === 'access_registry_auto_renew') return 'Автопродление'
  if (normalized === 'admin_override') return 'Администратор'
  return normalized || '—'
}

export function formatAccessScopeLabel(scope?: string | null) {
  return String(scope || '').trim().toLowerCase() === 'traffic_limited'
    ? 'Доступ с лимитом трафика'
    : 'Базовая'
}

export function formatAccessGrantStatusLabel(status?: string | null) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'active') return 'Активен'
  if (normalized === 'expired') return 'Истёк'
  if (normalized === 'revoked') return 'Отозван'
  return normalized || '—'
}

export function formatAccessRequestStatusLabel(status?: string | null) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'pending') return 'На рассмотрении'
  if (normalized === 'approved') return 'Одобрена'
  if (normalized === 'rejected') return 'Отклонена'
  if (normalized === 'expired') return 'Истекла'
  return normalized || '—'
}

export function formatAccessRequestStatusBadgeClass(status?: string | null) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'approved') return 'cabinet-badge--ok'
  if (normalized === 'rejected') return 'cabinet-badge--danger'
  return 'cabinet-badge--warm'
}

export function formatAccessRequestKindLabel(
  value?: string | null,
  options: { includeAccessNoun?: boolean } = {},
) {
  const normalized = String(value || '').trim().toLowerCase()
  const includeAccessNoun = options.includeAccessNoun ?? false
  if (normalized === 'renewal') {
    return includeAccessNoun ? 'Продление доступа' : 'Продление'
  }
  return 'Новый доступ'
}
