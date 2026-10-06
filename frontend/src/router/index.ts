import { h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { loadStoredKsuserSession } from '../services/ksuser-auth'

const EmptyRouteView = {
  name: 'EmptyRouteView',
  render: () => h('div'),
}

const SIGNIN_QUERY_VALUE = 'signin'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/signin',
      name: 'signin',
      component: EmptyRouteView,
      meta: {
        public: true,
      },
    },
    {
      path: '/auth/callback',
      name: 'auth-callback',
      component: EmptyRouteView,
      meta: {
        public: true,
      },
    },
    {
      path: '/',
      name: 'dashboard',
      component: EmptyRouteView,
    },
    {
      path: '/strategy',
      name: 'strategy-workbench',
      component: EmptyRouteView,
      meta: {
        requiresAuth: true,
      },
    },
    {
      path: '/account',
      name: 'account',
      component: EmptyRouteView,
      meta: {
        requiresAuth: true,
      },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach((to) => {
  const session = loadStoredKsuserSession()
  const requiresAuth = Boolean(to.meta.requiresAuth)

  if (to.name === 'signin') {
    if (session) {
      return typeof to.query.redirect === 'string' && to.query.redirect.startsWith('/') ? to.query.redirect : '/'
    }

    const query = {
      ...to.query,
      auth: SIGNIN_QUERY_VALUE,
    }

    return {
      name: 'dashboard',
      query,
    }
  }

  if (requiresAuth && !session) {
    return {
      name: 'dashboard',
      query: {
        auth: SIGNIN_QUERY_VALUE,
        redirect: to.fullPath,
      },
    }
  }

  return true
})

export default router
