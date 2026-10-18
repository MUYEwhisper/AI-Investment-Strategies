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
    await page.route('http://127.0.0.1:8001/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname === '/health') {
        await route.fulfill({ json: { status: 'ok' } })
      } else if (url.pathname === '/v1/chat/completions') {
        const frames = [
          { choices: [{ delta: { content: '### 结论\n**保持观察。**\n\n### 分析依据\n- 测试数据不足\n\n### 风险提示\n' } }] },
          { choices: [{ delta: { content: '需结合实时数据。\n<script>window.__modelHtmlExecuted = true</script>' } }] },
        ]
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: `${frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join('')}data: [DONE]\n\n`,
        })
      } else {
        await route.fulfill({ status: 404, body: '' })
      }
    })
    await page.route('https://www.muyewhisper.cn/chat/local-context', async (route) => {
      await route.fulfill({ json: { records: [] } })
    })
    const localButton = page.locator('.desktop-sidebar-item').filter({ hasText: '本地智投' })
    await expect(localButton).toBeVisible({ timeout: 60000 })
    await expect(localButton).toHaveCount(1)
    await localButton.click()
    await expect.poll(() => page.url()).toContain('local-ai.html')
    await expect(page.locator('.brand strong')).toHaveText('本地智投')
    await expect(page.locator('#composer')).toBeVisible()
    await expect(page.locator('#input')).toBeVisible()
    await expect(page.locator('#historyList')).toBeVisible()
    await expect(page.locator('#gpuToggle')).toBeVisible()
    await expect(page.locator('#status')).toHaveText('本机模型就绪')
    const composer = page.locator('#input')
    await composer.fill('测试本地模型 Markdown 渲染')
    await page.locator('#send').click()
    const answer = page.locator('.message.ai').last()
    await expect(answer.locator('h3').first()).toHaveText('结论')
    await expect(answer.locator('strong')).toHaveText('保持观察。')
    await expect(answer.locator('li')).toHaveText('测试数据不足')
    await expect(answer.locator('h3').nth(1)).toHaveText('分析依据')
    await expect(answer.locator('script')).toHaveCount(0)
    const unsafeOutputExecuted = await page.evaluate(() => Boolean(window.__modelHtmlExecuted))
    if (unsafeOutputExecuted) throw new Error('Untrusted model HTML was executed')
    await page.locator('#newChat').click()
    await expect(page.locator('#historyList .history-item')).toHaveCount(2)
    const persistedHistoryCount = await page.evaluate(() => JSON.parse(localStorage.getItem('ai_invest_local_chats') || '[]').length)
    if (persistedHistoryCount !== 2) throw new Error('Local chat history was not persisted')
    const scrollCheck = await page.evaluate(() => {
      const messages = document.querySelector('#messages')
      const panel = messages
      const bubble = document.createElement('div')
      bubble.className = 'message ai'
      bubble.textContent = '长篇回答内容。'.repeat(1800)
      messages.appendChild(bubble)
      const result = {
        viewportFits: document.documentElement.scrollHeight === window.innerHeight,
        messagesScroll: panel.scrollHeight > panel.clientHeight,
        bubbleWithinPanel: bubble.getBoundingClientRect().width <= panel.clientWidth,
      }
      bubble.remove()
      return result
    })
    if (!scrollCheck.viewportFits || !scrollCheck.messagesScroll || !scrollCheck.bubbleWithinPanel) {
      throw new Error(`Local chat scrolling/layout failed: ${JSON.stringify(scrollCheck)}`)
    }
    const localHealth = await page.evaluate(async () => {
      try { return await (await fetch('http://127.0.0.1:8001/health')).json() }
      catch { return null }
    })
    if (localHealth?.status === 'ok') {
      await expect(page.locator('#status')).toHaveText('本机模型就绪')
    } else {
      await expect(page.locator('#installModel')).toBeVisible()
      await expect(page.locator('#installModel')).toHaveText(/安装本地模型|启动本地模型/)
    }
    await page.locator('#back').click()
    await expect.poll(() => page.url(), { timeout: 60000 }).toBe('https://www.muyewhisper.cn/')
    await expect.poll(() => page.locator('html').evaluate((node) => node.classList.contains('desktop-shell'))).toBe(true)
    await localButton.click()
    await expect.poll(() => page.url(), { timeout: 60000 }).toContain('local-ai.html')
    console.log(JSON.stringify({ localAssistant: 'bundled-page', navigation: 'passed', composer: 'visible', markdown: 'rendered' }))
  } finally {
    await application.close()
    await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1 })
