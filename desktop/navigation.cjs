const SITE_URL = 'https://www.muyewhisper.cn/'
const REPOSITORY_URL = 'https://github.com/MUYEwhisper/AI-Investment-Strategies'
const RELEASES_URL = `${REPOSITORY_URL}/releases/latest`
const SITE_ORIGINS = new Set([new URL(SITE_URL).origin, 'https://muyewhisper.cn'])
const APP_ORIGINS = new Set([
  ...SITE_ORIGINS,
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

function isWebsiteNavigation(value) {
  const url = parseHttpsUrl(value)
  return Boolean(url && SITE_ORIGINS.has(url.origin))
}

function isExternalLink(value) {
  return Boolean(parseHttpsUrl(value))
}

module.exports = { SITE_URL, REPOSITORY_URL, RELEASES_URL, isAppNavigation, isWebsiteNavigation, isExternalLink }
