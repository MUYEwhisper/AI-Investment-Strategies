const { test } = require('node:test')
const assert = require('node:assert/strict')
const { isAppNavigation, isWebsiteNavigation, isExternalLink } = require('../navigation.cjs')
const fs = require('node:fs')
const path = require('node:path')

test('registered OAuth origins and callback stay inside the app', () => {
  for (const url of [
    'https://www.muyewhisper.cn/auth/callback?code=example&state=example',
    'https://auth.ksuser.cn/oauth/authorize',
    'https://api.ksuser.cn/oauth2/token',
    'https://muyewhisper.cn/strategy',
  ]) assert.equal(isAppNavigation(url), true)
})

test('desktop chrome is limited to the investment website', () => {
  assert.equal(isWebsiteNavigation('https://www.muyewhisper.cn/strategy'), true)
  assert.equal(isWebsiteNavigation('https://muyewhisper.cn/auth/callback'), true)
  assert.equal(isWebsiteNavigation('https://auth.ksuser.cn/oauth/authorize'), false)
  assert.equal(isWebsiteNavigation('https://github.com/MUYEwhisper/AI-Investment-Strategies'), false)
})

test('untrusted origins and privileged URL schemes cannot enter the app', () => {
  for (const url of [
    'https://www.muyewhisper.cn.evil.example/',
    'https://www.muyewhisper.cn@evil.example/',
    'https://user:password@www.muyewhisper.cn/',
    'https://www.muyewhisper.cn:444/',
    'http://www.muyewhisper.cn/',
    'file:///C:/Windows/system.ini',
    'javascript:alert(1)',
    'data:text/html,test',
    'not a URL',
  ]) assert.equal(isAppNavigation(url), false, url)
  assert.equal(isExternalLink('https://github.com/MUYEwhisper/AI-Investment-Strategies'), true)
  assert.equal(isExternalLink('file:///C:/Windows/system.ini'), false)
  assert.equal(isExternalLink('javascript:alert(1)'), false)
})

test('the local assistant is bundled as an app page instead of a remote route', () => {
  const main = fs.readFileSync(path.join(__dirname, '..', 'main.cjs'), 'utf8')
  assert.equal(fs.existsSync(path.join(__dirname, '..', 'local-ai.html')), true)
  assert.match(main, /loadFile\(localAiFile\)/)
  assert.doesNotMatch(main, /window\.location\.assign\('\/local-ai'\)/)
})
