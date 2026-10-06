const DEFAULT_KSUSER_AUTH_BASE = 'https://auth.ksuser.cn'
const DEFAULT_KSUSER_API_BASE = 'https://api.ksuser.cn'
const DEFAULT_LOCAL_AUTH_API_BASE = '/api/auth'

export const AUTH_SESSION_STORAGE_KEY = 'ai_invest_ksuser_session'
export const AUTH_PENDING_STORAGE_KEY = 'ai_invest_ksuser_pending'
export const AUTH_RUNTIME_CONFIG_STORAGE_KEY = 'ai_invest_ksuser_runtime_config'

export type KsuserUserInfo = {
  openid: string
  unionid: string
  sub?: string
  nickname?: string
  avatar_url?: string
  email?: string
}

export type KsuserAuthConfig = {
  authBase: string
  apiBase: string
  authorizeEndpoint: string
  tokenEndpoint: string
  userinfoEndpoint: string
  openidConfigurationEndpoint: string
  localAuthApiBase: string
  localStartEndpoint: string
  localCallbackEndpoint: string
  localMeEndpoint: string
  localSessionsEndpoint: string
  localRevokeEndpoint: string
  localLogoutEndpoint: string
  clientId: string
  redirectUri: string
  scope: string[]
}

export type KsuserRuntimeConfig = {
  localAuthApiBase?: string
  redirectUri?: string
}

export type KsuserSession = {
  accessToken: string
  tokenType: string
  scope: string[]
  scopeText: string
  openid: string
  unionid: string
  idToken?: string
  expiresAt: number
  createdAt: number
  clientId: string
  redirectUri: string
  authorizeEndpoint: string
  tokenEndpoint: string
  userinfoEndpoint: string
  profile: KsuserUserInfo
}

function removeTrailingSlash(input: string): string {
  return input.replace(/\/+$/, '')
}

function normalizeOptionalString(input: string | undefined): string | undefined {
  return input === undefined ? undefined : input.trim()
}

function firstDefined<T>(...values: Array<T | undefined>): T | undefined {
  for (const value of values) {
    if (value !== undefined) return value
  }

  return undefined
}

function getStorage(kind: 'local' | 'session'): Storage | null {
  if (typeof window === 'undefined') return null
  return kind === 'local' ? window.localStorage : window.sessionStorage
}

function readRuntimeConfig(): KsuserRuntimeConfig {
  const raw = getStorage('local')?.getItem(AUTH_RUNTIME_CONFIG_STORAGE_KEY)
  if (!raw) return {}

  try {
    return JSON.parse(raw) as KsuserRuntimeConfig
  } catch {
    return {}
  }
}

function normalizeRuntimeConfig(config: KsuserRuntimeConfig): KsuserRuntimeConfig {
  const normalizedEntries = Object.entries(config).map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value])

  return Object.fromEntries(normalizedEntries.filter(([, value]) => value)) as KsuserRuntimeConfig
}

function parseScope(scopeText: string | undefined): string[] {
  if (scopeText === undefined) return []

  const normalized = scopeText
    .split(/\s+/)
    .map((item) => item.trim())
    .filter((item) => Boolean(item) && item.toLowerCase() !== 'openid')

  return Array.from(new Set(normalized))
}

function stringifyScope(scope: string[]): string {
  return scope.join(' ')
}

function resolveRedirectUri(): string {
  if (import.meta.env.VITE_KSUSER_REDIRECT_URI?.trim()) {
    return import.meta.env.VITE_KSUSER_REDIRECT_URI.trim()
  }

  if (typeof window === 'undefined') {
    return 'http://localhost:5173/auth/callback'
  }

  return new URL('/auth/callback', window.location.origin).toString()
}

function toAbsoluteUrl(input: string, base: string): string {
  return new URL(input, `${base.endsWith('/') ? base : `${base}/`}`).toString()
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const text = await response.text()

  let payload: T | null = null
  try {
    payload = JSON.parse(text) as T
  } catch {
    payload = null
  }

  if (!response.ok) {
    const details = payload as Record<string, unknown> | null
    throw new Error(
      (details?.error as string | undefined) ||
        (details?.message as string | undefined) ||
        text ||
        `请求失败: ${response.status}`,
    )
  }

  if (!payload) {
    throw new Error(text || '认证服务返回了无法解析的数据。')
  }

  return payload
}

export function getKsuserAuthConfig(): KsuserAuthConfig {
  const runtimeConfig = normalizeRuntimeConfig(readRuntimeConfig())
  const authBase = removeTrailingSlash(normalizeOptionalString(import.meta.env.VITE_KSUSER_AUTH_BASE) || DEFAULT_KSUSER_AUTH_BASE)
  const apiBase = removeTrailingSlash(normalizeOptionalString(import.meta.env.VITE_KSUSER_API_BASE) || DEFAULT_KSUSER_API_BASE)
  const localAuthApiBase =
    removeTrailingSlash(
      firstDefined(
        normalizeOptionalString(import.meta.env.VITE_LOCAL_AUTH_API_BASE),
        runtimeConfig.localAuthApiBase,
        DEFAULT_LOCAL_AUTH_API_BASE,
      ) || DEFAULT_LOCAL_AUTH_API_BASE,
    )

  const scope = parseScope(normalizeOptionalString(import.meta.env.VITE_KSUSER_SCOPE) || 'profile email')

  return {
    authBase,
    apiBase,
    authorizeEndpoint: toAbsoluteUrl('oauth/authorize', authBase),
    tokenEndpoint: toAbsoluteUrl('oauth2/token', apiBase),
    userinfoEndpoint: toAbsoluteUrl('oauth2/userinfo', apiBase),
    openidConfigurationEndpoint: toAbsoluteUrl('.well-known/openid-configuration', authBase),
    localAuthApiBase,
    localStartEndpoint: `${localAuthApiBase}/start`,
    localCallbackEndpoint: `${localAuthApiBase}/callback`,
    localMeEndpoint: `${localAuthApiBase}/me`,
    localSessionsEndpoint: `${localAuthApiBase}/sessions`,
    localRevokeEndpoint: `${localAuthApiBase}/revoke`,
    localLogoutEndpoint: `${localAuthApiBase}/logout`,
    clientId: normalizeOptionalString(import.meta.env.VITE_KSUSER_CLIENT_ID) || '',
    redirectUri: firstDefined(runtimeConfig.redirectUri, resolveRedirectUri()) || resolveRedirectUri(),
    scope,
  }
}

export function isKsuserConfigured(config = getKsuserAuthConfig()): boolean {
  return Boolean(config.clientId)
}

export function saveKsuserRuntimeConfig(config: KsuserRuntimeConfig): KsuserRuntimeConfig {
  const normalized = normalizeRuntimeConfig(config)

  if (Object.keys(normalized).length) {
    getStorage('local')?.setItem(AUTH_RUNTIME_CONFIG_STORAGE_KEY, JSON.stringify(normalized))
  } else {
    getStorage('local')?.removeItem(AUTH_RUNTIME_CONFIG_STORAGE_KEY)
  }

  return normalized
}

export function clearKsuserRuntimeConfig(): void {
  getStorage('local')?.removeItem(AUTH_RUNTIME_CONFIG_STORAGE_KEY)
}

export function clearPendingAuthRequest(): void {
  getStorage('session')?.removeItem(AUTH_PENDING_STORAGE_KEY)
}

export async function createKsuserAuthorizationRequest(returnTo = '/'): Promise<{ url: string }> {
  const config = getKsuserAuthConfig()
  const redirectTo = returnTo.startsWith('/') ? returnTo : '/'
  const url = new URL(config.localStartEndpoint, window.location.origin)
  url.searchParams.set('redirect_to', redirectTo)
  return { url: url.toString() }
}

function persistSession(session: KsuserSession): void {
  getStorage('local')?.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session))
}

export function clearStoredKsuserSession(): void {
  getStorage('local')?.removeItem(AUTH_SESSION_STORAGE_KEY)
}

export function loadStoredKsuserSession(): KsuserSession | null {
  const raw = getStorage('local')?.getItem(AUTH_SESSION_STORAGE_KEY)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as Partial<KsuserSession>
    if (!parsed.accessToken || !parsed.profile?.openid || !parsed.profile?.unionid || !parsed.expiresAt) {
      clearStoredKsuserSession()
      return null
    }

    if (parsed.expiresAt <= Date.now()) {
      clearStoredKsuserSession()
      return null
    }

    const scope = Array.isArray(parsed.scope) ? parsed.scope.filter(Boolean) : parseScope(parsed.scopeText)

    return {
      accessToken: parsed.accessToken,
      tokenType: parsed.tokenType || 'Bearer',
      scope,
      scopeText: stringifyScope(scope),
      openid: parsed.openid || parsed.profile.openid,
      unionid: parsed.unionid || parsed.profile.unionid,
      idToken: parsed.idToken,
      expiresAt: parsed.expiresAt,
      createdAt: parsed.createdAt || Date.now(),
      clientId: parsed.clientId || getKsuserAuthConfig().clientId,
      redirectUri: parsed.redirectUri || resolveRedirectUri(),
      authorizeEndpoint: parsed.authorizeEndpoint || getKsuserAuthConfig().authorizeEndpoint,
      tokenEndpoint: parsed.tokenEndpoint || getKsuserAuthConfig().tokenEndpoint,
      userinfoEndpoint: parsed.userinfoEndpoint || getKsuserAuthConfig().userinfoEndpoint,
      profile: parsed.profile,
    }
  } catch {
    clearStoredKsuserSession()
    return null
  }
}

export function getStoredAccessToken(): string | null {
  return loadStoredKsuserSession()?.accessToken ?? null
}

export async function completeKsuserAuthorization(
  searchParams: URLSearchParams,
): Promise<{ session: KsuserSession; returnTo: string }> {
  const authError = searchParams.get('error')
  if (authError) {
    clearPendingAuthRequest()
    const description = searchParams.get('error_description')
    throw new Error(description || authError)
  }

  const code = searchParams.get('code')
  const state = searchParams.get('state')

  if (!code || !state) {
    throw new Error('Ksuser 回调缺少必要参数，请重新发起登录。')
  }

  const config = getKsuserAuthConfig()
  const url = new URL(config.localCallbackEndpoint, window.location.origin)
  url.searchParams.set('code', code)
  url.searchParams.set('state', state)

  const payload = await parseJsonResponse<{ success?: boolean; session?: KsuserSession; returnTo?: string; error?: string }>(
    await fetch(url.toString(), {
      headers: {
        Accept: 'application/json',
      },
    }),
  )

  if (!payload.success || !payload.session) {
    throw new Error(payload.error || '未能成功完成登录。')
  }

  persistSession(payload.session)

  return {
    session: payload.session,
    returnTo: payload.returnTo || '/',
  }
}
