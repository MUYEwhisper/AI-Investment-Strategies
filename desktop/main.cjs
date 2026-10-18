const { app, BrowserWindow, Menu, dialog, shell, screen, session, ipcMain } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const crypto = require('node:crypto')
const { spawn, spawnSync } = require('node:child_process')
const https = require('node:https')
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
let localModelServerReady = false
let localModelInstall = null
let localModelGpuActive = false
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
            '<button class="desktop-sidebar-item" type="button" data-route="strategy">策略工作台</button>',
            '<button class="desktop-sidebar-item" type="button" data-route="account">账号中心</button>',
            '<button class="desktop-sidebar-item" type="button" data-route="local-ai">本地智投</button>',
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
          const injectedLocalButton = sidebar.querySelector('[data-route="local-ai"]')
          if (injectedLocalButton) injectedLocalButton.dataset.localAiHandler = 'installed'
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
          localItem = Array.from(sidebar.querySelectorAll('button')).find((item) => item.textContent?.trim() === '本地智投')
          if (localItem) localItem.dataset.route = 'local-ai'
        }
        if (!localItem) {
          const nav = sidebar.querySelector('.desktop-sidebar-nav') || sidebar
          localItem = document.createElement('button')
          localItem.className = 'desktop-sidebar-item'
          localItem.type = 'button'
          localItem.dataset.route = 'local-ai'
          localItem.textContent = '本地智投'
          nav.appendChild(localItem)
        }
        const localNav = sidebar.querySelector('.desktop-sidebar-nav')
        if (localNav && localItem.parentElement === localNav && localNav.lastElementChild !== localItem) {
          localNav.appendChild(localItem)
        }
        if (!localItem.dataset.localAiHandler) {
          localItem.dataset.localAiHandler = 'installed'
        }

        // Use one delegated handler for both the injected and Vue-rendered
        // entry. This avoids stale listeners after Vue reorders/re-renders the
        // sidebar, which previously made the entry work only from one side.
        if (!sidebar.dataset.localAiClickHandler) {
          sidebar.dataset.localAiClickHandler = 'installed'
          sidebar.addEventListener('click', (event) => {
            const target = event.target instanceof Element
              ? event.target.closest('[data-route="local-ai"]')
              : null
            if (!target || !sidebar.contains(target)) return
            event.preventDefault()
            event.stopImmediatePropagation()
            window.aiInvestmentDesktop?.openLocalAi?.()
          }, true)
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

const MODEL_FILE = 'DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf'
const MODEL_URL = 'https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf'
const MODEL_SHA256 = 'f3bdf9cf31dee4b57ae4e455a1cb0d01b5c2c1b50d72d3112141c195506c2840'

function modelDirectory() {
  return path.join(app.getPath('userData'), 'models')
}

function modelPath() {
  return path.join(modelDirectory(), MODEL_FILE)
}

function modelSettingsPath() {
  return path.join(app.getPath('userData'), 'local-model-settings.json')
}

function readLocalModelSettings() {
  try {
    const settings = JSON.parse(fs.readFileSync(modelSettingsPath(), 'utf8'))
    return { gpuEnabled: Boolean(settings?.gpuEnabled) }
  } catch {
    return { gpuEnabled: false }
  }
}

function writeLocalModelSettings(settings) {
  fs.mkdirSync(path.dirname(modelSettingsPath()), { recursive: true })
  fs.writeFileSync(modelSettingsPath(), JSON.stringify({ gpuEnabled: Boolean(settings.gpuEnabled) }, null, 2))
}

function detectGpu() {
  const resourcesDir = process.resourcesPath || path.join(__dirname, '..')
  const runtimeDir = app.isPackaged
    ? path.join(resourcesDir, 'local-runtime')
    : path.join(__dirname, 'llama-runtime')
  // NVIDIA detection alone is insufficient: the bundled llama runtime must
  // also contain a CUDA backend before we advertise or pass GPU flags.
  if (!fs.existsSync(path.join(runtimeDir, 'ggml-cuda.dll'))) return false
  try {
    const result = spawnSync('nvidia-smi', ['--query-gpu=name', '--format=csv,noheader'], { windowsHide: true, encoding: 'utf8', timeout: 2500 })
    return result.status === 0 && Boolean(result.stdout?.trim())
  } catch {
    return false
  }
}

function localModelStatus() {
  const installed = fs.existsSync(modelPath()) && fs.statSync(modelPath()).size > 1_000_000_000
  return {
    model: 'DeepSeek-R1-Distill-Qwen-1.5B',
    installed,
    running: localModelServerReady,
    downloading: Boolean(localModelInstall),
    progress: localModelInstall?.progress || 0,
    gpuEnabled: readLocalModelSettings().gpuEnabled,
    gpuAvailable: detectGpu(),
    gpuActive: localModelGpuActive,
    message: localModelInstall?.message || (installed ? '本地模型已安装' : '本地模型尚未安装'),
  }
}

function broadcastModelStatus() {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('local-model-status', localModelStatus())
}

function startLocalModelServer() {
  if (process.env.AI_INVEST_DISABLE_LOCAL_MODEL === '1') return
  const resourcesDir = process.resourcesPath || path.join(__dirname, '..')
  const llamaDir = app.isPackaged
    ? path.join(resourcesDir, 'local-runtime')
    : path.join(__dirname, '..', 'desktop', 'llama-runtime')
  const bundledModel = modelPath()
  const llamaServer = path.join(llamaDir, process.platform === 'win32' ? 'llama-server.exe' : 'llama-server')
  if (!fs.existsSync(llamaServer) || !fs.existsSync(bundledModel)) return
  if (localModelProcess && !localModelProcess.killed) return
  const settings = readLocalModelSettings()
  const gpuRequested = settings.gpuEnabled && detectGpu()
  localModelGpuActive = gpuRequested
  const serverArgs = [
    '--model', bundledModel, '--host', '127.0.0.1', '--port', '8001',
    '--ctx-size', '4096', '--threads', String(Math.max(2, Math.min(8, Number.parseInt(process.env.LOCAL_MODEL_THREADS || '4', 10)))),
    '--reasoning', 'off',
  ]
  if (gpuRequested) serverArgs.push('--n-gpu-layers', '999')
  localModelProcess = spawn(llamaServer, [
    ...serverArgs,
  ], {
    cwd: llamaDir,
    env: {
      ...process.env,
    },
    stdio: app.isPackaged ? 'ignore' : 'pipe',
    windowsHide: true,
  })
  localModelProcess.on('error', (error) => {
    localModelServerReady = false
    localModelGpuActive = false
    if (!app.isPackaged) console.error('Local model server failed to start:', error)
  })
  localModelProcess.on('exit', () => { localModelProcess = undefined; localModelServerReady = false; localModelGpuActive = false; broadcastModelStatus() })
  broadcastModelStatus()
  void waitForLocalModelServer().catch(() => {})
}

function waitForLocalModelServer(timeoutMs = 180000) {
  const startedAt = Date.now()
  return new Promise((resolve, reject) => {
    const check = () => {
      if (!localModelProcess || localModelProcess.killed) return reject(new Error('本地模型服务启动失败，请重试。'))
      const request = require('node:http').get('http://127.0.0.1:8001/health', (response) => {
        response.resume()
        if (response.statusCode === 200) {
          localModelServerReady = true
          broadcastModelStatus()
          return resolve()
        }
        retry()
      })
      request.setTimeout(1500, () => request.destroy())
      request.on('error', retry)
      function retry() {
        if (Date.now() - startedAt >= timeoutMs) return reject(new Error('本地模型启动超时，请检查磁盘空间后重试。'))
        setTimeout(check, 1200)
      }
    }
    check()
  })
}

function downloadLocalModel() {
  if (localModelInstall) return localModelInstall.promise
  fs.mkdirSync(modelDirectory(), { recursive: true })
  const temporaryPath = `${modelPath()}.download`
  const promise = new Promise((resolve, reject) => requestModel(MODEL_URL, temporaryPath, 0, resolve, reject))
  localModelInstall = { progress: 0, message: '正在连接 ModelScope…', promise }
  broadcastModelStatus()
  promise.then(() => {
    fs.renameSync(temporaryPath, modelPath())
    localModelInstall = null
    startLocalModelServer()
    broadcastModelStatus()
  }).catch((error) => {
    try { fs.rmSync(temporaryPath, { force: true }) } catch {}
    localModelInstall = null
    if (!app.isPackaged) console.error('Local model download failed:', error)
    broadcastModelStatus()
  })
  return promise
}

function streamModel(response, resolve, reject, temporaryPath) {
  const total = Number(response.headers['content-length'] || 0)
  let received = 0
  const digest = crypto.createHash('sha256')
  const output = fs.createWriteStream(temporaryPath)
  response.on('data', (chunk) => {
    received += chunk.length
    digest.update(chunk)
    if (localModelInstall) {
      localModelInstall.progress = total ? Math.min(99, Math.floor(received / total * 100)) : 0
      localModelInstall.message = total ? `正在下载本地模型 ${Math.round(received / 1024 / 1024)} / ${Math.round(total / 1024 / 1024)} MB` : '正在下载本地模型…'
      broadcastModelStatus()
    }
  })
  response.on('error', reject)
  output.on('error', reject)
  output.on('finish', () => {
    const actual = digest.digest('hex')
    if (actual !== MODEL_SHA256) return reject(new Error('下载校验未通过，请检查网络后重试。'))
    resolve()
  })
  response.pipe(output)
}

function requestModel(url, temporaryPath, redirects, resolve, reject) {
  if (redirects > 5) return reject(new Error('ModelScope 下载地址重定向次数过多。'))
  const request = https.get(url, { headers: { 'User-Agent': 'AI-Investment-Strategies/1.1.2' } }, (response) => {
    if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
      response.resume()
      return requestModel(new URL(response.headers.location, url).toString(), temporaryPath, redirects + 1, resolve, reject)
    }
    if (response.statusCode !== 200) {
      response.resume()
      return reject(new Error(`ModelScope 下载失败（HTTP ${response.statusCode}）`))
    }
    streamModel(response, resolve, reject, temporaryPath)
  })
  request.on('error', reject)
}

function stopLocalModelServer() {
  if (!localModelProcess || localModelProcess.killed) return
  localModelProcess.kill()
  localModelProcess = undefined
  localModelServerReady = false
  localModelGpuActive = false
  broadcastModelStatus()
}

ipcMain.handle('install-local-model', async () => {
  if (localModelServerReady) return localModelStatus()
  if (localModelStatus().installed) {
    startLocalModelServer()
    try {
      await waitForLocalModelServer()
      return localModelStatus()
    } catch (error) {
      return { ...localModelStatus(), error: error instanceof Error ? error.message : '本地模型启动失败' }
    }
  }
  try {
    await downloadLocalModel()
    await waitForLocalModelServer()
    return localModelStatus()
  } catch (error) {
    return { ...localModelStatus(), error: error instanceof Error ? error.message : '本地模型安装失败' }
  }
})

ipcMain.handle('local-model-settings', () => ({ ...readLocalModelSettings(), gpuAvailable: detectGpu(), gpuActive: localModelGpuActive }))
ipcMain.handle('set-local-model-settings', async (_event, patch = {}) => {
  const settings = { ...readLocalModelSettings(), gpuEnabled: Boolean(patch.gpuEnabled) }
  writeLocalModelSettings(settings)
  if (localModelProcess && !localModelProcess.killed) {
    stopLocalModelServer()
    startLocalModelServer()
    try { await waitForLocalModelServer() } catch { /* the UI can retry after a failed restart */ }
  }
  return { ...readLocalModelSettings(), gpuAvailable: detectGpu(), gpuActive: localModelGpuActive }
})

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
    if (channel === 'open-local-ai') {
      void contents.loadFile(localAiFile).catch(() => {})
    }
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
    ipcMain.handle('local-model-status', () => localModelStatus())
    createWindow()
    startLocalModelServer()
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
  })
  app.on('before-quit', stopLocalModelServer)
  app.on('window-all-closed', () => app.quit())
}
