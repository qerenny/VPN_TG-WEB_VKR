import { getData, getItems, patchData, postData, http } from './http'
import type { AccessRequestItem, UserProfileFields } from './types'

export interface WebProfile extends UserProfileFields {
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

export interface WebAccessRequestItem extends AccessRequestItem {}

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
  return getData<WebReferralStats>(http, '/me/referrals')
}

export async function fetchProfile() {
  return getData<WebProfile>(http, '/me/profile')
}

export async function updateProfile(payload: Partial<WebProfile>) {
  return patchData<WebProfile, Partial<WebProfile>>(http, '/me/profile', payload)
}

export async function fetchLinks() {
  return getData<WebLinks>(http, '/me/links')
}

export async function fetchSubscriptions() {
  return getData<WebSubscriptions>(http, '/me/subscriptions')
}

export async function fetchPayments() {
  return getItems<WebPaymentItem>(http, '/me/payments')
}

export async function fetchPlanCatalog() {
  return getData<WebPlanCatalog>(http, '/me/plans')
}

export async function fetchAccessRequests() {
  return getItems<WebAccessRequestItem>(http, '/me/access-requests')
}

export async function createAccessRequest(payload: { template_code?: string | null; request_kind?: string | null; comment?: string | null }) {
  return postData<WebAccessRequestItem, typeof payload>(http, '/me/access-requests', payload)
}

export async function repeatAccessRequest(requestId: number) {
  return postData<WebAccessRequestItem>(http, `/me/access-requests/${requestId}/repeat`)
}

export async function fetchAccessGrants() {
  return getItems<WebAccessGrantItem>(http, '/me/access-grants')
}

export async function startTelegramLink() {
  return postData<TelegramLinkStartResult>(http, '/me/links/telegram/start')
}

export async function createStandardCheckout(planCode: string, method = 'external_card') {
  return postData<{ checkout_url: string }, { plan_code: string; method: string }>(http, '/me/payments/checkout', {
    plan_code: planCode,
    method,
  })
}

export async function createTrafficLimitedCheckout(planCode: string, method = 'external_card') {
  return postData<{ checkout_url: string }, { plan_code: string; method: string }>(http, '/me/payments/checkout/traffic-limited', {
    plan_code: planCode,
    method,
  })
}

export interface WebPromoApplyResult {
  status: string
  granted_days: number
  message: string
}

export async function applyPromoCode(code: string) {
  return postData<WebPromoApplyResult, { code: string }>(http, '/me/promo/apply', { code })
}
