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
  traffic_limited: {
    scope: 'traffic_limited'
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
  access_policy?: {
    registry_managed: boolean
    registry_template_code: string | null
    registry_template_label: string | null
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
  traffic_limited: WebCatalogPlan[]
}

export interface WebAccessRequestItem {
  id: number
  user_id: number
  requested_template_code: string | null
  requested_template_label?: string | null
  approved_template_label?: string | null
  access_grant_id: number | null
  channel: string
  request_kind: string
  status: string
  comment: string | null
  review_note: string | null
  reviewed_by_actor: string | null
  requested_at: string
  reviewed_at: string | null
  expires_at: string | null
  metadata: Record<string, unknown>
}

export interface WebAccessGrantItem {
  id: number
  template_code: string
  template_label?: string
  scope: string
  entitlement_kind: string
  source_type: string
  source_ref: string | null
  status: string
  expires_at: string | null
  quota_bytes: number | null
  granted_by_user_id: number | null
  created_at: string
  activated_at: string | null
  revoked_at: string | null
  metadata: Record<string, unknown>
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

export async function fetchAccessRequests() {
  const response = await http.get<{ items: WebAccessRequestItem[] }>('/me/access-requests')
  return response.data.items
}

export async function createAccessRequest(payload: { template_code?: string | null; request_kind?: string | null; comment?: string | null }) {
  const response = await http.post<WebAccessRequestItem>('/me/access-requests', payload)
  return response.data
}

export async function repeatAccessRequest(requestId: number) {
  const response = await http.post<WebAccessRequestItem>(`/me/access-requests/${requestId}/repeat`)
  return response.data
}

export async function fetchAccessGrants() {
  const response = await http.get<{ items: WebAccessGrantItem[] }>('/me/access-grants')
  return response.data.items
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

export async function createTrafficLimitedCheckout(planCode: string, method = 'external_card') {
  const response = await http.post('/me/payments/checkout/traffic-limited', {
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
