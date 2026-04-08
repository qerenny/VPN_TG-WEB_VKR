import { http } from './http'

export interface PublicLinkPreview {
  status: string
  purpose: string | null
  expires_at: string | null
}

export interface PublicLinkConsumeResult {
  status: string
  linked_user_id: number | null
}

export async function fetchPublicLinkPreview(token: string) {
  const response = await http.get<PublicLinkPreview>(`/public/link/telegram/${encodeURIComponent(token)}`)
  return response.data
}

export async function consumePublicLink(token: string) {
  const response = await http.post<PublicLinkConsumeResult>('/public/link/consume', { token })
  return response.data
}
