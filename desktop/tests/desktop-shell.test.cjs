const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { JSDOM } = require('jsdom')

const main = fs.readFileSync(path.join(__dirname, '..', 'main.cjs'), 'utf8')
const shellSource = main.slice(main.indexOf('async function applyDesktopShell('), main.indexOf('\nfunction openExternal('))

function fixture(t, vueSidebar = false) {
  const buttons = ['市场总览', 'AI 投顾', '策略工作台', '账号中心', '本地智投']
    .map((text) => `<button class="desktop-sidebar-item">${text}</button>`).join('')
  const dom = new JSDOM(`<div class="app-page desktop-view-market">
    ${vueSidebar ? `<aside class="desktop-sidebar"><nav class="desktop-sidebar-nav">${buttons}</nav></aside>` : ''}
    <div class="app"><button id="pageNavDashboard"></button><button id="pageNavStrategyLocked"></button>
    <button class="login-entry-btn"></button><a id="desktopClientDownloadLink"></a><div id="work"></div></div>
    </div>`, { url: 'https://www.muyewhisper.cn/', runScripts: 'outside-only', pretendToBeVisual: true })
  t.after(() => dom.window.close())
  const errors = []
  let localOpens = 0
  dom.window.aiInvestmentDesktop = { openLocalAi: () => { localOpens += 1 } }
  const context = vm.createContext({
    desktopShellCss: '/* fixture */',
    isWebsiteNavigation: () => true,
    app: { isPackaged: false },
    console: { error: (...args) => errors.push(args) },
  })
  const apply = vm.runInContext(`${shellSource}; applyDesktopShell`, context)
  const contents = {
    getURL: () => dom.window.location.href,
    insertCSS: async () => {},
    executeJavaScript: async (source) => vm.runInContext(source, dom.getInternalVMContext()),
  }
  return {
    window: dom.window,
    document: dom.window.document,
    apply: async () => { await apply(contents); assert.deepEqual(errors, []) },
    localOpens: () => localOpens,
    settle: () => new Promise((resolve) => setTimeout(resolve, 65)),
  }
}

test('Vue-owned navigation keeps its selected view after rendering and repeated shell injection', async (t) => {
  const f = fixture(t, true)
  const page = f.document.querySelector('.app-page')
  const ai = [...f.document.querySelectorAll('button')].find((item) => item.textContent === 'AI 投顾')
  let nativeClicks = 0
  let injectedViewEvents = 0
  f.window.addEventListener('desktop-view-change', () => { injectedViewEvents += 1 })
  ai.addEventListener('click', () => {
    nativeClicks += 1
    page.classList.replace('desktop-view-market', 'desktop-view-ai')
    ai.setAttribute('aria-current', 'page')
    f.document.querySelector('#work').textContent = 'AI 投顾 rendered by Vue'
  })
  await f.apply()
  await f.apply()
  ai.click()
  await f.settle()
  assert.equal(nativeClicks, 1)
  assert.equal(page.classList.contains('desktop-view-ai'), true)
  assert.equal(ai.getAttribute('aria-current'), 'page')
  assert.equal(injectedViewEvents, 0)
  assert.equal(f.document.documentElement.classList.contains('desktop-legacy-layout'), false)
  assert.equal(f.document.querySelectorAll('.desktop-sidebar-item').length, 5)
})

test('bundled local assistant intercepts Vue navigation once even after its button is replaced', async (t) => {
  const f = fixture(t, true)
  let nativeLocalClicks = 0
  const local = [...f.document.querySelectorAll('.desktop-sidebar-item')].find((item) => item.textContent === '本地智投')
  local.addEventListener('click', () => { nativeLocalClicks += 1 })
  await f.apply()
  await f.apply()
  local.click()
  assert.equal(f.localOpens(), 1)
  assert.equal(nativeLocalClicks, 0)
  const replacement = f.document.createElement('button')
  replacement.className = 'desktop-sidebar-item'
  replacement.innerHTML = '<span>本地智投</span>'
  replacement.addEventListener('click', () => { nativeLocalClicks += 1 })
  local.replaceWith(replacement)
  replacement.querySelector('span').click()
  assert.equal(f.localOpens(), 2)
  assert.equal(nativeLocalClicks, 0)
})

test('legacy website gets one shell and one navigation action after repeated injection', async (t) => {
  const f = fixture(t)
  let dashboardClicks = 0
  let viewEvents = 0
  f.document.querySelector('#pageNavDashboard').addEventListener('click', () => { dashboardClicks += 1 })
  f.window.addEventListener('desktop-view-change', () => { viewEvents += 1 })
  await f.apply()
  await f.apply()
  const initialEvents = viewEvents
  f.document.querySelector('[data-route="ai"]').click()
  await f.settle()
  assert.equal(dashboardClicks, 1)
  assert.equal(viewEvents - initialEvents, 1)
  assert.equal(f.document.querySelector('.app-page').classList.contains('desktop-view-ai'), true)
  await f.apply()
  assert.equal(f.document.querySelector('.app-page').classList.contains('desktop-view-ai'), true)
  assert.equal(f.document.querySelectorAll('.desktop-sidebar').length, 1)
  assert.equal(f.document.querySelectorAll('.desktop-sidebar-item').length, 5)
  f.document.querySelector('[data-route="local-ai"]').click()
  assert.equal(f.localOpens(), 1)
  f.document.querySelector('[data-route="market"]').click()
  await f.settle()
  assert.equal(dashboardClicks, 2)
  assert.equal(f.document.querySelector('.app-page').classList.contains('desktop-view-market'), true)
})
