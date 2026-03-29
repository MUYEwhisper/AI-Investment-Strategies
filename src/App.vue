<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

type Stock = {
  id: string
  name: string
  code: string
  price: number
  change: number
  turnover: string
  pe: string
  pb: string
  marketCap: string
  volumeRatio: string
  mainFlow: string
  sentiment: string
  tags: string[]
}

type SectorData = {
  labels: string[]
  flow: number[]
  heat: number[]
  sentiment: number[]
  insights: string[]
}

type ChatMessage = {
  role: 'user' | 'ai'
  content: string
}

type SseFrame = {
  event: string
  data: string
}

type ChatSession = {
  id: string
  title: string
  createdAt: string
  messages: ChatMessage[]
}

type ChartInstance = {
  destroy: () => void
}

type ChartCtor = new (
  item: HTMLCanvasElement,
  config: {
    type: string
    data: Record<string, unknown>
    options: Record<string, unknown>
  },
) => ChartInstance

const STOCK_TRANSITION_MS = 240
const LIST_ITEM_ANIM_MS = 220
const CHAT_SWITCH_MS = 220
const STORAGE_KEY = 'ai_invest_chat_history'
const AI_CHAT_ENDPOINT = (import.meta.env.VITE_AI_CHAT_ENDPOINT as string | undefined) ?? '/chat/endpoint'

const addStockFormRef = ref<HTMLElement | null>(null)
const watchlistViewRef = ref<HTMLElement | null>(null)
const stockDetailViewRef = ref<HTMLElement | null>(null)
const messagesPanelRef = ref<HTMLElement | null>(null)
const flowCanvasRef = ref<HTMLCanvasElement | null>(null)
const sentimentCanvasRef = ref<HTMLCanvasElement | null>(null)

const stockInput = ref('')
const chatInput = ref('')

const enteringStockId = ref<string | null>(null)
const leavingStockId = ref<string | null>(null)
const enteringChatId = ref<string | null>(null)
const leavingChatId = ref<string | null>(null)

const selectedStockId = ref<string | null>(null)
const isDetailVisible = ref(false)
const isStockTransitioning = ref(false)

const chats = ref<ChatSession[]>([])
const activeChatId = ref<string | null>(null)
const isChatSwitching = ref(false)
const bubbleAnimationEnabled = ref(false)
const isAiResponding = ref(false)
const useThinking = ref(true)
const streamHint = ref('')

let flowChart: ChartInstance | null = null
let sentimentChart: ChartInstance | null = null
let chartLoadPromise: Promise<void> | null = null
let activeAiAbortController: AbortController | null = null

const watchlist = ref<Stock[]>([
  {
    id: '',
    name: '贵州茅台',
    code: '600519',
    price: 1765.52,
    change: 1.68,
    turnover: '2.83%',
    pe: '29.4',
    pb: '9.1',
    marketCap: '2.22万亿',
    volumeRatio: '1.08',
    mainFlow: '+3.5亿',
    sentiment: '偏强',
    tags: ['白酒龙头', '北向关注', '高ROE'],
  },
  {
    id: '',
    name: '宁德时代',
    code: '300750',
    price: 204.33,
    change: -0.92,
    turnover: '3.52%',
    pe: '22.1',
    pb: '4.8',
    marketCap: '0.90万亿',
    volumeRatio: '0.93',
    mainFlow: '-1.2亿',
    sentiment: '震荡',
    tags: ['储能', '新能源车', '机构重仓'],
  },
  {
    id: '',
    name: '中际旭创',
    code: '300308',
    price: 147.09,
    change: 3.22,
    turnover: '9.37%',
    pe: '35.7',
    pb: '7.3',
    marketCap: '0.12万亿',
    volumeRatio: '1.35',
    mainFlow: '+4.1亿',
    sentiment: '强势',
    tags: ['CPO', '算力', '高弹性'],
  },
])

const sectorTemplate: SectorData = {
  labels: ['半导体', 'AI算力', '创新药', '低空经济', '券商', '机器人'],
  flow: [28, 21, -6, 15, -3, 12],
  heat: [86, 80, 48, 72, 43, 67],
  sentiment: [78, 74, 61, 66, 58, 63],
  insights: [
    '主线资金继续围绕科技成长，AI算力和半导体获得持续增量资金。',
    '情绪指标位于中高位，短线分歧加大，追高需控制仓位。',
    '政策风向偏向科技自主可控与新质生产力，产业链龙头受益更明确。',
    '顺周期板块资金承接偏弱，建议观察成交量能否持续修复。',
  ],
}

const sectorData = ref<SectorData>(cloneSectorData(sectorTemplate))

watchlist.value.forEach((stock) => {
  stock.id = createUid('stock')
})

const selectedStock = computed(() =>
  watchlist.value.find((stock) => stock.id === selectedStockId.value),
)

const detailKpis = computed(() => {
  const stock = selectedStock.value
  if (!stock) return [] as { label: string; value: string }[]

  return [
    { label: '成交额换手', value: stock.turnover },
    { label: '市盈率(PE)', value: stock.pe },
    { label: '市净率(PB)', value: stock.pb },
    { label: '总市值', value: stock.marketCap },
    { label: '量比', value: stock.volumeRatio },
    { label: '主力净流入', value: stock.mainFlow },
    { label: '短线情绪', value: stock.sentiment },
  ]
})

const summaryList = computed(() =>
  sectorData.value.labels.map((name, index) => ({
    name,
    heat: sectorData.value.heat[index],
  })),
)

const activeChat = computed(() => chats.value.find((chat) => chat.id === activeChatId.value) ?? null)

function createUid(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 1e7)}`
}

function createDefaultAiMessage(): ChatMessage {
  return {
    role: 'ai',
    content: '你好，我是投资分析助手。你可以问我：个股风险、仓位建议、板块轮动判断等问题。',
  }
}

function cloneSectorData(data: SectorData): SectorData {
  return JSON.parse(JSON.stringify(data)) as SectorData
}

function changeClass(value: number): 'up' | 'down' {
  return value >= 0 ? 'up' : 'down'
}

function formatChange(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function clearStockAnimClass(el: HTMLElement | null): void {
  if (!el) return
  el.classList.remove('view-enter-from-right', 'view-enter-from-left', 'view-exit-to-left', 'view-exit-to-right')
}

function showStockDetailById(stockId: string): void {
  if (isStockTransitioning.value) return
  const stock = watchlist.value.find((item) => item.id === stockId)
  if (!stock) return

  selectedStockId.value = stock.id
  isStockTransitioning.value = true

  const addFormEl = addStockFormRef.value
  const watchlistEl = watchlistViewRef.value
  const detailEl = stockDetailViewRef.value

  clearStockAnimClass(addFormEl)
  clearStockAnimClass(watchlistEl)
  clearStockAnimClass(detailEl)

  addFormEl?.classList.add('view-exit-to-left')
  watchlistEl?.classList.add('view-exit-to-left')

  window.setTimeout(() => {
    isDetailVisible.value = true

    nextTick(() => {
      const nextDetailEl = stockDetailViewRef.value
      clearStockAnimClass(addStockFormRef.value)
      clearStockAnimClass(watchlistViewRef.value)
      clearStockAnimClass(nextDetailEl)
      nextDetailEl?.classList.add('view-enter-from-right')
    })

    window.setTimeout(() => {
      clearStockAnimClass(stockDetailViewRef.value)
      isStockTransitioning.value = false
    }, STOCK_TRANSITION_MS)
  }, STOCK_TRANSITION_MS)
}

function backToWatchlist(): void {
  if (isStockTransitioning.value) return
  isStockTransitioning.value = true

  const detailEl = stockDetailViewRef.value
  clearStockAnimClass(detailEl)
  detailEl?.classList.add('view-exit-to-right')

  window.setTimeout(() => {
    isDetailVisible.value = false

    nextTick(() => {
      const addFormEl = addStockFormRef.value
      const watchlistEl = watchlistViewRef.value
      clearStockAnimClass(addFormEl)
      clearStockAnimClass(watchlistEl)
      addFormEl?.classList.add('view-enter-from-left')
      watchlistEl?.classList.add('view-enter-from-left')
    })

    window.setTimeout(() => {
      clearStockAnimClass(addStockFormRef.value)
      clearStockAnimClass(watchlistViewRef.value)
      isStockTransitioning.value = false
    }, STOCK_TRANSITION_MS)
  }, STOCK_TRANSITION_MS)
}

function addStock(): void {
  const value = stockInput.value.trim()
  if (!value) return

  const isCode = /^\d{6}$/.test(value)
  const randomChange = (Math.random() * 8 - 4).toFixed(2)
  const sentimentPool = ['偏强', '中性', '震荡', '转弱']
  const randomSentiment = sentimentPool[Math.floor(Math.random() * sentimentPool.length)] ?? '中性'
  const newStock: Stock = {
    id: createUid('stock'),
    name: isCode ? `股票${value}` : value,
    code: isCode ? value : String(Math.floor(100000 + Math.random() * 900000)),
    price: Number((Math.random() * 150 + 10).toFixed(2)),
    change: Number(randomChange),
    turnover: `${(Math.random() * 8 + 1).toFixed(2)}%`,
    pe: (Math.random() * 60 + 10).toFixed(1),
    pb: (Math.random() * 10 + 1).toFixed(1),
    marketCap: `${(Math.random() * 1.2 + 0.05).toFixed(2)}万亿`,
    volumeRatio: (Math.random() * 2 + 0.5).toFixed(2),
    mainFlow: `${Math.random() > 0.5 ? '+' : '-'}${(Math.random() * 5).toFixed(1)}亿`,
    sentiment: randomSentiment,
    tags: ['新添加', '待跟踪'],
  }

  watchlist.value.unshift(newStock)
  stockInput.value = ''
  enteringStockId.value = newStock.id
  window.setTimeout(() => {
    if (enteringStockId.value === newStock.id) enteringStockId.value = null
  }, 320)
}

function onStockInputKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') addStock()
}

function deleteStock(stockId: string): void {
  if (isStockTransitioning.value || leavingStockId.value) return
  leavingStockId.value = stockId

  window.setTimeout(() => {
    watchlist.value = watchlist.value.filter((stock) => stock.id !== stockId)
    if (selectedStockId.value === stockId) {
      selectedStockId.value = null
      isDetailVisible.value = false
    }
    leavingStockId.value = null
  }, LIST_ITEM_ANIM_MS)
}

function getChartCtor(): ChartCtor | null {
  const maybeChart = (window as unknown as { Chart?: ChartCtor }).Chart
  return maybeChart ?? null
}

function ensureChartJsLoaded(): Promise<void> {
  if (getChartCtor()) return Promise.resolve()
  if (chartLoadPromise) return chartLoadPromise

  chartLoadPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById('chartjs-cdn-script') as HTMLScriptElement | null
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('加载 Chart.js 失败')), { once: true })
      return
    }

    const script = document.createElement('script')
    script.id = 'chartjs-cdn-script'
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('加载 Chart.js 失败'))
    document.head.appendChild(script)
  })

  return chartLoadPromise
}

function renderSectorCharts(): void {
  const Chart = getChartCtor()
  if (!Chart || !flowCanvasRef.value || !sentimentCanvasRef.value) return

  flowChart?.destroy()
  sentimentChart?.destroy()

  flowChart = new Chart(flowCanvasRef.value, {
    type: 'doughnut',
    data: {
      labels: sectorData.value.labels,
      datasets: [
        {
          label: '资金关注度',
          data: sectorData.value.flow.map((n) => Math.abs(n)),
          backgroundColor: ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#14b8a6'],
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '52%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 10, font: { size: 11 } },
        },
      },
    },
  })

  sentimentChart = new Chart(sentimentCanvasRef.value, {
    type: 'pie',
    data: {
      labels: sectorData.value.labels,
      datasets: [
        {
          label: '市场情绪',
          data: sectorData.value.sentiment,
          backgroundColor: ['#0ea5e9', '#22c55e', '#f97316', '#eab308', '#a855f7', '#f43f5e'],
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 10, font: { size: 11 } },
        },
      },
    },
  })
}

function refreshSectorData(): void {
  const data = cloneSectorData(sectorTemplate)
  data.flow = data.flow.map((n) => Number((n + (Math.random() * 12 - 6)).toFixed(1)))
  data.heat = data.heat.map((n) => Math.max(15, Math.min(98, Math.round(n + (Math.random() * 16 - 8)))))
  data.sentiment = data.sentiment.map((n) => Math.max(20, Math.min(95, Math.round(n + (Math.random() * 12 - 6)))))
  sectorData.value = data
  renderSectorCharts()
}

function loadChats(): void {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    const parsed = saved ? (JSON.parse(saved) as ChatSession[]) : []

    chats.value = parsed.map((chat) => ({
      id: chat.id || createUid('chat'),
      title: chat.title || '新对话',
      createdAt: chat.createdAt || new Date().toLocaleString(),
      messages:
        Array.isArray(chat.messages) && chat.messages.length
          ? chat.messages
          : [createDefaultAiMessage()],
    }))
  } catch {
    chats.value = []
  }

  if (!chats.value.length) {
    createNewChat(false)
    return
  }

  const firstChat = chats.value[0]
  if (!firstChat) return
  activeChatId.value = firstChat.id
  renderMessages(false)
}

function persistChats(): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.value))
}

function renderMessages(withBubbleAnim = false): void {
  bubbleAnimationEnabled.value = withBubbleAnim
  nextTick(() => {
    const panel = messagesPanelRef.value
    if (!panel) return
    panel.scrollTop = panel.scrollHeight
  })
}

function transitionToChat(chatId: string, enterChatId: string | null = null, withBubbleAnim = true): void {
  if (isChatSwitching.value || chatId === activeChatId.value) return

  const panel = messagesPanelRef.value
  isChatSwitching.value = true
  panel?.classList.remove('chat-switch-in', 'chat-switch-out')
  panel?.classList.add('chat-switch-out')

  window.setTimeout(() => {
    activeChatId.value = chatId
    enteringChatId.value = enterChatId
    renderMessages(withBubbleAnim)

    panel?.classList.remove('chat-switch-out')
    panel?.classList.add('chat-switch-in')

    window.setTimeout(() => {
      panel?.classList.remove('chat-switch-in')
      isChatSwitching.value = false
      enteringChatId.value = null
    }, CHAT_SWITCH_MS)
  }, CHAT_SWITCH_MS)
}

function createNewChat(withAnim = true): void {
  const id = createUid('chat')
  chats.value.unshift({
    id,
    title: '新对话',
    createdAt: new Date().toLocaleString(),
    messages: [createDefaultAiMessage()],
  })
  persistChats()

  if (!activeChatId.value || !withAnim) {
    activeChatId.value = id
    enteringChatId.value = id
    renderMessages(withAnim)
    window.setTimeout(() => {
      if (enteringChatId.value === id) enteringChatId.value = null
    }, 320)
    return
  }

  transitionToChat(id, id, true)
}

function onNewChatClick(): void {
  if (isAiResponding.value) return
  createNewChat(true)
}

function switchChat(chatId: string): void {
  if (isAiResponding.value) return
  transitionToChat(chatId, null, true)
}

function deleteChat(chatId: string): void {
  if (isAiResponding.value || isChatSwitching.value || leavingChatId.value) return

  leavingChatId.value = chatId
  const removingActive = chatId === activeChatId.value
  const panel = messagesPanelRef.value

  if (removingActive) {
    panel?.classList.remove('chat-switch-in', 'chat-switch-out')
    panel?.classList.add('chat-switch-out')
  }

  window.setTimeout(() => {
    chats.value = chats.value.filter((chat) => chat.id !== chatId)

    if (!chats.value.length) {
      activeChatId.value = null
      leavingChatId.value = null
      createNewChat(false)
      panel?.classList.remove('chat-switch-out')
      panel?.classList.add('chat-switch-in')
      window.setTimeout(() => panel?.classList.remove('chat-switch-in'), CHAT_SWITCH_MS)
      persistChats()
      return
    }

    if (removingActive) {
      const firstChat = chats.value[0]
      if (firstChat) activeChatId.value = firstChat.id
      renderMessages(true)
      panel?.classList.remove('chat-switch-out')
      panel?.classList.add('chat-switch-in')
      window.setTimeout(() => panel?.classList.remove('chat-switch-in'), CHAT_SWITCH_MS)
    }

    leavingChatId.value = null
    persistChats()
  }, LIST_ITEM_ANIM_MS)
}

function getChatById(chatId: string): ChatSession | null {
  return chats.value.find((chat) => chat.id === chatId) ?? null
}

function appendAiMessage(chatId: string, messageIndex: number, text: string): void {
  const chat = getChatById(chatId)
  const msg = chat?.messages[messageIndex]
  if (!chat || !msg || msg.role !== 'ai') return
  msg.content += text
}

function consumeSseFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n')
  const chunks = normalized.split('\n\n')
  const rest = chunks.pop() ?? ''
  const frames: SseFrame[] = []

  chunks.forEach((chunk) => {
    if (!chunk.trim()) return

    let event = 'message'
    const dataLines: string[] = []
    chunk.split('\n').forEach((line) => {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim()
      }
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }
    })

    if (!dataLines.length) return
    frames.push({ event, data: dataLines.join('\n') })
  })

  return { frames, rest }
}

function parseSseData(data: string): Record<string, unknown> | null {
  try {
    return JSON.parse(data) as Record<string, unknown>
  } catch {
    return null
  }
}

function handleSseFrame(chatId: string, messageIndex: number, frame: SseFrame): void {
  const payload = parseSseData(frame.data)

  if (frame.event === 'start') {
    const reasoningMode = payload?.reasoning === 'enabled' ? '已启用推理' : '已禁用推理'
    streamHint.value = `连接成功，${reasoningMode}`
    return
  }

  if (frame.event === 'reasoning') {
    const content = typeof payload?.content === 'string' ? payload.content : ''
    if (content) streamHint.value = `推理中：${content}`
    return
  }

  if (frame.event === 'tool_call') {
    const toolName = typeof payload?.name === 'string' ? payload.name : 'unknown_tool'
    streamHint.value = `调用工具：${toolName}`
    return
  }

  if (frame.event === 'tool_result') {
    if (typeof payload?.error === 'string' && payload.error) {
      streamHint.value = `工具返回错误：${payload.error}`
    } else {
      streamHint.value = '工具结果已返回'
    }
    return
  }

  if (frame.event === 'message') {
    const content = typeof payload?.content === 'string' ? payload.content : frame.data
    appendAiMessage(chatId, messageIndex, content)
    renderMessages(false)
    return
  }

  if (frame.event === 'error') {
    const message = typeof payload?.message === 'string' ? payload.message : '服务端返回错误'
    appendAiMessage(chatId, messageIndex, `\n\n[错误] ${message}`)
    renderMessages(false)
    return
  }

  if (frame.event === 'end') {
    const finishReason = typeof payload?.finish_reason === 'string' ? payload.finish_reason : 'stop'
    streamHint.value = `回复完成（${finishReason}）`
  }
}

async function streamChatBySse(chatId: string, messageIndex: number, prompt: string): Promise<void> {
  const controller = new AbortController()
  activeAiAbortController = controller

  const response = await fetch(AI_CHAT_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      prompt,
      stream: true,
      sse: true,
      thinking: useThinking.value,
    }),
    signal: controller.signal,
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `请求失败: ${response.status}`)
  }

  if (!response.body) {
    throw new Error('服务端未返回可读取的流')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const { frames, rest } = consumeSseFrames(buffer)
    buffer = rest

    frames.forEach((frame) => {
      handleSseFrame(chatId, messageIndex, frame)
    })
  }

  const tail = decoder.decode()
  if (tail) {
    buffer += tail
  }

  if (buffer.trim()) {
    const { frames } = consumeSseFrames(`${buffer}\n\n`)
    frames.forEach((frame) => {
      handleSseFrame(chatId, messageIndex, frame)
    })
  }
}

async function sendMessage(): Promise<void> {
  if (isAiResponding.value) return

  const text = chatInput.value.trim()
  if (!text || !activeChat.value) return

  const currentChatId = activeChat.value.id
  const targetChat = getChatById(currentChatId)
  if (!targetChat) return

  targetChat.messages.push({ role: 'user', content: text })
  if (targetChat.title === '新对话') {
    targetChat.title = text.slice(0, 14)
  }

  const aiMessageIndex = targetChat.messages.push({ role: 'ai', content: '' }) - 1

  chatInput.value = ''
  isAiResponding.value = true
  streamHint.value = '正在连接 AI 服务...'
  renderMessages(false)
  persistChats()

  try {
    await streamChatBySse(currentChatId, aiMessageIndex, text)

    const chat = getChatById(currentChatId)
    const msg = chat?.messages[aiMessageIndex]
    if (msg && !msg.content.trim()) {
      msg.content = '已接收请求，但模型未返回文本内容。'
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '请求失败'
    appendAiMessage(currentChatId, aiMessageIndex, `\n\n[连接失败] ${message}`)
  } finally {
    isAiResponding.value = false
    activeAiAbortController = null
    window.setTimeout(() => {
      streamHint.value = ''
    }, 1500)
    persistChats()
    renderMessages(false)
  }
}

function onChatInputKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

onMounted(async () => {
  loadChats()
  try {
    await ensureChartJsLoaded()
    renderSectorCharts()
  } catch {
    // Chart.js 加载失败时忽略，页面其它功能仍可用。
  }
})

onBeforeUnmount(() => {
  activeAiAbortController?.abort()
  flowChart?.destroy()
  sentimentChart?.destroy()
})
</script>

<template>
  <div class="app-page">
    <div class="app">
      <section class="top-grid">
        <article class="panel watchlist-wrap" id="watchlistPanel">
          <div class="panel-header">
            <div>
              <div class="panel-title">自选股区</div>
              <div class="panel-subtitle">添加/选择股票，查看该股参数与分析标签</div>
            </div>
          </div>

          <div
            v-show="!isDetailVisible"
            ref="addStockFormRef"
            class="add-stock"
            id="addStockForm"
          >
            <input
              v-model="stockInput"
              id="stockInput"
              type="text"
              placeholder="输入股票名或代码，如：贵州茅台 或 600519"
              @keydown="onStockInputKeydown"
            />
            <button
              class="btn primary"
              :class="{ active: !!stockInput.trim() }"
              id="addStockBtn"
              @click="addStock"
            >
              添加
            </button>
          </div>

          <div v-show="!isDetailVisible" ref="watchlistViewRef" class="watchlist-view" id="watchlistView">
            <div
              v-for="stock in watchlist"
              :key="stock.id"
              class="stock-item"
              :class="{
                'list-item-enter': stock.id === enteringStockId,
                'list-item-leave': stock.id === leavingStockId,
              }"
              @click="showStockDetailById(stock.id)"
            >
              <div class="stock-item-main">
                <div>
                  <strong>{{ stock.name }}</strong>
                </div>
                <div class="stock-code">{{ stock.code }}</div>
              </div>
              <div class="stock-item-actions">
                <div class="stock-change" :class="changeClass(stock.change)">
                  {{ formatChange(stock.change) }}
                </div>
                <button class="btn primary row-action-btn" type="button" @click.stop="deleteStock(stock.id)">
                  删除
                </button>
              </div>
            </div>
          </div>

          <div
            v-show="isDetailVisible && selectedStock"
            ref="stockDetailViewRef"
            class="stock-detail-view"
            :class="{ active: isDetailVisible }"
            id="stockDetailView"
          >
            <div class="detail-head">
              <div>
                <div class="detail-name" id="detailName">{{ selectedStock?.name ?? '--' }}</div>
                <div class="detail-code" id="detailCode">{{ selectedStock?.code ?? '--' }}</div>
              </div>
              <button class="btn" id="backToWatchlistBtn" @click="backToWatchlist">返回自选列表</button>
            </div>
            <div class="detail-price" id="detailPrice">
              {{ selectedStock ? `${selectedStock.price.toFixed(2)} 元` : '--' }}
            </div>
            <div class="stock-change" :class="changeClass(selectedStock?.change ?? 0)" id="detailChange">
              {{ selectedStock ? formatChange(selectedStock.change) : '--' }}
            </div>
            <div class="detail-tags" id="detailTags">
              <span v-for="tag in selectedStock?.tags ?? []" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <div class="detail-grid" id="detailGrid">
              <div v-for="item in detailKpis" :key="item.label" class="kpi">
                <div class="kpi-label">{{ item.label }}</div>
                <div class="kpi-value">{{ item.value }}</div>
              </div>
            </div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">板块分析区</div>
              <div class="panel-subtitle">概念板块/行业板块资金流向、情绪热度、政策风向</div>
            </div>
            <button class="btn" id="refreshSectorBtn" @click="refreshSectorData">刷新数据</button>
          </div>

          <div class="sector-body">
            <div class="chart-card">
              <div class="card-title">板块图表分析（直观饼图）</div>
              <div class="pie-grid">
                <div class="pie-box">
                  <div class="pie-title">资金关注度占比</div>
                  <div class="pie-wrap"><canvas ref="flowCanvasRef" id="flowChart"></canvas></div>
                </div>
                <div class="pie-box">
                  <div class="pie-title">市场情绪占比</div>
                  <div class="pie-wrap"><canvas ref="sentimentCanvasRef" id="sentimentChart"></canvas></div>
                </div>
              </div>
              <div class="summary-list" id="summaryList">
                <div v-for="item in summaryList" :key="item.name" class="summary-item">
                  {{ item.name }}：强弱评分 {{ item.heat }}
                </div>
              </div>
            </div>

            <div class="insight-card">
              <div class="card-title">市场情绪与政策风向解读</div>
              <div class="insight-list" id="insightList">
                <div v-for="line in sectorData.insights" :key="line" class="insight-item">{{ line }}</div>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section class="panel chat-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">AI 对话区</div>
            <div class="panel-subtitle">投资分析大模型交互（含历史对话侧栏）</div>
          </div>
        </div>

        <div class="chat-main">
          <aside class="chat-history">
            <div class="history-head">
              <strong style="font-size: 13px">历史对话</strong>
              <button class="btn" id="newChatBtn" :disabled="isAiResponding" @click="onNewChatClick">新建</button>
            </div>
            <div class="history-list" id="historyList">
              <div
                v-for="chat in chats"
                :key="chat.id"
                class="history-item"
                :class="{
                  active: chat.id === activeChatId,
                  'list-item-enter': chat.id === enteringChatId,
                  'list-item-leave': chat.id === leavingChatId,
                }"
                @click="switchChat(chat.id)"
              >
                <div class="history-meta">
                  <div class="history-title">{{ chat.title }}</div>
                  <div class="history-time">{{ chat.createdAt }}</div>
                </div>
                <button
                  class="btn primary row-action-btn"
                  type="button"
                  :disabled="isAiResponding"
                  @click.stop="deleteChat(chat.id)"
                >
                  删除
                </button>
              </div>
            </div>
          </aside>

          <div class="chat-body">
            <div class="chat-status">
              <label class="thinking-toggle">
                <input v-model="useThinking" type="checkbox" :disabled="isAiResponding" />
                推理模式
              </label>
              <span class="status-text">{{ streamHint || (isAiResponding ? '正在生成回复...' : '就绪') }}</span>
            </div>
            <div ref="messagesPanelRef" class="messages" id="messages">
              <div
                v-for="(msg, idx) in activeChat?.messages ?? []"
                :key="`${activeChat?.id ?? 'chat'}_${idx}`"
                class="msg"
                :class="{
                  user: msg.role === 'user',
                  ai: msg.role === 'ai',
                  'msg-enter': bubbleAnimationEnabled,
                }"
                :style="bubbleAnimationEnabled ? { '--msg-delay': `${Math.min(idx * 36, 220)}ms` } : {}"
              >
                {{ msg.content }}
              </div>
            </div>
            <div class="chat-input-wrap">
              <textarea
                v-model="chatInput"
                id="chatInput"
                placeholder="请输入你的问题，例如：结合半导体板块资金流向，给出仓位建议"
                :disabled="isAiResponding"
                @keydown="onChatInputKeydown"
              ></textarea>
              <button
                class="btn primary"
                :class="{ active: !!chatInput.trim() }"
                id="sendBtn"
                :disabled="isAiResponding"
                @click="sendMessage"
              >
                {{ isAiResponding ? '生成中...' : '发送' }}
              </button>
            </div>
            <div class="note">
              说明：当前已接入 SSE 流式对话。可通过环境变量 VITE_AI_CHAT_ENDPOINT 配置后端地址，默认请求 /chat/endpoint。
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.app-page {
  --bg: #f4f7fb;
  --card: #ffffff;
  --ink: #0d1b2a;
  --sub: #5b6b7a;
  --line: #d7e1ea;
  --accent: #1363df;
  --accent-soft: #e8f0ff;
  --up: #d64545;
  --down: #1f9d62;
  --shadow: 0 10px 24px rgba(17, 34, 68, 0.08);
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

.app-page {
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  color: var(--ink);
  background:
    radial-gradient(circle at 10% 10%, #fef5dd 0, transparent 35%),
    radial-gradient(circle at 90% 0%, #dce9ff 0, transparent 35%),
    var(--bg);
  min-height: 100vh;
  padding: 16px;
}

.app {
  display: grid;
  grid-template-rows: minmax(420px, 58vh) minmax(320px, 42vh);
  gap: 14px;
  max-width: 1600px;
  margin: 0 auto;
}

.top-grid {
  display: grid;
  grid-template-columns: 32% 68%;
  gap: 14px;
  min-height: 0;
}

.panel {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: var(--shadow);
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: linear-gradient(180deg, #ffffff, #f8fbff);
}

.panel-title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.panel-subtitle {
  font-size: 12px;
  color: var(--sub);
  margin-top: 2px;
}

.btn {
  border: 1px solid rgba(255, 255, 255, 0.55);
  background: rgba(255, 255, 255, 0.28);
  backdrop-filter: blur(10px) saturate(150%);
  -webkit-backdrop-filter: blur(10px) saturate(150%);
  color: #0d1b2a;
  font-weight: 600;
  border-radius: 10px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.62),
    0 8px 16px rgba(20, 40, 70, 0.11);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease,
    background 0.2s ease;
}

.btn:hover {
  border-color: rgba(19, 99, 223, 0.52);
  background: rgba(255, 255, 255, 0.38);
  color: var(--accent);
  transform: translateY(-1px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    0 10px 18px rgba(19, 99, 223, 0.18);
}

.btn:focus-visible {
  outline: none;
  border-color: rgba(19, 99, 223, 0.6);
  box-shadow:
    0 0 0 3px rgba(19, 99, 223, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    0 10px 18px rgba(19, 99, 223, 0.18);
}

.btn:active {
  transform: translateY(0);
  box-shadow:
    inset 0 2px 6px rgba(13, 27, 42, 0.12),
    0 4px 10px rgba(13, 27, 42, 0.1);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.btn.primary {
  background: rgba(19, 99, 223, 0.72);
  color: #ffffff;
  border-color: rgba(146, 188, 255, 0.88);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.32),
    0 10px 20px rgba(19, 99, 223, 0.35);
}

.btn.primary:hover {
  background: rgba(19, 99, 223, 0.8);
  border-color: rgba(177, 210, 255, 0.92);
  color: #ffffff;
  filter: none;
}

.btn.primary:focus-visible {
  box-shadow:
    0 0 0 3px rgba(147, 189, 255, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.3),
    0 10px 20px rgba(19, 99, 223, 0.25);
}

.btn.primary.active {
  background: rgba(19, 99, 223, 0.98);
  border-color: rgba(177, 210, 255, 0.99);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 12px 24px rgba(19, 99, 223, 0.45);
  transform: translateY(-1px);
}

.btn.primary.active:hover {
  background: rgba(19, 99, 223, 0.99);
  border-color: rgba(200, 230, 255, 0.99);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.48),
    0 14px 28px rgba(19, 99, 223, 0.5);
}

#backToWatchlistBtn,
#refreshSectorBtn,
#newChatBtn {
  background: rgba(255, 255, 255, 0.32);
  backdrop-filter: blur(12px) saturate(155%);
  -webkit-backdrop-filter: blur(12px) saturate(155%);
  border: 1px solid rgba(255, 255, 255, 0.58);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.68),
    0 10px 18px rgba(20, 40, 70, 0.12);
}

#backToWatchlistBtn:hover,
#refreshSectorBtn:hover,
#newChatBtn:hover {
  background: rgba(255, 255, 255, 0.42);
  border-color: rgba(19, 99, 223, 0.56);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.75),
    0 12px 20px rgba(19, 99, 223, 0.16);
}

.watchlist-wrap {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.add-stock {
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.add-stock input {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 9px 11px;
  outline: none;
  font-size: 13px;
}

.add-stock input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.watchlist-view,
.stock-detail-view {
  flex: 1;
  min-height: 0;
}

.watchlist-view {
  overflow-y: auto;
}

.stock-item {
  margin: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.45);
  border-radius: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.32);
  backdrop-filter: blur(8px) saturate(140%);
  -webkit-backdrop-filter: blur(8px) saturate(140%);
  cursor: pointer;
  transition: all 0.2s ease;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    0 6px 12px rgba(20, 40, 70, 0.08);
}

.stock-item-main {
  min-width: 0;
}

.stock-item-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-action-btn {
  padding: 4px 10px;
  font-size: 12px;
  line-height: 1.2;
  border-radius: 9px;
  opacity: 0;
  visibility: hidden;
  transform: translateX(6px) scale(0.97);
  transition: opacity 0.18s ease, transform 0.18s ease, visibility 0.18s ease;
  pointer-events: none;
}

.stock-item:hover .row-action-btn,
.stock-item:focus-within .row-action-btn,
.history-item:hover .row-action-btn,
.history-item:focus-within .row-action-btn {
  opacity: 1;
  visibility: visible;
  transform: translateX(0) scale(1);
  pointer-events: auto;
}

.stock-item:hover {
  border-color: rgba(19, 99, 223, 0.48);
  background: rgba(255, 255, 255, 0.42);
  transform: translateY(-2px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.65),
    0 8px 16px rgba(19, 99, 223, 0.14);
}

.stock-code {
  color: var(--sub);
  font-size: 12px;
  margin-top: 2px;
}

.stock-change.up {
  color: var(--up);
  font-weight: 700;
  font-size: 13px;
}

.stock-change.down {
  color: var(--down);
  font-weight: 700;
  font-size: 13px;
}

.stock-detail-view {
  display: none;
  padding: 16px;
  overflow-y: auto;
}

.view-enter-from-right {
  animation: viewEnterFromRight 0.3s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}

.view-enter-from-left {
  animation: viewEnterFromLeft 0.3s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}

.view-exit-to-left {
  animation: viewExitToLeft 0.24s ease both;
}

.view-exit-to-right {
  animation: viewExitToRight 0.24s ease both;
}

.stock-detail-view.active {
  display: block;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.detail-name {
  font-size: 20px;
  font-weight: 800;
}

.detail-code {
  color: var(--sub);
  font-size: 13px;
  margin-top: 2px;
}

.detail-price {
  font-size: 28px;
  font-weight: 800;
  margin: 10px 0 4px;
}

.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 14px;
}

.tag {
  padding: 4px 8px;
  font-size: 12px;
  border-radius: 999px;
  background: #f1f5fa;
  color: #334155;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.kpi {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px;
  background: #fbfdff;
}

.kpi-label {
  font-size: 12px;
  color: var(--sub);
  margin-bottom: 4px;
}

.kpi-value {
  font-size: 15px;
  font-weight: 700;
}

.sector-body {
  padding: 14px;
  overflow-y: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  min-height: 0;
}

.chart-card,
.insight-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  background: #fcfdff;
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 8px;
}

.pie-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.pie-box {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px;
  background: #fff;
}

.pie-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 6px;
}

.pie-wrap {
  height: 190px;
}

.insight-list {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.insight-item {
  border: 1px dashed #cdd9e6;
  border-radius: 10px;
  padding: 9px 10px;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
  background: #fff;
}

.summary-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.summary-item {
  font-size: 12px;
  color: #334155;
  padding: 8px 9px;
  border-radius: 8px;
  background: #fff;
  border: 1px dashed #cfd9e6;
}

.chat-panel {
  min-height: 0;
}

.chat-main {
  display: grid;
  grid-template-columns: 280px 1fr;
  min-height: 0;
  flex: 1;
}

.chat-history {
  border-right: 1px solid var(--line);
  background: #f8fbff;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.history-head {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-list {
  overflow-y: auto;
  padding: 8px;
  display: grid;
  gap: 8px;
}

.history-item {
  border: 1px solid rgba(255, 255, 255, 0.45);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.32);
  backdrop-filter: blur(8px) saturate(140%);
  -webkit-backdrop-filter: blur(8px) saturate(140%);
  padding: 9px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    0 5px 10px rgba(20, 40, 70, 0.07);
}

.history-meta {
  min-width: 0;
}

.history-item.active,
.history-item:hover {
  border-color: rgba(19, 99, 223, 0.52);
  background: rgba(19, 99, 223, 0.14);
  backdrop-filter: blur(8px) saturate(145%);
  -webkit-backdrop-filter: blur(8px) saturate(145%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 6px 12px rgba(19, 99, 223, 0.12);
}

.history-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-time {
  font-size: 11px;
  color: var(--sub);
}

.chat-body {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-status {
  border-bottom: 1px solid var(--line);
  padding: 8px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--sub);
  background: #fbfdff;
}

.thinking-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  user-select: none;
}

.thinking-toggle input {
  width: 14px;
  height: 14px;
  accent-color: var(--accent);
}

.status-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 14px;
  display: grid;
  gap: 10px;
  align-content: start;
  background:
    linear-gradient(180deg, #fff, #f8fbff),
    repeating-linear-gradient(0deg, transparent 0, transparent 26px, rgba(13, 27, 42, 0.02) 27px);
}

.messages.chat-switch-out {
  animation: chatSwitchOut 0.22s ease both;
}

.messages.chat-switch-in {
  animation: chatSwitchIn 0.24s ease both;
}

.msg {
  max-width: min(80%, 820px);
  border-radius: 12px;
  padding: 9px 11px;
  line-height: 1.6;
  font-size: 14px;
  border: 1px solid var(--line);
  white-space: pre-wrap;
}

.msg.user {
  justify-self: end;
  background: #eaf1ff;
  border-color: #b9d0ff;
}

.msg.ai {
  justify-self: start;
  background: #ffffff;
}

.msg.msg-enter {
  opacity: 0;
  transform: translateY(8px);
  animation: msgEnter 0.28s ease forwards;
  animation-delay: var(--msg-delay, 0ms);
}

.list-item-enter {
  animation: listItemEnter 0.28s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}

.list-item-leave {
  pointer-events: none;
  animation: listItemLeave 0.22s ease both;
}

.chat-input-wrap {
  border-top: 1px solid var(--line);
  padding: 10px 12px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.chat-input-wrap textarea {
  resize: none;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 9px 11px;
  min-height: 46px;
  max-height: 110px;
  outline: none;
  font-size: 13px;
  font-family: inherit;
}

.chat-input-wrap textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.note {
  font-size: 11px;
  color: var(--sub);
  padding: 0 12px 10px;
}

@keyframes viewEnterFromRight {
  from {
    opacity: 0;
    transform: translateX(20px) scale(0.99);
  }

  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

@keyframes viewEnterFromLeft {
  from {
    opacity: 0;
    transform: translateX(-20px) scale(0.99);
  }

  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

@keyframes viewExitToLeft {
  from {
    opacity: 1;
    transform: translateX(0) scale(1);
  }

  to {
    opacity: 0;
    transform: translateX(-18px) scale(0.99);
  }
}

@keyframes viewExitToRight {
  from {
    opacity: 1;
    transform: translateX(0) scale(1);
  }

  to {
    opacity: 0;
    transform: translateX(18px) scale(0.99);
  }
}

@keyframes chatSwitchOut {
  from {
    opacity: 1;
    transform: translateY(0);
  }

  to {
    opacity: 0;
    transform: translateY(6px);
  }
}

@keyframes chatSwitchIn {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes msgEnter {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes listItemEnter {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.98);
  }

  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes listItemLeave {
  from {
    opacity: 1;
    transform: translateY(0) scale(1);
  }

  to {
    opacity: 0;
    transform: translateY(-8px) scale(0.98);
  }
}

@media (max-width: 1100px) {
  .top-grid {
    grid-template-columns: 1fr;
  }

  .sector-body {
    grid-template-columns: 1fr;
  }

  .chat-main {
    grid-template-columns: 1fr;
  }

  .chat-history {
    border-right: 0;
    border-bottom: 1px solid var(--line);
    max-height: 170px;
  }
}

@media (max-width: 720px) {
  .app-page {
    padding: 10px;
  }

  .app {
    grid-template-rows: auto auto;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .pie-grid {
    grid-template-columns: 1fr;
  }
}
</style>
