const { contextBridge, ipcRenderer } = require('electron')

// Identify the client before Vue renders and expose only the two navigation actions
// needed by the bundled local assistant page.
contextBridge.exposeInMainWorld('aiInvestmentDesktop', Object.freeze({
  platform: 'win32',
  openLocalAi: () => ipcRenderer.send('open-local-ai'),
  openWebsite: () => ipcRenderer.send('open-website'),
}))
