declare global {
  interface Window {
    aiInvestmentDesktop?: Readonly<{
      platform: string
      getLocalModelStatus?: () => Promise<LocalModelStatus>
      installLocalModel?: () => Promise<LocalModelStatus & { error?: string }>
      onLocalModelStatus?: (callback: (status: LocalModelStatus) => void) => () => void
    }>
  }
}

export type LocalModelStatus = {
  installed: boolean
  running: boolean
  downloading?: boolean
  progress?: number
  message?: string
}

// Electron's user agent also lets already-installed clients use the Vue layout.
export const isDesktopClient = window.aiInvestmentDesktop?.platform === 'win32'
  || /\bElectron\//.test(navigator.userAgent)
