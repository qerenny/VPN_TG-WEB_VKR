import { API_BASE_URL } from './base'
import { getUrlData } from './http'
import { createCachedSingleFlight } from './requestCache'
import type { FeatureFlags } from './types'

export type FrontendFeatureFlags = FeatureFlags

const FEATURE_FLAG_KEYS = [
  'access_requests_enabled',
  'access_registry_enabled',
  'access_admin_override_enabled',
  'commerce_enabled',
  'referrals_enabled',
  'promos_enabled',
  'web_purchase_enabled',
  'telegram_bot_enabled',
  'mail_enabled',
  'standard_config_enabled',
  'traffic_limited_config_enabled',
] as const satisfies readonly (keyof FrontendFeatureFlags)[]

export const DEFAULT_FEATURE_FLAGS: FrontendFeatureFlags = Object.freeze({
  access_requests_enabled: false,
  access_registry_enabled: false,
  access_admin_override_enabled: false,
  commerce_enabled: true,
  referrals_enabled: true,
  promos_enabled: true,
  web_purchase_enabled: true,
  telegram_bot_enabled: true,
  mail_enabled: false,
  standard_config_enabled: false,
  traffic_limited_config_enabled: false,
})

export function normalizeFeatureFlags(
  payload?: Partial<Record<keyof FrontendFeatureFlags, unknown>> | null,
): FrontendFeatureFlags {
  const flags: FrontendFeatureFlags = { ...DEFAULT_FEATURE_FLAGS }
  const source = payload || {}

  for (const key of FEATURE_FLAG_KEYS) {
    if (typeof source[key] === 'boolean') {
      flags[key] = source[key]
    }
  }

  return flags
}

export interface FrontendProductConfig {
  name: string
  short_name: string
  description: string
  profile_title: string
  traffic_profile_title: string
  support_name: string
  support_link: string
  docs_links: Record<string, string>
}

export const DEFAULT_PRODUCT_CONFIG: FrontendProductConfig = Object.freeze({
  name: 'Remote Access Service',
  short_name: 'Remote Access',
  description: 'Automated protected remote access service',
  profile_title: 'Remote Access',
  traffic_profile_title: 'Traffic-Limited Remote Access',
  support_name: 'Support',
  support_link: '',
  docs_links: {},
})

export interface FrontendPublicConfig {
  product: FrontendProductConfig
  features: FrontendFeatureFlags
  support_link?: string
  payment_methods?: {
    primary?: string
    items?: Array<{
      code: string
      label: string
    }>
  }
  subscription_add_links?: {
    happ?: string
  }
  subscription_client?: {
    name?: string
  }
  app_links?: {
    happ_ios_global?: string
    happ_ios?: string
    happ_android?: string
    happ_android_apk?: string
    happ_windows?: string
    happ_macos?: string
    happ_macos_dmg?: string
    happ_linux?: string
    happ_linux_rpm?: string
    happ_apple_tv?: string
    happ_android_tv?: string
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

const EMPTY_PUBLIC_CONFIG: FrontendPublicConfig = Object.freeze({
  product: DEFAULT_PRODUCT_CONFIG,
  features: DEFAULT_FEATURE_FLAGS,
  support_link: undefined,
  payment_methods: { primary: 'external_card', items: [] },
  subscription_add_links: {},
  subscription_client: { name: 'Happ' },
  app_links: {},
  instruction_links: {},
})

export function createEmptyPublicConfig(): FrontendPublicConfig {
  return {
    features: { ...DEFAULT_FEATURE_FLAGS },
    product: { ...DEFAULT_PRODUCT_CONFIG, docs_links: {} },
    support_link: undefined,
    payment_methods: { primary: 'external_card', items: [] },
    subscription_add_links: {},
    subscription_client: { name: 'Happ' },
    app_links: {},
    instruction_links: {},
  }
}

const loadCachedPublicConfig = createCachedSingleFlight<FrontendPublicConfig>()

function normalizePublicConfig(payload: unknown): FrontendPublicConfig {
  const value = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {}
  const rawFeatures =
    value.features && typeof value.features === 'object'
      ? (value.features as Partial<Record<keyof FrontendFeatureFlags, unknown>>)
      : {}
  const rawProduct =
    value.product && typeof value.product === 'object'
      ? (value.product as Partial<Record<keyof FrontendProductConfig, unknown>>)
      : {}

  const subscriptionAddLinks =
    value.subscription_add_links && typeof value.subscription_add_links === 'object'
      ? (value.subscription_add_links as FrontendPublicConfig['subscription_add_links'])
      : {}

  const appLinks =
    value.app_links && typeof value.app_links === 'object'
      ? (value.app_links as FrontendPublicConfig['app_links'])
      : {}
  const subscriptionClient =
    value.subscription_client && typeof value.subscription_client === 'object'
      ? (value.subscription_client as FrontendPublicConfig['subscription_client'])
      : { name: 'Happ' }

  const instructionLinks =
    value.instruction_links && typeof value.instruction_links === 'object'
      ? (value.instruction_links as FrontendPublicConfig['instruction_links'])
      : {}
  const paymentMethods =
    value.payment_methods && typeof value.payment_methods === 'object'
      ? (value.payment_methods as FrontendPublicConfig['payment_methods'])
      : { primary: 'external_card', items: [] }

  return {
    ...EMPTY_PUBLIC_CONFIG,
    product: {
      ...DEFAULT_PRODUCT_CONFIG,
      name: typeof rawProduct.name === 'string' ? rawProduct.name : DEFAULT_PRODUCT_CONFIG.name,
      short_name: typeof rawProduct.short_name === 'string' ? rawProduct.short_name : DEFAULT_PRODUCT_CONFIG.short_name,
      description:
        typeof rawProduct.description === 'string' ? rawProduct.description : DEFAULT_PRODUCT_CONFIG.description,
      profile_title:
        typeof rawProduct.profile_title === 'string' ? rawProduct.profile_title : DEFAULT_PRODUCT_CONFIG.profile_title,
      traffic_profile_title:
        typeof rawProduct.traffic_profile_title === 'string'
          ? rawProduct.traffic_profile_title
          : DEFAULT_PRODUCT_CONFIG.traffic_profile_title,
      support_name:
        typeof rawProduct.support_name === 'string' ? rawProduct.support_name : DEFAULT_PRODUCT_CONFIG.support_name,
      support_link:
        typeof rawProduct.support_link === 'string' ? rawProduct.support_link : DEFAULT_PRODUCT_CONFIG.support_link,
      docs_links:
        rawProduct.docs_links && typeof rawProduct.docs_links === 'object'
          ? (rawProduct.docs_links as Record<string, string>)
          : {},
    },
    features: normalizeFeatureFlags(rawFeatures),
    support_link: typeof value.support_link === 'string' ? value.support_link : undefined,
    payment_methods: paymentMethods,
    subscription_add_links: subscriptionAddLinks,
    subscription_client: subscriptionClient,
    app_links: appLinks,
    instruction_links: instructionLinks,
  }
}

export async function fetchPublicConfig(): Promise<FrontendPublicConfig> {
  return loadCachedPublicConfig(async () => {
    const payload = await getUrlData<unknown>(`${API_BASE_URL}/user/public-config`)
    return normalizePublicConfig(payload)
  })
}
