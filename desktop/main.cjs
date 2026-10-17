const { app, BrowserWindow, Menu, dialog, shell, screen, session } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const { spawn } = require('node:child_process')
const { SITE_URL, REPOSITORY_URL, RELEASES_URL, isAppNavigation, isWebsiteNavigation, isExternalLink } = require('./navigation.cjs')
const { readWindowState, saveWindowState } = require('./window-state.cjs')

// A stable profile keeps website sessions and account-scoped local storage across upgrades.
app.setName('AI Investment Strategies')
app.setAppUserModelId('cn.muyewhisper.investment')
if (process.env.AI_INVEST_TEST_PROFILE) {
  app.setPath('userData', path.resolve(process.env.AI_INVEST_TEST_PROFILE))
}

let mainWindow
let localModelProcess
const offlineFile = path.join(__dirname, 'offline.html')
const localAiFile = path.join(__dirname, 'local-ai.html')
const desktopShellCssFile = path.join(__dirname, '..', 'frontend', 'src', 'assets', 'desktop-shell.css')

let desktopShellCss
try {
  desktopShellCss = fs.readFileSync(desktopShellCssFile, 'utf8')
} catch {
  desktopShellCss = ''
}

async function applyDesktopShell(contents) {
  if (!desktopShellCss || !isWebsiteNavigation(contents.getURL())) return
  try {
    await contents.insertCSS(desktopShellCss)
    await contents.executeJavaScript(`
      (() => {
        const root = document.documentElement
        const page = document.querySelector('.app-page')
        const app = page && Array.from(page.children).find((item) => item.classList?.contains('app'))
        root.classList.add('desktop-shell')
        document.body?.setAttribute('data-client', 'windows-desktop')
        document.querySelector('#desktopClientDownloadLink')?.setAttribute('hidden', 'hidden')
        if (!page || !app) return
        // Newer website builds render part of the shell in Vue. Keep their state
        // and event handlers intact, but still add the local assistant entry.
        root.classList.add('desktop-legacy-layout')

        const viewClasses = ['desktop-view-market', 'desktop-view-ai']
        const setView = (view) => {
          const nextView = view === 'ai' ? 'ai' : 'market'
          window.__desktopView = nextView
          const activeClass = nextView === 'ai' ? 'desktop-view-ai' : 'desktop-view-market'
          page.classList.remove(...viewClasses)
          page.classList.add(activeClass)
          window.dispatchEvent(new CustomEvent('desktop-view-change', { detail: { view: nextView } }))
          requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
        }

        const syncNavigation = () => {
          const currentPath = location.pathname.replace(/\\/+$/, '') || '/'
          const currentView = window.__desktopView === 'ai' ? 'ai' : 'market'
          const activeRoute = currentPath === '/strategy'
            ? 'strategy'
            : currentPath === '/local-ai'
              ? 'local-ai'
            : currentPath === '/account'
              ? 'account'
              : currentPath === '/'
                ? currentView
                : ''
          document.querySelectorAll('.desktop-sidebar-item').forEach((item) => {
            const active = item.getAttribute('data-route') === activeRoute
            item.setAttribute('aria-current', active ? 'page' : 'false')
          })
          if (currentPath === '/') setView(currentView)
          else page.classList.remove(...viewClasses)

          const status = document.querySelector('[data-desktop-session]')
          const user = document.querySelector('.user-chip-copy strong')?.textContent?.trim()
          if (status) status.textContent = user ? user + ' · 云端已连接' : '游客 · 云端已连接'
        }

        let sidebar = page.querySelector('.desktop-sidebar')
        if (!sidebar) {
          sidebar = document.createElement('aside')
          sidebar.className = 'desktop-sidebar'
          sidebar.setAttribute('aria-label', '桌面工作区导航')
          sidebar.innerHTML = [
            '<div class="desktop-sidebar-brand"><strong>智能投资平台</strong><span>云端投资工作台</span></div>',
            '<div class="desktop-sidebar-section">工作区</div>',
            '<nav class="desktop-sidebar-nav" aria-label="工作区导航">',
            '<button class="desktop-sidebar-item" type="button" data-route="market">市场总览</button>',
            '<button class="desktop-sidebar-item" type="button" data-route="ai">AI 投顾</button>',
            '<button class="desktop-sidebar-item" type="button" data-route="local-ai">本地智投</button>',
            '<button class="desktop-sidebar-item" type="button" data-route="strategy">策略工作台</button>',
            '<button class="desktop-sidebar-item" type="button" data-route="account">账号中心</button>',
            '</nav>',
            '<div class="desktop-sidebar-foot"><div class="desktop-sidebar-status" data-desktop-session>游客 · 云端已连接</div><div class="desktop-sidebar-version">Windows 64 位客户端</div></div>',
          ].join('')
          page.insertBefore(sidebar, app)

          sidebar.querySelector('[data-route="market"]')?.addEventListener('click', () => {
            window.__desktopView = 'market'
            document.getElementById('pageNavDashboard')?.click()
            setView('market')
            scheduleNavigationSync()
          })
          sidebar.querySelector('[data-route="ai"]')?.addEventListener('click', () => {
            window.__desktopView = 'ai'
            document.getElementById('pageNavDashboard')?.click()
            setView('ai')
            scheduleNavigationSync()
          })
          sidebar.querySelector('[data-route="local-ai"]')?.addEventListener('click', () => {
            window.aiInvestmentDesktop?.openLocalAi?.()
          })
          sidebar.querySelector('[data-route="strategy"]')?.addEventListener('click', () => {
            document.getElementById('pageNavStrategy')?.click()
            document.getElementById('pageNavStrategyLocked')?.click()
            scheduleNavigationSync()
          })
          sidebar.querySelector('[data-route="account"]')?.addEventListener('click', () => {
            const account = document.getElementById('pageNavAccount')
            if (account) account.click()
            else document.querySelector('.login-entry-btn')?.click()
            scheduleNavigationSync()
          })
        }

        let localItem = sidebar.querySelector('[data-route="local-ai"]')
        if (!localItem) {
          const nav = sidebar.querySelector('.desktop-sidebar-nav') || sidebar
          localItem = document.createElement('button')
          localItem.className = 'desktop-sidebar-item'
          localItem.type = 'button'
          localItem.dataset.route = 'local-ai'
          localItem.textContent = '本地智投'
          nav.appendChild(localItem)
        }
        if (!localItem.dataset.localAiHandler) {
          localItem.dataset.localAiHandler = 'installed'
          localItem.addEventListener('click', () => window.aiInvestmentDesktop?.openLocalAi?.())
        }

        if (!window.__desktopNavigationInstalled) {
          window.__desktopNavigationInstalled = true
          window.__desktopView = 'market'
          for (const method of ['pushState', 'replaceState']) {
            const original = history[method]
            history[method] = function (...args) {
              const result = original.apply(this, args)
              scheduleNavigationSync()
              return result
            }
          }
          window.addEventListener('popstate', scheduleNavigationSync)
          const observer = new MutationObserver(scheduleNavigationSync)
          observer.observe(page, { childList: true, subtree: true })
          window.__desktopNavigationObserver = observer
        }

        let syncPending = false
        function scheduleNavigationSync() {
          if (syncPending) return
          syncPending = true
          requestAnimationFrame(() => {
            syncPending = false
            syncNavigation()
          })
        }

        syncNavigation()
      })()
    `, true)
  } catch (error) {
    if (!app.isPackaged) console.error('Desktop shell injection failed:', error)
  }
}

function openExternal(url) {
  if (isExternalLink(url)) void shell.openExternal(url).catch(() => {})
}

function startLocalModelServer() {
  if (process.env.AI_INVEST_DISABLE_LOCAL_MODEL === '1') return
  const packagedBackend = path.join(process.resourcesPath || '', 'app.asar.unpacked', 'backend')
  const backendDir = app.isPackaged && fs.existsSync(path.join(packagedBackend, 'local_server.py'))
    ? packagedBackend
    : path.join(__dirname, '..', 'backend')
  const bundledRuntime = path.join(process.resourcesPath || '', 'local-runtime', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const bundledModel = path.join(process.resourcesPath || '', 'models', 'deepseek-ai', 'DeepSeek-R1-Distill-Qwen-1.5B')
  const candidates = process.platform === 'win32'
    ? [bundledRuntime, path.join(backendDir, '.venv', 'Scripts', 'python.exe'), 'python']
    : [path.join(backendDir, '.venv', 'bin', 'python'), 'python3', 'python']
  const python = candidates.find((candidate) => candidate === 'python' || fs.existsSync(candidate))
  if (!python || !fs.existsSync(path.join(backendDir, 'local_server.py'))) return
  localModelProcess = spawn(python, ['local_server.py'], {
    cwd: backendDir,
    env: {
      ...process.env,
      LOCAL_MODEL_PORT: '8001',
      LOCAL_MODEL_CACHE: path.join(app.getPath('userData'), 'models'),
      ...(fs.existsSync(path.join(bundledModel, 'config.json')) ? { LOCAL_MODEL_PATH: bundledModel } : {}),
    },
    stdio: app.isPackaged ? 'ignore' : 'pipe',
    windowsHide: true,
  })
  localModelProcess.on('error', (error) => {
    if (!app.isPackaged) console.error('Local model server failed to start:', error)
  })
  localModelProcess.on('exit', () => { localModelProcess = undefined })
}

function stopLocalModelServer() {
  if (!localModelProcess || localModelProcess.killed) return
  localModelProcess.kill()
  localModelProcess = undefined
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
      { label: '打开官网', click: () => openExternal(SITE_URL) },
      { label: '下载 Windows 客户端', click: () => openExternal(RELEASES_URL) },
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
      { label: 'GitHub 项目与使用说明', click: () => openExternal(REPOSITORY_URL) },
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
      preload: path.join(__dirname, 'preload.cjs'),
    },
  })
  if (state.maximized) mainWindow.maximize()
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.on('close', () => saveWindowState(stateFile, mainWindow))
  mainWindow.on('closed', () => { mainWindow = null })
  const contents = mainWindow.webContents
  contents.on('ipc-message', (_event, channel) => {
    if (channel === 'open-local-ai') void mainWindow.loadFile(localAiFile)
    if (channel === 'open-website') void goHome()
  })
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
  contents.on('did-finish-load', () => {
    void applyDesktopShell(contents)
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
    startLocalModelServer()
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
  })
  app.on('before-quit', stopLocalModelServer)
  app.on('window-all-closed', () => app.quit())
}
