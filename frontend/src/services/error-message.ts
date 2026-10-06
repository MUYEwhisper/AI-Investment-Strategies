const HTML_TAG_PATTERN = /<[^>]+>/g
const URL_PATTERN = /https?:\/\/\S+/gi
const WHITESPACE_PATTERN = /\s+/g

export function sanitizeApiMessage(raw: unknown, fallback = '请求失败'): string {
  const text = typeof raw === 'string' ? raw.trim() : ''
  if (!text) return fallback

  const lowered = text.toLowerCase()
  const looksLikeHtml = lowered.includes('<html') || lowered.includes('<!doctype html')

  if (looksLikeHtml) {
    if (lowered.includes('504') || lowered.includes('gateway time-out') || lowered.includes('gateway timeout')) {
      return '上游行情服务网关超时（HTTP 504），请稍后重试。'
    }
    if (lowered.includes('503') || lowered.includes('service unavailable')) {
      return '上游行情服务暂不可用（HTTP 503），请稍后重试。'
    }
    if (lowered.includes('502') || lowered.includes('bad gateway')) {
      return '上游行情服务网关异常（HTTP 502），请稍后重试。'
    }
    return '上游服务返回了异常页面，请稍后重试。'
  }

  const cleaned = text
    .replace(HTML_TAG_PATTERN, ' ')
    .replace(URL_PATTERN, '上游服务')
    .replace(WHITESPACE_PATTERN, ' ')
    .trim()

  if (!cleaned) return fallback
  if (cleaned.length <= 220) return cleaned
  return `${cleaned.slice(0, 220)}...`
}

export function sanitizeOptionalApiMessage(raw: unknown): string | null | undefined {
  if (raw === null || raw === undefined) return raw as null | undefined
  const sanitized = sanitizeApiMessage(raw, '')
  return sanitized || null
}
