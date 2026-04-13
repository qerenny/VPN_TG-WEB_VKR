import { API_BASE_URL } from './base'
import { getUrlData } from './http'
import { createSingleFlightByKey } from './requestCache'

const runUserInfoRequest = createSingleFlightByKey<string, unknown>()

export async function fetchUserInfo(token: string, scope: 'standard' | 'traffic_limited' = 'standard') {
  const requestKey = `${scope}:${token}`
  const path =
    scope === 'traffic_limited' ? `/subscription/traffic-limited/${token}` : `/subscription/${token}`

  return runUserInfoRequest(requestKey, async () => {
    return getUrlData<unknown>(`${API_BASE_URL}${path}`)
  })
}
