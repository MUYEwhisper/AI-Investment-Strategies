import { apiFetch } from './http'
import { sanitizeApiMessage, sanitizeOptionalApiMessage } from './error-message'

const SECTOR_API_BASE = (import.meta.env.VITE_SECTOR_API_BASE as string | undefined) ?? '/api/sectors'

export type SectorOverviewItem = {
  name: string
  code: string
  kind: string
  attentionScore: number
  sentimentScore: number
  strengthScore: number
  reason: string
  avgChange?: number | null
  coverageCount?: number | null
}

export type SectorOverviewPayload = {
  sectors: SectorOverviewItem[]
  insights: string[]
  statusNote?: string | null
  sourceNote?: string | null
  detailLoaded?: boolean
}

type SectorEnvelope = {
  success: boolean
  error?: string
  overview?: SectorOverviewPayload
}

const SECTOR_SNAPSHOT_KEY = 'ai_invest_sector_overview:'

// Electron opens the local assistant in the same window, so returning to the
// website mounts App again. Keep the last completed analysis for this session.
export function loadStoredSectorOverview(workspaceId: string): SectorOverviewPayload | null {
  try {
    const raw = sessionStorage.getItem(SECTOR_SNAPSHOT_KEY + workspaceId)
    if (!raw) return null
    const payload = JSON.parse(raw) as SectorOverviewPayload
    if (!Array.isArray(payload?.sectors) || !Array.isArray(payload?.insights)) return null
    if (!payload.sectors.every((item) => item && typeof item.name === 'string'
      && typeof item.reason === 'string'
      && [item.attentionScore, item.sentimentScore, item.strengthScore].every(Number.isFinite))
      || !payload.insights.every((line) => typeof line === 'string')) return null
    return payload
  } catch {
    return null
  }
}

export function storeSectorOverview(workspaceId: string, payload: SectorOverviewPayload): void {
  try {
    sessionStorage.setItem(SECTOR_SNAPSHOT_KEY + workspaceId, JSON.stringify(payload))
  } catch {
    // A storage restriction must not discard an analysis already shown in memory.
  }
}

export async function fetchSectorOverview(stockCodes: string[]): Promise<SectorOverviewPayload> {
  const response = await apiFetch(`${SECTOR_API_BASE}/overview`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ stockCodes }),
  })

  const text = await response.text()
  let payload: SectorEnvelope | null = null
  try {
    payload = JSON.parse(text) as SectorEnvelope
  } catch {
    payload = null
  }

  if (!response.ok || !payload?.success || !payload.overview) {
    throw new Error(sanitizeApiMessage(payload?.error || text, `请求失败: ${response.status}`))
  }

  return {
    ...payload.overview,
    sectors: payload.overview.sectors.map((item) => ({
      ...item,
      name: sanitizeApiMessage(item.name, '--'),
      reason: sanitizeApiMessage(item.reason, '暂无说明'),
    })),
    insights: payload.overview.insights.map((line) => sanitizeApiMessage(line, '')).filter(Boolean),
    statusNote: sanitizeOptionalApiMessage(payload.overview.statusNote),
    sourceNote: sanitizeOptionalApiMessage(payload.overview.sourceNote),
  }
}
