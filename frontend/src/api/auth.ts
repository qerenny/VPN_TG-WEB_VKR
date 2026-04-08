import { http } from './http'

export interface WebMe {
  user_id: number
  email: string | null
  email_verified: boolean
  telegram_linked: boolean
  telegram_id: number | null
  telegram_username: string | null
  display_name: string | null
  timezone: string | null
  locale: string | null
  marketing_opt_in: boolean
  preferred_contact_email: string | null
  created_at: string
  last_login_at: string | null
}

export interface WebLoginPayload {
  email: string
  password: string
  device_name?: string | null
}

export interface WebRegisterVerifyPayload {
  email: string
  code: string
  password: string
  device_name?: string | null
}

export interface WebPasswordResetPayload {
  email: string
  code: string
  new_password: string
}

export interface WebPublicLinkLoginPayload {
  token: string
  device_name?: string | null
}

export interface WebRegistrationStartResult {
  status: string
  verification_required: boolean
}

export async function fetchWebMe() {
  const response = await http.get<WebMe>('/me')
  return response.data
}

export async function loginWeb(payload: WebLoginPayload) {
  await http.post('/auth/login', payload)
}

export async function loginViaTelegramLink(payload: WebPublicLinkLoginPayload) {
  await http.post('/auth/link/telegram/login', payload)
}

export async function logoutWeb() {
  await http.post('/auth/logout')
}

export async function startWebRegistration(email: string) {
  const response = await http.post<WebRegistrationStartResult>('/auth/register/start', { email })
  return response.data
}

export async function resendWebRegistration(email: string) {
  const response = await http.post<WebRegistrationStartResult>('/auth/register/resend', { email })
  return response.data
}

export async function verifyWebRegistration(payload: WebRegisterVerifyPayload) {
  await http.post('/auth/register/verify', payload)
}

export async function startPasswordReset(email: string) {
  await http.post('/auth/password/forgot', { email })
}

export async function resetPassword(payload: WebPasswordResetPayload) {
  await http.post('/auth/password/reset', payload)
}
