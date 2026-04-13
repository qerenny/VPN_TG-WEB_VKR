import { API_BASE_URL } from './base'
import { createHttpClient, deleteData, getData, getItems, patchData, postData, postItems } from './http'
import type { AccessRequestItem, FeatureFlags } from './types'

export interface AdminActionPayload {
  action_type: string
  target_user_id?: number | null
  target_tg_id?: number | null
  reason?: string
  dry_run?: boolean
  params?: Record<string, unknown>
}

export interface AdminFeatureFlags extends FeatureFlags {}

export interface AdminOverview {
  actor?: string
  role?: string
  stats?: Record<string, number>
  queues?: Record<string, unknown>
  cache?: Record<string, unknown>
  features?: Partial<AdminFeatureFlags>
  sources?: Record<string, string>
}

export interface AdminAccessRequestItem extends AccessRequestItem {}

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

const adminApi = createHttpClient(`${API_BASE_URL}/admin`)

export async function loginAdmin(token: string, actor?: string) {
  return postData(adminApi, '/session/login', {
    token,
    actor: actor || 'web-admin',
  })
}

export async function logoutAdmin() {
  await postData(adminApi, '/session/logout')
}

export async function fetchAdminOverview() {
  return getData<AdminOverview>(adminApi, '/overview')
}

export async function searchAdminUsers(query?: string) {
  return getItems(adminApi, '/users', {
    params: {
      q: query || undefined,
    },
  })
}

export async function fetchAdminUser(userId: number) {
  return getData(adminApi, `/users/${userId}`)
}

export async function fetchAdminAudit(targetTgId?: number) {
  return getItems(adminApi, '/audit', {
    params: {
      target_tg_id: targetTgId || undefined,
    },
  })
}

export async function runAdminAction(payload: AdminActionPayload) {
  return postData(adminApi, '/actions', payload)
}

export async function fetchAdminAccessRequests(status?: string, limit = 100) {
  return getItems<AdminAccessRequestItem>(adminApi, '/access-requests', {
    params: {
      status: status || undefined,
      limit,
    },
  })
}

export async function reviewAdminAccessRequest(
  requestId: number,
  payload: { decision: 'approve' | 'reject'; review_note?: string | null; template_code?: string | null },
) {
  return postData<AdminAccessRequestItem, typeof payload>(adminApi, `/access-requests/${requestId}/review`, payload)
}

export async function fetchAdminAccessRegistry(limit = 200) {
  return getItems<AdminAccessRegistryItem>(adminApi, '/access-registry', {
    params: { limit },
  })
}

export async function upsertAdminAccessRegistry(payload: {
  identity_type: string
  identity_value: string
  auto_approve?: boolean
  allow_auto_renew?: boolean
  is_active?: boolean
  note?: string | null
}) {
  return postData<AdminAccessRegistryItem, typeof payload>(adminApi, '/access-registry', payload)
}

export async function updateAdminAccessRegistry(entryId: number, payload: {
  identity_type: string
  identity_value: string
  auto_approve?: boolean
  allow_auto_renew?: boolean
  is_active?: boolean
  note?: string | null
}) {
  return patchData<AdminAccessRegistryItem, typeof payload>(adminApi, `/access-registry/${entryId}`, payload)
}

export async function batchUpsertAdminAccessRegistry(payload: {
  identities_text: string
  auto_approve?: boolean
  allow_auto_renew?: boolean
  is_active?: boolean
  note?: string | null
}) {
  return postItems<AdminAccessRegistryItem, typeof payload>(adminApi, '/access-registry/batch', payload)
}

export async function disableAndRevokeAdminAccessRegistry(entryId: number) {
  return postData<{
    entry: AdminAccessRegistryItem
    matched_users: number
    revoked_grants: number
    runtime_revocations: number
  }>(adminApi, `/access-registry/${entryId}/disable-and-revoke`)
}

export async function deleteAdminAccessRegistry(entryId: number) {
  return deleteData<{ status: string }>(adminApi, `/access-registry/${entryId}`)
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
  return getItems<AdminPromoCode>(adminApi, '/promos', { params: { limit } })
}

export async function createAdminPromo(payload: AdminPromoCreatePayload) {
  return postData<AdminPromoCode, AdminPromoCreatePayload>(adminApi, '/promos', payload)
}

export async function toggleAdminPromo(promoId: number, isActive: boolean) {
  return patchData(adminApi, `/promos/${promoId}`, { is_active: isActive })
}
