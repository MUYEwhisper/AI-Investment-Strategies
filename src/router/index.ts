import { h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

const EmptyRouteView = {
  name: 'EmptyRouteView',
  render: () => h('div'),
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: EmptyRouteView,
    },
    {
      path: '/strategy',
      name: 'strategy-workbench',
      component: EmptyRouteView,
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export default router
