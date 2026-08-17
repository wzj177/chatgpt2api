import apiClient from './client'

export interface UserKey {
  id: string
  name: string
  role: 'user' | 'admin'
  enabled: boolean
  created_at?: string | null
  last_used_at?: string | null
  email?: string | null
  phone?: string | null
  usage_count: number
  daily_image_count: number
  daily_image_bonus: number
  daily_image_remaining: number
  daily_image_base_remaining: number
  login_count: number
  registration_source: string
  registration_source_label: string
}

export interface UserKeysResponse {
  items: UserKey[]
  total: number
  page: number
  page_size: number
}

export interface UserKeyUpdatePayload {
  name?: string
  enabled?: boolean
  key?: string
}

export interface UserKeyUpdateResponse {
  item: UserKey
}

export interface UserKeyDeleteResponse {
  deleted_id: string
}

export interface UserDailyImageAdjustmentResponse {
  items: UserKey[]
  count: number
}

export interface UserStats {
  total_registered: number
  active_today: number
  images_today: number
  total_usage: number
  daily_image_limit: number
  total_quota: number
  unknown_quota_count: number
  unlimited_quota_count: number
}

export const userKeysApi = {
  list: (params?: { page?: number; page_size?: number; registration_source?: string }) =>
    apiClient.get<never, UserKeysResponse>('/api/auth/users', { params: params || undefined }),
  stats: () => apiClient.get<never, UserStats>('/api/auth/users/stats'),

  update: (keyId: string, updates: UserKeyUpdatePayload) =>
    apiClient.post<UserKeyUpdatePayload, UserKeyUpdateResponse>(`/api/auth/users/${keyId}`, updates),

  delete: (keyId: string) =>
    apiClient.delete<never, UserKeyDeleteResponse>(`/api/auth/users/${keyId}`),

  adjustDailyImages: (userIds: string[], count: number) =>
    apiClient.post<{ user_ids: string[]; count: number }, UserDailyImageAdjustmentResponse>(
      '/api/auth/users/daily-image-adjustment',
      { user_ids: userIds, count },
    ),
}
