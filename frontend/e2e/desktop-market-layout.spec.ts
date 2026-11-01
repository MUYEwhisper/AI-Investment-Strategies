import { test, expect, type Page } from '@playwright/test'

test.use({ headless: true, contextOptions: { reducedMotion: 'reduce' } })

const statusNote = ['601138', '000969', '300308', '002636']
  .map((code) => `股票 ${code} 的关联板块提取失败：连接今日投资 MCP 超时，请稍后重试。`)
  .join('；')
const overview = {
  sectors: ['创投', '核电', '有色金属概念', '半导体', '电子通信', '绿色金融', '央企改革']
    .map((name, index) => ({ name, code: String(index), kind: 'concept', attentionScore: 50 + index, sentimentScore: 50 + index, strengthScore: 52 + index, reason: '布局回归测试' })),
  insights: [
    '两市4602家下跌、93家跌停，普跌格局情绪偏冷。',
    '美股AI板块回调传导，电子通信承压最明显。',
    'ESG国家标准落地，绿色金融主题获政策支持。',
    '央企国企改革具防御属性，弱市中相对抗跌。',
    '资金避险为主，等待情绪修复与政策催化。',
  ],
  statusNote,
  sourceNote: '模型未覆盖全部板块评分。基于5只自选股关联的 MCP 行业/概念板块聚合与最新新闻情绪。',
}

async function installMocks(page: Page, cachedNote?: string) {
  await page.addInitScript(({ overview, cachedNote }) => {
    Object.defineProperty(window, 'aiInvestmentDesktop', { value: { platform: 'win32' }, configurable: true })
    localStorage.setItem('ai_invest_ksuser_session', JSON.stringify({
      accessToken: 'layout-test-session', tokenType: 'Bearer', scope: [], scopeText: '',
      openid: 'layout-test-user', unionid: 'layout-test-union',
      profile: { openid: 'layout-test-user', unionid: 'layout-test-union', nickname: '布局测试用户' },
      expiresAt: Date.now() + 3600000, createdAt: Date.now(),
    }))
    if (cachedNote) sessionStorage.setItem('ai_invest_sector_overview:layout-test-user', JSON.stringify({ ...overview, statusNote: cachedNote }))
  }, { overview, cachedNote })

  let releaseRefresh: () => void = () => {}
  const refreshGate = new Promise<void>((resolve) => { releaseRefresh = resolve })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/sectors/overview') {
      await refreshGate
      await route.fulfill({ json: { success: true, overview } })
      return
    }
    const user = { id: 1, openid: 'layout-test-user', unionid: 'layout-test-union', nickname: '布局测试用户', email: '', avatar_url: '' }
    const stocks = Array.from({ length: 30 }, (_, index) => ({ name: `测试股票${index}`, code: String(600000 + index), tags: [] }))
    await route.fulfill({ json: {
      success: true, user, sessions: [], chats: [],
      ...(path === '/api/user/watchlist' ? { watchlist: stocks } : {}),
      ...(path.includes('/stocks/') ? { stock: stocks[0] } : {}),
    } })
  })
  return releaseRefresh
}

async function layout(page: Page) {
  return page.locator('.top-grid').evaluate((grid) => {
    const watchlist = grid.querySelector<HTMLElement>('#watchlistPanel')!
    const sector = grid.querySelector<HTMLElement>('.sector-panel')!
    const body = grid.querySelector<HTMLElement>('.sector-body')!
    const list = grid.querySelector<HTMLElement>('#watchlistView')!
    const lastScore = grid.querySelector<HTMLElement>('#summaryList .summary-item:last-child')!
    return {
      height: grid.getBoundingClientRect().height,
      watchlistHeight: watchlist.getBoundingClientRect().height,
      sectorHeight: sector.getBoundingClientRect().height,
      bodyOverflow: body.scrollHeight - body.clientHeight,
      overflowY: getComputedStyle(body).overflowY,
      lastScoreBottom: lastScore?.getBoundingClientRect().bottom ?? 0,
      sectorBottom: sector.getBoundingClientRect().bottom,
      listOverflows: list.scrollHeight > list.clientHeight,
      pageWidth: document.documentElement.scrollWidth,
    }
  })
}

for (const width of [1101, 1280, 1440, 2048, 375]) {
  test(`market analysis stays complete before and after refresh at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1100 })
    const releaseRefresh = await installMocks(page)
    await page.goto('/')
    await expect(page.locator('#watchlistView .stock-item')).toHaveCount(30)
    const before = await layout(page)
    if (width > 1100) expect(before.height).toBe(1200)
    await page.locator('#refreshSectorBtn').click()
    await expect(page.locator('#refreshSectorBtn')).toHaveAttribute('aria-busy', 'true')
    if (width > 1100) expect((await layout(page)).height).toBe(before.height)
    releaseRefresh()
    await expect(page.locator('#summaryList .summary-item')).toHaveCount(7)
    await expect(page.locator('.sector-status-note')).toContainText('002636')
    await expect.poll(async () => (await layout(page)).bodyOverflow).toBeLessThanOrEqual(0)
    const after = await layout(page)
    expect(after.overflowY).toBe('visible')
    expect(after.lastScoreBottom).toBeLessThanOrEqual(after.sectorBottom)
    expect(after.pageWidth).toBeLessThanOrEqual(width)
    if (width > 1100) {
      expect(after.height).toBe(before.height)
      expect(after.watchlistHeight).toBe(after.sectorHeight)
      expect(after.listOverflows).toBe(true)
    }
    if (width === 1440) await page.screenshot({ path: testInfo.outputPath('market-layout.png'), fullPage: true })
    const nav = (title: string) => page.locator('.desktop-sidebar-item').filter({ hasText: title })
    await nav('AI 投顾').click()
    await nav('市场总览').click()
    await expect(page.locator('#summaryList .summary-item')).toHaveCount(7)
    if (width > 1100) expect((await layout(page)).height).toBe(after.height)
    await expect.poll(async () => (await layout(page)).bodyOverflow).toBeLessThanOrEqual(0)
  })
}

test('exceptionally long cached analysis grows both panels once and keeps that height on refresh', async ({ page }) => {
  await page.setViewportSize({ width: 1101, height: 1100 })
  const releaseRefresh = await installMocks(page, statusNote.repeat(12))
  await page.goto('/')
  await expect.poll(async () => (await layout(page)).height).toBeGreaterThan(1200)
  await expect.poll(async () => (await layout(page)).bodyOverflow).toBeLessThanOrEqual(0)
  const before = await layout(page)
  expect(before.watchlistHeight).toBe(before.sectorHeight)
  await page.locator('#refreshSectorBtn').click()
  releaseRefresh()
  await expect(page.locator('#refreshSectorBtn')).toHaveAttribute('aria-busy', 'false')
  expect((await layout(page)).height).toBe(before.height)
  expect((await layout(page)).bodyOverflow).toBeLessThanOrEqual(0)
})
