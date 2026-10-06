import { describe, expect, it } from 'vitest'

import { buildChatStartHint, buildStructuredChatMessages } from '../services/chat-memory'

describe('chat-memory helpers', () => {
  it('filters greeting, empty assistant placeholders, and transient failures', () => {
    const messages = buildStructuredChatMessages(
      [
        { role: 'ai', content: '你好，我是资产配置引擎。' },
        { role: 'user', content: '我偏稳健，帮我看看 600519' },
        { role: 'ai', content: '' },
        { role: 'ai', content: '\n\n[连接失败] timeout' },
        { role: 'ai', content: '可以先把风险偏好定为稳健，再看仓位上限。' },
      ],
      '你好，我是资产配置引擎。',
    )

    expect(messages).toEqual([
      { role: 'user', content: '我偏稳健，帮我看看 600519' },
      { role: 'assistant', content: '可以先把风险偏好定为稳健，再看仓位上限。' },
    ])
  })

  it('formats start hint with memory metadata', () => {
    expect(
      buildChatStartHint(true, {
        sharedMemoryLoaded: true,
        chatSummaryUsed: true,
        recentMessageCount: 12,
      }),
    ).toBe('连接成功：已启用推理 · 共享记忆已加载 · 历史摘要已启用 · 近期上下文 12 条')
  })
})
