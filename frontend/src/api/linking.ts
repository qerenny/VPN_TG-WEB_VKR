import { getData, postData, http } from './http'

export interface PublicLinkPreview {
  status: string
  purpose: string | null
  expires_at: string | null
}

interface PublicLinkConsumeResult {
  status: string
  linked_user_id: number | null
}

export async function fetchPublicLinkPreview(token: string) {
  return getData<PublicLinkPreview>(http, `/public/link/telegram/${encodeURIComponent(token)}`)
}

export async function consumePublicLink(token: string) {
  return postData<PublicLinkConsumeResult, { token: string }>(http, '/public/link/consume', { token })
}
