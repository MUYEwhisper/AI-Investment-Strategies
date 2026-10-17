const { _electron: electron, expect } = require('@playwright/test')
const path = require('node:path')
const fs = require('node:fs/promises')
const os = require('node:os')

async function main() {
  const root = path.resolve(__dirname, '..')
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'ai-invest-local-smoke-'))
  const executablePath = process.argv[2] ? path.resolve(process.argv[2]) : undefined
  const env = { ...process.env, AI_INVEST_TEST_PROFILE: profile, AI_INVEST_DISABLE_LOCAL_MODEL: '1' }
  delete env.ELECTRON_RUN_AS_NODE
  const application = await electron.launch({
    ...(executablePath ? { executablePath, args: [] } : { args: [root] }), env, timeout: 60000,
  })
  try {
    const page = await application.firstWindow()
    const localButton = page.locator('.desktop-sidebar-item').filter({ hasText: '本地智投' })
    await expect(localButton).toBeVisible({ timeout: 60000 })
    await localButton.click()
    await expect.poll(() => page.url()).toContain('/local-ai.html')
    await expect(page.locator('h1')).toHaveText('本地智投问答')
    await expect(page.locator('#composer')).toBeVisible()
    await expect(page.locator('#input')).toBeVisible()
    await page.locator('#back').click()
    await expect.poll(() => page.url(), { timeout: 60000 }).toBe('https://www.muyewhisper.cn/')
    console.log(JSON.stringify({ localAssistant: 'bundled-page', navigation: 'passed', composer: 'visible' }))
  } finally {
    await application.close()
    await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1 })
