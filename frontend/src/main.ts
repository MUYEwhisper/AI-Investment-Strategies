import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './assets/motion.css'

const FORCED_FAVICON_HREF = '/site-icon.png?v=20260419-retouch'

function forceFavicon(): void {
  const ensureLink = (selector: string, rel: string): HTMLLinkElement => {
    const existing = document.head.querySelector<HTMLLinkElement>(selector)
    if (existing) return existing
    const link = document.createElement('link')
    link.rel = rel
    document.head.appendChild(link)
    return link
  }

  const icon = ensureLink('link[rel="icon"]', 'icon')
  icon.type = 'image/png'
  icon.sizes = '32x32'
  icon.href = FORCED_FAVICON_HREF

  const shortcutIcon = ensureLink('link[rel="shortcut icon"]', 'shortcut icon')
  shortcutIcon.type = 'image/png'
  shortcutIcon.href = FORCED_FAVICON_HREF

  const appleTouchIcon = ensureLink('link[rel="apple-touch-icon"]', 'apple-touch-icon')
  appleTouchIcon.href = FORCED_FAVICON_HREF
}

forceFavicon()

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
