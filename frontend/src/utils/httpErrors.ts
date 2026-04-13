import axios from 'axios'

export function getAxiosErrorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) {
    return fallback
  }

  const detail = error.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

export function isAxiosStatus(error: unknown, status: number) {
  return axios.isAxiosError(error) && error.response?.status === status
}
