import { test, expect, type Page } from '@playwright/test'

test.use({ headless: true, contextOptions: { reducedMotion: 'reduce' } })

async function installMocks(page: Page, desktop = true) {
  await page.addInitScript((desktop) => {
    if (desktop) {
      Object.defineProperty(window, 'aiInvestmentDesktop', {
        value: { platform: 'win32' }, configurable: true,
      })
    }
    localStorage.setItem('ai_invest_ksuser_session', JSON.stringify({
      accessToken: 'ai-layout-test-session', tokenType: 'Bearer', scope: [], scopeText: '',
      openid: 'ai-layout-test-user', unionid: 'ai-layout-test-union',
      profile: { openid: 'ai-layout-test-user', unionid: 'ai-layout-test-union', nickname: '布局测试用户' },
      expiresAt: Date.now() + 3600000, createdAt: Date.now(),
    }))
  }, desktop)
  await page.route('**/api/**', async (route) => {
    await route.fulfill({ json: {
      success: true,
      user: { id: 1, openid: 'ai-layout-test-user', unionid: 'ai-layout-test-union', nickname: '布局测试用户', email: '', avatar_url: '' },
      sessions: [], chats: [], watchlist: [],
    } })
  })
}

const navigation = (page: Page, title: string) => page.locator('.desktop-sidebar-item').filter({ hasText: title })

async function chatLayout(page: Page) {
  return page.locator('.chat-panel').evaluate((panel) => {
    const box = (selector: string) => panel.querySelector<HTMLElement>(selector)!.getBoundingClientRect()
    const panelBox = panel.getBoundingClientRect()
    const sidebar = box('.chat-sidebar')
    const body = box('.chat-body')
    const input = box('#chatInput')
    return {
      height: panelBox.height,
      bottom: panelBox.bottom,
      sidebarHeight: sidebar.height,
      sidebarBottom: sidebar.bottom,
      bodyHeight: body.height,
      bodyBottom: body.bottom,
      inputTop: input.top,
      inputBottom: input.bottom,
      messagesHeight: box('#messages').height,
      historyHeight: box('#historyList').height,
      historyBottom: box('#historyList').bottom,
      pageWidth: document.documentElement.scrollWidth,
    }
  })
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 2048, height: 1200 }, { width: 960, height: 640 }]) {
  test(`AI adviser fills the desktop height at ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await installMocks(page)
    await page.goto('/')
    await navigation(page, 'AI 投顾').click()
    await expect(page.locator('.app-page')).toHaveClass(/desktop-view-ai/)
    await expect(page.locator('#chatInput')).toBeEditable()
    const expectedHeight = Math.max(viewport.height - 122, 540)
    await expect.poll(async () => (await chatLayout(page)).height).toBe(expectedHeight)
    const layout = await chatLayout(page)
    expect(layout.pageWidth).toBeLessThanOrEqual(viewport.width)
    if (viewport.width > 1100) {
      expect(layout.bottom).toBeLessThanOrEqual(viewport.height)
      expect(layout.bottom).toBeGreaterThanOrEqual(viewport.height - 30)
      expect(layout.sidebarHeight).toBe(layout.bodyHeight)
      expect(layout.sidebarBottom).toBe(layout.bodyBottom)
      expect(layout.inputTop).toBeGreaterThan(0)
      expect(layout.inputBottom).toBeLessThanOrEqual(viewport.height)
      expect(layout.messagesHeight).toBeGreaterThan(expectedHeight / 2)
      expect(layout.historyHeight).toBeGreaterThan(expectedHeight * 0.4)
      expect(layout.sidebarBottom - layout.historyBottom).toBeLessThanOrEqual(20)
    }
    await page.locator('#chatInput').fill('布局恢复后可以继续输入')
    await expect(page.locator('#chatInput')).toHaveValue('布局恢复后可以继续输入')
    if (viewport.width === 1440) await page.screenshot({ path: testInfo.outputPath('ai-adviser-layout.png'), fullPage: true })

    await navigation(page, '市场总览').click()
    await expect(page.locator('.chat-panel')).toHaveCount(0)
    if (viewport.width > 1100) {
      const market = await page.locator('.top-grid').evaluate((grid) => ({
        height: grid.getBoundingClientRect().height,
        watchlistHeight: grid.querySelector('#watchlistPanel')!.getBoundingClientRect().height,
        sectorHeight: grid.querySelector('.sector-panel')!.getBoundingClientRect().height,
      }))
      expect(market.height).toBe(1200)
      expect(market.watchlistHeight).toBe(market.sectorHeight)
    }
    await navigation(page, 'AI 投顾').click()
    await expect.poll(async () => (await chatLayout(page)).height).toBe(expectedHeight)
    await expect(page.locator('#chatInput')).toBeEditable()
  })
}

test('ordinary web chat keeps its existing height', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await installMocks(page, false)
  await page.goto('/')
  await expect(page.locator('.chat-panel')).toHaveCSS('height', '580px')
  await expect(page.locator('html')).not.toHaveClass(/desktop-shell/)
})

test('switching from AI adviser leaves the local AI panel height unchanged', async ({ page }) => {
  await page.setViewportSize({ width: 960, height: 640 })
  await installMocks(page)
  await page.goto('/')
  await navigation(page, 'AI 投顾').click()
  await expect(page.locator('.chat-panel')).toHaveCSS('min-height', '540px')
  await navigation(page, '本地智投').click()
  await expect(page.locator('.local-ai-chat-panel')).toBeVisible()
  await expect(page.locator('.local-ai-chat-panel')).toHaveCSS('min-height', '518px')
})

test('mobile desktop shell keeps its existing chat height', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 1100 })
  await installMocks(page)
  await page.goto('/')
  await navigation(page, 'AI 投顾').click()
  await expect(page.locator('.chat-panel')).toHaveCSS('height', '638px')
  expect((await chatLayout(page)).pageWidth).toBeLessThanOrEqual(375)
})
