import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

import { API_BASE_URL } from './base'

interface CollectionResponse<T> {
  items: T[]
}

export function createHttpClient(baseURL = API_BASE_URL) {
  return axios.create({
    baseURL,
    withCredentials: true,
  })
}

export const http = createHttpClient()

export async function getData<T>(client: AxiosInstance, path: string, config?: AxiosRequestConfig) {
  const response = await client.get<T>(path, config)
  return response.data
}

export async function getItems<T>(client: AxiosInstance, path: string, config?: AxiosRequestConfig) {
  const response = await client.get<CollectionResponse<T>>(path, config)
  return response.data.items
}

export async function postItems<TItem, TPayload = undefined>(
  client: AxiosInstance,
  path: string,
  payload?: TPayload,
  config?: AxiosRequestConfig,
) {
  const response = await client.post<CollectionResponse<TItem>>(path, payload, config)
  return response.data.items
}

export async function postData<TResponse, TPayload = undefined>(
  client: AxiosInstance,
  path: string,
  payload?: TPayload,
  config?: AxiosRequestConfig,
) {
  const response = await client.post<TResponse>(path, payload, config)
  return response.data
}

export async function patchData<TResponse, TPayload>(
  client: AxiosInstance,
  path: string,
  payload: TPayload,
  config?: AxiosRequestConfig,
) {
  const response = await client.patch<TResponse>(path, payload, config)
  return response.data
}

export async function deleteData<TResponse>(client: AxiosInstance, path: string, config?: AxiosRequestConfig) {
  const response = await client.delete<TResponse>(path, config)
  return response.data
}

export async function getUrlData<T>(url: string, config?: AxiosRequestConfig) {
  const response = await axios.get<T>(url, config)
  return response.data
}
