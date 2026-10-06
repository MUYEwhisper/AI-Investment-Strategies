import { apiFetch } from './http'
import { getKsuserAuthConfig, clearStoredKsuserSession, type KsuserSession } from './ksuser-auth'

export type AccountUser = {
  id: number
  openid: string
  unionid: string
  nickname: string
  email: string
  avatar_url: string
}

export type AccountSession = {
  id: number
  createdAt: string
  lastSeenAt: string
  expiresAt: string
  ip: string
  userAgent: string
  isCurrent: boolean
}

function toError(text: string, status: number): Error {
  return new Error(text || `请求失败: ${status}`)
}

async function parseEnvelope<T>(response: Response, key: string): Promise<T> {
  const text = await response.text()
  let parsed: Record<string, unknown> | null = null
  try {
    parsed = JSON.parse(text) as Record<string, unknown>
  } catch {
    parsed = null
  }

  if (!response.ok || !parsed?.success || !(key in parsed)) {
    const message = (parsed?.error as string | undefined) || text
    throw toError(message || '', response.status)
  }

  return parsed[key] as T
}

export async function fetchAccountUser(): Promise<AccountUser> {
  const config = getKsuserAuthConfig()
  const response = await apiFetch(config.localMeEndpoint, {}, 'required')
  return parseEnvelope<AccountUser>(response, 'user')
}

export async function fetchAccountSessions(): Promise<AccountSession[]> {
  const config = getKsuserAuthConfig()
  const response = await apiFetch(config.localSessionsEndpoint, {}, 'required')
  return parseEnvelope<AccountSession[]>(response, 'sessions')
}

export async function revokeSessions(target: 'current' | 'others'): Promise<void> {
  const config = getKsuserAuthConfig()
  const response = await apiFetch(
    config.localRevokeEndpoint,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target }),
    },
    'required',
  )

  const text = await response.text()
  let parsed: Record<string, unknown> | null = null
  try {
    parsed = JSON.parse(text) as Record<string, unknown>
  } catch {
    parsed = null
  }
  if (!response.ok || !parsed?.success) {
    throw toError((parsed?.error as string | undefined) || text, response.status)
  }

  if (target === 'current') {
    clearStoredKsuserSession()
  }
}

export async function logoutAccount(): Promise<void> {
  const config = getKsuserAuthConfig()
  const response = await apiFetch(
    config.localLogoutEndpoint,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    },
    'required',
  )

  const text = await response.text()
  let parsed: Record<string, unknown> | null = null
  try {
    parsed = JSON.parse(text) as Record<string, unknown>
  } catch {
    parsed = null
  }
  if (!response.ok || !parsed?.success) {
    throw toError((parsed?.error as string | undefined) || text, response.status)
  }

  clearStoredKsuserSession()
}

export function toKsuserSessionUserPatch(session: KsuserSession | null, user: AccountUser): KsuserSession | null {
  if (!session) return null
  return {
    ...session,
    profile: {
      ...session.profile,
      openid: user.openid,
      unionid: user.unionid,
      nickname: user.nickname,
      email: user.email,
      avatar_url: user.avatar_url,
    },
    openid: user.openid,
    unionid: user.unionid,
  }
}
