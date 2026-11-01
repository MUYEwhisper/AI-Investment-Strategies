import { test, expect } from '@playwright/test'

const names = ['创投', '核电', '有色金属概念', '半导体', '电子通信', '绿色金融', '央企改革']

test.use({ headless: true })

for (const reducedMotion of ['reduce', 'no-preference'] as const) {
  for (const width of [1440, 1101]) {
    test(`HTML chart legends support mouse and keyboard at ${width}px (${reducedMotion})`, async ({ page }, testInfo) => {
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.setViewportSize({ width, height: 1100 })
      await page.emulateMedia({ reducedMotion })
      await page.addInitScript(() => {
        Object.defineProperty(window, 'aiInvestmentDesktop', { value: { platform: 'win32' }, configurable: true })
      })
      const sectors = names.map((name, index) => ({ name, code: String(index), kind: 'concept', attentionScore: 50 + index, sentimentScore: 50 + index, strengthScore: 52 + index, reason: '分页测试' }))
      await page.route('**/api/sectors/overview', (route) => route.fulfill({ json: {
        success: true, overview: { sectors, insights: ['分页测试'], detailLoaded: true },
      } }))
      await page.goto('/')
      await page.locator('#refreshSectorBtn').click()
      await expect(page.locator('#summaryList .summary-item')).toHaveCount(7)
      await page.locator('#sentimentChart canvas').waitFor()

      for (const input of ['mouse', 'keyboard'] as const) {
        for (const id of ['flowChart', 'sentimentChart']) {
          const chart = page.locator(`#${id}`)
          const other = page.locator(id === 'flowChart' ? '#sentimentChart' : '#flowChart')
          const previous = chart.getByRole('button', { name: /上一页$/ })
          const next = chart.getByRole('button', { name: /下一页$/ })
          await expect(previous).toBeDisabled()
          await expect(chart.getByRole('status')).toHaveText('1/7')
          if (input === 'keyboard') {
            await chart.locator('.legend-current').focus()
            await page.keyboard.press('Tab')
            await expect(next).toBeFocused()
          }
          for (const direction of ['next', 'previous'] as const) {
            for (let step = 1; step < names.length; step++) {
              const button = direction === 'next' ? next : previous
              if (input === 'mouse') await button.click()
              else {
                await button.focus()
                await button.press(step % 2 ? 'Enter' : 'Space')
              }
              const index = direction === 'next' ? step : names.length - 1 - step
              await expect(chart.locator('.legend-name')).toHaveText(names[index]!)
              await expect(chart.getByRole('status')).toHaveText(`${index + 1}/7`)
              await expect(other.locator('.legend-name')).toHaveText(names[0]!)
              await expect(other.getByRole('status')).toHaveText('1/7')
            }
            await expect(direction === 'next' ? next : previous).toBeDisabled()
          }
        }
      }

      const nav = (title: string) => page.locator('.desktop-sidebar-item').filter({ hasText: title })
      await nav('AI 投顾').click()
      await expect(page.locator('.chat-panel')).toBeVisible()
      await nav('市场总览').click()
      await page.locator('#flowChart canvas').waitFor()
      for (const id of ['flowChart', 'sentimentChart']) {
        const chart = page.locator(`#${id}`)
        await chart.getByRole('button', { name: /下一页$/ }).click()
        await expect(chart.locator('.legend-name')).toHaveText(names[1]!)
        await chart.getByRole('button', { name: /上一页$/ }).focus()
        await page.keyboard.press('Space')
        await expect(chart.locator('.legend-name')).toHaveText(names[0]!)
      }
      await page.screenshot({ path: testInfo.outputPath('html-legend.png'), fullPage: true })
      expect(errors).toEqual([])
    })
  }
}
