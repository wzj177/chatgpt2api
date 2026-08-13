import apiClient, { clearAuthToken, setAuthToken } from './client'

export type AuthRole = 'admin' | 'user' | 'unknown'
export type AuthCapability = 'admin_console' | 'studio'

export interface AuthSubject {
  id: string
  name: string
  role: AuthRole
}

export interface AuthCapabilities {
  admin_console: boolean
  studio: boolean
}

export interface AuthView {
  schema_version: 1
  authenticated: boolean
  version: string
  subject: AuthSubject | null
  capabilities: AuthCapabilities
  home_route: '/login' | '/' | '/studio'
  access_token?: string | null
}

export interface LoginRequest {
  password: string
}

export interface PasswordLoginRequest {
  email: string
  password: string
  captcha?: string
}

export interface RegisterRequest {
  email: string
  password: string
  password_confirmation: string
  username: string
  phone?: string
  captcha?: string
  accepted_terms: boolean
}

export interface PublicProtocolView {
  markdown: string
  revision: string
}

export const authApi = {
  async login(data: LoginRequest) {
    setAuthToken(data.password)
    try {
      return await apiClient.post<never, AuthView>('/auth/login')
    } catch (error) {
      clearAuthToken()
      throw error
    }
  },
  async passwordLogin(data: PasswordLoginRequest) {
    const result = await apiClient.post<PasswordLoginRequest, AuthView>('/auth/login', data)
    if (result.access_token) setAuthToken(result.access_token)
    return result
  },
  async register(data: RegisterRequest) {
    const result = await apiClient.post<RegisterRequest, AuthView>('/auth/register', data)
    if (result.access_token) setAuthToken(result.access_token)
    return result
  },
  protocol: () => apiClient.get<never, PublicProtocolView>('/auth/protocol'),

  logout: () => {
    clearAuthToken()
    return Promise.resolve({ ok: true })
  },

  checkAuth: () => apiClient.get<never, AuthView>('/auth/status', { timeout: 8000 }),
}
