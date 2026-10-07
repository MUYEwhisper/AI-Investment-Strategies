const { _electron: electron, expect } = require('@playwright/test')
const path = require('node:path')
const fs = require('node:fs/promises')
const os = require('node:os')

async function main() {
  const root = path.resolve(__dirname, '..')
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'ai-invest-smoke-'))
  const output = path.join(root, 'test-results')
  await fs.mkdir(output, { recursive: true })
  const executablePath = process.argv[2] ? path.resolve(process.argv[2]) : undefined
  const env = { ...process.env, AI_INVEST_TEST_PROFILE: profile }
  delete env.ELECTRON_RUN_AS_NODE
  const application = await electron.launch({
    ...(executablePath ? { executablePath, args: [] } : { args: [root] }), env, timeout: 60000,
  })
  try {
    const page = await application.firstWindow()
    await expect(page.locator('#watchlistPanel')).toBeVisible({ timeout: 60000 })
    await expect(page.locator('html.desktop-shell')).toHaveCount(1)
    await expect(page.locator('.desktop-sidebar')).toBeVisible()
    await expect(page.locator('.desktop-sidebar-item')).toHaveCount(4)
    await expect(page.locator('#desktopClientDownloadLink')).toBeHidden()
    await expect(page.locator('.login-entry-btn')).toBeVisible()
    await page.locator('.desktop-sidebar-item[data-route="ai"]').click()
    await expect(page.locator('.chat-panel')).toBeVisible()
    await expect(page.locator('#watchlistPanel')).toBeHidden()
    await page.locator('.desktop-sidebar-item[data-route="market"]').click()
    await expect(page.locator('#watchlistPanel')).toBeVisible()
    const security = await page.evaluate(() => ({
      nodeUnavailable: typeof window.require === 'undefined' && typeof window.process === 'undefined',
      origin: window.location.origin,
    }))
    if (!security.nodeUnavailable || security.origin !== 'https://www.muyewhisper.cn') throw new Error('Unexpected renderer context')
    await page.screenshot({ path: path.join(output, 'desktop-home.png'), fullPage: true })
    const responses = await page.evaluate(async () => {
      const results = []
      for (const endpoint of ['/api/auth/me', '/api/user/watchlist', '/api/user/chats', '/api/profile', '/api/sim/account', '/api/sim/reviews']) {
        const response = await fetch(endpoint)
        results.push({ endpoint, status: response.status })
      }
      const chat = await fetch('/chat/endpoint', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      results.push({ endpoint: '/chat/endpoint (empty prompt)', status: chat.status })
      return results
    })
    if (responses.some(({ status }, i) => status !== (i === responses.length - 1 ? 400 : 401))) throw new Error(JSON.stringify(responses))
    await page.locator('.login-entry-btn').click()
    await page.waitForURL('https://auth.ksuser.cn/**', { timeout: 60000 })
    await expect(page.locator('body')).toContainText(/登录|Sign in/i, { timeout: 30000 })
    await page.screenshot({ path: path.join(output, 'desktop-signin.png'), fullPage: true })
    if (application.windows().length !== 1) throw new Error('OAuth escaped the main window')
    console.log(JSON.stringify({ desktop: executablePath ? 'packaged' : 'development', desktopShell: 'injected', downloadLink: 'hidden', security, responses, oauth: 'Ksuser login reached in the same window' }, null, 2))

    // Simulate a failed network load, then verify the bundled recovery page and retry link.
    await application.evaluate(async ({ BrowserWindow }) => {
      BrowserWindow.getAllWindows()[0].webContents.emit('did-fail-load', {}, -105, 'ERR_NAME_NOT_RESOLVED', 'https://www.muyewhisper.cn/', true)
    })
    await expect(page.locator('h1')).toHaveText('暂时无法连接服务器', { timeout: 15000 })
    await page.locator('a').click()
    await expect(page.locator('#watchlistPanel')).toBeVisible({ timeout: 60000 })
    console.log('Recovery page and reconnect passed.')
  } finally {
    await application.close()
    await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1 })
