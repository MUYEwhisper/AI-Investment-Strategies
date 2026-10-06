import { beforeEach, describe, expect, it } from 'vitest'

import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../App.vue'
import router from '../router'
import { AUTH_SESSION_STORAGE_KEY, type KsuserSession } from '../services/ksuser-auth'

function createMockSession(): KsuserSession {
  return {
    accessToken: 'mock_access_token_1234567890',
    tokenType: 'Bearer',
    scope: ['openid', 'profile', 'email'],
    scopeText: 'openid profile email',
    openid: 'oid_mock_user',
    unionid: 'uid_mock_user',
    idToken: 'mock_id_token',
    expiresAt: Date.now() + 60 * 60 * 1000,
    createdAt: Date.now(),
    clientId: 'mock-client-id',
    redirectUri: 'http://localhost/auth/callback',
    authorizeEndpoint: 'https://auth.ksuser.cn/oauth/authorize',
    tokenEndpoint: 'https://api.ksuser.cn/oauth2/token',
    userinfoEndpoint: 'https://api.ksuser.cn/oauth2/userinfo',
    profile: {
      openid: 'oid_mock_user',
      unionid: 'uid_mock_user',
      nickname: '测试用户',
      email: 'demo@example.com',
    },
  }
}

describe('App', () => {
  beforeEach(async () => {
    localStorage.clear()
    sessionStorage.clear()
    await router.replace('/')
  })

  it('switches between dashboard and strategy workspace routes', async () => {
    localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(createMockSession()))
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    expect(wrapper.find('#watchlistPanel').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'StrategyWorkbenchPage' }).exists()).toBe(false)

    await router.push('/strategy')
    await flushPromises()

    expect(wrapper.find('#watchlistPanel').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'StrategyWorkbenchPage' }).exists()).toBe(true)
  })

  it('keeps guests on dashboard by default', async () => {
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    expect(router.currentRoute.value.name).toBe('dashboard')
    expect(wrapper.find('#watchlistPanel').exists()).toBe(true)
    expect(wrapper.find('#signInPanel').exists()).toBe(false)
  })

  it('redirects guests to sign in when visiting strategy workspace', async () => {
    await router.push('/strategy')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    expect(router.currentRoute.value.name).toBe('dashboard')
    expect(router.currentRoute.value.query.auth).toBe('signin')
    expect(wrapper.find('#watchlistPanel').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'StrategyWorkbenchPage' }).exists()).toBe(false)
  })

  it('starts oauth redirect when guests visit the legacy signin route', async () => {
    await router.push('/signin')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    expect(router.currentRoute.value.name).toBe('dashboard')
    expect(router.currentRoute.value.query.auth).toBe('signin')
    expect(wrapper.find('#signInPanel').exists()).toBe(false)
  })

  it('starts oauth redirect when guests try to manage the watchlist', async () => {
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    await wrapper.get('.watchlist-login-btn').trigger('click')
    await flushPromises()

    expect(wrapper.find('#signInPanel').exists()).toBe(false)
  })
})
