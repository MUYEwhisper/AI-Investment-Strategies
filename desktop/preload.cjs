const { contextBridge } = require('electron')

// Identify the client before Vue renders. Expose no Node or IPC capabilities.
contextBridge.exposeInMainWorld('aiInvestmentDesktop', Object.freeze({ platform: 'win32' }))
