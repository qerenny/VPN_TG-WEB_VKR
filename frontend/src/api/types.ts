export interface FeatureFlags {
  access_requests_enabled: boolean
  access_registry_enabled: boolean
  access_admin_override_enabled: boolean
  commerce_enabled: boolean
  referrals_enabled: boolean
  promos_enabled: boolean
  web_purchase_enabled: boolean
  telegram_bot_enabled: boolean
  mail_enabled: boolean
  standard_config_enabled: boolean
  traffic_limited_config_enabled: boolean
}

export interface UserProfileFields {
  display_name: string | null
  timezone: string | null
  locale: string | null
  marketing_opt_in: boolean
  preferred_contact_email: string | null
}

export interface AccessRequestItem {
  id: number
  user_id: number
  requested_template_code: string | null
  requested_template_label?: string | null
  approved_template_label?: string | null
  access_grant_id: number | null
  channel: string
  request_kind: string
  status: string
  comment: string | null
  review_note: string | null
  reviewed_by_actor: string | null
  requested_at: string
  reviewed_at: string | null
  expires_at: string | null
  metadata: Record<string, unknown>
}
