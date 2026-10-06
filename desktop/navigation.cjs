const SITE_URL = 'https://www.muyewhisper.cn/'
const APP_ORIGINS = new Set([
  new URL(SITE_URL).origin,
  'https://muyewhisper.cn',
  'https://auth.ksuser.cn',
  'https://api.ksuser.cn',
  'https://ksuser.cn',
  'https://www.ksuser.cn',
])

function parseHttpsUrl(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? url : null
  } catch {
    return null
  }
}

function isAppNavigation(value) {
  const url = parseHttpsUrl(value)
  return Boolean(url && APP_ORIGINS.has(url.origin))
}

function isExternalLink(value) {
  return Boolean(parseHttpsUrl(value))
}

module.exports = { SITE_URL, isAppNavigation, isExternalLink }
