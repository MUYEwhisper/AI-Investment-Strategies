export type StoredChatMessage = {
  role: 'user' | 'ai'
  content: string
}

export type StructuredChatMessage = {
  role: 'user' | 'assistant'
  content: string
}

export type ChatStartMemoryPayload = {
  sharedMemoryLoaded?: boolean
  chatSummaryUsed?: boolean
  recentMessageCount?: number
}

const TRANSIENT_ASSISTANT_PREFIX = /^\[(连接失败|错误)\]/

function normalizeText(input: string | null | undefined): string {
  return String(input ?? '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .trim()
}

export function buildStructuredChatMessages(
  messages: StoredChatMessage[],
  agentGreeting: string,
): StructuredChatMessage[] {
  const normalizedGreeting = normalizeText(agentGreeting)
  const normalizedMessages: StructuredChatMessage[] = []

  messages.forEach((message) => {
    const content = normalizeText(message.content)
    if (!content) return

    if (message.role === 'user') {
      normalizedMessages.push({ role: 'user', content })
      return
    }

    if (content === normalizedGreeting) return
    if (TRANSIENT_ASSISTANT_PREFIX.test(content)) return

    normalizedMessages.push({ role: 'assistant', content })
  })

  return normalizedMessages
}

export function buildChatStartHint(
  reasoningEnabled: boolean,
  memory?: ChatStartMemoryPayload | null,
): string {
  const segments = [reasoningEnabled ? '已启用推理' : '已关闭推理']

  if (memory) {
    if (memory.sharedMemoryLoaded) {
      segments.push('共享记忆已加载')
    }
    if (memory.chatSummaryUsed) {
      segments.push('历史摘要已启用')
    }
    if (typeof memory.recentMessageCount === 'number') {
      segments.push(`近期上下文 ${memory.recentMessageCount} 条`)
    }
  }

  return `连接成功：${segments.join(' · ')}`
}
