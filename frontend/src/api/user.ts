import axios from 'axios'

import { API_BASE_URL } from './base'

const inflightRequests = new Map<string, Promise<unknown>>()

export async function fetchUserInfo(token: string, scope: 'standard' | 'whitelist' = 'standard') {
  const requestKey = `${scope}:${token}`
  const existingRequest = inflightRequests.get(requestKey)
  if (existingRequest) {
    return existingRequest
  }

  const path =
    scope === 'whitelist' ? `/subscription/whitelist/${token}` : `/subscription/${token}`
  const request = axios
    .get(`${API_BASE_URL}${path}`)
    .then((res) => res.data)
    .catch((error: unknown) => {
      if (axios.isAxiosError(error)) {
        throw error
      }
      throw new Error('Unexpected error')
    })
    .finally(() => {
      inflightRequests.delete(requestKey)
    })

  inflightRequests.set(requestKey, request)

  return await request
}
