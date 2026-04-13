import { reactive } from 'vue'

import { fetchWebMe, logoutWeb, type WebMe } from '../api/auth'
import { isAxiosStatus } from '../utils/httpErrors'

interface SessionState {
  me: WebMe | null
  initialized: boolean
  loading: boolean
}

const sessionState = reactive<SessionState>({
  me: null,
  initialized: false,
  loading: false,
})

let inflightRequest: Promise<WebMe | null> | null = null

export function useSessionState() {
  return sessionState
}

export async function ensureSession(force = false) {
  if (!force && sessionState.initialized) {
    return sessionState.me
  }

  if (!force && inflightRequest) {
    return inflightRequest
  }

  sessionState.loading = true
  inflightRequest = fetchWebMe()
    .then((me) => {
      sessionState.me = me
      sessionState.initialized = true
      return me
    })
    .catch((error: unknown) => {
      if (isAxiosStatus(error, 401)) {
        sessionState.me = null
        sessionState.initialized = true
        return null
      }
      throw error
    })
    .finally(() => {
      sessionState.loading = false
      inflightRequest = null
    })

  return inflightRequest
}

export async function refreshSession() {
  return await ensureSession(true)
}

export async function clearSession() {
  try {
    await logoutWeb()
  } finally {
    sessionState.me = null
    sessionState.initialized = true
  }
}
