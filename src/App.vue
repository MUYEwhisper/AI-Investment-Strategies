<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AGENT_LIST, DEFAULT_AGENT, PRIMARY_AGENT_ID, getAgentPrompt, type AgentProfile } from './agents'
import EChartsPie from './components/EChartsPie.vue'
import { fetchSectorOverview, type SectorOverviewPayload } from './services/sectors'
import { addWatchlistStock, fetchStockDetail, type StockApiPayload } from './services/stocks'

type Stock = StockApiPayload & {
  id: string
  isLoading: boolean
  detailLoading: boolean
}

type PersistedStock = StockApiPayload & {
  id?: string
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
  agentId: string
  title: string
  createdAt: string
  messages: ChatMessage[]
}

const STOCK_TRANSITION_MS = 240
const LIST_ITEM_ANIM_MS = 220
const CHAT_SWITCH_MS = 220
const STORAGE_KEY = 'ai_invest_chat_history'
const WATCHLIST_STORAGE_KEY = 'ai_invest_watchlist'
const AI_CHAT_ENDPOINT = (import.meta.env.VITE_AI_CHAT_ENDPOINT as string | undefined) ?? '/chat/endpoint'

const addStockFormRef = ref<HTMLElement | null>(null)
const watchlistViewRef = ref<HTMLElement | null>(null)
const stockDetailViewRef = ref<HTMLElement | null>(null)
const messagesPanelRef = ref<HTMLElement | null>(null)

const stockInput = ref('')
const chatInput = ref('')
const isAddingStock = ref(false)
const isWatchlistRefreshing = ref(false)
const stockActionHint = ref('')
const isSectorLoading = ref(false)

const enteringStockId = ref<string | null>(null)
const leavingStockId = ref<string | null>(null)
const enteringChatId = ref<string | null>(null)
const leavingChatId = ref<string | null>(null)

const selectedStockId = ref<string | null>(null)
const isDetailVisible = ref(false)
const isStockTransitioning = ref(false)

const chats = ref<ChatSession[]>([])
const activeChatId = ref<string | null>(null)
const activeAgentId = ref(PRIMARY_AGENT_ID)
const isAgentPickerExpanded = ref(false)
const isChatSwitching = ref(false)
const bubbleAnimationEnabled = ref(false)
const isAiResponding = ref(false)
const useThinking = ref(true)
const streamHint = ref('')

let activeAiAbortController: AbortController | null = null

const watchlist = ref<Stock[]>([
  createEmptyStock('贵州茅台', '600519'),
  createEmptyStock('宁德时代', '300750'),
  createEmptyStock('中际旭创', '300308'),
])
const sectorData = ref<SectorOverviewPayload>(createEmptySectorOverview())

const selectedStock = computed(() =>
  watchlist.value.find((stock) => stock.id === selectedStockId.value),
)

const detailTags = computed(() => {
  const stock = selectedStock.value
  if (!stock) return [] as string[]
  if (stock.tags.length) return stock.tags
  if (stock.detailLoading) return ['分析中']
  return [] as string[]
})

const selectedStockStatusNote = computed(() => {
  const stock = selectedStock.value
  if (!stock) return ''
  if (stock.detailLoading) return '正在同步今日投资数据并生成分析标签...'
  if (stock.isLoading) return '正在刷新自选股卡片数据...'
  return stock.statusNote ?? ''
})

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

const flowChartItems = computed(() =>
  sectorData.value.sectors.map((item) => ({
    name: item.name,
    value: item.attentionScore,
  })),
)

const sentimentChartItems = computed(() =>
  sectorData.value.sectors.map((item) => ({
    name: item.name,
    value: item.sentimentScore,
  })),
)

const summaryList = computed(() =>
  sectorData.value.sectors.map((item) => ({
    name: item.name,
    heat: item.strengthScore,
    reason: item.reason,
  })),
)

const sectorStatusNote = computed(() => {
  if (isSectorLoading.value) return '正在同步今日投资 MCP 市场数据并生成板块分析...'
  return [sectorData.value.statusNote, sectorData.value.sourceNote].filter(Boolean).join('；')
})

const watchlistRefreshButtonText = computed(() => {
  if (isWatchlistRefreshing.value) return '刷新中...'
  return isDetailVisible.value ? '刷新详情' : '刷新自选'
})

const activeChat = computed(() => chats.value.find((chat) => chat.id === activeChatId.value) ?? null)
const activeAgent = computed(
  () => AGENT_LIST.find((agent) => agent.id === activeAgentId.value) ?? DEFAULT_AGENT,
)
const foldedAgents = computed(() => AGENT_LIST.filter((agent) => agent.id !== activeAgentId.value))
const activeAgentChats = computed(() =>
  chats.value.filter((chat) => chat.agentId === activeAgentId.value),
)

function createUid(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 1e7)}`
}

function createEmptyStock(name: string, code: string): Stock {
  return {
    id: createUid('stock'),
    name,
    code,
    price: null,
    change: null,
    turnover: '--',
    pe: '--',
    pb: '--',
    marketCap: '--',
    volumeRatio: '--',
    mainFlow: '--',
    sentiment: '--',
    tags: [],
    statusNote: '',
    detailLoaded: false,
    isLoading: false,
    detailLoading: false,
  }
}

function applyStockPayload(target: Stock, payload: StockApiPayload): void {
  target.name = payload.name
  target.code = payload.code
  target.price = payload.price ?? null
  target.change = payload.change ?? null
  target.turnover = payload.turnover || '--'
  target.pe = payload.pe || '--'
  target.pb = payload.pb || '--'
  target.marketCap = payload.marketCap || '--'
  target.volumeRatio = payload.volumeRatio || '--'
  target.mainFlow = payload.mainFlow || '--'
  target.sentiment = payload.sentiment || '--'
  target.tags = Array.isArray(payload.tags) ? [...payload.tags] : []
  target.statusNote = payload.statusNote ?? ''
  target.detailLoaded = Boolean(payload.detailLoaded)
}

function createStockFromPayload(payload: StockApiPayload): Stock {
  const stock = createEmptyStock(payload.name, payload.code)
  applyStockPayload(stock, payload)
  return stock
}

function toPersistedStock(stock: Stock): PersistedStock {
  return {
    id: stock.id,
    name: stock.name,
    code: stock.code,
    price: stock.price,
    change: stock.change,
    turnover: stock.turnover,
    pe: stock.pe,
    pb: stock.pb,
    marketCap: stock.marketCap,
    volumeRatio: stock.volumeRatio,
    mainFlow: stock.mainFlow,
    sentiment: stock.sentiment,
    tags: [...stock.tags],
    statusNote: stock.statusNote ?? '',
    detailLoaded: Boolean(stock.detailLoaded),
  }
}

function restorePersistedStock(payload: PersistedStock): Stock {
  const stock = createEmptyStock(payload.name || '未命名股票', payload.code || '------')
  stock.id = payload.id || stock.id
  applyStockPayload(stock, payload)
  return stock
}

function getAgentById(agentId: string): AgentProfile {
  return AGENT_LIST.find((agent) => agent.id === agentId) ?? DEFAULT_AGENT
}

function createDefaultAiMessage(agentId: string): ChatMessage {
  const agent = getAgentById(agentId)
  return {
    role: 'ai',
    content: agent.greeting,
  }
}

function createEmptySectorOverview(): SectorOverviewPayload {
  return {
    sectors: [],
    insights: [],
    statusNote: '',
    sourceNote: '',
    detailLoaded: false,
  }
}

function changeClass(value: number | null | undefined): 'up' | 'down' | 'flat' {
  if (typeof value !== 'number') return 'flat'
  return value >= 0 ? 'up' : 'down'
}

function formatChange(value: number | null | undefined): string {
  if (typeof value !== 'number') return '--'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function formatPrice(value: number | null | undefined): string {
  return typeof value === 'number' ? `${value.toFixed(2)} 元` : '--'
}

function clearStockAnimClass(el: HTMLElement | null): void {
  if (!el) return
  el.classList.remove('view-enter-from-right', 'view-enter-from-left', 'view-exit-to-left', 'view-exit-to-right')
}

async function refreshStockSummary(target: Stock, query = target.code): Promise<void> {
  target.isLoading = true
  try {
    const payload = await addWatchlistStock(query)
    applyStockPayload(target, payload)
  } catch (error) {
    const message = error instanceof Error ? error.message : '股票卡片刷新失败'
    target.statusNote = message
  } finally {
    target.isLoading = false
  }
}

async function refreshWatchlistData(): Promise<void> {
  if (isWatchlistRefreshing.value) return

  const currentStock = selectedStock.value
  if (isDetailVisible.value && !currentStock) return
  if (!isDetailVisible.value && !watchlist.value.length) {
    stockActionHint.value = '当前没有可刷新的自选股。'
    return
  }

  isWatchlistRefreshing.value = true
  try {
    if (isDetailVisible.value && currentStock) {
      await loadStockDetail(currentStock)
      return
    }

    await Promise.allSettled(watchlist.value.map((stock) => refreshStockSummary(stock)))
    stockActionHint.value = '自选股卡片已手动刷新。'
  } finally {
    isWatchlistRefreshing.value = false
  }
}

async function loadStockDetail(target: Stock): Promise<void> {
  if (target.detailLoading) return

  target.detailLoading = true
  try {
    const payload = await fetchStockDetail(target.code)
    applyStockPayload(target, payload)
  } catch (error) {
    const message = error instanceof Error ? error.message : '股票详情加载失败'
    target.statusNote = message
  } finally {
    target.detailLoading = false
  }
}

function showStockDetailById(stockId: string): void {
  if (isStockTransitioning.value) return
  const stock = watchlist.value.find((item) => item.id === stockId)
  if (!stock) return

  selectedStockId.value = stock.id
  void loadStockDetail(stock)
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

async function addStock(): Promise<void> {
  const value = stockInput.value.trim()
  if (!value || isAddingStock.value) return

  isAddingStock.value = true
  stockActionHint.value = '正在识别股票并同步自选股卡片...'

  try {
    const payload = await addWatchlistStock(value)
    const existingIndex = watchlist.value.findIndex((stock) => stock.code === payload.code)

    if (existingIndex >= 0) {
      const existing = watchlist.value[existingIndex]
      if (!existing) return
      watchlist.value.splice(existingIndex, 1)
      applyStockPayload(existing, payload)
      watchlist.value.unshift(existing)
      enteringStockId.value = existing.id
      stockActionHint.value = payload.statusNote
        ? `${payload.name} 已在自选中，已刷新。${payload.statusNote}`
        : `${payload.name} 已在自选中，卡片已刷新。`
    } else {
      const newStock = createStockFromPayload(payload)
      watchlist.value.unshift(newStock)
      enteringStockId.value = newStock.id
      stockActionHint.value = payload.statusNote
        ? `${payload.name} 已加入自选。${payload.statusNote}`
        : `${payload.name} 已加入自选。`
    }

    stockInput.value = ''
    window.setTimeout(() => {
      if (enteringStockId.value) enteringStockId.value = null
    }, 320)
  } catch (error) {
    stockActionHint.value = error instanceof Error ? error.message : '股票添加失败'
  } finally {
    isAddingStock.value = false
  }
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

function currentSectorProbeCodes(): string[] {
  return watchlist.value.map((stock) => stock.code).filter((code) => /^\d{6}$/.test(code))
}

async function refreshSectorData(): Promise<void> {
  if (isSectorLoading.value) return

  isSectorLoading.value = true
  try {
    const payload = await fetchSectorOverview(currentSectorProbeCodes())
    sectorData.value = payload
  } catch (error) {
    const message = error instanceof Error ? error.message : '板块分析刷新失败'
    sectorData.value = {
      ...sectorData.value,
      statusNote: message,
    }
  } finally {
    isSectorLoading.value = false
  }
}

function loadWatchlist(): void {
  try {
    const saved = localStorage.getItem(WATCHLIST_STORAGE_KEY)
    if (saved === null) return

    const parsed = JSON.parse(saved) as PersistedStock[]
    if (!Array.isArray(parsed)) return

    watchlist.value = parsed.map((stock) => restorePersistedStock(stock))
  } catch {
    localStorage.removeItem(WATCHLIST_STORAGE_KEY)
  }
}

function persistWatchlist(): void {
  const payload = watchlist.value.map((stock) => toPersistedStock(stock))
  localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(payload))
}

function loadChats(): void {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    const parsed = saved ? (JSON.parse(saved) as ChatSession[]) : []

    chats.value = parsed.map((chat) => ({
      id: chat.id || createUid('chat'),
      agentId: chat.agentId || PRIMARY_AGENT_ID,
      title: chat.title || '新对话',
      createdAt: chat.createdAt || new Date().toLocaleString(),
      messages:
        Array.isArray(chat.messages) && chat.messages.length
          ? chat.messages
          : [createDefaultAiMessage(chat.agentId || PRIMARY_AGENT_ID)],
    }))
  } catch {
    chats.value = []
  }

  const primaryAgentFirstChat = chats.value.find((chat) => chat.agentId === PRIMARY_AGENT_ID)
  if (primaryAgentFirstChat) {
    activeAgentId.value = PRIMARY_AGENT_ID
    activeChatId.value = primaryAgentFirstChat.id
    renderMessages(false)
    return
  }

  if (!chats.value.length) {
    createNewChat(false, PRIMARY_AGENT_ID)
    return
  }

  const firstChat = chats.value[0]
  if (!firstChat) return
  activeAgentId.value = firstChat.agentId
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

function createNewChat(withAnim = true, targetAgentId = activeAgentId.value): void {
  const agent = getAgentById(targetAgentId)
  const id = createUid('chat')
  chats.value.unshift({
    id,
    agentId: targetAgentId,
    title: `${agent.name}对话`,
    createdAt: new Date().toLocaleString(),
    messages: [createDefaultAiMessage(targetAgentId)],
  })
  activeAgentId.value = targetAgentId
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
  createNewChat(true, activeAgentId.value)
}

function selectAgent(agentId: string): void {
  if (isAiResponding.value) return
  activeAgentId.value = agentId
  isAgentPickerExpanded.value = false

  const existingChat = chats.value.find((chat) => chat.agentId === agentId)
  if (!existingChat) {
    createNewChat(false, agentId)
    return
  }

  transitionToChat(existingChat.id, null, true)
}

function toggleAgentPicker(): void {
  isAgentPickerExpanded.value = !isAgentPickerExpanded.value
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

    const currentAgentChats = chats.value.filter((chat) => chat.agentId === activeAgentId.value)

    if (!chats.value.length) {
      activeChatId.value = null
      leavingChatId.value = null
      createNewChat(false, activeAgentId.value)
      panel?.classList.remove('chat-switch-out')
      panel?.classList.add('chat-switch-in')
      window.setTimeout(() => panel?.classList.remove('chat-switch-in'), CHAT_SWITCH_MS)
      persistChats()
      return
    }

    if (removingActive) {
      const firstChat = currentAgentChats[0]
      if (firstChat) {
        activeChatId.value = firstChat.id
        renderMessages(true)
        panel?.classList.remove('chat-switch-out')
        panel?.classList.add('chat-switch-in')
        window.setTimeout(() => panel?.classList.remove('chat-switch-in'), CHAT_SWITCH_MS)
      } else {
        activeChatId.value = null
        createNewChat(false, activeAgentId.value)
      }
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

async function streamChatBySse(
  chatId: string,
  messageIndex: number,
  prompt: string,
  agentId: string,
): Promise<void> {
  const agent = getAgentById(agentId)
  const fullPrompt = getAgentPrompt(agent, prompt)
  const controller = new AbortController()
  activeAiAbortController = controller

  const response = await fetch(AI_CHAT_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      prompt: fullPrompt,
      agentId,
      agentName: agent.name,
      systemPrompt: agent.systemPrompt,
      originalPrompt: prompt,
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
  const currentAgentId = activeChat.value.agentId
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
    await streamChatBySse(currentChatId, aiMessageIndex, text, currentAgentId)

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

watch(
  watchlist,
  () => {
    persistWatchlist()
  },
  { deep: true },
)

onMounted(async () => {
  loadWatchlist()
  loadChats()
})

onBeforeUnmount(() => {
  activeAiAbortController?.abort()
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
            <button
              class="btn"
              id="refreshWatchlistBtn"
              :disabled="isWatchlistRefreshing || isAddingStock"
              @click="refreshWatchlistData"
            >
              {{ watchlistRefreshButtonText }}
            </button>
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
              :disabled="isAddingStock"
              @click="addStock"
            >
              {{ isAddingStock ? '识别中...' : '添加' }}
            </button>
            <div v-if="stockActionHint" class="stock-action-hint">{{ stockActionHint }}</div>
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
                  {{ stock.isLoading && stock.change === null ? '同步中' : formatChange(stock.change) }}
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
            <div class="detail-price" id="detailPrice">{{ formatPrice(selectedStock?.price) }}</div>
            <div class="stock-change" :class="changeClass(selectedStock?.change)" id="detailChange">
              {{ selectedStock ? formatChange(selectedStock.change) : '--' }}
            </div>
            <div v-if="selectedStockStatusNote" class="stock-status-note">{{ selectedStockStatusNote }}</div>
            <div class="detail-tags" id="detailTags">
              <span v-for="tag in detailTags" :key="tag" class="tag">{{ tag }}</span>
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
            <button class="btn" id="refreshSectorBtn" :disabled="isSectorLoading" @click="refreshSectorData">
              {{ isSectorLoading ? '分析中...' : '刷新数据' }}
            </button>
          </div>

          <div class="sector-body">
            <div class="chart-card">
              <div class="card-title">板块图表分析（直观饼图）</div>
              <div v-if="sectorStatusNote" class="sector-status-note">{{ sectorStatusNote }}</div>
              <div class="pie-grid">
                <div class="pie-box">
                  <div class="pie-title">资金关注度占比</div>
                  <div class="pie-wrap">
                    <EChartsPie
                      id="flowChart"
                      :items="flowChartItems"
                      mode="donut"
                      series-name="资金关注度"
                      :loading="isSectorLoading"
                      empty-text="暂无资金关注度数据"
                    />
                  </div>
                </div>
                <div class="pie-box">
                  <div class="pie-title">市场情绪占比</div>
                  <div class="pie-wrap">
                    <EChartsPie
                      id="sentimentChart"
                      :items="sentimentChartItems"
                      mode="pie"
                      series-name="市场情绪"
                      :loading="isSectorLoading"
                      empty-text="暂无市场情绪数据"
                    />
                  </div>
                </div>
              </div>
              <div class="summary-list" id="summaryList">
                <div v-for="item in summaryList" :key="item.name" class="summary-item">
                  {{ item.name }}：强弱评分 {{ item.heat }}
                </div>
                <div v-if="!summaryList.length && !isSectorLoading" class="summary-item">等待今日投资 MCP 返回真实板块数据。</div>
              </div>
            </div>

            <div class="insight-card">
              <div class="card-title">市场情绪与政策风向解读</div>
              <div class="insight-list" id="insightList">
                <div v-for="line in sectorData.insights" :key="line" class="insight-item">{{ line }}</div>
                <div v-if="!sectorData.insights.length && !isSectorLoading" class="insight-item">等待模型基于 MCP 数据生成解读。</div>
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
            <div class="agent-picker">
              <button
                class="agent-focus"
                :class="{ active: activeAgent?.primary }"
                type="button"
                :disabled="isAiResponding"
                @click="selectAgent(activeAgentId)"
              >
                <span class="agent-focus-name">{{ activeAgent?.name }}</span>
                <span class="agent-focus-subtitle">{{ activeAgent?.subtitle }}</span>
                <span class="agent-focus-desc">{{ activeAgent?.description }}</span>
              </button>
              <button
                class="btn agent-toggle-btn"
                type="button"
                :disabled="isAiResponding"
                @click="toggleAgentPicker"
              >
                {{ isAgentPickerExpanded ? '收起智能体' : `展开其他智能体（${foldedAgents.length}）` }}
              </button>
              <div v-show="isAgentPickerExpanded" class="agent-fold-list">
                <button
                  v-for="agent in foldedAgents"
                  :key="agent.id"
                  class="agent-option"
                  :class="{ active: agent.id === activeAgentId }"
                  type="button"
                  :disabled="isAiResponding"
                  @click="selectAgent(agent.id)"
                >
                  <span class="agent-option-name">{{ agent.name }}</span>
                  <span class="agent-option-subtitle">{{ agent.subtitle }}</span>
                  <span class="agent-option-desc">{{ agent.description }}</span>
                </button>
              </div>
            </div>

            <div class="history-head">
              <strong style="font-size: 13px">{{ activeAgent?.name }}会话</strong>
              <button class="btn history-new-btn" id="newChatBtn" :disabled="isAiResponding" @click="onNewChatClick">
                新建
              </button>
            </div>
            <div class="history-list" id="historyList">
              <div
                v-for="chat in activeAgentChats"
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
              <div v-if="!activeAgentChats.length" class="history-empty">当前智能体暂无会话，点击右上角新建开始对话。</div>
            </div>
          </aside>

          <div class="chat-body">
            <div class="chat-status">
              <span class="agent-badge">当前智能体：{{ activeAgent?.name }}</span>
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
                :placeholder="`向${activeAgent?.name || '智能体'}提问，例如：结合半导体板块资金流向，给出仓位建议`"
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
              说明：当前已接入 SSE 流式对话，并会携带智能体标识。可通过环境变量 VITE_AI_CHAT_ENDPOINT 配置后端地址，默认请求 /chat/endpoint。
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style>
.app-page {
  --bg-start: #06b6d4;
  --bg-end: #3b82f6;
  --card: rgba(255, 255, 255, 0.58);
  --surface: rgba(255, 255, 255, 0.52);
  --surface-strong: rgba(255, 255, 255, 0.72);
  --surface-soft: rgba(246, 251, 255, 0.5);
  --ink: #0d1b2a;
  --sub: #5b6b7a;
  --line: rgba(137, 176, 233, 0.42);
  --surface-stroke: rgba(133, 173, 233, 0.46);
  --surface-bg: rgba(255, 255, 255, 0.56);
  --accent: #0ea5e9;
  --accent-deep: #3b82f6;
  --accent-soft: rgba(59, 130, 246, 0.16);
  --up: #d64545;
  --down: #1f9d62;
  --shadow: 0 12px 26px rgba(9, 41, 93, 0.16);
  --motion-fast: 0.18s;
  --motion-normal: 0.24s;
  --motion-slow: 0.32s;
  --motion-ease: cubic-bezier(0.2, 0.7, 0.2, 1);
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

.app-page {
  position: relative;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  color: var(--ink);
  background:
    linear-gradient(160deg, rgba(6, 182, 212, 0.96) 0%, rgba(25, 165, 222, 0.96) 38%, rgba(47, 141, 240, 0.95) 68%, rgba(59, 130, 246, 0.95) 100%);
  min-height: 100vh;
  padding: 16px;
}

.app-page::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0.03) 36%, rgba(255, 255, 255, 0) 100%);
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
  border: 1px solid var(--surface-stroke);
  border-radius: 16px;
  box-shadow:
    var(--shadow),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(14px) saturate(132%);
  -webkit-backdrop-filter: blur(14px) saturate(132%);
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-header {
  position: relative;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(126, 166, 224, 0.3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: rgba(255, 255, 255, 0.56);
  backdrop-filter: blur(7px) saturate(120%);
  -webkit-backdrop-filter: blur(7px) saturate(120%);
}

.panel-header::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(124, 165, 226, 0.6), transparent);
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
    transform var(--motion-fast) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease),
    color var(--motion-fast) var(--motion-ease),
    background var(--motion-normal) var(--motion-ease);
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
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.9), rgba(59, 130, 246, 0.92));
  color: #ffffff;
  border-color: rgba(180, 221, 255, 0.9);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.32),
    0 10px 20px rgba(23, 119, 225, 0.38);
}

.btn.primary:hover {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.96), rgba(59, 130, 246, 0.98));
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
  background: linear-gradient(135deg, rgba(6, 182, 212, 1), rgba(59, 130, 246, 1));
  border-color: rgba(177, 210, 255, 0.99);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 12px 24px rgba(19, 99, 223, 0.45);
  transform: translateY(-1px);
}

.btn.primary.active:hover {
  background: linear-gradient(135deg, rgba(6, 182, 212, 1), rgba(59, 130, 246, 1));
  border-color: rgba(200, 230, 255, 0.99);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.48),
    0 14px 28px rgba(19, 99, 223, 0.5);
}

#backToWatchlistBtn,
#refreshWatchlistBtn,
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
#refreshWatchlistBtn:hover,
#refreshSectorBtn:hover,
#newChatBtn:hover {
  background: rgba(255, 255, 255, 0.42);
  border-color: rgba(19, 99, 223, 0.56);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.75),
    0 12px 20px rgba(19, 99, 223, 0.16);
}

#addStockBtn {
  min-width: 74px;
  color: #ffffff;
  border: 1px solid rgba(176, 219, 255, 0.9);
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.94), rgba(59, 130, 246, 0.95));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.34),
    0 10px 20px rgba(23, 119, 225, 0.36);
}

#addStockBtn:hover {
  color: #ffffff;
  border-color: rgba(196, 229, 255, 0.96);
  background: linear-gradient(135deg, rgba(6, 182, 212, 1), rgba(59, 130, 246, 1));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.42),
    0 12px 22px rgba(23, 119, 225, 0.42);
}

#addStockBtn:active {
  transform: translateY(1px) scale(0.97);
}

#addStockBtn:not(.active) {
  filter: saturate(88%);
  opacity: 0.88;
}

.watchlist-wrap {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.add-stock {
  margin: 0;
  padding: 14px 16px;
  border: 0;
  border-bottom: 1px solid rgba(126, 166, 224, 0.28);
  border-radius: 0;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  background: var(--surface-soft);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.76);
}

.stock-action-hint {
  grid-column: 1 / -1;
  font-size: 12px;
  color: rgba(36, 73, 120, 0.82);
  line-height: 1.5;
}

.add-stock input {
  border: 1px solid rgba(146, 183, 236, 0.5);
  border-radius: 14px;
  padding: 10px 14px;
  outline: none;
  font-size: 13px;
  color: #173354;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(241, 248, 255, 0.88));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.85),
    0 6px 12px rgba(25, 75, 146, 0.08);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.add-stock input::placeholder {
  color: rgba(46, 75, 112, 0.62);
}

.add-stock input:focus {
  border-color: rgba(59, 130, 246, 0.72);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(243, 249, 255, 0.94));
  box-shadow:
    0 0 0 3px rgba(59, 130, 246, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 8px 16px rgba(31, 93, 180, 0.14);
}

.watchlist-view,
.stock-detail-view {
  flex: 1;
  min-height: 0;
}

.watchlist-view {
  margin: 0;
  border: 0;
  border-radius: 0;
  background: var(--surface);
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
  transition:
    transform var(--motion-fast) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease),
    background var(--motion-normal) var(--motion-ease);
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
  transition:
    opacity var(--motion-fast) var(--motion-ease),
    transform var(--motion-fast) var(--motion-ease),
    visibility var(--motion-fast) var(--motion-ease);
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

.stock-change.flat {
  color: rgba(48, 75, 108, 0.72);
  font-weight: 700;
  font-size: 13px;
}

.stock-detail-view {
  display: none;
  margin: 0;
  border: 0;
  border-radius: 0;
  background: var(--surface);
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

.stock-status-note {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(44, 72, 104, 0.8);
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
  margin: 0;
  padding: 14px;
  border: 0;
  border-radius: 0;
  background: var(--surface);
  overflow-y: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  min-height: 0;
}

.chart-card,
.insight-card {
  border: 1px solid #d4e4fb;
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.74);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.75),
    0 8px 15px rgba(25, 58, 115, 0.08);
  transition:
    transform var(--motion-fast) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease);
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 8px;
}

.sector-status-note {
  margin-bottom: 10px;
  padding: 9px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(44, 72, 104, 0.82);
  border: 1px dashed #bfd1ea;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.8);
}

.pie-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.pie-box {
  border: 1px solid #d7e5f9;
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.8);
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
  border: 1px dashed #bfd1ea;
  border-radius: 10px;
  padding: 9px 10px;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
  background: rgba(255, 255, 255, 0.82);
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
  background: rgba(255, 255, 255, 0.8);
  border: 1px dashed #c5d6ee;
}

.chat-panel {
  min-height: 0;
}

.chat-main {
  display: grid;
  grid-template-columns: 320px 1fr;
  position: relative;
  margin: 0;
  padding: 10px 0 10px 10px;
  gap: 10px;
  border: 0;
  border-radius: 0;
  background:
    var(--surface);
  min-height: 0;
  flex: 1;
}

.chat-main::before {
  content: '';
  position: absolute;
  left: 14px;
  right: 14px;
  top: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(125, 170, 232, 0.66), transparent);
}

.chat-history {
  border: 1px solid var(--surface-stroke);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.66);
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: #b8ccea transparent;
}

.chat-history::before,
.chat-history::after {
  content: '';
  position: sticky;
  left: 0;
  right: 0;
  height: 16px;
  z-index: 4;
  pointer-events: none;
}

.chat-history::before {
  top: 0;
  background: linear-gradient(180deg, rgba(246, 250, 255, 0.96), rgba(246, 250, 255, 0));
}

.chat-history::after {
  bottom: 0;
  background: linear-gradient(0deg, rgba(243, 248, 255, 0.96), rgba(243, 248, 255, 0));
}

.chat-history::-webkit-scrollbar {
  width: 9px;
}

.chat-history::-webkit-scrollbar-track {
  background: transparent;
}

.chat-history::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #c5d8f5, #9fbde8);
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: content-box;
}

.chat-history::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, #afcaef, #84aee3);
  background-clip: content-box;
}

.agent-picker {
  padding: 10px;
  border-bottom: 1px solid rgba(126, 166, 224, 0.28);
  background: rgba(255, 255, 255, 0.56);
  display: grid;
  gap: 8px;
}

.agent-focus {
  border: 1px solid rgba(134, 178, 240, 0.68);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(235, 246, 255, 0.88));
  padding: 10px;
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 2px;
  transition:
    transform var(--motion-fast) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease),
    background var(--motion-normal) var(--motion-ease);
}

.agent-focus:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(34, 80, 160, 0.16);
}

.agent-focus.active {
  border-color: #8db8ff;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.72),
    0 10px 22px rgba(34, 80, 160, 0.16);
}

.agent-focus-name {
  font-size: 14px;
  font-weight: 800;
  color: #1f2a44;
}

.agent-focus-subtitle {
  font-size: 11px;
  color: #4b6485;
}

.agent-focus-desc {
  font-size: 11px;
  color: #365273;
  margin-top: 3px;
  line-height: 1.45;
}

.agent-toggle-btn {
  width: 100%;
}

.agent-fold-list {
  display: grid;
  gap: 7px;
}

.agent-option {
  border: 1px solid #d7e5fa;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.88);
  padding: 8px 9px;
  text-align: left;
  cursor: pointer;
  transition:
    transform var(--motion-fast) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease),
    background var(--motion-normal) var(--motion-ease);
  display: grid;
  gap: 1px;
}

.agent-option:hover,
.agent-option.active {
  border-color: #78afea;
  background: linear-gradient(135deg, rgba(237, 247, 255, 0.98), rgba(220, 238, 255, 0.92));
}

.agent-option-name {
  font-size: 13px;
  font-weight: 700;
  color: #1f2a44;
}

.agent-option-subtitle {
  font-size: 11px;
  color: #5c708d;
}

.agent-option-desc {
  font-size: 11px;
  color: #60738e;
  line-height: 1.4;
}

.history-head {
  margin: 8px 10px;
  padding: 10px 12px;
  border: 1px solid #c9ddff;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(238, 247, 255, 0.9));
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.72),
    0 8px 18px rgba(35, 77, 145, 0.1);
}

.history-new-btn {
  border: 1px solid rgba(255, 255, 255, 0.58);
  background: rgba(255, 255, 255, 0.32);
  backdrop-filter: blur(12px) saturate(155%);
  -webkit-backdrop-filter: blur(12px) saturate(155%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.68),
    0 10px 18px rgba(20, 40, 70, 0.12);
  min-width: 68px;
}

.history-new-btn:hover {
  background: rgba(255, 255, 255, 0.42);
  border-color: rgba(19, 99, 223, 0.56);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.75),
    0 12px 20px rgba(19, 99, 223, 0.16);
}

.history-new-btn:active {
  transform: translateY(1px) scale(0.97);
  box-shadow:
    inset 0 2px 6px rgba(13, 27, 42, 0.12),
    0 4px 10px rgba(13, 27, 42, 0.1);
}

.history-list {
  flex: none;
  overflow: visible;
  margin: 0 10px 10px;
  padding: 10px;
  display: grid;
  gap: 8px;
  min-height: auto;
  padding-bottom: 16px;
  border: 1px solid var(--surface-stroke);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.62);
  backdrop-filter: blur(8px) saturate(138%);
  -webkit-backdrop-filter: blur(8px) saturate(138%);
}

.history-empty {
  font-size: 12px;
  color: var(--sub);
  border: 1px dashed #c8d9f3;
  border-radius: 10px;
  padding: 10px;
  background: #f8fbff;
}

.history-item {
  border: 1px solid #d3e2fa;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(237, 245, 255, 0.82));
  backdrop-filter: blur(8px) saturate(145%);
  -webkit-backdrop-filter: blur(8px) saturate(145%);
  padding: 9px;
  cursor: pointer;
  transition:
    transform var(--motion-fast) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease),
    background var(--motion-normal) var(--motion-ease);
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    0 7px 14px rgba(20, 40, 70, 0.09);
}

.history-meta {
  min-width: 0;
}

.history-item.active,
.history-item:hover {
  border-color: rgba(90, 149, 242, 0.75);
  background: linear-gradient(135deg, rgba(226, 238, 255, 0.96), rgba(205, 225, 255, 0.88));
  backdrop-filter: blur(9px) saturate(150%);
  -webkit-backdrop-filter: blur(9px) saturate(150%);
  transform: translateY(-1px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.6),
    0 10px 18px rgba(49, 106, 194, 0.2);
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
  border: 1px solid var(--surface-stroke);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.68);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-status {
  border-bottom: 1px solid rgba(126, 166, 224, 0.28);
  padding: 8px 12px;
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--sub);
  background: rgba(255, 255, 255, 0.58);
}

.agent-badge {
  padding: 3px 8px;
  border-radius: 999px;
  background: #edf4ff;
  color: #284a79;
  border: 1px solid #c8ddff;
  font-size: 11px;
  white-space: nowrap;
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
  margin-left: auto;
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
  border: 1px solid rgba(146, 183, 236, 0.5);
  border-radius: 14px;
  padding: 10px 14px;
  min-height: 46px;
  max-height: 110px;
  outline: none;
  font-size: 13px;
  font-family: inherit;
  color: #173354;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(241, 248, 255, 0.88));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.85),
    0 6px 12px rgba(25, 75, 146, 0.08);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.chat-input-wrap textarea::placeholder {
  color: rgba(46, 75, 112, 0.62);
}

.chat-input-wrap textarea:focus {
  border-color: rgba(59, 130, 246, 0.72);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(243, 249, 255, 0.94));
  box-shadow:
    0 0 0 3px rgba(59, 130, 246, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 8px 16px rgba(31, 93, 180, 0.14);
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
    max-height: 320px;
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
