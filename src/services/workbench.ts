const PROFILE_API_BASE = (import.meta.env.VITE_PROFILE_API_BASE as string | undefined) ?? '/api/profile'
const PORTFOLIO_API_BASE = (import.meta.env.VITE_PORTFOLIO_API_BASE as string | undefined) ?? '/api/portfolio'
const EXPLAIN_API_BASE = (import.meta.env.VITE_EXPLAIN_API_BASE as string | undefined) ?? '/api/explain'
const SIM_API_BASE = (import.meta.env.VITE_SIM_API_BASE as string | undefined) ?? '/api/sim'

export type RiskAnswers = {
  experience: string
  lossTolerance: string
  horizon: string
  objective: string
  style: string
  tradingFrequency: string
  decisionStyle: string
  positionStyle: string
  supplementDescription: string
}

export type InvestorProfile = {
  riskScore: number
  riskLevel: string
  maxSingleStockWeight: number
  maxSingleSectorWeight: number
  summary: string
  recommendation: string
  analysisBasis: string[]
  analysisSource: string
  answers: RiskAnswers
  updatedAt: string
}

export type PortfolioWarning = {
  level: string
  title: string
  detail: string
}

export type PortfolioRadar = {
  label: string
  score: number
}

export type PortfolioPositionBreakdown = {
  code: string
  name: string
  weight: number
  sectorName: string
  change?: number | null
  sentiment: string
  tags: string[]
}

export type PortfolioHealthReport = {
  source: string
  healthScore: number
  summary: string
  riskProfile: InvestorProfile
  radar: PortfolioRadar[]
  sectorBreakdown: Array<{ name: string; weight: number }>
  positionBreakdown: PortfolioPositionBreakdown[]
  warnings: PortfolioWarning[]
  suggestions: string[]
  metrics: {
    maxStockWeight: number
    maxSectorWeight: number
    hotStockRatio: number
    averageMove: number
  }
}

export type SimAccount = {
  initialCash: number
  cash: number
  equity: number
  positionValue: number
  realizedPnl: number
  totalPnl: number
  positionCount: number
  tradeCount: number
  updatedAt: string
}

export type SimPosition = {
  code: string
  name: string
  quantity: number
  averageCost: number
  costAmount: number
  marketValue: number
  lastPrice: number | null
  unrealizedPnl: number
  pnlRatio: number
  change?: number | null
  sentiment: string
  tags: string[]
  sectorName: string
  takeProfit: string
  stopLoss: string
  planHorizon: string
  lastRationale: string
  lastTradeAt: string
}

export type SimTrade = {
  id: number
  stockCode: string
  stockName: string
  side: string
  quantity: number
  price: number
  amount: number
  fees: number
  rationale: string
  planHorizon: string
  takeProfit: string
  stopLoss: string
  createdAt: string
}

export type SimulationSnapshot = {
  account: SimAccount
  positions: SimPosition[]
  trades: SimTrade[]
}

export type AnomalyReport = {
  stock: {
    name: string
    code: string
    price?: number | null
    change?: number | null
    sentiment: string
    sectorName: string
  }
  signalType: string
  confidence: number
  summary: string
  evidenceItems: string[]
  newsItems: Array<{ title: string; summary: string }>
  announcementTitles: string[]
  riskFlags: string[]
}

export type TradeReview = {
  stock: {
    code: string
    name: string
    sectorName: string
    averageCost: number | null
    currentPrice: number | null
    pnlRatio: number
    quantity: number
  }
  thesisStatus: string
  thesisDetail: string
  disciplineScore: number
  disciplineItems: string[]
  emotionRisk: string
  sentiment: string
  summary: string
  improvements: string[]
}

async function parseEnvelope<T>(response: Response, dataKey: string): Promise<T> {
  const text = await response.text()
  const fallbackMessage = text || `请求失败: ${response.status}`

  let parsed: Record<string, unknown> | null = null
  try {
    parsed = JSON.parse(text) as Record<string, unknown>
  } catch {
    parsed = null
  }

  if (!response.ok || !parsed?.success || !(dataKey in parsed)) {
    throw new Error((parsed?.error as string | undefined) || fallbackMessage)
  }

  return parsed[dataKey] as T
}

export async function fetchInvestorProfile(): Promise<InvestorProfile> {
  const response = await fetch(PROFILE_API_BASE)
  return parseEnvelope<InvestorProfile>(response, 'profile')
}

export async function evaluateInvestorProfile(answers: RiskAnswers): Promise<InvestorProfile> {
  const response = await fetch(`${PROFILE_API_BASE}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  })
  return parseEnvelope<InvestorProfile>(response, 'profile')
}

export async function fetchPortfolioHealth(watchlist: Array<Record<string, unknown>>): Promise<PortfolioHealthReport> {
  const response = await fetch(`${PORTFOLIO_API_BASE}/health`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ watchlist }),
  })
  return parseEnvelope<PortfolioHealthReport>(response, 'report')
}

export async function fetchSimulationSnapshot(): Promise<SimulationSnapshot> {
  const response = await fetch(`${SIM_API_BASE}/account`)
  return parseEnvelope<SimulationSnapshot>(response, 'snapshot')
}

export async function resetSimulationSnapshot(initialCash = 100000): Promise<SimulationSnapshot> {
  const response = await fetch(`${SIM_API_BASE}/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initialCash }),
  })
  return parseEnvelope<SimulationSnapshot>(response, 'snapshot')
}

export async function submitSimulationTrade(payload: {
  stockCode: string
  stockName: string
  side: string
  quantity: number
  rationale: string
  planHorizon: string
  takeProfit: string
  stopLoss: string
}): Promise<SimulationSnapshot> {
  const response = await fetch(`${SIM_API_BASE}/trade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseEnvelope<SimulationSnapshot>(response, 'snapshot')
}

export async function fetchAnomalyReport(stockCode: string): Promise<AnomalyReport> {
  const response = await fetch(`${EXPLAIN_API_BASE}/anomaly/${encodeURIComponent(stockCode)}`)
  return parseEnvelope<AnomalyReport>(response, 'report')
}

export async function fetchTradeReview(stockCode: string): Promise<TradeReview> {
  const response = await fetch(`${SIM_API_BASE}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stockCode }),
  })
  return parseEnvelope<TradeReview>(response, 'review')
}
