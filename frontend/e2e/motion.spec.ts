import { test, expect, type Page } from '@playwright/test'

test.use({ headless: true })

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const user = { id: 1, openid: 'test-user', unionid: 'test-union', nickname: '测试用户', email: '', avatar_url: '' }
    const stock = { name: '测试股票', code: '600519', tags: [] }
    const chats = ['一', '二', '三'].map((label, index) => ({
      id: `chat-${index}`, agentId: 'smartq-invest', title: `会话${label}`, createdAt: '测试时间',
      messages: [{ role: 'ai', content: `内容${label}` }],
    }))
    await route.fulfill({ json: {
      success: true, user, sessions: [],
      ...(path === '/api/user/watchlist' ? { watchlist: [stock] } : {}),
      ...(path === '/api/user/chats' ? { chats } : {}),
      ...(path.includes('/stocks/') ? { stock } : {}),
    } })
  })
  await page.addInitScript(() => {
    localStorage.setItem('ai_invest_ksuser_session', JSON.stringify({
      accessToken: 'test-session', tokenType: 'Bearer', scope: [], scopeText: '',
      openid: 'test-user', unionid: 'test-union', profile: { openid: 'test-user', unionid: 'test-union', nickname: '测试用户' },
      expiresAt: Date.now() + 3600000, createdAt: Date.now(),
    }))
  })
  await page.goto('/')
  await expect(page.locator('#historyList .history-item')).toHaveCount(3)
})

async function settled(page: Page) {
  await expect.poll(() => page.evaluate(() => document.getAnimations().length)).toBe(0)
  await expect(page.locator('.page-stage')).toHaveCSS('opacity', '1')
  await expect(page.locator('.page-stage')).toHaveCSS('transform', 'none')
}

async function animationStarted(page: Page) {
  await expect.poll(() => page.evaluate(() => document.getAnimations().length)).toBeGreaterThan(0)
}

test('rapid route changes show the last page and leave no hidden stage', async ({ page }) => {
  await page.locator('#pageNavStrategy').click()
  await animationStarted(page)
  await settled(page)
  for (let cycle = 0; cycle < 3; cycle++) {
    await page.evaluate(async () => {
      for (const id of ['pageNavStrategy', 'pageNavAccount', 'pageNavDashboard']) {
        document.getElementById(id)!.click()
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      }
    })
    await expect(page.locator('#watchlistPanel')).toBeVisible()
    await settled(page)
  }
  await page.locator('#pageNavAccount').click()
  await expect(page.locator('#accountCenterPanel')).toBeVisible()
  await settled(page)
})

test('desktop view changes always animate and accept the last click', async ({ page }) => {
  // Exercise the event used by the Electron sidebar, including cancellation within one frame.
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('desktop-view-change', { detail: { view: 'ai' } })))
  await animationStarted(page)
  await settled(page)
  for (let cycle = 0; cycle < 3; cycle++) {
    await page.evaluate(async () => {
      for (const view of ['market', 'ai', 'market', 'ai']) {
        window.dispatchEvent(new CustomEvent('desktop-view-change', { detail: { view } }))
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      }
    })
    await expect(page.locator('.top-grid')).toBeHidden()
    await expect(page.locator('.chat-panel')).toBeVisible()
    await settled(page)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('desktop-view-change', { detail: { view: 'market' } })))
  await expect(page.locator('.top-grid')).toBeVisible()
  await expect(page.locator('.chat-panel')).toBeHidden()
  await settled(page)
})

test('chat and stock switches remain responsive during their enter animation', async ({ page }) => {
  await page.locator('.history-item').nth(1).click()
  await animationStarted(page)
  await settled(page)
  await page.evaluate(async () => {
    for (const index of [1, 2, 0, 2]) {
      (document.querySelectorAll('.history-item')[index] as HTMLElement).click()
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    }
  })
  await expect(page.locator('#messages')).toHaveText('内容三')
  await page.evaluate(async () => {
    for (let cycle = 0; cycle < 3; cycle++) {
      (document.querySelector('.stock-item') as HTMLElement).click()
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      document.getElementById('backToWatchlistBtn')!.click()
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    }
  })
  await expect(page.locator('#watchlistView')).toBeVisible()
  await expect(page.locator('#stockDetailView')).toBeHidden()
  await settled(page)
})

test('reduced motion leaves routes, desktop views and messages visible immediately', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.locator('#pageNavAccount').click()
  await expect(page.locator('#accountCenterPanel')).toBeVisible()
  await page.locator('#pageNavDashboard').click()
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('desktop-view-change', { detail: { view: 'ai' } })))
  await expect(page.locator('.chat-panel')).toBeVisible()
  await expect(page.locator('#messages')).toHaveCSS('opacity', '1')
  await settled(page)
})
