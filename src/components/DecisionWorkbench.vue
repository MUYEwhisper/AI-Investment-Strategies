<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import type { StockApiPayload } from '../services/stocks'
import {
  evaluateInvestorProfile,
  fetchAnomalyReport,
  fetchInvestorProfile,
  fetchPortfolioHealth,
  fetchSimulationSnapshot,
  fetchTradeReview,
  resetSimulationSnapshot,
  submitSimulationTrade,
  type AnomalyReport,
  type InvestorProfile,
  type PortfolioHealthReport,
  type RiskAnswers,
  type SimulationSnapshot,
  type TradeReview,
} from '../services/workbench'

type WorkbenchStock = StockApiPayload & {
  id?: string
}

type ChoiceOption = {
  value: string
  label: string
  hint?: string
}

const props = defineProps<{
  watchlist: WorkbenchStock[]
  selectedStock?: WorkbenchStock | null
}>()

const experienceOptions: ChoiceOption[] = [
  { value: 'newbie', label: '几乎没有经验', hint: '刚接触交易规则' },
  { value: 'starter', label: '刚入门', hint: '做过少量尝试' },
  { value: 'experienced', label: '完整交易过', hint: '经历过一轮行情' },
  { value: 'advanced', label: '方法较稳定', hint: '已有固定框架' },
  { value: 'systematic', label: '系统化交易', hint: '会复盘和迭代' },
]

const lossToleranceOptions: ChoiceOption[] = [
  { value: 'very_low', label: '极低回撤容忍', hint: '本金安全优先' },
  { value: 'low', label: '低回撤容忍', hint: '不喜欢大波动' },
  { value: 'medium', label: '中等波动可接受', hint: '接受正常震荡' },
  { value: 'high', label: '较高波动可接受', hint: '能承受阶段回撤' },
  { value: 'very_high', label: '高波动换收益', hint: '接受激进配置' },
]

const horizonOptions: ChoiceOption[] = [
  { value: 'ultra_short', label: '超短观察', hint: '以数日节奏为主' },
  { value: 'short', label: '短期', hint: '1 个月内找机会' },
  { value: 'medium', label: '中期', hint: '1 到 3 个月跟踪' },
  { value: 'long', label: '长期', hint: '半年到一年持有' },
  { value: 'very_long', label: '超长期', hint: '一年以上配置' },
]

const objectiveOptions: ChoiceOption[] = [
  { value: 'capital_preserve', label: '保本优先', hint: '回撤控制第一' },
  { value: 'income', label: '现金流/红利', hint: '偏稳定收益' },
  { value: 'steady', label: '稳健增值', hint: '收益和风险平衡' },
  { value: 'growth', label: '追求成长', hint: '接受换手提升弹性' },
  { value: 'aggressive', label: '收益弹性优先', hint: '愿意博取高收益' },
]

const styleOptions: ChoiceOption[] = [
  { value: 'income', label: '红利防守', hint: '偏高股息和低波' },
  { value: 'value', label: '价值低估', hint: '看估值修复' },
  { value: 'balanced', label: '均衡配置', hint: '行业分散为主' },
  { value: 'growth', label: '成长风格', hint: '看业绩和趋势' },
  { value: 'theme', label: '热点主题', hint: '更关注题材轮动' },
]

const tradingFrequencyOptions: ChoiceOption[] = [
  { value: 'daily', label: '高频盯盘', hint: '几乎每天交易/调仓' },
  { value: 'weekly', label: '每周跟踪', hint: '短中线结合' },
  { value: 'monthly', label: '月度调整', hint: '偏耐心持有' },
  { value: 'event_driven', label: '事件驱动', hint: '公告/催化触发' },
]

const decisionStyleOptions: ChoiceOption[] = [
  { value: 'research', label: '基本面研究', hint: '看财报和逻辑' },
  { value: 'technical', label: '技术面交易', hint: '看形态和量价' },
  { value: 'news', label: '新闻催化', hint: '对消息反应快' },
  { value: 'blended', label: '混合判断', hint: '多维度综合' },
]

const positionStyleOptions: ChoiceOption[] = [
  { value: 'light', label: '轻仓试错', hint: '先验证再加仓' },
  { value: 'balanced', label: '均衡持仓', hint: '控制单票风险' },
  { value: 'concentrated', label: '相对集中', hint: '押注高确定性方向' },
  { value: 'aggressive', label: '激进集中', hint: '追求净值弹性' },
]

const tradeHorizonOptions: ChoiceOption[] = [
  { value: '短期（1~14天）', label: '短期', hint: '1 到 14 天' },
  { value: '中期（15~60天）', label: '中期', hint: '15 到 60 天' },
  { value: '长期（60+）', label: '长期', hint: '60 天以上' },
  { value: '波段（箱体、通道内波段）', label: '波段', hint: '箱体/通道交易' },
]

const tradeSideOptions: ChoiceOption[] = [
  { value: 'buy', label: '买入' },
  { value: 'sell', label: '卖出' },
]

const profile = ref<InvestorProfile | null>(null)
const healthReport = ref<PortfolioHealthReport | null>(null)
const simSnapshot = ref<SimulationSnapshot | null>(null)
const anomalyReport = ref<AnomalyReport | null>(null)
const tradeReview = ref<TradeReview | null>(null)

const profileLoading = ref(false)
const healthLoading = ref(false)
const simLoading = ref(false)
const explainLoading = ref(false)
const reviewLoading = ref(false)
const healthDirty = ref(true)
const explainDirty = ref(true)

const profileError = ref('')
const healthError = ref('')
const simError = ref('')
const explainError = ref('')
const reviewError = ref('')

const profileForm = reactive<RiskAnswers>({
  experience: 'starter',
  lossTolerance: 'medium',
  horizon: 'medium',
  objective: 'growth',
  style: 'balanced',
  tradingFrequency: 'weekly',
  decisionStyle: 'research',
  positionStyle: 'balanced',
  supplementDescription: '',
})

const tradeForm = reactive({
  stockCode: '',
  stockName: '',
  side: 'buy',
  quantity: 100,
  rationale: '',
  planHorizon: '中期（15~60天）',
  takeProfit: '达到预期收益后分批止盈',
  stopLoss: '跌破计划止损位及时复盘',
})

const explainStockCode = ref('')

const watchlistItems = computed(() => props.watchlist)
const focusStock = computed(() => props.selectedStock ?? props.watchlist[0] ?? null)
const explainStock = computed(
  () => watchlistItems.value.find((item) => item.code === explainStockCode.value) ?? focusStock.value,
)
const isBuySide = computed(() => tradeForm.side === 'buy')
const currentPositions = computed(() => simSnapshot.value?.positions ?? [])
const recentTrades = computed(() => simSnapshot.value?.trades.slice(0, 5) ?? [])

watch(
  () => profile.value?.answers,
  (answers) => {
    if (!answers) return
    profileForm.experience = answers.experience
    profileForm.lossTolerance = answers.lossTolerance
    profileForm.horizon = answers.horizon
    profileForm.objective = answers.objective
    profileForm.style = answers.style
    profileForm.tradingFrequency = answers.tradingFrequency
    profileForm.decisionStyle = answers.decisionStyle
    profileForm.positionStyle = answers.positionStyle
    profileForm.supplementDescription = answers.supplementDescription ?? ''
  },
  { immediate: true },
)

watch(
  focusStock,
  (stock) => {
    if (!stock) return
    if (!tradeForm.stockCode || !watchlistItems.value.some((item) => item.code === tradeForm.stockCode)) {
      tradeForm.stockCode = stock.code
      tradeForm.stockName = stock.name
    }
    if (!explainStockCode.value || !watchlistItems.value.some((item) => item.code === explainStockCode.value)) {
      explainStockCode.value = stock.code
    }
  },
  { immediate: true },
)

watch(
  () => tradeForm.stockCode,
  (code) => {
    const selected = watchlistItems.value.find((item) => item.code === code)
    if (selected) tradeForm.stockName = selected.name
  },
)

watch(explainStockCode, () => {
  explainDirty.value = true
})

watch(
  () => props.watchlist.map((item) => `${item.code}:${item.change}:${item.sentiment}`).join('|'),
  () => {
    healthDirty.value = true
    explainDirty.value = true
    if (!watchlistItems.value.length) {
      explainStockCode.value = ''
      tradeForm.stockCode = ''
      tradeForm.stockName = ''
      return
    }
    if (!watchlistItems.value.some((item) => item.code === explainStockCode.value)) {
      explainStockCode.value = focusStock.value?.code ?? watchlistItems.value[0].code
    }
    if (!watchlistItems.value.some((item) => item.code === tradeForm.stockCode)) {
      const fallbackStock = focusStock.value ?? watchlistItems.value[0]
      tradeForm.stockCode = fallbackStock.code
      tradeForm.stockName = fallbackStock.name
    }
  },
)

function formatCurrency(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--'
  return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatRatio(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function riskTone(score: number | undefined): string {
  if (typeof score !== 'number') return 'neutral'
  if (score >= 80) return 'good'
  if (score >= 60) return 'warn'
  return 'bad'
}

async function loadProfile(): Promise<void> {
  profileLoading.value = true
  profileError.value = ''
  try {
    profile.value = await fetchInvestorProfile()
  } catch (error) {
    profileError.value = error instanceof Error ? error.message : '画像读取失败'
  } finally {
    profileLoading.value = false
  }
}

async function saveProfile(): Promise<void> {
  profileLoading.value = true
  profileError.value = ''
  try {
    profile.value = await evaluateInvestorProfile({ ...profileForm })
    healthDirty.value = true
  } catch (error) {
    profileError.value = error instanceof Error ? error.message : '画像生成失败'
  } finally {
    profileLoading.value = false
  }
}

async function loadHealth(): Promise<void> {
  healthLoading.value = true
  healthError.value = ''
  try {
    healthReport.value = await fetchPortfolioHealth(props.watchlist)
    healthDirty.value = false
  } catch (error) {
    healthError.value = error instanceof Error ? error.message : '组合体检失败'
  } finally {
    healthLoading.value = false
  }
}

async function loadSimulation(): Promise<void> {
  simLoading.value = true
  simError.value = ''
  try {
    simSnapshot.value = await fetchSimulationSnapshot()
  } catch (error) {
    simError.value = error instanceof Error ? error.message : '模拟账户读取失败'
  } finally {
    simLoading.value = false
  }
}

async function submitTrade(): Promise<void> {
  simLoading.value = true
  simError.value = ''
  try {
    const selected = props.watchlist.find((item) => item.code === tradeForm.stockCode)
    simSnapshot.value = await submitSimulationTrade({
      stockCode: tradeForm.stockCode.trim(),
      stockName: selected?.name || tradeForm.stockName.trim(),
      side: tradeForm.side,
      quantity: tradeForm.quantity,
      rationale: tradeForm.rationale.trim(),
      planHorizon: isBuySide.value ? tradeForm.planHorizon.trim() : '',
      takeProfit: isBuySide.value ? tradeForm.takeProfit.trim() : '',
      stopLoss: isBuySide.value ? tradeForm.stopLoss.trim() : '',
    })
    tradeForm.rationale = ''
    healthDirty.value = true
  } catch (error) {
    simError.value = error instanceof Error ? error.message : '模拟交易失败'
  } finally {
    simLoading.value = false
  }
}

async function resetSimulation(): Promise<void> {
  simLoading.value = true
  simError.value = ''
  try {
    simSnapshot.value = await resetSimulationSnapshot(100000)
    tradeReview.value = null
    healthDirty.value = true
  } catch (error) {
    simError.value = error instanceof Error ? error.message : '模拟账户重置失败'
  } finally {
    simLoading.value = false
  }
}

async function loadExplain(stockCode?: string): Promise<void> {
  const code = stockCode || explainStock.value?.code || ''
  if (!code) return
  explainLoading.value = true
  explainError.value = ''
  try {
    anomalyReport.value = await fetchAnomalyReport(code)
    explainDirty.value = false
  } catch (error) {
    explainError.value = error instanceof Error ? error.message : '异动解释失败'
  } finally {
    explainLoading.value = false
  }
}

async function loadReview(stockCode: string): Promise<void> {
  reviewLoading.value = true
  reviewError.value = ''
  try {
    tradeReview.value = await fetchTradeReview(stockCode)
  } catch (error) {
    reviewError.value = error instanceof Error ? error.message : '复盘报告生成失败'
  } finally {
    reviewLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadProfile(), loadSimulation()])
})
</script>

<template>
  <section class="panel workbench-panel">
    <div class="panel-header">
      <div>
        <div class="panel-title">策略工作台</div>
        <div class="panel-subtitle">风险画像、组合体检、异动解释、模拟交易与 AI 复盘闭环</div>
      </div>
    </div>

    <div class="workbench-grid">
      <article class="work-card profile-work-card">
        <div class="work-card-head">
          <div>
            <div class="work-card-title">投资者风险画像</div>
            <div class="work-card-subtitle">先定义适合你的风险边界，再驱动后续体检与建议</div>
          </div>
          <button class="btn primary action-cta" :class="{ loading: profileLoading }" :disabled="profileLoading" @click="saveProfile">
            {{ profileLoading ? '分析中...' : '更新画像' }}
          </button>
        </div>

        <div class="profile-form-grid">
          <div class="field-card full-line">
            <div class="field-label">经验水平</div>
            <div class="choice-grid">
              <button
                v-for="option in experienceOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.experience === option.value }"
                @click="profileForm.experience = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <div class="field-card full-line">
            <div class="field-label">可承受回撤</div>
            <div class="choice-grid">
              <button
                v-for="option in lossToleranceOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.lossTolerance === option.value }"
                @click="profileForm.lossTolerance = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <div class="field-card full-line">
            <div class="field-label">投资周期</div>
            <div class="choice-grid">
              <button
                v-for="option in horizonOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.horizon === option.value }"
                @click="profileForm.horizon = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <div class="field-card">
            <div class="field-label">投资目标</div>
            <div class="choice-grid compact-grid">
              <button
                v-for="option in objectiveOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.objective === option.value }"
                @click="profileForm.objective = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <div class="field-card">
            <div class="field-label">偏好风格</div>
            <div class="choice-grid compact-grid">
              <button
                v-for="option in styleOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.style === option.value }"
                @click="profileForm.style = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <div class="field-card">
            <div class="field-label">交易节奏</div>
            <div class="choice-grid compact-grid">
              <button
                v-for="option in tradingFrequencyOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.tradingFrequency === option.value }"
                @click="profileForm.tradingFrequency = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <div class="field-card">
            <div class="field-label">决策方式</div>
            <div class="choice-grid compact-grid">
              <button
                v-for="option in decisionStyleOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.decisionStyle === option.value }"
                @click="profileForm.decisionStyle = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <div class="field-card full-line">
            <div class="field-label">仓位风格</div>
            <div class="choice-grid compact-grid">
              <button
                v-for="option in positionStyleOptions"
                :key="option.value"
                type="button"
                class="choice-pill"
                :class="{ active: profileForm.positionStyle === option.value }"
                @click="profileForm.positionStyle = option.value"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.hint }}</small>
              </button>
            </div>
          </div>

          <label class="field-card full-line">
            <span class="field-label">补充描述</span>
            <textarea
              v-model="profileForm.supplementDescription"
              class="glass-textarea"
              rows="4"
              placeholder="补充你的交易特点、预期收益、可接受回撤、偏好的题材/风格、止盈止损纪律等，更新画像时会与上方选项一起交给 AI 分析。"
            ></textarea>
            <span class="field-note">
              画像分数、风险标签和配置建议均由 AI 结合你的选项与补充描述分析生成；若 AI 暂不可用，系统会自动回退到规则评分。
            </span>
          </label>
        </div>

        <div v-if="profile" class="profile-box enriched-box">
          <div class="profile-topline">
            <div class="score-badge" :class="riskTone(profile.riskScore)">{{ profile.riskLevel }}</div>
            <div class="source-pill">{{ profile.analysisSource || 'AI 分析' }}</div>
          </div>
          <div class="score-line">风险分 {{ profile.riskScore }}/100</div>
          <div class="summary-text">{{ profile.summary || profile.recommendation }}</div>
          <div v-if="profile.recommendation && profile.recommendation !== profile.summary" class="analysis-note">
            {{ profile.recommendation }}
          </div>
          <div v-if="profile.analysisBasis?.length" class="section-block compact-block">
            <div class="section-title">AI 分析依据</div>
            <div class="stat-row">
              <div v-for="item in profile.analysisBasis" :key="item" class="stat-chip soft-chip">{{ item }}</div>
            </div>
          </div>
          <div class="stat-row">
            <div class="stat-chip">单股建议上限 {{ Math.round(profile.maxSingleStockWeight * 100) }}%</div>
            <div class="stat-chip">单行业建议上限 {{ Math.round(profile.maxSingleSectorWeight * 100) }}%</div>
            <div class="stat-chip">更新时间 {{ profile.updatedAt }}</div>
          </div>
        </div>
        <div v-if="profileError" class="feedback error">{{ profileError }}</div>
      </article>

      <article class="work-card health-work-card">
        <div class="work-card-head">
          <div>
            <div class="work-card-title">组合体检报告</div>
            <div class="work-card-subtitle">优先分析模拟持仓；若暂无持仓，则按自选股等权体检</div>
          </div>
          <button
            class="btn primary action-cta"
            :class="{ loading: healthLoading }"
            :disabled="healthLoading || !watchlistItems.length"
            @click="loadHealth"
          >
            {{ healthLoading ? '体检中...' : '立即体检' }}
          </button>
        </div>

        <template v-if="healthReport">
          <div class="health-overview-card">
            <div class="health-top">
              <div class="health-score" :class="riskTone(healthReport.healthScore)">{{ healthReport.healthScore }}</div>
              <div class="health-copy">
                <div class="summary-text">{{ healthReport.summary }}</div>
                <div class="source-note">分析来源：{{ healthReport.source }}</div>
              </div>
            </div>

            <div class="health-metrics-grid">
              <div class="health-metric-card">
                <span>最大单股</span>
                <strong>{{ healthReport.metrics.maxStockWeight }}%</strong>
                <small>单一标的集中度</small>
              </div>
              <div class="health-metric-card">
                <span>最大行业</span>
                <strong>{{ healthReport.metrics.maxSectorWeight }}%</strong>
                <small>行业集中暴露</small>
              </div>
              <div class="health-metric-card">
                <span>热点暴露</span>
                <strong>{{ healthReport.metrics.hotStockRatio }}%</strong>
                <small>高情绪板块占比</small>
              </div>
            </div>
          </div>

          <div class="section-block health-radar-card">
            <div class="section-title">体检维度</div>
            <div class="radar-list">
              <div v-for="item in healthReport.radar" :key="item.label" class="radar-row">
                <span>{{ item.label }}</span>
                <div class="progress-track">
                  <div class="progress-bar" :style="{ width: `${item.score}%` }"></div>
                </div>
                <strong>{{ item.score }}</strong>
              </div>
            </div>
          </div>

          <div class="health-columns">
            <div class="section-block health-column-card">
              <div class="section-title">主要预警</div>
              <div v-if="healthReport.warnings.length" class="stack-list">
                <div v-for="warning in healthReport.warnings" :key="warning.title" class="warn-item" :class="warning.level">
                  <strong>{{ warning.title }}</strong>
                  <span>{{ warning.detail }}</span>
                </div>
              </div>
              <div v-else class="empty-note">当前没有明显结构性预警。</div>
            </div>

            <div class="section-block health-column-card">
              <div class="section-title">优化建议</div>
              <div class="stack-list">
                <div v-for="tip in healthReport.suggestions" :key="tip" class="plain-item">{{ tip }}</div>
              </div>
            </div>
          </div>

          <div class="section-block health-exposure-card">
            <div class="section-title">行业暴露</div>
            <div v-if="healthReport.sectorBreakdown.length" class="exposure-list">
              <div v-for="item in healthReport.sectorBreakdown" :key="item.name" class="exposure-item">
                <div class="exposure-head">
                  <span>{{ item.name }}</span>
                  <strong>{{ item.weight }}%</strong>
                </div>
                <div class="exposure-track">
                  <div class="exposure-fill" :style="{ width: `${Math.min(item.weight, 100)}%` }"></div>
                </div>
              </div>
            </div>
            <div v-else class="empty-note">暂无行业暴露数据。</div>
          </div>
        </template>
        <div v-else class="empty-note">添加自选股后即可运行组合体检。</div>
        <div v-if="healthDirty && healthReport" class="feedback">自选股、仓位或画像变化后，点击右上角“立即体检”再刷新报告。</div>
        <div v-if="healthError" class="feedback error">{{ healthError }}</div>
      </article>

      <article class="work-card">
        <div class="work-card-head">
          <div>
            <div class="work-card-title">模拟交易 + AI 复盘</div>
            <div class="work-card-subtitle">按 A 股整手模拟下单，并强制记录交易理由</div>
          </div>
          <button
            class="btn danger action-pill action-cta"
            :class="{ loading: simLoading }"
            :disabled="simLoading"
            @click="resetSimulation"
          >
            重置 10 万账户
          </button>
        </div>

        <div v-if="simSnapshot" class="account-grid">
          <div class="account-box">
            <span>总资产</span>
            <strong>{{ formatCurrency(simSnapshot.account.equity) }}</strong>
          </div>
          <div class="account-box">
            <span>现金</span>
            <strong>{{ formatCurrency(simSnapshot.account.cash) }}</strong>
          </div>
          <div class="account-box">
            <span>持仓市值</span>
            <strong>{{ formatCurrency(simSnapshot.account.positionValue) }}</strong>
          </div>
          <div class="account-box">
            <span>累计盈亏</span>
            <strong :class="riskTone(simSnapshot.account.totalPnl >= 0 ? 82 : 45)">{{ formatCurrency(simSnapshot.account.totalPnl) }}</strong>
          </div>
        </div>

          <div class="mini-form trade-form">
            <label class="field-card">
              <span class="field-label">交易标的</span>
              <div class="select-shell">
              <select v-model="tradeForm.stockCode" class="glass-select">
                <option v-for="stock in watchlistItems" :key="stock.code" :value="stock.code">{{ stock.name }} ({{ stock.code }})</option>
              </select>
            </div>
          </label>

          <div class="field-card">
            <span class="field-label">交易方向</span>
            <div class="segmented-row">
              <button
                v-for="option in tradeSideOptions"
                :key="option.value"
                type="button"
                class="segmented-btn"
                :class="{ active: tradeForm.side === option.value }"
                @click="tradeForm.side = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

            <label class="field-card">
              <span class="field-label">数量</span>
              <input v-model.number="tradeForm.quantity" class="glass-input" type="number" min="100" step="100" />
            </label>

            <Transition name="trade-extra">
              <div v-if="isBuySide" class="trade-extra-grid full-line">
                <div class="field-card full-line">
                  <span class="field-label">计划周期</span>
                  <div class="choice-grid trade-cycle-grid">
                    <button
                      v-for="option in tradeHorizonOptions"
                      :key="option.value"
                      type="button"
                      class="choice-pill cycle-pill"
                      :class="{ active: tradeForm.planHorizon === option.value }"
                      @click="tradeForm.planHorizon = option.value"
                    >
                      <strong>{{ option.label }}</strong>
                      <small>{{ option.hint }}</small>
                    </button>
                  </div>
                </div>

                <label class="field-card">
                  <span class="field-label">止盈计划</span>
                  <input v-model="tradeForm.takeProfit" class="glass-input" type="text" />
                </label>

                <label class="field-card">
                  <span class="field-label">止损计划</span>
                  <input v-model="tradeForm.stopLoss" class="glass-input" type="text" />
                </label>
              </div>
            </Transition>

            <label class="field-card full-line trade-rationale-card">
              <span class="field-label">买卖理由</span>
              <textarea
              v-model="tradeForm.rationale"
              class="glass-textarea"
              rows="3"
              placeholder="例如：板块联动增强，打算做一段波段；若跌破关键位则止损，并在复盘里检查执行纪律。"
            ></textarea>
          </label>

          </div>

        <div class="action-row action-row-center">
          <button class="btn primary submit-strip" :disabled="simLoading || !watchlistItems.length" @click="submitTrade">
            {{ simLoading ? '提交中...' : '提交模拟交易' }}
          </button>
        </div>

        <div class="section-block">
          <div class="section-title">当前持仓</div>
          <div v-if="currentPositions.length" class="stack-list">
            <div v-for="position in currentPositions" :key="position.code" class="position-item">
              <div>
                <strong>{{ position.name }}</strong>
                <span>{{ position.code }} · {{ position.sectorName }}</span>
              </div>
              <div class="position-meta">
                <span>{{ position.quantity }} 股</span>
                <span>{{ position.planHorizon }}</span>
                <span>{{ formatRatio(position.pnlRatio) }}</span>
                <button class="btn small" :disabled="reviewLoading" @click="loadReview(position.code)">AI复盘</button>
              </div>
            </div>
          </div>
          <div v-else class="empty-note">当前还没有模拟持仓，先用上面的表单试一次下单。</div>
        </div>

        <div v-if="tradeReview" class="section-block review-box">
          <div class="section-title">最新复盘</div>
          <div class="summary-text">{{ tradeReview.summary }}</div>
          <div class="stat-row">
            <div class="stat-chip">{{ tradeReview.thesisStatus }}</div>
            <div class="stat-chip">纪律分 {{ tradeReview.disciplineScore }}</div>
            <div class="stat-chip">情绪风险 {{ tradeReview.emotionRisk }}</div>
          </div>
          <div class="stack-list">
            <div v-for="item in tradeReview.improvements" :key="item" class="plain-item">{{ item }}</div>
          </div>
        </div>

        <div v-if="recentTrades.length" class="section-block">
          <div class="section-title">最近交易</div>
          <div class="stack-list">
            <div v-for="trade in recentTrades" :key="trade.id" class="plain-item">
              {{ trade.createdAt }} · {{ trade.stockName }} · {{ trade.side === 'buy' ? '买入' : '卖出' }} {{ trade.quantity }} 股
            </div>
          </div>
        </div>

        <div v-if="simError" class="feedback error">{{ simError }}</div>
        <div v-if="reviewError" class="feedback error">{{ reviewError }}</div>
      </article>

      <article class="work-card">
        <div class="work-card-head">
          <div>
            <div class="work-card-title">异动原因解释引擎</div>
            <div class="work-card-subtitle">把价格、量能、板块联动、新闻公告串成可解释结论</div>
          </div>
          <button
            class="btn primary action-cta"
            :class="{ loading: explainLoading }"
            :disabled="explainLoading || !explainStock"
            @click="loadExplain(explainStock?.code)"
          >
            {{ explainLoading ? '解释中...' : '解释异动' }}
          </button>
        </div>

        <label class="field-card selector-card">
          <span class="field-label">切换分析标的</span>
          <div class="selector-shell">
            <div class="selector-caption">从自选池中选择一个标的，生成对应的异动解释。</div>
            <div class="select-shell">
              <select v-model="explainStockCode" class="glass-select">
                <option v-for="stock in watchlistItems" :key="stock.code" :value="stock.code">{{ stock.name }} ({{ stock.code }})</option>
              </select>
            </div>
          </div>
          <span class="field-note">支持在用户自选池范围内切换股票后重新解释异动。</span>
        </label>

        <div v-if="explainStock" class="focus-stock">当前分析标的：<strong>{{ explainStock.name }}</strong>（{{ explainStock.code }}）</div>

        <template v-if="anomalyReport">
          <div class="profile-box">
            <div class="score-badge" :class="riskTone(Math.round(anomalyReport.confidence * 100))">{{ anomalyReport.signalType }}</div>
            <div class="summary-text">{{ anomalyReport.summary }}</div>
            <div class="stat-row">
              <div class="stat-chip">置信度 {{ Math.round(anomalyReport.confidence * 100) }}%</div>
              <div class="stat-chip">情绪 {{ anomalyReport.stock.sentiment }}</div>
              <div class="stat-chip">{{ anomalyReport.stock.sectorName }}</div>
            </div>
          </div>

          <div class="section-block">
            <div class="section-title">证据链</div>
            <div class="stack-list">
              <div v-for="item in anomalyReport.evidenceItems" :key="item" class="plain-item">{{ item }}</div>
            </div>
          </div>

          <div v-if="anomalyReport.newsItems.length" class="section-block">
            <div class="section-title">相关消息</div>
            <div class="stack-list">
              <div v-for="item in anomalyReport.newsItems" :key="item.title" class="plain-item">
                {{ item.title }}
              </div>
            </div>
          </div>

          <div v-if="anomalyReport.announcementTitles.length" class="section-block">
            <div class="section-title">相关公告</div>
            <div class="stack-list">
              <div v-for="item in anomalyReport.announcementTitles" :key="item" class="plain-item">{{ item }}</div>
            </div>
          </div>

          <div v-if="anomalyReport.riskFlags.length" class="section-block">
            <div class="section-title">风险提醒</div>
            <div class="stack-list">
              <div v-for="item in anomalyReport.riskFlags" :key="item" class="warn-item medium">{{ item }}</div>
            </div>
          </div>
        </template>
        <div v-if="explainDirty && anomalyReport" class="feedback">标的或行情变化后，点击右上角“解释异动”再刷新说明。</div>
        <div v-if="!anomalyReport" class="empty-note">选择自选股后点击“解释异动”，即可生成可解释说明。</div>
        <div v-if="explainError" class="feedback error">{{ explainError }}</div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.workbench-panel {
  margin-top: 12px;
  height: clamp(920px, 104vh, 1420px);
}

.workbench-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #b8ccea transparent;
}

.workbench-grid::-webkit-scrollbar {
  width: 9px;
}

.workbench-grid::-webkit-scrollbar-track {
  background: transparent;
}

.workbench-grid::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #c5d8f5, #9fbde8);
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: content-box;
}

.workbench-grid::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, #afcaef, #84aee3);
  background-clip: content-box;
}

.work-card {
  border: 1px solid rgba(132, 172, 234, 0.38);
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.72), transparent 28%),
    linear-gradient(180deg, rgba(240, 248, 255, 0.8), rgba(224, 239, 255, 0.64));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.74),
    0 16px 28px rgba(28, 61, 116, 0.1);
  padding: 14px;
  display: grid;
  gap: 12px;
}

.profile-work-card,
.health-work-card {
  height: clamp(560px, 78vh, 760px);
  overflow-y: auto;
  align-content: start;
  scrollbar-width: thin;
  scrollbar-color: #b8ccea transparent;
}

.profile-work-card::-webkit-scrollbar,
.health-work-card::-webkit-scrollbar {
  width: 8px;
}

.profile-work-card::-webkit-scrollbar-track,
.health-work-card::-webkit-scrollbar-track {
  background: transparent;
}

.profile-work-card::-webkit-scrollbar-thumb,
.health-work-card::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #c5d8f5, #9fbde8);
  border-radius: 999px;
}

.work-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.work-card-title {
  font-size: 16px;
  font-weight: 800;
  color: #173354;
}

.work-card-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(45, 73, 108, 0.78);
  line-height: 1.5;
}

.mini-form,
.profile-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.field-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(133, 173, 232, 0.32);
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(232, 244, 255, 0.84));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    0 10px 20px rgba(30, 74, 141, 0.08);
}

.field-label {
  font-size: 12px;
  font-weight: 700;
  color: #244c79;
  letter-spacing: 0.02em;
}

.field-note {
  font-size: 12px;
  line-height: 1.6;
  color: rgba(36, 66, 96, 0.76);
}

.choice-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(136px, 1fr));
  gap: 8px;
}

.compact-grid {
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
}

.choice-pill,
.segmented-btn {
  appearance: none;
  border: 1px solid rgba(128, 168, 224, 0.3);
  border-radius: 16px;
  padding: 11px 12px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.86), rgba(236, 246, 255, 0.72));
  color: #244260;
  text-align: left;
  display: grid;
  gap: 4px;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

.choice-pill:hover,
.segmented-btn:hover {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.4);
  box-shadow: 0 10px 18px rgba(45, 94, 167, 0.12);
}

.choice-pill strong,
.segmented-btn strong {
  font-size: 13px;
  font-weight: 700;
}

.choice-pill small {
  font-size: 11px;
  line-height: 1.45;
  color: rgba(43, 70, 103, 0.72);
}

.choice-pill.active,
.segmented-btn.active {
  border-color: rgba(76, 149, 255, 0.66);
  background:
    linear-gradient(145deg, rgba(217, 239, 255, 0.95), rgba(179, 223, 255, 0.9));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.76),
    0 12px 22px rgba(52, 127, 216, 0.18);
  color: #0f4788;
}

.select-shell {
  position: relative;
}

.select-shell::after {
  content: '';
  position: absolute;
  right: 14px;
  top: 50%;
  width: 8px;
  height: 8px;
  border-right: 2px solid rgba(36, 76, 121, 0.7);
  border-bottom: 2px solid rgba(36, 76, 121, 0.7);
  transform: translateY(-60%) rotate(45deg);
  pointer-events: none;
}

.glass-select,
.glass-input,
.glass-textarea {
  width: 100%;
  border: 1px solid rgba(146, 183, 236, 0.4);
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 13px;
  color: #173354;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.glass-select {
  appearance: none;
  padding-right: 38px;
}

.glass-select:focus,
.glass-input:focus,
.glass-textarea:focus {
  outline: none;
  border-color: rgba(59, 130, 246, 0.52);
  box-shadow:
    0 0 0 3px rgba(96, 165, 250, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.glass-textarea {
  resize: vertical;
  min-height: 92px;
  font-family: inherit;
  line-height: 1.6;
}

.segmented-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  min-height: 52px;
}

.segmented-btn {
  text-align: center;
  place-items: center;
  min-height: 52px;
  height: 52px;
  width: 100%;
  transform-origin: center;
}

.trade-cycle-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.cycle-pill {
  min-height: 82px;
  align-content: center;
}

.full-line {
  grid-column: 1 / -1;
}

.profile-box,
.review-box {
  border: 1px solid rgba(122, 170, 235, 0.32);
  border-radius: 16px;
  padding: 14px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(235, 246, 255, 0.9));
  display: grid;
  gap: 10px;
}

.enriched-box {
  gap: 12px;
}

.profile-topline {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.score-badge {
  width: fit-content;
  padding: 6px 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #244c79;
  background: #e6f0ff;
}

.source-pill {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(132, 172, 234, 0.35);
  font-size: 12px;
  color: #244260;
}

.score-badge.good {
  color: #0f766e;
  background: rgba(16, 185, 129, 0.15);
}

.score-badge.warn {
  color: #9a5b00;
  background: rgba(245, 158, 11, 0.16);
}

.score-badge.bad {
  color: #b42318;
  background: rgba(239, 68, 68, 0.16);
}

.score-line,
.source-note,
.focus-stock {
  font-size: 12px;
  color: rgba(43, 70, 103, 0.8);
}

.summary-text {
  font-size: 13px;
  line-height: 1.6;
  color: #244260;
}

.analysis-note {
  font-size: 12px;
  line-height: 1.65;
  color: rgba(35, 67, 101, 0.84);
}

.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.stat-chip {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(132, 172, 234, 0.35);
  font-size: 12px;
  color: #244260;
}

.soft-chip {
  background: rgba(244, 250, 255, 0.86);
}

.health-overview-card,
.health-radar-card,
.health-column-card,
.health-exposure-card,
.selector-card {
  border: 1px solid rgba(132, 172, 234, 0.28);
  border-radius: 18px;
  background:
    linear-gradient(150deg, rgba(255, 255, 255, 0.9), rgba(236, 246, 255, 0.82));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 12px 22px rgba(34, 79, 144, 0.08);
  padding: 14px;
  align-content: start;
}

.health-top {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
  align-items: start;
}

.health-score {
  min-width: 72px;
  height: 72px;
  border-radius: 20px;
  display: grid;
  place-items: center;
  font-size: 28px;
  font-weight: 800;
  color: #244260;
  background: rgba(230, 240, 255, 0.95);
}

.health-score.good {
  color: #0f766e;
  background: rgba(16, 185, 129, 0.15);
}

.health-score.warn {
  color: #9a5b00;
  background: rgba(245, 158, 11, 0.16);
}

.health-score.bad {
  color: #b42318;
  background: rgba(239, 68, 68, 0.16);
}

.health-metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
  align-items: start;
}

.health-metric-card {
  border-radius: 16px;
  border: 1px solid rgba(132, 172, 234, 0.26);
  background: rgba(255, 255, 255, 0.78);
  padding: 12px;
  display: grid;
  gap: 4px;
  align-content: start;
}

.health-metric-card span,
.selector-caption {
  font-size: 12px;
  color: rgba(43, 70, 103, 0.74);
}

.health-metric-card strong {
  font-size: 22px;
  font-weight: 800;
  color: #173354;
}

.health-metric-card small {
  font-size: 11px;
  color: rgba(43, 70, 103, 0.68);
}

.radar-list,
.stack-list {
  display: grid;
  gap: 8px;
}

.radar-row {
  display: grid;
  grid-template-columns: 68px 1fr auto;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: #2c4b74;
}

.progress-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(191, 213, 245, 0.5);
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #22c55e, #3b82f6);
}

.section-block {
  display: grid;
  gap: 8px;
}

.compact-block {
  gap: 6px;
}

.health-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #173354;
}

.warn-item,
.plain-item,
.position-item {
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.55;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(132, 172, 234, 0.28);
  color: #274362;
}

.warn-item {
  display: grid;
  gap: 4px;
}

.warn-item.high {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(254, 242, 242, 0.92);
}

.warn-item.medium {
  border-color: rgba(245, 158, 11, 0.34);
  background: rgba(255, 247, 237, 0.92);
}

.exposure-list {
  display: grid;
  gap: 10px;
}

.exposure-item {
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(132, 172, 234, 0.22);
  padding: 12px;
  display: grid;
  gap: 8px;
}

.exposure-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  color: #274362;
}

.exposure-head strong {
  font-size: 14px;
  color: #173354;
}

.exposure-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(187, 210, 243, 0.58);
  overflow: hidden;
}

.exposure-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #38bdf8, #2563eb);
}

.selector-card {
  gap: 12px;
}

.selector-shell {
  display: grid;
  gap: 10px;
}

.selector-card .glass-select {
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.97), rgba(244, 250, 255, 0.95));
  border-color: rgba(124, 172, 239, 0.42);
  min-height: 56px;
  font-size: 14px;
  font-weight: 700;
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.account-box {
  border: 1px solid rgba(132, 172, 234, 0.3);
  border-radius: 14px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.84);
  display: grid;
  gap: 5px;
}

.account-box span {
  font-size: 12px;
  color: rgba(43, 70, 103, 0.74);
}

.account-box strong {
  font-size: 16px;
  color: #173354;
}

.trade-form {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
}

.trade-rationale-card {
  grid-column: 1 / -1;
}

.trade-extra-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  align-items: start;
}

.action-row {
  display: flex;
}

.action-row-center {
  justify-content: center;
}

.submit-strip {
  min-width: 240px;
  padding: 14px 22px;
  border-radius: 16px;
}

.action-pill {
  min-width: 148px;
  padding: 10px 18px;
  border-radius: 16px;
}

.btn.danger {
  background: linear-gradient(135deg, rgba(248, 113, 113, 0.96), rgba(220, 38, 38, 0.96));
  color: #ffffff;
  border-color: rgba(255, 218, 218, 0.92);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.28),
    0 10px 20px rgba(220, 38, 38, 0.28);
}

.btn.danger:hover {
  background: linear-gradient(135deg, rgba(248, 113, 113, 1), rgba(220, 38, 38, 1));
  color: #ffffff;
  border-color: rgba(255, 226, 226, 1);
}

.btn.danger:focus-visible {
  box-shadow:
    0 0 0 3px rgba(248, 113, 113, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.32),
    0 10px 20px rgba(220, 38, 38, 0.3);
}

.action-cta {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  --cta-shadow-rest: rgba(23, 119, 225, 0.22);
  --cta-shadow-float: rgba(23, 119, 225, 0.32);
}

.action-cta::before {
  content: '';
  position: absolute;
  inset: -1px auto -1px -38%;
  width: 34%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.34), transparent);
  transform: skewX(-20deg) translateX(-220%);
  transition: transform 0.52s ease;
  pointer-events: none;
  z-index: -1;
}

.action-cta:hover::before,
.action-cta:focus-visible::before {
  transform: skewX(-20deg) translateX(420%);
}

.action-cta.loading {
  animation: ctaPulse 1.35s ease-in-out infinite;
}

.btn.danger.action-cta {
  --cta-shadow-rest: rgba(220, 38, 38, 0.28);
  --cta-shadow-float: rgba(220, 38, 38, 0.36);
}

.trade-extra-enter-active,
.trade-extra-leave-active {
  transition:
    opacity 0.24s ease,
    transform 0.24s ease,
    max-height 0.24s ease;
  overflow: hidden;
}

.trade-extra-enter-from,
.trade-extra-leave-to {
  opacity: 0;
  transform: translateY(-10px);
  max-height: 0;
}

.trade-extra-enter-to,
.trade-extra-leave-from {
  opacity: 1;
  transform: translateY(0);
  max-height: 360px;
}

.position-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.position-item > div {
  display: grid;
  gap: 3px;
}

.position-item span {
  font-size: 12px;
  color: rgba(43, 70, 103, 0.76);
}

.position-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.feedback {
  font-size: 12px;
  color: rgba(43, 70, 103, 0.78);
}

.feedback.error {
  color: #b42318;
}

.empty-note {
  border: 1px dashed rgba(132, 172, 234, 0.46);
  border-radius: 14px;
  padding: 12px;
  font-size: 13px;
  color: rgba(43, 70, 103, 0.76);
  background: rgba(255, 255, 255, 0.72);
}

.btn.small {
  min-width: auto;
  padding: 5px 9px;
  font-size: 12px;
}

@keyframes ctaPulse {
  0%,
  100% {
    transform: translateY(0);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.32),
      0 10px 20px var(--cta-shadow-rest);
  }

  50% {
    transform: translateY(-1px);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.38),
      0 14px 24px var(--cta-shadow-float);
  }
}

@media (max-width: 1180px) {
  .workbench-panel {
    height: clamp(980px, 118vh, 1600px);
  }

  .workbench-grid {
    grid-template-columns: 1fr;
  }

  .trade-cycle-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trade-extra-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .mini-form,
  .profile-form-grid,
  .trade-form,
  .account-grid,
  .health-metrics-grid,
  .health-columns {
    grid-template-columns: 1fr;
  }

  .profile-work-card,
  .health-work-card {
    height: auto;
    overflow: visible;
  }

  .trade-cycle-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .workbench-panel {
    height: auto;
  }

  .work-card-head,
  .position-item,
  .health-top {
    display: grid;
    grid-template-columns: 1fr;
  }

  .choice-grid,
  .compact-grid,
  .trade-cycle-grid,
  .segmented-row {
    grid-template-columns: 1fr;
  }

  .submit-strip,
  .action-pill {
    width: 100%;
  }
}
</style>
