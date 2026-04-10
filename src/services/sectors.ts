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

export async function fetchSectorOverview(stockCodes: string[]): Promise<SectorOverviewPayload> {
  const response = await fetch(`${SECTOR_API_BASE}/overview`, {
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
    throw new Error(payload?.error || text || `请求失败: ${response.status}`)
  }

  return payload.overview
}
