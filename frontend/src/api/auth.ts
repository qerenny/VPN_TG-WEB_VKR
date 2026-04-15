import { getData, postData, http } from './http'
import type { UserProfileFields } from './types'

export interface WebMe extends UserProfileFields {
  user_id: number
  email: string | null
  email_verified: boolean
  telegram_linked: boolean
  telegram_id: number | null
  telegram_username: string | null
  created_at: string
  last_login_at: string | null
}

interface WebLoginPayload {
  email: string
  password: string
  device_name?: string | null
}

interface WebRegisterVerifyPayload {
  email: string
  code: string
  password: string
  device_name?: string | null
}

interface WebPasswordResetPayload {
  email: string
  code: string
  new_password: string
}

interface WebPublicLinkLoginPayload {
  token: string
  device_name?: string | null
}

interface WebRegistrationStartResult {
  status: string
  verification_required: boolean
}

export async function fetchWebMe() {
  return getData<WebMe>(http, '/me')
}

export async function loginWeb(payload: WebLoginPayload) {
  await postData(http, '/auth/login', payload)
}

export async function loginViaTelegramLink(payload: WebPublicLinkLoginPayload) {
  await postData(http, '/auth/link/telegram/login', payload)
}

export async function logoutWeb() {
  await postData(http, '/auth/logout')
}

export async function startWebRegistration(email: string) {
  return postData<WebRegistrationStartResult, { email: string }>(http, '/auth/register/start', { email })
}

export async function resendWebRegistration(email: string) {
  return postData<WebRegistrationStartResult, { email: string }>(http, '/auth/register/resend', { email })
}

export async function verifyWebRegistration(payload: WebRegisterVerifyPayload) {
  await postData(http, '/auth/register/verify', payload)
}

export async function startPasswordReset(email: string) {
  await postData(http, '/auth/password/forgot', { email })
}

export async function resetPassword(payload: WebPasswordResetPayload) {
  await postData(http, '/auth/password/reset', payload)
}
