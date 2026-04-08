import axios from 'axios'

import { API_BASE_URL } from './base'

export const http = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
})
