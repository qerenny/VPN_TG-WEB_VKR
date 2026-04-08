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
  return response.data
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
