import { apiFetch } from './http'

async function parseEnvelope<T>(response: Response, key: string): Promise<T> {
  const text = await response.text()
  let parsed: Record<string, unknown> | null = null
  try {
    parsed = JSON.parse(text) as Record<string, unknown>
  } catch {
    parsed = null
  }

  if (!response.ok || !parsed?.success || !(key in parsed)) {
    throw new Error((parsed?.error as string | undefined) || text || `请求失败: ${response.status}`)
  }

  return parsed[key] as T
}

export async function fetchUserWatchlist<T = Record<string, unknown>>(): Promise<T[]> {
  const response = await apiFetch('/api/user/watchlist', {}, 'required')
  return parseEnvelope<T[]>(response, 'watchlist')
}

export async function saveUserWatchlist(items: unknown[]): Promise<void> {
  const response = await apiFetch(
    '/api/user/watchlist',
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ watchlist: items }),
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
    throw new Error((parsed?.error as string | undefined) || text || `请求失败: ${response.status}`)
  }
}

export type CloudChatMessage = {
  role: 'user' | 'ai'
  content: string
}

export type CloudChatSession = {
  id: string
  agentId: string
  title: string
  createdAt: string
  messages: CloudChatMessage[]
}

export async function fetchUserChats(): Promise<CloudChatSession[]> {
  const response = await apiFetch('/api/user/chats', {}, 'required')
  return parseEnvelope<CloudChatSession[]>(response, 'chats')
}

export async function saveUserChats(chats: CloudChatSession[]): Promise<void> {
  const response = await apiFetch(
    '/api/user/chats',
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chats }),
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
    throw new Error((parsed?.error as string | undefined) || text || `请求失败: ${response.status}`)
  }
}
