import { http } from './http'

export interface WebProfile {
  display_name: string | null
  timezone: string | null
  locale: string | null
  marketing_opt_in: boolean
  preferred_contact_email: string | null
  auth_email: string | null
  email_verified: boolean
}

export interface WebLinks {
  web: {
    linked: boolean
    email: string | null
    email_verified: boolean
    linked_at: string | null
    last_login_at: string | null
  }
  telegram: {
    linked: boolean
    telegram_id: number | null
    username: string | null
    linked_at: string | null
    first_seen_at: string | null
    last_seen_at: string | null
  }
}

export interface WebSubscriptions {
  standard: {
    scope: 'standard'
    is_active: boolean
    expires_at: string | null
    human_view_expiration_remaining: string | null
    subscription_import_url: string | null
    external_email: string | null
    subscription_external_id: string | null
  }
  whitelist: {
    scope: 'whitelist'
    is_active: boolean
    expires_at: string | null
    human_view_expiration_remaining: string | null
    subscription_import_url: string | null
    external_email: string | null
    subscription_external_id: string | null
    traffic_allocated_bytes: number | null
    traffic_used_bytes: number | null
    traffic_remaining_bytes: number | null
    human_view_traffic_allocated: string | null
    human_view_traffic_used: string | null
    human_view_traffic_remaining: string | null
  }
}

export interface WebPaymentItem {
  order_id: number
  plan_code: string
  plan_name: string
  scope: string
  entitlement_kind: string
  status: string
  runtime_status: string
  amount: string
  currency: string
  provider: string | null
  provider_payment_id: string | null
  provider_status: string | null
  created_at: string | null
  paid_at: string | null
  fulfilled_at: string | null
}

export interface WebCatalogPlan {
  code: string
  name: string
  scope: string
  entitlement_kind: string
  duration_days: number
  quota_bytes: number | null
  price_amount: string
  currency: string
  human_view_traffic_quota: string | null
}

export interface WebPlanCatalog {
  standard: WebCatalogPlan[]
  whitelist: WebCatalogPlan[]
}

export interface TelegramLinkStartResult {
  status: string
  deep_link: string | null
  expires_at: string | null
  telegram_id: number | null
  telegram_username: string | null
}

export interface WebReferralStats {
  invited_count: number
  paid_count: number
  pending_days: number
  referral_link: string | null
  telegram_linked: boolean
}

export async function fetchReferralStats() {
  const response = await http.get<WebReferralStats>('/me/referrals')
  return response.data
}

export async function fetchProfile() {
  const response = await http.get<WebProfile>('/me/profile')
  return response.data
}

export async function updateProfile(payload: Partial<WebProfile>) {
  const response = await http.patch<WebProfile>('/me/profile', payload)
  return response.data
}

export async function fetchLinks() {
  const response = await http.get<WebLinks>('/me/links')
  return response.data
}

export async function fetchSubscriptions() {
  const response = await http.get<WebSubscriptions>('/me/subscriptions')
  return response.data
}

export async function fetchPayments() {
  const response = await http.get<{ items: WebPaymentItem[] }>('/me/payments')
  return response.data.items
}

export async function fetchPlanCatalog() {
  const response = await http.get<WebPlanCatalog>('/me/plans')
  return response.data
}

export async function startTelegramLink() {
  const response = await http.post<TelegramLinkStartResult>('/me/links/telegram/start')
  return response.data
}

export async function createStandardCheckout(planCode: string, method = 'external_card') {
  const response = await http.post('/me/payments/checkout', {
    plan_code: planCode,
    method,
  })
  return response.data as { checkout_url: string }
}

export async function createWhitelistCheckout(planCode: string, method = 'external_card') {
  const response = await http.post('/me/payments/checkout/whitelist', {
    plan_code: planCode,
    method,
  })
  return response.data as { checkout_url: string }
}

export interface WebPromoApplyResult {
  status: string
  granted_days: number
  message: string
}

export async function applyPromoCode(code: string) {
  const response = await http.post<WebPromoApplyResult>('/me/promo/apply', { code })
  return response.data
}
