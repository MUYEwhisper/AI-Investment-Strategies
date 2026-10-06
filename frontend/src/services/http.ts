import { getStoredAccessToken } from './ksuser-auth'

type AuthMode = 'optional' | 'required'

export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  authMode: AuthMode = 'optional',
): Promise<Response> {
  const headers = new Headers(init.headers ?? undefined)
  const token = getStoredAccessToken()

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  } else if (authMode === 'required') {
    throw new Error('当前尚未登录，无法继续请求。')
  }

  let normalizedInput: RequestInfo | URL = input
  if (typeof input === 'string' && input.startsWith('/')) {
    const baseOrigin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
    normalizedInput = new URL(input, baseOrigin).toString()
  }

  return fetch(normalizedInput, {
    ...init,
    headers,
  })
}
