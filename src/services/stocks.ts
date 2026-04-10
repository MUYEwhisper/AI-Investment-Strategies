const STOCK_API_BASE = (import.meta.env.VITE_STOCK_API_BASE as string | undefined) ?? '/api/stocks'

export type StockApiPayload = {
  name: string
  code: string
  price: number | null
  change: number | null
  turnover: string
  pe: string
  pb: string
  marketCap: string
  volumeRatio: string
  mainFlow: string
  sentiment: string
  tags: string[]
  statusNote?: string | null
  detailLoaded?: boolean
}

type StockApiEnvelope = {
  success: boolean
  error?: string
  stock?: StockApiPayload
}

async function parseEnvelope(response: Response): Promise<StockApiEnvelope> {
  const text = await response.text()
  const fallbackMessage = text || `请求失败: ${response.status}`

  let parsed: StockApiEnvelope | null = null
  try {
    parsed = JSON.parse(text) as StockApiEnvelope
  } catch {
    parsed = null
  }

  if (!response.ok || !parsed?.success || !parsed.stock) {
    throw new Error(parsed?.error || fallbackMessage)
  }

  return parsed
}

export async function addWatchlistStock(query: string): Promise<StockApiPayload> {
  const response = await fetch(`${STOCK_API_BASE}/watchlist`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  })

  const payload = await parseEnvelope(response)
  return payload.stock as StockApiPayload
}

export async function fetchStockDetail(code: string): Promise<StockApiPayload> {
  const response = await fetch(`${STOCK_API_BASE}/${encodeURIComponent(code)}`)
  const payload = await parseEnvelope(response)
  return payload.stock as StockApiPayload
}
