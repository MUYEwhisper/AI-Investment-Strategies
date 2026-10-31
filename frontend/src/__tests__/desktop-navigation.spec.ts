import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'
import router from '../router'

vi.mock('../utils/client', () => ({ isDesktopClient: true }))

describe('desktop workspace compatibility', () => {
  beforeEach(async () => {
    localStorage.clear()
    sessionStorage.clear()
    window.__desktopView = 'market'
    await router.replace('/')
  })

  afterEach(() => {
    delete window.__desktopView
  })

  it('keeps AI chat selected when an installed shell synchronizes its legacy view', async () => {
    const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
    try {
      await flushPromises()
      const workspace = (title: string) => wrapper.findAll('.desktop-sidebar-item')
        .find((button) => button.text() === title)!
      expect(wrapper.find('#watchlistPanel').exists()).toBe(true)
      expect(wrapper.find('.chat-panel').exists()).toBe(false)

      await workspace('AI 投顾').trigger('click')
      await flushPromises()
      // Old clients dispatch this after every Vue DOM mutation.
      window.dispatchEvent(new CustomEvent('desktop-view-change', {
        detail: { view: window.__desktopView === 'ai' ? 'ai' : 'market' },
      }))
      await flushPromises()

      expect(window.__desktopView).toBe('ai')
      expect(wrapper.find('.page-title').text()).toBe('AI 投顾')
      expect(wrapper.find('.chat-panel').exists()).toBe(true)
      expect(wrapper.find('#watchlistPanel').exists()).toBe(false)

      await workspace('市场总览').trigger('click')
      await flushPromises()
      expect(window.__desktopView).toBe('market')
      expect(wrapper.find('#watchlistPanel').exists()).toBe(true)
      expect(wrapper.find('.chat-panel').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })
})
