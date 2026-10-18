const { _electron: electron, expect } = require('@playwright/test')
const path = require('node:path')
const fs = require('node:fs/promises')
const os = require('node:os')

async function main() {
  const root = path.resolve(__dirname, '..')
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'ai-invest-local-smoke-'))
  const executablePath = process.argv[2] ? path.resolve(process.argv[2]) : undefined
  const env = { ...process.env, AI_INVEST_TEST_PROFILE: profile }
  delete env.ELECTRON_RUN_AS_NODE
  const application = await electron.launch({
    ...(executablePath ? { executablePath, args: [] } : { args: [root] }), env, timeout: 60000,
  })
  try {
    const page = await application.firstWindow()
    const localButton = page.locator('.desktop-sidebar-item').filter({ hasText: '本地智投' })
    await expect(localButton).toBeVisible({ timeout: 60000 })
    await localButton.click()
    await expect.poll(() => page.url()).toContain('/local-ai')
    await expect(page.locator('.chat-panel')).toBeVisible()
    await expect(page.locator('.chat-sidebar')).toBeVisible()
    await expect(page.locator('#localHistoryList')).toBeVisible()
    await expect(page.locator('#localMessages')).toBeVisible()
    const localHealth = await page.evaluate(async () => {
      try { return await (await fetch('http://127.0.0.1:8001/health')).json() }
      catch { return null }
    })
    if (localHealth?.status === 'ok') {
      await expect(page.locator('.local-model-status')).toHaveText('本机模型就绪')
    } else {
      await expect(page.locator('.local-model-setup .btn')).toBeVisible()
      await expect(page.locator('.local-model-setup .btn')).toHaveText(/安装本地模型|启动本地模型/)
    }
    await page.locator('.desktop-sidebar-item').filter({ hasText: '市场总览' }).click()
    await expect.poll(() => page.url(), { timeout: 60000 }).toBe('https://www.muyewhisper.cn/')
    console.log(JSON.stringify({ localAssistant: 'vue-route', navigation: 'passed', history: 'visible' }))
  } finally {
    await application.close()
    await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1 })
