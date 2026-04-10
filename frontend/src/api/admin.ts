import axios from 'axios'

import { API_BASE_URL } from './base'

export interface AdminActionPayload {
  action_type: string
  target_user_id?: number | null
  target_tg_id?: number | null
  reason?: string
  dry_run?: boolean
  params?: Record<string, unknown>
}

export interface AdminFeatureFlags {
  access_requests_enabled: boolean
  access_registry_enabled: boolean
  access_admin_override_enabled: boolean
  commerce_enabled: boolean
  referrals_enabled: boolean
  promos_enabled: boolean
  web_purchase_enabled: boolean
  telegram_bot_enabled: boolean
  mail_enabled: boolean
  standard_config_enabled: boolean
  traffic_limited_config_enabled: boolean
}

export interface AdminOverview {
  actor?: string
  role?: string
  stats?: Record<string, number>
  queues?: Record<string, unknown>
  cache?: Record<string, unknown>
  features?: Partial<AdminFeatureFlags>
  sources?: Record<string, string>
}

export interface AdminAccessRequestItem {
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

export interface AdminAccessRegistryItem {
  id: number
  identity_type: string
  identity_value: string
  template_code: string
  template_label?: string
  auto_approve: boolean
  allow_auto_renew: boolean
  is_active: boolean
  note: string | null
  created_by_actor: string | null
  updated_by_actor: string | null
  created_at: string
  updated_at: string
  matched_users_count: number
  issued_users_count: number
  access_issued: boolean
  issuance_status_label: string
  metadata: Record<string, unknown>
}

const adminApi = axios.create({
  baseURL: `${API_BASE_URL}/admin`,
  withCredentials: true,
})

export async function loginAdmin(token: string, actor?: string) {
  const response = await adminApi.post('/session/login', {
    token,
    actor: actor || 'web-admin',
  })
  return response.data
}

export async function logoutAdmin() {
  await adminApi.post('/session/logout')
}

export async function fetchAdminOverview() {
  const response = await adminApi.get('/overview')
  return response.data as AdminOverview
}

export async function searchAdminUsers(query?: string) {
  const response = await adminApi.get('/users', {
    params: {
      q: query || undefined,
    },
  })
  return response.data.items
}

export async function fetchAdminUser(userId: number) {
  const response = await adminApi.get(`/users/${userId}`)
  return response.data
}

export async function fetchAdminAudit(targetTgId?: number) {
  const response = await adminApi.get('/audit', {
    params: {
      target_tg_id: targetTgId || undefined,
    },
  })
  return response.data.items
}

export async function runAdminAction(payload: AdminActionPayload) {
  const response = await adminApi.post('/actions', payload)
  return response.data
}

export async function fetchAdminAccessRequests(status?: string, limit = 100) {
  const response = await adminApi.get('/access-requests', {
    params: {
      status: status || undefined,
      limit,
    },
  })
  return response.data.items as AdminAccessRequestItem[]
}

export async function reviewAdminAccessRequest(
  requestId: number,
  payload: { decision: 'approve' | 'reject'; review_note?: string | null; template_code?: string | null },
) {
  const response = await adminApi.post(`/access-requests/${requestId}/review`, payload)
  return response.data as AdminAccessRequestItem
}

export async function fetchAdminAccessRegistry(limit = 200) {
  const response = await adminApi.get('/access-registry', {
    params: { limit },
  })
  return response.data.items as AdminAccessRegistryItem[]
}

export async function upsertAdminAccessRegistry(payload: {
  identity_type: string
  identity_value: string
  auto_approve?: boolean
  allow_auto_renew?: boolean
  is_active?: boolean
  note?: string | null
}) {
  const response = await adminApi.post('/access-registry', payload)
  return response.data as AdminAccessRegistryItem
}

export async function updateAdminAccessRegistry(entryId: number, payload: {
  identity_type: string
  identity_value: string
  auto_approve?: boolean
  allow_auto_renew?: boolean
  is_active?: boolean
  note?: string | null
}) {
  const response = await adminApi.patch(`/access-registry/${entryId}`, payload)
  return response.data as AdminAccessRegistryItem
}

export async function toggleAdminAccessRegistry(entryId: number, is_active: boolean, entry?: Partial<AdminAccessRegistryItem>) {
  return updateAdminAccessRegistry(entryId, {
    identity_type: String(entry?.identity_type || ''),
    identity_value: String(entry?.identity_value || ''),
    auto_approve: Boolean(entry?.auto_approve),
    allow_auto_renew: Boolean(entry?.allow_auto_renew),
    is_active,
    note: entry?.note || undefined,
  })
}

export async function batchUpsertAdminAccessRegistry(payload: {
  identities_text: string
  auto_approve?: boolean
  allow_auto_renew?: boolean
  is_active?: boolean
  note?: string | null
}) {
  const response = await adminApi.post('/access-registry/batch', payload)
  return response.data.items as AdminAccessRegistryItem[]
}

export async function disableAndRevokeAdminAccessRegistry(entryId: number) {
  const response = await adminApi.post(`/access-registry/${entryId}/disable-and-revoke`)
  return response.data as {
    entry: AdminAccessRegistryItem
    matched_users: number
    revoked_grants: number
    runtime_revocations: number
  }
}

export async function deleteAdminAccessRegistry(entryId: number) {
  const response = await adminApi.delete(`/access-registry/${entryId}`)
  return response.data as { status: string }
}

export interface AdminPromoCode {
  id: number
  code: string
  plan_id: number | null
  plan_name: string | null
  duration_days_override: number | null
  max_redemptions: number | null
  per_user_limit: number
  redemptions_count: number
  valid_from: string | null
  valid_until: string | null
  is_active: boolean
  created_at: string | null
}

export interface AdminPromoCreatePayload {
  code: string
  plan_id?: number | null
  duration_days_override?: number | null
  max_redemptions?: number | null
  per_user_limit?: number
  valid_from?: string | null
  valid_until?: string | null
}

export async function fetchAdminPromos(limit = 100) {
  const response = await adminApi.get('/promos', { params: { limit } })
  return response.data.items as AdminPromoCode[]
}

export async function createAdminPromo(payload: AdminPromoCreatePayload) {
  const response = await adminApi.post('/promos', payload)
  return response.data as AdminPromoCode
}

export async function toggleAdminPromo(promoId: number, isActive: boolean) {
  const response = await adminApi.patch(`/promos/${promoId}`, { is_active: isActive })
  return response.data
}
