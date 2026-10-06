const { test } = require('node:test')
const assert = require('node:assert/strict')
const { isAppNavigation, isExternalLink } = require('../navigation.cjs')

test('registered OAuth origins and callback stay inside the app', () => {
  for (const url of [
    'https://www.muyewhisper.cn/auth/callback?code=example&state=example',
    'https://auth.ksuser.cn/oauth/authorize',
    'https://api.ksuser.cn/oauth2/token',
    'https://muyewhisper.cn/strategy',
  ]) assert.equal(isAppNavigation(url), true)
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
