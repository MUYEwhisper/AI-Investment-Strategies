import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'
import router from '../router'
import { AUTH_SESSION_STORAGE_KEY } from '../services/ksuser-auth'
import { fetchSectorOverview, loadStoredSectorOverview, storeSectorOverview, type SectorOverviewPayload } from '../services/sectors'

vi.mock('../utils/client', () => ({ isDesktopClient: true }))
vi.mock('../services/sectors', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/sectors')>(),
  fetchSectorOverview: vi.fn(),
}))

const overview: SectorOverviewPayload = {
  sectors: [{ name: '半导体', code: 'test', kind: 'industry', attentionScore: 68, sentimentScore: 72, strengthScore: 65, reason: '测试分析依据' }],
  insights: ['市场解读快照'],
  sourceNote: '测试数据源',
  detailLoaded: true,
}

describe('desktop sector analysis retention', () => {
  beforeEach(async () => {
    localStorage.clear()
    sessionStorage.clear()
    vi.mocked(fetchSectorOverview).mockReset()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('No network in unit tests')))
    await router.replace('/')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    delete window.__desktopView
  })

  function mountApp(realTransitions = false) {
    return mount(App, {
      global: {
        plugins: [createPinia(), router],
        stubs: { Transition: !realTransitions, EChartsPie: true, StrategyWorkbenchPage: true, KsuserAccountCenter: true },
      },
    })
  }

  it('retains results across workspace switches and a full remount, replacing them only after a successful refresh', async () => {
    vi.mocked(fetchSectorOverview).mockResolvedValueOnce(overview)
    let wrapper = mountApp()
    try {
      await flushPromises()
      await wrapper.get('#refreshSectorBtn').trigger('click')
      await flushPromises()
      expect(wrapper.get('.sector-panel').text()).toContain('市场解读快照')

      const workspace = (title: string) => wrapper.findAll('.desktop-sidebar-item')
        .find((button) => button.text() === title)!
      await workspace('AI 投顾').trigger('click')
      await flushPromises()
      await workspace('市场总览').trigger('click')
      await flushPromises()
      expect(wrapper.get('.sector-panel').text()).toContain('市场解读快照')
      expect(fetchSectorOverview).toHaveBeenCalledTimes(1)

      // Electron's local assistant loads another document; returning mounts App anew.
      wrapper.unmount()
      wrapper = mountApp()
      await flushPromises()
      expect(wrapper.get('.sector-panel').text()).toContain('市场解读快照')
      expect(wrapper.findComponent({ name: 'EChartsPie' }).props('items')).toEqual([{ name: '半导体', value: 68 }])
      expect(fetchSectorOverview).toHaveBeenCalledTimes(1)

      vi.mocked(fetchSectorOverview).mockRejectedValueOnce(new Error('刷新暂时失败'))
      await wrapper.get('#refreshSectorBtn').trigger('click')
      await flushPromises()
      expect(wrapper.get('.sector-panel').text()).toContain('市场解读快照')
      expect(wrapper.get('.sector-panel').text()).toContain('刷新暂时失败')

      wrapper.unmount()
      wrapper = mountApp()
      await flushPromises()
      expect(wrapper.get('.sector-panel').text()).toContain('市场解读快照')

      vi.mocked(fetchSectorOverview).mockResolvedValueOnce({ ...overview, insights: ['下一次分析结果'] })
      await wrapper.get('#refreshSectorBtn').trigger('click')
      await flushPromises()
      expect(wrapper.get('.sector-panel').text()).toContain('下一次分析结果')
      expect(wrapper.get('.sector-panel').text()).not.toContain('市场解读快照')

      wrapper.unmount()
      wrapper = mountApp()
      await flushPromises()
      expect(wrapper.get('.sector-panel').text()).toContain('下一次分析结果')
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps the account analysis when returning from strategy and account routes', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify({
      accessToken: 'unit-test-token',
      expiresAt: Date.now() + 60_000,
      profile: { openid: 'account-a', unionid: 'unit-test-union', nickname: '测试账号' },
    }))
    storeSectorOverview('account-a', overview)
    const wrapper = mountApp(true)
    try {
      await flushPromises()
      for (const title of ['策略工作台', '账号中心']) {
        const workspace = (label: string) => wrapper.findAll('.desktop-sidebar-item')
          .find((button) => button.text() === label)!
        await workspace(title).trigger('click')
        await flushPromises()
        expect(wrapper.find('.sector-panel').exists()).toBe(false)
        await workspace('市场总览').trigger('click')
        await flushPromises()
        expect(wrapper.get('.sector-panel').text()).toContain('市场解读快照')
        expect(wrapper.findComponent({ name: 'EChartsPie' }).props('items')).toEqual([{ name: '半导体', value: 68 }])
      }
      expect(fetchSectorOverview).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('isolates snapshots by account and ignores invalid stored data', () => {
    storeSectorOverview('account-a', overview)
    expect(loadStoredSectorOverview('account-a')).toEqual(overview)
    expect(loadStoredSectorOverview('account-b')).toBeNull()
    expect(loadStoredSectorOverview('__guest__')).toBeNull()
    sessionStorage.setItem('ai_invest_sector_overview:account-a', '{invalid')
    expect(loadStoredSectorOverview('account-a')).toBeNull()
    sessionStorage.setItem('ai_invest_sector_overview:account-a', JSON.stringify({ sectors: [null], insights: [] }))
    expect(loadStoredSectorOverview('account-a')).toBeNull()
  })
})
