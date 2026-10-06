function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function sanitizeUrl(value: string): string | null {
  const normalized = value.trim()
  if (/^(https?:|mailto:)/i.test(normalized)) {
    return escapeHtml(normalized)
  }
  return null
}

function normalizeModelRichText(value: string): string {
  return value
    .replace(/\r\n?/g, '\n')
    .replace(/&nbsp;/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<p\b[^>]*>/gi, '\n\n')
    .replace(/<\/p\s*>/gi, '')
    .replace(/<div\b[^>]*>/gi, '\n\n')
    .replace(/<\/div\s*>/gi, '')
}

function parseInlineMarkdown(value: string): string {
  const codeTokens: string[] = []
  let html = escapeHtml(value).replace(/`([^`\n]+)`/g, (_, code: string) => {
    const token = `@@CODE_${codeTokens.length}@@`
    codeTokens.push(`<code>${code}</code>`)
    return token
  })

  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label: string, href: string) => {
    const safeHref = sanitizeUrl(href)
    if (!safeHref) return label
    return `<a href="${safeHref}" target="_blank" rel="noreferrer">${label}</a>`
  })

  html = html
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')

  return html.replace(/@@CODE_(\d+)@@/g, (_, index: string) => codeTokens[Number(index)] ?? '')
}

function renderParagraph(lines: string[]): string {
  if (!lines.length) return ''
  return `<p>${parseInlineMarkdown(lines.join('\n')).replace(/\n/g, '<br />')}</p>`
}

function renderList(type: 'ul' | 'ol', items: string[]): string {
  if (!items.length) return ''
  const body = items.map((item) => `<li>${parseInlineMarkdown(item)}</li>`).join('')
  return `<${type}>${body}</${type}>`
}

type TableAlignment = 'left' | 'center' | 'right' | null

function parseTableRow(line: string): string[] {
  const trimmed = line.trim()
  if (!trimmed.includes('|')) return []

  let content = trimmed
  if (content.startsWith('|')) content = content.slice(1)
  if (content.endsWith('|')) content = content.slice(0, -1)

  return content.split('|').map((cell) => cell.trim())
}

function isTableSeparatorLine(line: string): boolean {
  const cells = parseTableRow(line)
  if (!cells.length) return false
  return cells.every((cell) => /^:?-{3,}:?$/.test(cell))
}

function parseTableAlignment(value: string): TableAlignment {
  const trimmed = value.trim()
  const startsWithColon = trimmed.startsWith(':')
  const endsWithColon = trimmed.endsWith(':')
  if (startsWithColon && endsWithColon) return 'center'
  if (endsWithColon) return 'right'
  if (startsWithColon) return 'left'
  return null
}

function tableAlignStyle(alignment: TableAlignment): string {
  return alignment ? ` style="text-align:${alignment}"` : ''
}

function normalizeTableRow(cells: string[], length: number): string[] {
  if (length <= 0) return []
  const normalized = cells.slice(0, length)
  while (normalized.length < length) {
    normalized.push('')
  }
  return normalized
}

function renderTable(headerLine: string, separatorLine: string, bodyLines: string[]): string {
  const headers = parseTableRow(headerLine)
  if (!headers.length) return ''

  const alignments = parseTableRow(separatorLine).map((cell) => parseTableAlignment(cell))

  const headerHtml = normalizeTableRow(headers, headers.length)
    .map((cell, index) => `<th${tableAlignStyle(alignments[index] ?? null)}>${parseInlineMarkdown(cell)}</th>`)
    .join('')

  const bodyHtml = bodyLines
    .map((line) => normalizeTableRow(parseTableRow(line), headers.length))
    .filter((cells) => cells.length > 0)
    .map((cells) => {
      const row = cells
        .map((cell, index) => `<td${tableAlignStyle(alignments[index] ?? null)}>${parseInlineMarkdown(cell)}</td>`)
        .join('')
      return `<tr>${row}</tr>`
    })
    .join('')

  return `<div class="md-table-wrap"><table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`
}

export function renderMarkdownToHtml(source: string): string {
  const normalized = normalizeModelRichText(source)
  if (!normalized.trim()) return ''

  const lines = normalized.split('\n')
  const blocks: string[] = []
  const paragraphLines: string[] = []
  const quoteLines: string[] = []
  const listItems: string[] = []

  let activeListType: 'ul' | 'ol' | null = null
  let inCodeFence = false
  let codeFenceLanguage = ''
  let codeFenceLines: string[] = []

  const flushParagraph = (): void => {
    const paragraph = renderParagraph(paragraphLines)
    if (paragraph) blocks.push(paragraph)
    paragraphLines.length = 0
  }

  const flushList = (): void => {
    if (activeListType && listItems.length) {
      blocks.push(renderList(activeListType, listItems))
    }
    activeListType = null
    listItems.length = 0
  }

  const flushQuote = (): void => {
    if (!quoteLines.length) return
    blocks.push(`<blockquote>${renderMarkdownToHtml(quoteLines.join('\n'))}</blockquote>`)
    quoteLines.length = 0
  }

  const flushCodeFence = (): void => {
    const languageClass = codeFenceLanguage ? ` class="language-${escapeHtml(codeFenceLanguage)}"` : ''
    blocks.push(
      `<pre><code${languageClass}>${escapeHtml(codeFenceLines.join('\n'))}</code></pre>`,
    )
    inCodeFence = false
    codeFenceLanguage = ''
    codeFenceLines = []
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? ''
    const fenceMatch = line.match(/^```([\w-]+)?\s*$/)
    if (fenceMatch) {
      flushParagraph()
      flushList()
      flushQuote()
      if (inCodeFence) {
        flushCodeFence()
      } else {
        inCodeFence = true
        codeFenceLanguage = fenceMatch[1] ?? ''
        codeFenceLines = []
      }
      continue
    }

    if (inCodeFence) {
      codeFenceLines.push(line)
      continue
    }

    if (!line.trim()) {
      flushParagraph()
      flushList()
      flushQuote()
      continue
    }

    const quoteMatch = line.match(/^>\s?(.*)$/)
    if (quoteMatch) {
      flushParagraph()
      flushList()
      quoteLines.push(quoteMatch[1] ?? '')
      continue
    }

    flushQuote()

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      const level = headingMatch[1]?.length ?? 1
      blocks.push(`<h${level}>${parseInlineMarkdown(headingMatch[2] ?? '')}</h${level}>`)
      continue
    }

    if (/^([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      flushParagraph()
      flushList()
      blocks.push('<hr />')
      continue
    }

    const nextLine = lines[index + 1] ?? ''
    if (line.includes('|') && isTableSeparatorLine(nextLine)) {
      flushParagraph()
      flushList()
      flushQuote()

      const bodyLines: string[] = []
      let cursor = index + 2
      while (cursor < lines.length) {
        const candidate = lines[cursor] ?? ''
        if (!candidate.trim()) break
        if (!candidate.includes('|')) break
        if (/^```/.test(candidate)) break
        bodyLines.push(candidate)
        cursor += 1
      }

      const table = renderTable(line, nextLine, bodyLines)
      if (table) blocks.push(table)
      index = cursor - 1
      continue
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/)
    if (orderedMatch) {
      flushParagraph()
      if (activeListType && activeListType !== 'ol') flushList()
      activeListType = 'ol'
      listItems.push(orderedMatch[1] ?? '')
      continue
    }

    const unorderedMatch = line.match(/^[-*+]\s+(.*)$/)
    if (unorderedMatch) {
      flushParagraph()
      if (activeListType && activeListType !== 'ul') flushList()
      activeListType = 'ul'
      listItems.push(unorderedMatch[1] ?? '')
      continue
    }

    if (activeListType && /^\s+/.test(line) && listItems.length) {
      const lastItemIndex = listItems.length - 1
      const lastItem = listItems[lastItemIndex]
      if (typeof lastItem === 'string') {
        listItems[lastItemIndex] = `${lastItem} ${line.trim()}`
      }
      continue
    }

    flushList()
    paragraphLines.push(line)
  }

  if (inCodeFence) flushCodeFence()
  flushParagraph()
  flushList()
  flushQuote()

  return blocks.join('')
}
