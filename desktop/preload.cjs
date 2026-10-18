const { contextBridge, ipcRenderer } = require('electron')

// Identify the client before Vue renders and expose only the two navigation actions
// needed by the bundled local assistant page.
contextBridge.exposeInMainWorld('aiInvestmentDesktop', Object.freeze({
  platform: 'win32',
  openLocalAi: () => ipcRenderer.send('open-local-ai'),
  openWebsite: () => ipcRenderer.send('open-website'),
  getLocalModelStatus: () => ipcRenderer.invoke('local-model-status'),
  installLocalModel: () => ipcRenderer.invoke('install-local-model'),
  onLocalModelStatus: (callback) => {
    const listener = (_event, status) => callback(status)
    ipcRenderer.on('local-model-status', listener)
    return () => ipcRenderer.removeListener('local-model-status', listener)
  },
}))
