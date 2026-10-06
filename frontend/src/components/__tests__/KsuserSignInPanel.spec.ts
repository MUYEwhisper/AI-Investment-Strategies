import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import KsuserSignInPanel from '../KsuserSignInPanel.vue'

describe('KsuserSignInPanel', () => {
  it('uses a real form submit so Enter in a configuration field advances the flow', async () => {
    const wrapper = mount(KsuserSignInPanel, {
      props: {
        busy: false,
        configured: true,
        errorMessage: '',
        clientId: 'demo-client',
        clientSecret: '',
        redirectUri: 'https://www.muyewhisper.cn/auth/callback',
        scope: ['profile', 'email'],
        authorizeEndpoint: 'https://auth.ksuser.cn/oauth/authorize',
        dialogReason: '登录后继续',
        registerUrl: 'https://auth.ksuser.cn/register',
      },
    })

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('signIn')).toHaveLength(1)
    expect(wrapper.emitted('signIn')?.[0]?.[0]).toMatchObject({
      clientId: 'demo-client',
      redirectUri: 'https://www.muyewhisper.cn/auth/callback',
      scopeText: 'profile email',
    })
  })
})
