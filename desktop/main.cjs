const { app, BrowserWindow, Menu, dialog, shell, screen, session } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const { spawn } = require('node:child_process')
const { SITE_URL, isAppNavigation, isExternalLink } = require('./navigation.cjs')
const { readWindowState, saveWindowState } = require('./window-state.cjs')

// A stable profile keeps website sessions and account-scoped local storage across upgrades.
app.setName('AI Investment Strategies')
app.setAppUserModelId('cn.muyewhisper.investment')
if (!app.isPackaged && process.env.AI_INVEST_TEST_PROFILE) {
  app.setPath('userData', path.resolve(process.env.AI_INVEST_TEST_PROFILE))
}

let mainWindow
const offlineFile = path.join(__dirname, 'offline.html')

function openExternal(url) {
  if (isExternalLink(url)) void shell.openExternal(url).catch(() => {})
}

function launchUninstaller() {
  if (!app.isPackaged) {
    void dialog.showMessageBox(mainWindow, {
      type: 'info', title: '智能投资平台', message: '开发模式无需卸载。',
      detail: '安装后的版本可以从“应用”菜单启动卸载程序，或在 Windows 设置 → 应用中卸载。',
    })
    return
  }

  const uninstallerDir = path.dirname(process.execPath)
  const uninstaller = [
    path.join(uninstallerDir, 'Uninstall 智能投资平台.exe'),
    path.join(uninstallerDir, 'Uninstall AI Investment Strategies.exe'),
  ].find((candidate) => fs.existsSync(candidate))
  if (!uninstaller) {
    void dialog.showMessageBox(mainWindow, {
      type: 'warning', title: '找不到卸载程序',
      message: '请从 Windows 设置 → 应用 → 已安装的应用中卸载智能投资平台。',
    })
    return
  }
  spawn(uninstaller, [], { detached: true, stdio: 'ignore' }).unref()
  app.quit()
}

async function goHome() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  try {
    await mainWindow.loadURL(SITE_URL)
  } catch {
    // did-fail-load displays the reconnect screen for main-frame network failures.
  }
}

function installMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: '应用', submenu: [
      { label: '市场总览', accelerator: 'Alt+Home', click: goHome },
      { label: '在浏览器中打开网站', click: () => openExternal(SITE_URL) },
      { label: '卸载智能投资平台', click: launchUninstaller },
      { type: 'separator' },
      { label: '退出', role: 'quit' },
    ] },
    { label: '编辑', submenu: [
      { label: '撤销', role: 'undo' }, { label: '重做', role: 'redo' }, { type: 'separator' },
      { label: '剪切', role: 'cut' }, { label: '复制', role: 'copy' },
      { label: '粘贴', role: 'paste' }, { label: '全选', role: 'selectAll' },
    ] },
    { label: '视图', submenu: [
      { label: '后退', accelerator: 'Alt+Left', click: () => {
        if (mainWindow.webContents.navigationHistory.canGoBack()) mainWindow.webContents.navigationHistory.goBack()
      } },
      { label: '前进', accelerator: 'Alt+Right', click: () => {
        if (mainWindow.webContents.navigationHistory.canGoForward()) mainWindow.webContents.navigationHistory.goForward()
      } },
      { label: '刷新 / 重新连接', accelerator: 'CmdOrCtrl+R', click: () => {
        if (mainWindow.webContents.getURL().startsWith('file:')) void goHome()
        else mainWindow.webContents.reload()
      } },
      { type: 'separator' },
      { label: '放大', role: 'zoomIn' }, { label: '缩小', role: 'zoomOut' },
      { label: '实际大小', role: 'resetZoom' }, { label: '全屏', role: 'togglefullscreen' },
      ...(!app.isPackaged ? [{ type: 'separator' }, { label: '开发者工具', role: 'toggleDevTools' }] : []),
    ] },
    { label: '帮助', submenu: [
      { label: '项目与使用说明', click: () => openExternal('https://github.com/MUYEwhisper/AI-Investment-Strategies') },
      { label: '关于智能投资平台', click: () => dialog.showMessageBox(mainWindow, {
        type: 'info', title: '智能投资平台', message: `智能投资平台 ${app.getVersion()}`,
        detail: 'Windows 64 位桌面客户端\n连接 muyewhisper.cn 云端服务\n投资有风险，请审慎决策。',
      }) },
    ] },
  ]))
}

function createWindow() {
  const stateFile = path.join(app.getPath('userData'), 'window-state.json')
  const state = readWindowState(stateFile, screen.getAllDisplays())
  mainWindow = new BrowserWindow({
    ...state, minWidth: 960, minHeight: 640, show: false,
    title: '智能投资平台', backgroundColor: '#f1f5f9',
    icon: path.join(__dirname, 'assets/icon.ico'),
    webPreferences: {
      nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, allowRunningInsecureContent: false,
      spellcheck: false, devTools: !app.isPackaged,
    },
  })
  if (state.maximized) mainWindow.maximize()
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.on('close', () => saveWindowState(stateFile, mainWindow))
  mainWindow.on('closed', () => { mainWindow = null })
  const contents = mainWindow.webContents
  contents.on('will-attach-webview', (event) => event.preventDefault())
  contents.on('will-navigate', (event, url) => {
    if (!isAppNavigation(url)) {
      event.preventDefault()
      openExternal(url)
    }
  })
  contents.on('will-redirect', (event, url) => {
    if (!isAppNavigation(url)) event.preventDefault()
  })
  contents.setWindowOpenHandler(({ url }) => {
    // Keep OAuth and its registered HTTPS callback in the same desktop session.
    if (isAppNavigation(url)) void contents.loadURL(url).catch(() => {})
    else openExternal(url)
    return { action: 'deny' }
  })
  contents.on('did-fail-load', (_event, code, _description, url, isMainFrame) => {
    if (isMainFrame && code !== -3 && isAppNavigation(url)) {
      void mainWindow.loadFile(offlineFile).catch(() => {})
    }
  })
  installMenu()
  void goHome()
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  })
  app.whenReady().then(() => {
    session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
    session.defaultSession.setPermissionCheckHandler(() => false)
    session.defaultSession.on('will-download', (_event, item) => {
      item.setSaveDialogOptions({
        title: '保存文件', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())),
      })
    })
    createWindow()
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
  })
  app.on('window-all-closed', () => app.quit())
}
