import type { WebCatalogPlan } from '../api/account'

export const ACCESS_TEMPLATE_LABELS: Record<string, string> = {
  month_1: '1 месяц · Базовая конфигурация',
  month_3: '3 месяца · Базовая конфигурация',
  month_6: '6 месяцев · Базовая конфигурация',
  year_1: '12 месяцев · Базовая конфигурация',
  traffic_limited_15gb: '15 GB · Лимит трафика',
  traffic_limited_35gb: '35 GB · Лимит трафика',
  traffic_limited_80gb: '80 GB · Лимит трафика',
}

export const REQUESTABLE_ACCESS_TEMPLATE_CODES = [
  'month_1',
  'month_3',
  'month_6',
  'year_1',
  'traffic_limited_15gb',
  'traffic_limited_35gb',
  'traffic_limited_80gb',
] as const

const PLAN_NAME_RU: Record<string, string> = {
  '1 month access': 'Доступ на 1 месяц',
  '3 months access': 'Доступ на 3 месяца',
  '6 months access': 'Доступ на 6 месяцев',
  '12 months access': 'Доступ на 12 месяцев',
  'Trial 3 days': 'Пробный период 3 дня',
  'News bonus 4 days': 'Бонус за канал 4 дня',
  'Traffic-limited trial 2 GB': 'Пробная конфигурация 2 ГБ',
  'Traffic-limited access 15 GB': 'Лимит трафика 15 ГБ',
  'Traffic-limited access 35 GB': 'Лимит трафика 35 ГБ',
  'Traffic-limited access 80 GB': 'Лимит трафика 80 ГБ',
}

export function localizePlanName(name: string) {
  return PLAN_NAME_RU[name] || name
}

export function formatAccessTemplateLabel(templateCode?: string | null) {
  const normalized = String(templateCode || '').trim().toLowerCase()
  if (!normalized) return 'Не указан'
  return ACCESS_TEMPLATE_LABELS[normalized] || normalized
}

export function buildAccessTemplateLabelFromPlan(plan: Pick<WebCatalogPlan, 'code' | 'name' | 'scope' | 'human_view_traffic_quota'>) {
  const normalizedCode = String(plan.code || '').trim().toLowerCase()
  if (ACCESS_TEMPLATE_LABELS[normalizedCode]) {
    return ACCESS_TEMPLATE_LABELS[normalizedCode]
  }
  if (String(plan.scope || '').trim().toLowerCase() === 'traffic_limited') {
    return `${plan.human_view_traffic_quota || localizePlanName(plan.name)} · Лимит трафика`
  }
  return `${localizePlanName(plan.name)} · Базовая конфигурация`
}

export function buildAccessTemplateOptions(options?: {
  standardEnabled?: boolean
  trafficLimitedEnabled?: boolean
}) {
  const standardEnabled = options?.standardEnabled ?? true
  const trafficLimitedEnabled = options?.trafficLimitedEnabled ?? true
  const items: Array<{ code: string; label: string }> = []
  if (standardEnabled) {
    items.push(
      { code: 'month_1', label: ACCESS_TEMPLATE_LABELS.month_1 },
      { code: 'month_3', label: ACCESS_TEMPLATE_LABELS.month_3 },
      { code: 'month_6', label: ACCESS_TEMPLATE_LABELS.month_6 },
      { code: 'year_1', label: ACCESS_TEMPLATE_LABELS.year_1 },
    )
  }
  if (trafficLimitedEnabled) {
    items.push(
      { code: 'traffic_limited_15gb', label: ACCESS_TEMPLATE_LABELS.traffic_limited_15gb },
      { code: 'traffic_limited_35gb', label: ACCESS_TEMPLATE_LABELS.traffic_limited_35gb },
      { code: 'traffic_limited_80gb', label: ACCESS_TEMPLATE_LABELS.traffic_limited_80gb },
    )
  }
  return items
}
