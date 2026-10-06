import { defineStore } from 'pinia'
import {
  clearPendingAuthRequest,
  clearStoredKsuserSession,
  completeKsuserAuthorization,
  createKsuserAuthorizationRequest,
  loadStoredKsuserSession,
  type KsuserSession,
} from '../services/ksuser-auth'

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '账号系统发生未知错误。'
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    session: null as KsuserSession | null,
    initialized: false,
    busy: false,
    errorMessage: '',
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.session),
    userLabel: (state) =>
      state.session?.profile.nickname || state.session?.profile.email || `用户 ${state.session?.profile.openid.slice(0, 8) ?? ''}`,
    userAvatar: (state) => state.session?.profile.avatar_url || '',
  },
  actions: {
    hydrate(): void {
      this.session = loadStoredKsuserSession()
      this.initialized = true
    },
    async startSignIn(returnTo = '/'): Promise<void> {
      this.busy = true
      this.errorMessage = ''

      try {
        const { url } = await createKsuserAuthorizationRequest(returnTo)
        if (typeof window !== 'undefined') {
          window.location.assign(url)
        }
      } catch (error) {
        this.errorMessage = toErrorMessage(error)
        throw error
      } finally {
        this.busy = false
      }
    },
    async finishSignIn(searchParams: URLSearchParams): Promise<string> {
      this.busy = true
      this.errorMessage = ''

      try {
        const { session, returnTo } = await completeKsuserAuthorization(searchParams)
        this.session = session
        this.initialized = true
        return returnTo
      } catch (error) {
        this.session = null
        this.initialized = true
        this.errorMessage = toErrorMessage(error)
        throw error
      } finally {
        this.busy = false
      }
    },
    logout(): void {
      clearPendingAuthRequest()
      clearStoredKsuserSession()
      this.session = null
      this.errorMessage = ''
      this.initialized = true
    },
  },
})
