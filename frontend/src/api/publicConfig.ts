import axios from 'axios'

import { API_BASE_URL } from './base'

export interface FrontendFeatureFlags {
  commerce_enabled: boolean
  referrals_enabled: boolean
  promos_enabled: boolean
  web_purchase_enabled: boolean
  telegram_bot_enabled: boolean
  telegram_proxy_enabled: boolean
}

export const DEFAULT_FEATURE_FLAGS: FrontendFeatureFlags = Object.freeze({
  commerce_enabled: true,
  referrals_enabled: true,
  promos_enabled: true,
  web_purchase_enabled: true,
  telegram_bot_enabled: true,
  telegram_proxy_enabled: false,
})

export interface FrontendPublicConfig {
  features: FrontendFeatureFlags
  support_link?: string
  telegram_proxy_url?: string
  subscription_add_links?: {
    happ?: string
  }
  app_links?: {
    happ_ios?: string
    happ_android?: string
    happ_windows?: string
    happ_macos?: string
    happ_linux?: string
    windows_nekoray?: string
  }
  instruction_links?: {
    ios?: string
    android?: string
    windows?: string
    macos?: string
    linux?: string
    windows_nekoray?: string
  }
}

export const EMPTY_PUBLIC_CONFIG: FrontendPublicConfig = Object.freeze({
  features: DEFAULT_FEATURE_FLAGS,
  support_link: undefined,
  telegram_proxy_url: undefined,
  subscription_add_links: {},
  app_links: {},
  instruction_links: {},
})

export function createEmptyPublicConfig(): FrontendPublicConfig {
  return {
    features: { ...DEFAULT_FEATURE_FLAGS },
    support_link: undefined,
    telegram_proxy_url: undefined,
    subscription_add_links: {},
    app_links: {},
    instruction_links: {},
  }
}

let inflightRequest: Promise<FrontendPublicConfig> | null = null
let cachedConfig: FrontendPublicConfig | null = null

function normalizePublicConfig(payload: unknown): FrontendPublicConfig {
  const value = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {}
  const rawFeatures =
    value.features && typeof value.features === 'object'
      ? (value.features as Partial<Record<keyof FrontendFeatureFlags, unknown>>)
      : {}

  const subscriptionAddLinks =
    value.subscription_add_links && typeof value.subscription_add_links === 'object'
      ? (value.subscription_add_links as FrontendPublicConfig['subscription_add_links'])
      : {}

  const appLinks =
    value.app_links && typeof value.app_links === 'object'
      ? (value.app_links as FrontendPublicConfig['app_links'])
      : {}

  const instructionLinks =
    value.instruction_links && typeof value.instruction_links === 'object'
      ? (value.instruction_links as FrontendPublicConfig['instruction_links'])
      : {}

  return {
    ...EMPTY_PUBLIC_CONFIG,
    features: {
      commerce_enabled:
        typeof rawFeatures.commerce_enabled === 'boolean'
          ? rawFeatures.commerce_enabled
          : DEFAULT_FEATURE_FLAGS.commerce_enabled,
      referrals_enabled:
        typeof rawFeatures.referrals_enabled === 'boolean'
          ? rawFeatures.referrals_enabled
          : DEFAULT_FEATURE_FLAGS.referrals_enabled,
      promos_enabled:
        typeof rawFeatures.promos_enabled === 'boolean'
          ? rawFeatures.promos_enabled
          : DEFAULT_FEATURE_FLAGS.promos_enabled,
      web_purchase_enabled:
        typeof rawFeatures.web_purchase_enabled === 'boolean'
          ? rawFeatures.web_purchase_enabled
          : DEFAULT_FEATURE_FLAGS.web_purchase_enabled,
      telegram_bot_enabled:
        typeof rawFeatures.telegram_bot_enabled === 'boolean'
          ? rawFeatures.telegram_bot_enabled
          : DEFAULT_FEATURE_FLAGS.telegram_bot_enabled,
      telegram_proxy_enabled:
        typeof rawFeatures.telegram_proxy_enabled === 'boolean'
          ? rawFeatures.telegram_proxy_enabled
          : DEFAULT_FEATURE_FLAGS.telegram_proxy_enabled,
    },
    support_link: typeof value.support_link === 'string' ? value.support_link : undefined,
    telegram_proxy_url: typeof value.telegram_proxy_url === 'string' ? value.telegram_proxy_url : undefined,
    subscription_add_links: subscriptionAddLinks,
    app_links: appLinks,
    instruction_links: instructionLinks,
  }
}

export async function fetchPublicConfig(): Promise<FrontendPublicConfig> {
  if (cachedConfig) {
    return cachedConfig
  }

  if (inflightRequest) {
    return inflightRequest
  }

  inflightRequest = axios
    .get(`${API_BASE_URL}/user/public-config`)
    .then((response) => {
      const normalized = normalizePublicConfig(response.data)
      cachedConfig = normalized
      return normalized
    })
    .finally(() => {
      inflightRequest = null
    })

  return inflightRequest
}
