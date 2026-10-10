declare global {
  interface Window {
    aiInvestmentDesktop?: Readonly<{ platform: string }>
  }
}

// Electron's user agent also lets already-installed clients use the Vue layout.
export const isDesktopClient = window.aiInvestmentDesktop?.platform === 'win32'
  || /\bElectron\//.test(navigator.userAgent)
