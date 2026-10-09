<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AGENT_LIST, DEFAULT_AGENT, PRIMARY_AGENT_ID, type AgentProfile } from './agents'
import EChartsPie from './components/EChartsPie.vue'
import KsuserAccountCenter from './components/KsuserAccountCenter.vue'
import StrategyWorkbenchPage from './components/StrategyWorkbenchPage.vue'
import {
  buildChatStartHint,
  buildStructuredChatMessages,
  type ChatStartMemoryPayload,
  type StructuredChatMessage,
} from './services/chat-memory'
import { apiFetch } from './services/http'
import { fetchSectorOverview, type SectorOverviewPayload } from './services/sectors'
import {
  getKsuserAuthConfig,
} from './services/ksuser-auth'
import { fetchAccountSessions, fetchAccountUser, logoutAccount, revokeSessions, type AccountSession } from './services/account'
import { addWatchlistStock, fetchStockDetail, type StockApiPayload } from './services/stocks'
import { fetchUserChats, fetchUserWatchlist, saveUserChats, saveUserWatchlist, type CloudChatSession } from './services/user-data'
import { useAuthStore } from './stores/auth'
import { renderMarkdownToHtml } from './utils/markdown'
import { cancelMotion, enterItem, enterPage, leaveItem, MOTION, playMotion } from './utils/motion'

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

const STORAGE_KEY = 'ai_invest_chat_history'
const WATCHLIST_STORAGE_KEY = 'ai_invest_watchlist'
const AI_CHAT_ENDPOINT = (import.meta.env.VITE_AI_CHAT_ENDPOINT as string | undefined) ?? '/chat/endpoint'
const SIGNIN_QUERY_VALUE = 'signin'
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
authStore.hydrate()
const authConfig = ref(getKsuserAuthConfig())

const messagesPanelRef = ref<HTMLElement | null>(null)

const stockInput = ref('')
const chatInput = ref('')
const isAddingStock = ref(false)
const isWatchlistRefreshing = ref(false)
const stockActionHint = ref('')
const isSectorLoading = ref(false)

const selectedStockId = ref<string | null>(null)
const isDetailVisible = ref(false)

const chats = ref<ChatSession[]>([])
const activeChatId = ref<string | null>(null)
const activeAgentId = ref(PRIMARY_AGENT_ID)
const isAgentPickerExpanded = ref(true)
const isAiResponding = ref(false)
const useThinking = ref(true)
const streamHint = ref('')
const shouldStickToLatestMessage = ref(true)

let activeAiAbortController: AbortController | null = null

const watchlist = ref<Stock[]>(createDefaultWatchlist())
const sectorData = ref<SectorOverviewPayload>(createEmptySectorOverview())
const callbackStatus = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const callbackMessage = ref('')
const pendingRedirectAfterSignIn = ref<string | null>(null)
const accountSessions = ref<AccountSession[]>([])
const accountActionBusy = ref(false)
const accountActionError = ref('')
const syncWatchlistInFlight = ref(false)
const syncChatsInFlight = ref(false)
const isAccountRoute = computed(() => route.name === 'account')
const isAuthCallbackRoute = computed(() => route.name === 'auth-callback')
const isStrategyRoute = computed(() => route.name === 'strategy-workbench')
const isDashboardRoute = computed(() => route.name === 'dashboard')
const desktopView = ref<'market' | 'ai' | null>(null)
function onDesktopViewChange(event: Event): void {
  const view = (event as CustomEvent).detail?.view
  if (view === 'market' || view === 'ai') desktopView.value = view
}
const hasVisitedStrategy = ref(isStrategyRoute.value)
const pageTitle = computed(() => {
  if (isAuthCallbackRoute.value) return '正在完成账号登录'
  if (isAccountRoute.value) return '账号中心'
  return isStrategyRoute.value ? '策略工作台' : '市场总览'
})
const pageDescription = computed(() =>
  isAuthCallbackRoute.value
    ? '正在校验授权结果、换取 Access Token 并同步用户资料，请稍候片刻。'
    : isAccountRoute.value
      ? '查看当前 Ksuser 登录会话、授权范围和设备状态。'
      : isStrategyRoute.value
        ? '集中处理策略分析、组合体检、模拟交易和异常解释。'
        : authStore.isAuthenticated
          ? '首页聚焦自选股、板块热度与 AI 对话，作为日常观察和交互入口。'
          : '游客可直接体验 AI 对话，登录后即可保存自选股、历史会话和个人工作区。',
)
const activeStageKey = computed(() => {
  if (isAuthCallbackRoute.value) return 'auth-callback'
  if (isAccountRoute.value) return 'account'
  if (isStrategyRoute.value) return 'strategy'
  return 'dashboard'
})
const currentUserName = computed(() => authStore.userLabel)
const currentUserAvatar = computed(() => authStore.userAvatar)
const currentUserEmail = computed(() => authStore.session?.profile.email || '')

const isGuestMode = computed(() => !authStore.isAuthenticated)
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
    { label: '市盈率 (PE)', value: stock.pe },
    { label: '市净率 (PB)', value: stock.pb },
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
  return [sectorData.value.statusNote, sectorData.value.sourceNote].filter(Boolean).join(' · ')
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

const CHAT_TITLE_MOJIBAKE_PATTERN = /[\uFFFD]|[鐎鐦闁锟]/

function createUid(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 1e7)}`
}

function createDefaultWatchlist(): Stock[] {
  return []
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

function defaultChatTitle(agentId: string): string {
  return `${getAgentById(agentId).name}会话`
}

function normalizeChatTitle(title: string | null | undefined, agentId: string): string {
  const fallback = defaultChatTitle(agentId)
  const value = typeof title === 'string' ? title.trim() : ''
  if (!value || value === '???' || value === '新对话') return fallback
  if (CHAT_TITLE_MOJIBAKE_PATTERN.test(value)) return fallback
  return value
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
  return typeof value === 'number' ? value.toFixed(2) + ' 元' : '--'
}

function enterStock(element: Element, done: () => void): void {
  const offset = isDetailVisible.value ? 10 : -10
  playMotion(element, [
    { opacity: 0, transform: `translateX(${offset}px)` },
    { opacity: 1, transform: 'translateX(0)' },
  ], MOTION.normal, done)
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
  const stock = watchlist.value.find((item) => item.id === stockId)
  if (!stock) return

  selectedStockId.value = stock.id
  void loadStockDetail(stock)
  isDetailVisible.value = true
}

function backToWatchlist(): void {
  isDetailVisible.value = false
}

function getScopedStorageKey(baseKey: string): string | null {
  const openid = authStore.session?.profile.openid
  return openid ? baseKey + ':' + openid : null
}

function getCurrentWorkspacePath(): string {
  const query = { ...route.query }
  delete query.auth
  delete query.redirect

  return router.resolve({
    path: route.path,
    query,
    hash: route.hash,
  }).fullPath
}

function openSignInDialog(_reason: string, redirectTarget = getCurrentWorkspacePath()): void {
  pendingRedirectAfterSignIn.value = redirectTarget.startsWith('/') ? redirectTarget : '/'
  void startKsuserSignIn(pendingRedirectAfterSignIn.value)
}

function closeSignInDialog(): void {
  pendingRedirectAfterSignIn.value = null

  if (route.query.auth === SIGNIN_QUERY_VALUE || typeof route.query.redirect === 'string') {
    const query = { ...route.query }
    delete query.auth
    delete query.redirect
    void router.replace({
      path: route.path,
      query,
      hash: route.hash,
    })
  }
}

async function addStock(): Promise<void> {
  const value = stockInput.value.trim()
  if (!value || isAddingStock.value) return

  if (isGuestMode.value) {
    openSignInDialog('登录后才可以添加和保存自选股。')
    return
  }

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
      stockActionHint.value = payload.statusNote
        ? payload.name + ' 已在自选中，已刷新。' + payload.statusNote
        : payload.name + ' 已在自选中，卡片已刷新。'
    } else {
      const newStock = createStockFromPayload(payload)
      watchlist.value.unshift(newStock)
      stockActionHint.value = payload.statusNote
        ? payload.name + ' 已加入自选。' + payload.statusNote
        : payload.name + ' 已加入自选。'
    }
    stockInput.value = ''
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
  if (isGuestMode.value) {
    openSignInDialog('登录后才可以编辑和保存你的自选股。')
    return
  }

  watchlist.value = watchlist.value.filter((stock) => stock.id !== stockId)
  if (selectedStockId.value === stockId) {
    selectedStockId.value = null
    isDetailVisible.value = false
  }
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

async function loadWatchlist(): Promise<void> {
  selectedStockId.value = null
  isDetailVisible.value = false

  if (isGuestMode.value) {
    watchlist.value = createDefaultWatchlist()
    return
  }

  syncWatchlistInFlight.value = true
  try {
    const cloudItems = await fetchUserWatchlist<PersistedStock>()
    let sourceItems = cloudItems

    if (!cloudItems.length) {
      const scopedKey = getScopedStorageKey(WATCHLIST_STORAGE_KEY)
      const fallbackKey = WATCHLIST_STORAGE_KEY
      const localRaw = (scopedKey ? localStorage.getItem(scopedKey) : null) ?? localStorage.getItem(fallbackKey)
      if (localRaw) {
        try {
          const parsed = JSON.parse(localRaw) as PersistedStock[]
          if (Array.isArray(parsed) && parsed.length) {
            sourceItems = parsed
            await saveUserWatchlist(parsed)
            if (scopedKey) localStorage.removeItem(scopedKey)
            localStorage.removeItem(fallbackKey)
          }
        } catch {
          if (scopedKey) localStorage.removeItem(scopedKey)
          localStorage.removeItem(fallbackKey)
        }
      }
    }

    watchlist.value = sourceItems.map((stock) => restorePersistedStock(stock))
  } catch {
    watchlist.value = createDefaultWatchlist()
  } finally {
    syncWatchlistInFlight.value = false
  }
}

async function persistWatchlist(): Promise<void> {
  if (isGuestMode.value || syncWatchlistInFlight.value) return

  const payload = watchlist.value.map((stock) => toPersistedStock(stock))
  syncWatchlistInFlight.value = true
  try {
    await saveUserWatchlist(payload)
  } catch (error) {
    stockActionHint.value = error instanceof Error ? error.message : '自选股同步失败'
  } finally {
    syncWatchlistInFlight.value = false
  }
}

async function loadChats(): Promise<void> {
  chats.value = []
  activeChatId.value = null

  if (isGuestMode.value) {
    activeAgentId.value = PRIMARY_AGENT_ID
    createNewChat(false, PRIMARY_AGENT_ID)
    return
  }

  syncChatsInFlight.value = true
  try {
    const cloudChats = await fetchUserChats()
    let sourceChats: CloudChatSession[] = cloudChats

    if (!cloudChats.length) {
      const scopedKey = getScopedStorageKey(STORAGE_KEY)
      const fallbackKey = STORAGE_KEY
      const localRaw = (scopedKey ? localStorage.getItem(scopedKey) : null) ?? localStorage.getItem(fallbackKey)
      if (localRaw) {
        try {
          const parsed = JSON.parse(localRaw) as CloudChatSession[]
          if (Array.isArray(parsed) && parsed.length) {
            sourceChats = parsed
            await saveUserChats(parsed)
            if (scopedKey) localStorage.removeItem(scopedKey)
            localStorage.removeItem(fallbackKey)
          }
        } catch {
          if (scopedKey) localStorage.removeItem(scopedKey)
          localStorage.removeItem(fallbackKey)
        }
      }
    }

    chats.value = sourceChats.map((chat) => ({
      id: chat.id || createUid('chat'),
      agentId: chat.agentId || PRIMARY_AGENT_ID,
      title: normalizeChatTitle(chat.title, chat.agentId || PRIMARY_AGENT_ID),
      createdAt: chat.createdAt || new Date().toLocaleString(),
      messages:
        Array.isArray(chat.messages) && chat.messages.length
          ? chat.messages
          : [createDefaultAiMessage(chat.agentId || PRIMARY_AGENT_ID)],
    }))
  } catch {
    chats.value = []
  } finally {
    syncChatsInFlight.value = false
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

async function persistChats(): Promise<void> {
  if (isGuestMode.value || syncChatsInFlight.value) return

  const payload: CloudChatSession[] = chats.value.map((chat) => ({
    id: chat.id,
    agentId: chat.agentId,
    title: chat.title,
    createdAt: chat.createdAt,
    messages: chat.messages,
  }))

  syncChatsInFlight.value = true
  try {
    await saveUserChats(payload)
  } catch {
    // keep local in-memory state when sync fails
  } finally {
    syncChatsInFlight.value = false
  }
}

function scrollMessagesToBottom(force = false): void {
  nextTick(() => {
    const panel = messagesPanelRef.value
    if (!panel) return
    if (!force && !shouldStickToLatestMessage.value) return
    panel.scrollTop = panel.scrollHeight
  })
}

function renderMessages(forceScroll = false): void {
  scrollMessagesToBottom(forceScroll)
}

function handleMessagesScroll(): void {
  const panel = messagesPanelRef.value
  if (!panel) return
  const distanceToBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight
  shouldStickToLatestMessage.value = distanceToBottom <= 24
}

function transitionToChat(chatId: string): void {
  if (chatId === activeChatId.value || !getChatById(chatId)) return
  activeChatId.value = chatId
  shouldStickToLatestMessage.value = true
  renderMessages(true)
}

function createNewChat(withAnim = true, targetAgentId = activeAgentId.value): void {
  const id = createUid('chat')
  chats.value.unshift({
    id,
    agentId: targetAgentId,
    title: defaultChatTitle(targetAgentId),
    createdAt: new Date().toLocaleString(),
    messages: [createDefaultAiMessage(targetAgentId)],
  })
  activeAgentId.value = targetAgentId
  void persistChats()

  if (!activeChatId.value || !withAnim) {
    activeChatId.value = id
    shouldStickToLatestMessage.value = true
    renderMessages(true)
    return
  }

  transitionToChat(id)
}

function onNewChatClick(): void {
  if (isGuestMode.value) {
    openSignInDialog('登录后才可以创建并保存历史对话。')
    return
  }

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

  transitionToChat(existingChat.id)
}

function toggleAgentPicker(): void {
  isAgentPickerExpanded.value = !isAgentPickerExpanded.value
}

function switchChat(chatId: string): void {
  if (isGuestMode.value) {
    openSignInDialog('登录后才可以切换和保存历史对话。')
    return
  }

  if (isAiResponding.value) return
  transitionToChat(chatId)
}

function deleteChat(chatId: string): void {
  if (isGuestMode.value) {
    openSignInDialog('登录后才可以管理和保存历史对话。')
    return
  }

  if (isAiResponding.value) return
  const removingActive = chatId === activeChatId.value
  chats.value = chats.value.filter((chat) => chat.id !== chatId)
  if (removingActive) {
    const firstChat = chats.value.find((chat) => chat.agentId === activeAgentId.value)
    if (firstChat) transitionToChat(firstChat.id)
    else {
      activeChatId.value = null
      createNewChat(false, activeAgentId.value)
    }
  }
  void persistChats()
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

function renderAiMessage(content: string): string {
  return renderMarkdownToHtml(content)
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
    streamHint.value = buildChatStartHint(
      payload?.reasoning === 'enabled',
      (payload?.memory as ChatStartMemoryPayload | null) ?? null,
    )
    return
  }

  if (frame.event === 'reasoning') {
    const content = typeof payload?.content === 'string' ? payload.content : ''
    if (content) streamHint.value = '推理中：' + content
    return
  }

  if (frame.event === 'tool_call') {
    const toolName = typeof payload?.name === 'string' ? payload.name : 'unknown_tool'
    streamHint.value = '调用工具：' + toolName
    return
  }

  if (frame.event === 'tool_result') {
    if (typeof payload?.error === 'string' && payload.error) {
      streamHint.value = '工具返回错误：' + payload.error
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
    appendAiMessage(chatId, messageIndex, '\n\n[错误] ' + message)
    renderMessages(false)
    return
  }

  if (frame.event === 'end') {
    const finishReason = typeof payload?.finish_reason === 'string' ? payload.finish_reason : 'stop'
    streamHint.value = '回复完成：' + finishReason
  }
}

async function streamChatBySse(
  chatId: string,
  messageIndex: number,
  prompt: string,
  agentId: string,
  messages: StructuredChatMessage[],
): Promise<void> {
  const agent = getAgentById(agentId)
  const controller = new AbortController()
  activeAiAbortController = controller

  const response = await apiFetch(
    AI_CHAT_ENDPOINT,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        chatId,
        agentId,
        systemPrompt: agent.systemPrompt,
        originalPrompt: prompt,
        messages,
        stream: true,
        sse: true,
        thinking: useThinking.value,
      }),
      signal: controller.signal,
    },
    'optional',
  )

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || ('请求失败: ' + response.status))
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
    const { frames } = consumeSseFrames(buffer + '\n\n')
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
  const requestMessages = buildStructuredChatMessages(
    targetChat.messages,
    getAgentById(currentAgentId).greeting,
  )
  if (targetChat.title === '新对话') {
    targetChat.title = text.slice(0, 14)
  }

  const aiMessageIndex = targetChat.messages.push({ role: 'ai', content: '' }) - 1

  chatInput.value = ''
  isAiResponding.value = true
  streamHint.value = '正在连接 AI 服务...'
  shouldStickToLatestMessage.value = true
  renderMessages(true)
  void persistChats()

  try {
    await streamChatBySse(currentChatId, aiMessageIndex, text, currentAgentId, requestMessages)

    const chat = getChatById(currentChatId)
    const msg = chat?.messages[aiMessageIndex]
    if (msg && !msg.content.trim()) {
      msg.content = '已接收请求，但模型未返回文本内容。'
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '请求失败'
    appendAiMessage(currentChatId, aiMessageIndex, '\n\n[连接失败] ' + message)
  } finally {
    isAiResponding.value = false
    activeAiAbortController = null
    window.setTimeout(() => {
      streamHint.value = ''
    }, 1500)
    void persistChats()
    renderMessages(false)
  }
}

function onChatInputKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

function openHeaderSignIn(): void {
  openSignInDialog('登录后可添加自选股、保存历史对话，并同步你的个人工作区。')
}

async function startKsuserSignIn(redirectTarget?: string): Promise<void> {
  const target = redirectTarget || pendingRedirectAfterSignIn.value || (isAuthCallbackRoute.value ? '/' : getCurrentWorkspacePath()) || '/'

  try {
    await authStore.startSignIn(target)
  } catch {
    // error message is already stored in auth store for UI rendering
  }
}

async function handleKsuserCallback(): Promise<void> {
  if (callbackStatus.value === 'loading') return

  callbackStatus.value = 'loading'
  callbackMessage.value = '正在校验授权结果并同步账号信息，请稍候。'

  try {
    await authStore.finishSignIn(new URLSearchParams(window.location.search))
    callbackStatus.value = 'success'
    callbackMessage.value = '登录成功，正在返回市场总览...'
    // The first successful OAuth login always lands on the stable dashboard.
    // This also prevents a stale redirect query from sending users back to Ksuser.
    await router.replace('/')
  } catch (error) {
    callbackStatus.value = 'error'
    callbackMessage.value = error instanceof Error ? error.message : 'Ksuser 登录失败，请稍后重试。'
  }
}

function goToAccountCenter(): void {
  if (isAccountRoute.value) return
  void router.push('/account')
}

async function logout(): Promise<void> {
  try {
    await logoutAccount()
  } catch {
    // ignore remote logout error and clear local state anyway
  }
  authStore.logout()
  closeSignInDialog()
  void router.replace('/')
}

function retryKsuserSignIn(): void {
  void startKsuserSignIn()
}

async function refreshAccountSessions(): Promise<void> {
  if (!authStore.isAuthenticated) {
    accountSessions.value = []
    return
  }

  accountActionError.value = ''
  try {
    const [user, sessions] = await Promise.all([fetchAccountUser(), fetchAccountSessions()])
    accountSessions.value = sessions
    if (authStore.session) {
      authStore.session.profile.nickname = user.nickname
      authStore.session.profile.email = user.email
      authStore.session.profile.avatar_url = user.avatar_url
      authStore.session.profile.openid = user.openid
      authStore.session.profile.unionid = user.unionid
      authStore.session.openid = user.openid
      authStore.session.unionid = user.unionid
    }
  } catch (error) {
    accountActionError.value = error instanceof Error ? error.message : '账号会话读取失败'
  }
}

async function revokeCurrentSession(): Promise<void> {
  if (accountActionBusy.value) return
  accountActionBusy.value = true
  accountActionError.value = ''
  try {
    await revokeSessions('current')
    authStore.logout()
    await router.replace('/')
  } catch (error) {
    accountActionError.value = error instanceof Error ? error.message : '撤销当前会话失败'
  } finally {
    accountActionBusy.value = false
  }
}

async function revokeOtherSessions(): Promise<void> {
  if (accountActionBusy.value) return
  accountActionBusy.value = true
  accountActionError.value = ''
  try {
    await revokeSessions('others')
    await refreshAccountSessions()
  } catch (error) {
    accountActionError.value = error instanceof Error ? error.message : '撤销其他会话失败'
  } finally {
    accountActionBusy.value = false
  }
}

watch(
  watchlist,
  () => {
    void persistWatchlist()
  },
  { deep: true },
)

watch(
  () => authStore.session?.profile.openid ?? '__guest__',
  () => {
    void loadWatchlist()
    void loadChats()
  },
  { immediate: true },
)

watch(
  () => [route.query.auth, route.query.redirect, authStore.isAuthenticated, isAuthCallbackRoute.value] as const,
  ([authQuery, redirectQuery, isAuthenticated, isAuthCallback]) => {
    if (isAuthenticated || isAuthCallback) {
      pendingRedirectAfterSignIn.value = null
      return
    }

    if (authQuery === SIGNIN_QUERY_VALUE) {
      if (typeof redirectQuery === 'string' && redirectQuery.startsWith('/')) {
        pendingRedirectAfterSignIn.value = redirectQuery
      }
      if (!authStore.busy) {
        void startKsuserSignIn(pendingRedirectAfterSignIn.value || '/')
      }
    }
  },
  { immediate: true },
)

watch(
  isStrategyRoute,
  (value) => {
    if (value) hasVisitedStrategy.value = true
  },
  { immediate: true },
)

watch(
  () => [isAccountRoute.value, authStore.isAuthenticated] as const,
  ([isAccount, isAuthenticated]) => {
    if (!isAccount || !isAuthenticated) {
      accountSessions.value = []
      accountActionError.value = ''
      return
    }
    void refreshAccountSessions()
  },
  { immediate: true },
)

watch(
  () => route.name,
  (name) => {
    if (name === 'auth-callback') {
      void handleKsuserCallback()
      return
    }

    callbackStatus.value = 'idle'
    callbackMessage.value = ''
  },
  { immediate: true },
)

onMounted(() => {
  window.addEventListener('desktop-view-change', onDesktopViewChange)
  if (document.documentElement.classList.contains('desktop-shell')) {
    desktopView.value = document.querySelector('.app-page')?.classList.contains('desktop-view-ai') ? 'ai' : 'market'
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('desktop-view-change', onDesktopViewChange)
  activeAiAbortController?.abort()
})
</script>

<template>
  <div class="app-page" :data-desktop-navigation="desktopView ? 'vue' : undefined">
    <div class="app">
      <header class="page-header">
        <div class="page-copy">
          <div class="page-kicker">AI Investment Console</div>
          <div class="page-title">{{ pageTitle }}</div>
          <div class="page-subtitle">{{ pageDescription }}</div>
        </div>
        <div class="header-actions">
          <a
            class="desktop-client-link"
            href="https://github.com/MUYEwhisper/AI-Investment-Strategies/releases/latest"
            target="_blank"
            rel="noreferrer"
            id="desktopClientDownloadLink"
            aria-label="下载 Windows 桌面客户端"
          >
            下载 Windows 客户端
          </a>
          <nav class="page-switcher" aria-label="页面导航">
            <RouterLink class="page-switch" :class="{ active: isDashboardRoute }" to="/" id="pageNavDashboard">
              市场总览
            </RouterLink>
            <RouterLink
              v-if="authStore.isAuthenticated"
              class="page-switch"
              :class="{ active: isStrategyRoute }"
              to="/strategy"
              id="pageNavStrategy"
            >
              策略工作台
            </RouterLink>
            <button
              v-else
              class="page-switch page-switch-locked"
              type="button"
              id="pageNavStrategyLocked"
              @click="openSignInDialog('登录后可访问策略工作台。', '/strategy')"
            >
              策略工作台（需登录）
            </button>
            <RouterLink
              v-if="authStore.isAuthenticated && !isAuthCallbackRoute"
              class="page-switch"
              :class="{ active: isAccountRoute }"
              to="/account"
              id="pageNavAccount"
            >
              账号中心
            </RouterLink>
          </nav>

          <div v-if="authStore.isAuthenticated && !isAuthCallbackRoute" class="user-toolbar">
            <button class="user-chip" type="button" @click="goToAccountCenter">
              <img v-if="currentUserAvatar" :src="currentUserAvatar" :alt="currentUserName + ' avatar'" class="user-chip-avatar" />
              <span v-else class="user-chip-avatar user-chip-avatar-fallback">{{ currentUserName.slice(0, 1) }}</span>
              <span class="user-chip-copy">
                <strong>{{ currentUserName }}</strong>
                <small>{{ currentUserEmail || 'Ksuser 已连接' }}</small>
              </span>
            </button>
            <button class="btn" type="button" @click="logout">退出</button>
          </div>
          <div v-else-if="!isAuthCallbackRoute" class="guest-toolbar">
            <span class="guest-chip">游客模式</span>
            <button class="btn primary login-entry-btn" type="button" @click="openHeaderSignIn">登录</button>
          </div>
        </div>
      </header>

      <Transition :css="false" @enter="enterPage" @enter-cancelled="cancelMotion">
        <div :key="activeStageKey" class="page-stage">
          <section v-if="isAuthCallbackRoute" class="panel auth-callback-panel" id="authCallbackPanel">
            <div class="auth-callback-badge" :class="callbackStatus">{{ callbackStatus === 'error' ? '授权失败' : '授权处理中' }}</div>
            <h2 class="auth-callback-title">
              {{ callbackStatus === 'success' ? 'Ksuser 登录成功' : callbackStatus === 'error' ? 'Ksuser 登录失败' : '正在完成登录' }}
            </h2>
            <p class="auth-callback-message">{{ callbackMessage || '正在准备授权结果...' }}</p>
            <div class="auth-callback-actions">
              <button v-if="callbackStatus === 'error'" class="btn primary" type="button" @click="retryKsuserSignIn">
                重新登录
              </button>
              <RouterLink v-if="callbackStatus === 'error'" class="btn" to="/signin">返回登录页</RouterLink>
            </div>
          </section>

          <KsuserAccountCenter
            v-else-if="isAccountRoute && authStore.session"
            :session="authStore.session"
            :sessions="accountSessions"
            :busy="accountActionBusy"
            :error-message="accountActionError"
            @sign-out="logout"
            @revoke-current="revokeCurrentSession"
            @revoke-others="revokeOtherSessions"
            @refresh-sessions="refreshAccountSessions"
          />

          <template v-else>
              <div v-if="!isStrategyRoute" key="workspace-dashboard" class="workspace-stage">
              <Transition :css="false" @enter="enterPage" @enter-cancelled="cancelMotion">
              <section v-show="desktopView !== 'ai'" class="top-grid">
        <article class="panel watchlist-wrap" id="watchlistPanel">
          <div class="panel-header">
            <div>
              <div class="panel-title">自选股区</div>
              <div class="panel-subtitle">{{ isGuestMode ? '登录后可保存自选股并同步到账号。' : '添加或选择股票，查看该股参数与分析标签。' }}</div>
            </div>
            <button
              v-if="!isGuestMode"
              class="btn"
              id="refreshWatchlistBtn"
              :disabled="isWatchlistRefreshing || isAddingStock"
              @click="refreshWatchlistData"
            >
              {{ watchlistRefreshButtonText }}
            </button>
          </div>

          <div v-if="isGuestMode" class="watchlist-guest-card">
            <div class="watchlist-guest-title">登录后保存自选股</div>
            <div class="watchlist-guest-text">游客模式下不展示和保存自选股，登录后可添加股票并同步到账户。</div>
            <button class="btn primary watchlist-login-btn" type="button" @click="openHeaderSignIn">登录后管理自选</button>
          </div>

          <template v-else>
            <Transition :css="false" @enter="enterStock" @enter-cancelled="cancelMotion">
            <div
              v-show="!isDetailVisible"
              class="add-stock"
              id="addStockForm"
            >
              <input
                v-model="stockInput"
                id="stockInput"
                type="text"
                placeholder="输入股票名或代码，例如：贵州茅台 或 600519"
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
            </Transition>

            <Transition :css="false" @enter="enterStock" @enter-cancelled="cancelMotion">
            <TransitionGroup v-show="!isDetailVisible" tag="div" class="watchlist-view" id="watchlistView"
              :css="false" @enter="enterItem" @leave="leaveItem" @enter-cancelled="cancelMotion" @leave-cancelled="cancelMotion">
              <div
                v-for="stock in watchlist"
                :key="stock.id"
                class="stock-item"
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
                    {{ stock.isLoading && stock.change === null ? '同步中...' : formatChange(stock.change) }}
                  </div>
                  <button class="btn primary row-action-btn" type="button" @click.stop="deleteStock(stock.id)">
                    删除
                  </button>
                </div>
              </div>
            </TransitionGroup>
            </Transition>

            <Transition :css="false" @enter="enterStock" @enter-cancelled="cancelMotion">
            <div
              v-show="isDetailVisible && selectedStock"
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
            </Transition>
          </template>
        </article>
        <article class="panel sector-panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">板块分析区</div>
              <div class="panel-subtitle">概念板块、行业板块的资金流向、情绪热度与政策风向。</div>
            </div>
            <button
              class="btn refresh-sector-btn"
              :class="{ 'is-loading': isSectorLoading }"
              id="refreshSectorBtn"
              :disabled="isSectorLoading"
              :aria-busy="isSectorLoading ? 'true' : 'false'"
              @click="refreshSectorData"
            >
              <span class="btn-content">
                <span v-if="isSectorLoading" class="btn-spinner" aria-hidden="true"></span>
                <span>{{ isSectorLoading ? '分析中' : '刷新数据' }}</span>
                <span v-if="isSectorLoading" class="loading-dots" aria-hidden="true">
                  <span>.</span>
                  <span>.</span>
                  <span>.</span>
                </span>
              </span>
            </button>
          </div>

          <div class="sector-body">
            <div class="chart-card">
              <div class="card-title">板块图表分析（直观饼图）</div>
              <div v-if="sectorStatusNote" class="sector-status-note">{{ sectorStatusNote }}</div>
              <div class="pie-grid">
                <div class="pie-box">
                  <div class="pie-title">资金关注</div>
                  <div class="pie-wrap">
                    <EChartsPie
                      id="flowChart"
                      :items="flowChartItems"
                      mode="donut"
                      series-name="资金关注度"
                      :loading="isSectorLoading"
                      empty-text="暂无资金关注数据"
                    />
                  </div>
                </div>
                <div class="pie-box">
                  <div class="pie-title">市场情绪</div>
                  <div class="pie-wrap">
                    <EChartsPie
                      id="sentimentChart"
                      :items="sentimentChartItems"
                      mode="pie"
                      series-name="市场情绪"
                      :loading="isSectorLoading"
                      empty-text="暂无情绪数据"
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
      </Transition>

      <Transition :css="false" @enter="enterPage" @enter-cancelled="cancelMotion">
      <section v-show="desktopView !== 'market'" class="panel chat-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">AI 对话区</div>
            <div class="panel-subtitle">投资分析大模型交互，支持历史会话与智能体切换。</div>
          </div>
        </div>

        <div class="chat-main">
          <aside class="chat-sidebar">
            <div class="chat-sidebar-section agent-section">
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
                  {{ isAgentPickerExpanded ? '收起智能体' : '展开其他智能体（' + foldedAgents.length + '）' }}
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
            </div>

            <div class="chat-sidebar-section history-section">
              <div class="history-head">
                <strong style="font-size: 13px">{{ authStore.isAuthenticated ? (activeAgent?.name || '智能体') + '会话' : '游客模式' }}</strong>
                <button
                  class="btn history-new-btn"
                  id="newChatBtn"
                  :disabled="isAiResponding"
                  @click="onNewChatClick"
                >
                  {{ authStore.isAuthenticated ? '新建' : '登录后保存' }}
                </button>
              </div>

              <TransitionGroup v-if="authStore.isAuthenticated" tag="div" class="history-list" id="historyList"
                :css="false" @enter="enterItem" @leave="leaveItem" @enter-cancelled="cancelMotion" @leave-cancelled="cancelMotion">
                <div
                  v-for="chat in activeAgentChats"
                  :key="chat.id"
                  class="history-item"
                  :class="{
                    active: chat.id === activeChatId,
                  }"
                  @click="switchChat(chat.id)"
                >
                  <div class="history-meta">
                    <div class="history-title">{{ chat.title }}</div>
                    <div class="history-time">{{ chat.createdAt }}</div>
                  </div>
                  <button
                    class="btn row-action-btn sidebar-delete-btn"
                    type="button"
                    :disabled="isAiResponding"
                    @click.stop="deleteChat(chat.id)"
                  >
                    删除
                  </button>
                </div>
                <div v-if="!activeAgentChats.length" key="empty-history" class="history-empty">当前智能体暂无会话，点击右上角新建开始对话。</div>
              </TransitionGroup>
              <div v-else class="history-guest-card">
                <div class="history-guest-title">当前支持直接体验 AI 对话</div>
                <div class="history-guest-text">游客对话不会保存到账号，登录后可同步历史会话和个人偏好。</div>
                <button class="btn primary history-login-btn" type="button" @click="openHeaderSignIn">登录后保存会话</button>
              </div>
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
            <Transition :css="false" @enter="enterPage" @enter-cancelled="cancelMotion">
            <div :key="activeChatId || 'empty-chat'" ref="messagesPanelRef" class="messages" id="messages" @scroll="handleMessagesScroll">
              <TransitionGroup tag="div" class="message-list" :css="false" @enter="enterItem" @enter-cancelled="cancelMotion">
              <div
                v-for="(msg, idx) in activeChat?.messages ?? []"
                :key="(activeChat?.id || 'chat') + '_' + idx"
                class="msg"
                :class="{
                  user: msg.role === 'user',
                  ai: msg.role === 'ai',
                }"
              >
                <div
                  v-if="msg.role === 'ai'"
                  class="msg-markdown"
                  v-html="renderAiMessage(msg.content)"
                ></div>
                <div v-else class="msg-text">{{ msg.content }}</div>
              </div>
              </TransitionGroup>
            </div>
            </Transition>
            <div class="chat-input-wrap">
              <textarea
                v-model="chatInput"
                id="chatInput"
                :placeholder="'向' + (activeAgent?.name || '智能体') + '提问，例如：结合半导体板块资金流向，给出仓位建议'"
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
      </Transition>
    </div>
              <div v-else key="workspace-strategy" class="workspace-stage">
                <KeepAlive>
                  <StrategyWorkbenchPage
                    v-if="hasVisitedStrategy"
                    :watchlist="watchlist"
                    :selected-stock="selectedStock ?? null"
                  />
                </KeepAlive>
              </div>
          </template>
        </div>
      </Transition>

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
  grid-auto-rows: auto;
  gap: 14px;
  max-width: 1800px;
  margin: 0 auto;
}

.page-stage {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.workspace-stage {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.34);
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.24), transparent 30%),
    linear-gradient(135deg, rgba(13, 27, 42, 0.2), rgba(59, 130, 246, 0.12), rgba(255, 255, 255, 0.12));
  box-shadow:
    var(--shadow),
    inset 0 1px 0 rgba(255, 255, 255, 0.45);
  backdrop-filter: blur(14px) saturate(132%);
  -webkit-backdrop-filter: blur(14px) saturate(132%);
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.desktop-client-link {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 0 14px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  color: rgba(247, 251, 255, 0.94);
  font-size: 12px;
  font-weight: 800;
  text-decoration: none;
  white-space: nowrap;
  transition: transform var(--motion-fast) var(--motion-ease), background var(--motion-normal) var(--motion-ease);
}

.desktop-client-link:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.24);
}

.desktop-client-link:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(165, 205, 255, 0.38);
}

.page-copy {
  display: grid;
  gap: 6px;
}

.page-kicker {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(232, 243, 255, 0.78);
}

.page-title {
  font-size: clamp(26px, 3.5vw, 38px);
  font-weight: 800;
  line-height: 1.04;
  color: #ffffff;
}

.page-subtitle {
  max-width: 760px;
  font-size: 13px;
  line-height: 1.65;
  color: rgba(236, 246, 255, 0.9);
}

.page-switcher {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.24);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.page-switch {
  min-width: 116px;
  padding: 10px 14px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: rgba(238, 247, 255, 0.86);
  font-size: 13px;
  font-weight: 700;
  text-align: center;
  text-decoration: none;
  font-family: inherit;
  line-height: 1.2;
  cursor: pointer;
  transition:
    transform var(--motion-fast) var(--motion-ease),
    background var(--motion-normal) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    color var(--motion-fast) var(--motion-ease);
}

.page-switch:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  color: #ffffff;
}

.page-switch:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(165, 205, 255, 0.38);
}

.page-switch.active {
  background: rgba(255, 255, 255, 0.94);
  color: #0f3e74;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.76),
    0 10px 18px rgba(9, 41, 93, 0.16);
}

.page-switch-locked {
  color: rgba(231, 244, 255, 0.7);
}

.page-switch-locked:hover {
  color: rgba(231, 244, 255, 0.86);
}

.user-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.guest-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.guest-chip {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(8, 22, 39, 0.24);
  color: rgba(244, 248, 255, 0.92);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.login-entry-btn {
  min-width: 110px;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
  padding: 8px 10px 8px 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  color: #f8fbff;
  cursor: pointer;
  transition:
    transform var(--motion-fast) var(--motion-ease),
    background var(--motion-fast) ease;
}

.user-chip:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.22);
}

.user-chip-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  object-fit: cover;
  flex: 0 0 auto;
}

.user-chip-avatar-fallback {
  display: grid;
  place-items: center;
  font-weight: 800;
  background: rgba(255, 255, 255, 0.2);
}

.user-chip-copy {
  display: grid;
  text-align: left;
}

.user-chip-copy strong {
  font-size: 13px;
}

.user-chip-copy small {
  color: rgba(238, 247, 255, 0.82);
  font-size: 11px;
}

.auth-callback-panel {
  display: grid;
  justify-items: start;
  gap: 14px;
  padding: 28px;
  border-radius: 28px;
}

.auth-callback-badge {
  padding: 7px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: rgba(14, 165, 233, 0.12);
  color: #0f4f82;
}

.auth-callback-badge.success {
  background: rgba(31, 157, 98, 0.12);
  color: #176c46;
}

.auth-callback-badge.error {
  background: rgba(214, 69, 69, 0.14);
  color: #aa2e2e;
}

.auth-callback-title {
  font-size: clamp(28px, 4vw, 40px);
  line-height: 1.04;
}

.auth-callback-message {
  max-width: 760px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--sub);
}

.auth-callback-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.guest-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px;
  border-radius: 28px;
  border: 1px solid rgba(255, 236, 196, 0.34);
  background:
    radial-gradient(circle at top right, rgba(255, 200, 90, 0.34), transparent 30%),
    linear-gradient(135deg, rgba(22, 28, 37, 0.82), rgba(36, 43, 54, 0.78));
  color: #f7fbff;
  box-shadow:
    0 24px 48px rgba(7, 19, 36, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.guest-banner-copy {
  display: grid;
  gap: 8px;
  max-width: 760px;
}

.guest-banner-kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(255, 193, 71, 0.92);
}

.guest-banner h2 {
  font-size: clamp(24px, 3vw, 34px);
  line-height: 1.08;
}

.guest-banner p {
  font-size: 14px;
  line-height: 1.75;
  color: rgba(231, 238, 247, 0.84);
}

.guest-banner-btn {
  min-width: 184px;
  min-height: 48px;
  padding-inline: 18px;
  white-space: nowrap;
}

.guest-banner-compact {
  padding-block: 18px;
}

.top-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.02fr) minmax(0, 1.98fr);
  gap: 14px;
  min-height: 0;
  height: clamp(480px, 54vh, 585px);
  align-items: stretch;
}

.top-grid > .panel {
  height: 100%;
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

.refresh-sector-btn .btn-content {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.refresh-sector-btn .btn-spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(20, 58, 102, 0.22);
  border-top-color: rgba(20, 58, 102, 0.88);
  animation: sectorSpin 0.8s linear infinite;
}

.refresh-sector-btn .loading-dots {
  display: inline-flex;
  gap: 1px;
  min-width: 14px;
}

.refresh-sector-btn .loading-dots span {
  opacity: 0.25;
  transform: translateY(0);
  animation: loadingDotPulse 0.95s ease-in-out infinite;
}

.refresh-sector-btn .loading-dots span:nth-child(2) {
  animation-delay: 0.12s;
}

.refresh-sector-btn .loading-dots span:nth-child(3) {
  animation-delay: 0.24s;
}

.refresh-sector-btn.is-loading {
  cursor: progress;
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

.sector-panel {
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

.watchlist-guest-card {
  margin: 16px;
  padding: 22px 20px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  background:
    radial-gradient(circle at top right, rgba(255, 198, 94, 0.18), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(244, 249, 255, 0.62));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 14px 28px rgba(20, 60, 120, 0.12);
  display: grid;
  gap: 12px;
  align-content: start;
}

.watchlist-guest-title {
  font-size: 22px;
  font-weight: 800;
  color: #10263f;
}

.watchlist-guest-text {
  max-width: 520px;
  font-size: 14px;
  line-height: 1.8;
  color: rgba(40, 69, 101, 0.82);
}

.watchlist-login-btn {
  width: fit-content;
  min-width: 156px;
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
  flex: 1;
  align-items: start;
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
  min-height: 0;
  align-self: stretch;
  display: flex;
  flex-direction: column;
}

.chart-card {
  align-self: start;
  height: auto;
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
  overflow: hidden;
}

.pie-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 6px;
}

.pie-wrap {
  height: 190px;
  overflow: hidden;
}

.insight-list {
  display: grid;
  gap: 8px;
  margin-top: 8px;
  min-height: 0;
  overflow-y: auto;
  flex: 1;
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
  height: clamp(560px, 58vh, 820px);
}

.chat-main {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
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
  height: 100%;
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

.chat-sidebar {
  border: 1px solid var(--surface-stroke);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.66);
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.chat-sidebar-section,
.history-list,
.messages {
  scrollbar-width: thin;
  scrollbar-color: #b8ccea transparent;
}

.chat-sidebar-section::-webkit-scrollbar,
.history-list::-webkit-scrollbar,
.messages::-webkit-scrollbar {
  width: 9px;
}

.chat-sidebar-section::-webkit-scrollbar-track,
.history-list::-webkit-scrollbar-track,
.messages::-webkit-scrollbar-track {
  background: transparent;
}

.chat-sidebar-section::-webkit-scrollbar-thumb,
.history-list::-webkit-scrollbar-thumb,
.messages::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #c5d8f5, #9fbde8);
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: content-box;
}

.chat-sidebar-section::-webkit-scrollbar-thumb:hover,
.history-list::-webkit-scrollbar-thumb:hover,
.messages::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, #afcaef, #84aee3);
  background-clip: content-box;
}

.chat-sidebar-section {
  min-height: 0;
}

.agent-section {
  flex: 0 1 auto;
  max-height: 300px;
  min-height: 0;
  overflow-y: auto;
  border-bottom: 1px solid rgba(126, 166, 224, 0.2);
}

.agent-picker {
  padding: 10px;
  background: rgba(255, 255, 255, 0.56);
  display: grid;
  gap: 8px;
}

.agent-focus {
  border: 1px solid rgba(126, 166, 224, 0.56);
  border-radius: 12px;
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.92), rgba(232, 244, 255, 0.9));
  padding: 10px;
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 2px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.74),
    0 8px 16px rgba(21, 62, 118, 0.12);
  transition:
    transform var(--motion-fast) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease),
    background var(--motion-normal) var(--motion-ease);
}

.agent-focus:hover {
  transform: translateY(-1px) scale(1.002);
  border-color: rgba(79, 140, 225, 0.72);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    0 12px 22px rgba(33, 93, 180, 0.2);
}

.agent-focus.active {
  border-color: rgba(88, 151, 239, 0.88);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    0 12px 24px rgba(29, 87, 174, 0.24);
}

.agent-focus:focus-visible {
  outline: none;
  border-color: rgba(67, 131, 221, 0.84);
  box-shadow:
    0 0 0 3px rgba(87, 150, 236, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 12px 24px rgba(29, 87, 174, 0.24);
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
  min-height: 40px;
}

.agent-fold-list {
  display: grid;
  gap: 7px;
}

.agent-option {
  border: 1px solid rgba(126, 166, 224, 0.48);
  border-radius: 11px;
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.9), rgba(233, 244, 255, 0.82));
  padding: 8px 9px;
  text-align: left;
  cursor: pointer;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.72),
    0 7px 14px rgba(20, 66, 128, 0.1);
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
  border-color: rgba(88, 151, 239, 0.82);
  background: linear-gradient(140deg, rgba(240, 248, 255, 0.98), rgba(217, 236, 255, 0.92));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.78),
    0 10px 18px rgba(29, 88, 174, 0.18);
}

.agent-option:focus-visible {
  outline: none;
  border-color: rgba(67, 131, 221, 0.84);
  box-shadow:
    0 0 0 3px rgba(87, 150, 236, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.78),
    0 10px 18px rgba(29, 88, 174, 0.18);
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
  margin: 8px 10px 0;
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

.chat-sidebar .btn {
  min-height: 40px;
  border-radius: 12px;
  font-weight: 700;
  letter-spacing: 0.1px;
}

.chat-sidebar .btn:not(.primary):not(.sidebar-delete-btn) {
  border: 1px solid rgba(126, 166, 224, 0.52);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.86), rgba(233, 245, 255, 0.8));
  color: #173a62;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.74),
    0 8px 16px rgba(20, 64, 124, 0.11);
}

.chat-sidebar .btn:not(.primary):not(.sidebar-delete-btn):hover {
  border-color: rgba(79, 140, 225, 0.74);
  background: linear-gradient(135deg, rgba(245, 251, 255, 0.94), rgba(225, 240, 255, 0.9));
  color: #114179;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 11px 20px rgba(26, 86, 170, 0.18);
}

.chat-sidebar .btn.primary {
  border: 1px solid rgba(177, 213, 255, 0.9);
  background: linear-gradient(135deg, rgba(9, 186, 215, 0.96), rgba(63, 134, 247, 0.98));
  color: #ffffff;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.36),
    0 10px 20px rgba(23, 119, 225, 0.35);
}

.chat-sidebar .btn.primary:hover {
  background: linear-gradient(135deg, rgba(12, 192, 220, 1), rgba(69, 140, 250, 1));
  border-color: rgba(193, 224, 255, 0.98);
  color: #ffffff;
}

.chat-sidebar .btn:focus-visible {
  outline: none;
  border-color: rgba(67, 131, 221, 0.84);
  box-shadow:
    0 0 0 3px rgba(87, 150, 236, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    0 10px 18px rgba(29, 88, 174, 0.2);
}

.history-new-btn {
  min-width: 72px;
}

.chat-sidebar #newChatBtn {
  border: 1px solid rgba(126, 166, 224, 0.52);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.86), rgba(233, 245, 255, 0.8));
  color: #173a62;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.74),
    0 8px 16px rgba(20, 64, 124, 0.11);
}

.chat-sidebar #newChatBtn:hover {
  border-color: rgba(79, 140, 225, 0.74);
  background: linear-gradient(135deg, rgba(245, 251, 255, 0.94), rgba(225, 240, 255, 0.9));
  color: #114179;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 11px 20px rgba(26, 86, 170, 0.18);
}

.sidebar-delete-btn {
  min-height: 30px;
  padding: 4px 10px;
  border: 1px solid rgba(251, 146, 146, 0.56);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(255, 242, 242, 0.92));
  color: #b42318;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.88),
    0 7px 14px rgba(185, 28, 28, 0.12);
}

.sidebar-delete-btn:hover {
  border-color: rgba(239, 68, 68, 0.7);
  background: linear-gradient(135deg, rgba(255, 250, 250, 1), rgba(255, 235, 235, 0.97));
  color: #991b1b;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 9px 16px rgba(185, 28, 28, 0.18);
}

.sidebar-delete-btn:focus-visible {
  outline: none;
  border-color: rgba(239, 68, 68, 0.82);
  box-shadow:
    0 0 0 3px rgba(248, 113, 113, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 9px 16px rgba(185, 28, 28, 0.2);
}

.history-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.history-list {
  --history-bubble-height: 76px;
  --history-bubble-gap: 8px;
  flex: 1 1 auto;
  overflow-y: auto;
  margin: 0 10px 10px;
  padding: 10px;
  display: grid;
  gap: var(--history-bubble-gap);
  align-content: start;
  grid-auto-rows: var(--history-bubble-height);
  height: auto;
  min-height: 0;
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

.history-guest-card {
  display: grid;
  gap: 12px;
  margin: 0 10px 10px;
  padding: 18px 16px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(255, 201, 114, 0.24), transparent 34%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.34), rgba(246, 250, 255, 0.28));
  border: 1px solid rgba(255, 214, 153, 0.38);
}

.history-guest-title {
  font-size: 14px;
  font-weight: 800;
  color: #143d5b;
}

.history-guest-text {
  font-size: 13px;
  line-height: 1.7;
  color: var(--sub);
}

.history-login-btn {
  width: 100%;
  min-height: 44px;
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
  height: 100%;
  min-height: 0;
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
  height: 100%;
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


.msg {
  max-width: min(92%, 1180px);
  border-radius: 12px;
  padding: 9px 11px;
  line-height: 1.6;
  font-size: 14px;
  border: 1px solid var(--line);
  white-space: normal;
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

.msg-text {
  white-space: pre-wrap;
}

.msg-markdown {
  color: #1f2a44;
}

.msg-markdown > :first-child {
  margin-top: 0;
}

.msg-markdown > :last-child {
  margin-bottom: 0;
}

.msg-markdown p,
.msg-markdown ul,
.msg-markdown ol,
.msg-markdown pre,
.msg-markdown blockquote,
.msg-markdown hr,
.msg-markdown h1,
.msg-markdown h2,
.msg-markdown h3,
.msg-markdown h4,
.msg-markdown h5,
.msg-markdown h6 {
  margin: 0 0 0.75em;
}

.msg-markdown ul,
.msg-markdown ol {
  padding-left: 1.4em;
}

.msg-markdown li + li {
  margin-top: 0.28em;
}

.msg-markdown h1,
.msg-markdown h2,
.msg-markdown h3,
.msg-markdown h4,
.msg-markdown h5,
.msg-markdown h6 {
  line-height: 1.35;
  color: #173354;
}

.msg-markdown h1 {
  font-size: 1.28em;
}

.msg-markdown h2 {
  font-size: 1.18em;
}

.msg-markdown h3 {
  font-size: 1.08em;
}

.msg-markdown code {
  padding: 0.1em 0.35em;
  border-radius: 6px;
  background: rgba(26, 67, 124, 0.08);
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 0.94em;
}

.msg-markdown pre {
  overflow-x: auto;
  padding: 0.75em 0.9em;
  border-radius: 10px;
  background: #f4f8ff;
  border: 1px solid #d7e5fa;
}

.msg-markdown pre code {
  padding: 0;
  background: transparent;
}

.msg-markdown blockquote {
  padding-left: 0.9em;
  border-left: 3px solid #9fc0ef;
  color: #4b6485;
}

.msg-markdown a {
  color: #1363df;
  text-decoration: none;
}

.msg-markdown a:hover {
  text-decoration: underline;
}

.message-list {
  display: grid;
  gap: 10px;
  align-content: start;
  min-width: 0;
}

.msg-markdown .md-table-wrap {
  overflow-x: auto;
  margin: 0 0 0.75em;
}

.msg-markdown table {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #d7e5fa;
  background: #ffffff;
}

.msg-markdown th,
.msg-markdown td {
  border: 1px solid #d7e5fa;
  padding: 0.5em 0.65em;
  vertical-align: top;
  line-height: 1.5;
}

.msg-markdown thead th {
  background: #edf4ff;
  color: #173354;
  font-weight: 700;
}

.msg-markdown tbody tr:nth-child(even) {
  background: #f8fbff;
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

@keyframes sectorSpin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@keyframes loadingDotPulse {
  0%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }

  50% {
    opacity: 0.95;
    transform: translateY(-1px);
  }
}


@media (max-width: 1100px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions {
    justify-content: stretch;
  }

  .page-switcher {
    width: 100%;
    justify-content: space-between;
  }

  .page-switch {
    flex: 1;
  }

  .user-toolbar {
    justify-content: space-between;
  }

  .guest-toolbar {
    justify-content: space-between;
  }

  .user-chip {
    flex: 1 1 240px;
  }

  .guest-banner {
    flex-direction: column;
    align-items: stretch;
  }

  .top-grid {
    grid-template-columns: 1fr;
    height: auto;
  }

  .sector-body {
    grid-template-columns: 1fr;
  }

  .chat-main {
    grid-template-columns: 1fr;
  }

  .chat-panel {
    height: clamp(560px, 58vh, 820px);
    min-height: 0;
  }

  .chat-sidebar {
    border-bottom: 1px solid var(--line);
    height: 320px;
  }

  .history-list {
    --history-bubble-height: 59px;
  }

  .agent-section {
    max-height: 180px;
    min-height: 0;
  }
}

@media (max-width: 720px) {
  .app-page {
    padding: 10px;
  }

  .app {
    grid-template-rows: auto auto;
  }

  .page-header {
    padding: 16px;
  }

  .page-switcher {
    display: grid;
    grid-template-columns: 1fr;
  }

  .header-actions,
  .guest-toolbar,
  .user-toolbar,
  .auth-callback-actions {
    width: 100%;
  }

  .user-chip {
    min-width: 0;
    width: 100%;
  }

  .guest-chip,
  .login-entry-btn,
  .guest-banner-btn {
    width: 100%;
    justify-content: center;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .pie-grid {
    grid-template-columns: 1fr;
  }

  .history-list {
    --history-bubble-height: 53px;
  }

}
</style>


