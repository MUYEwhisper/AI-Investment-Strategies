declare global {
  interface Window {
    aiInvestmentDesktop?: Readonly<{
      platform: string
      getLocalModelStatus?: () => Promise<LocalModelStatus>
      installLocalModel?: () => Promise<LocalModelStatus & { error?: string }>
      getLocalModelSettings?: () => Promise<LocalModelSettings>
      setLocalModelSettings?: (settings: { gpuEnabled: boolean }) => Promise<LocalModelSettings>
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
  gpuEnabled?: boolean
  gpuAvailable?: boolean
  gpuActive?: boolean
}

export type LocalModelSettings = {
  gpuEnabled: boolean
  gpuAvailable: boolean
  gpuActive: boolean
}

// Electron's user agent also lets already-installed clients use the Vue layout.
export const isDesktopClient = window.aiInvestmentDesktop?.platform === 'win32'
  || /\bElectron\//.test(navigator.userAgent)
