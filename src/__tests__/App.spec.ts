import { describe, expect, it } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'
import router from '../router'

describe('App', () => {
  it('switches between dashboard and strategy workspace routes', async () => {
    router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
      },
    })

    expect(wrapper.find('#watchlistPanel').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'StrategyWorkbenchPage' }).exists()).toBe(false)

    await router.push('/strategy')
    await flushPromises()

    expect(wrapper.find('#watchlistPanel').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'StrategyWorkbenchPage' }).exists()).toBe(true)
  })
})
