# 智能投资平台（Windows 11 桌面版）

这是 MUYEwhisper 的智能投资决策项目整合仓库。桌面客户端适用于 64 位 Windows 11，界面和业务功能与线上站点保持一致，业务请求直接连接生产服务器 `https://www.muyewhisper.cn/`。仓库同时保留 Vue 3 前端源码、Flask 后端同步快照、线上构建快照和可审计的服务器基线清单。

## 项目结构

- `frontend/`：Vue 3 + TypeScript + Vite + Pinia + Vue Router 前端源码。
- `backend/`：从 `/work/StockAnalyzerPro` 同步的 Flask API，包含认证、股票、板块、聊天 SSE、策略工作台和模拟交易接口。
- `desktop/`：Electron Windows 客户端。生产模式不启动本地 Python 或 MySQL，直接加载线上站点。
- `deploy/site-snapshot/`：2026-10-06 从线上 `/work/html` 取得的网页部署快照。
- `docs/server-baseline.json`：服务器文件的 SHA-256 基线及同步结果。
- `scripts/`：基线校验和桌面冒烟脚本。

## 直接使用 Windows 应用

运行 Release 中最新的 `AI-Investment-Strategies-Setup-1.0.5-x64.exe`，按安装程序提示安装。应用需要网络连接；登录、聊天、行情和账户数据均由服务器处理。安装器不会写入密钥，登录会话保存在 Electron 的应用用户数据目录中。安装程序同时注册 Windows 卸载程序，应用菜单也提供“卸载智能投资平台”入口。

当前桌面客户端加载 `https://www.muyewhisper.cn/`。如果服务器暂时不可达，应用会显示重连页面，点击“重新连接”或按 `Ctrl + R` 即可恢复。

桌面客户端在远程网页功能之上注入独立的桌面应用壳：使用左侧工作区导航栏，将市场总览、AI 投顾、策略工作台和账号中心分开显示，并配合紧凑卡片与 Windows 风格控件。下载入口只在网站端显示，桌面端会自动隐藏，避免在应用内部出现自我下载链接；所有股票、板块、AI 对话、登录和策略工作台功能仍使用同一套线上页面与服务器接口。

## 本地开发

需要 Node.js 22.12+（推荐 Node.js 24）和 npm。

```powershell
npm install
npm run desktop:dev
```

桌面端连接线上服务，不启动本地 Python 或 MySQL。若要开发前端源码：

```powershell
npm run frontend:install
npm run frontend:dev
npm run frontend:build
npm run frontend:test
```

前端开发服务器默认把 `/api` 和 `/chat` 代理到 `http://localhost:8000`。可通过 `frontend/.env.local` 设置 `VITE_BACKEND_PROXY_TARGET=https://www.muyewhisper.cn` 进行线上接口联调。

后端仅用于需要修改服务端逻辑时的本地开发：

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/pip install -r backend/requirements.txt
# 根据 backend/.env.example 创建 backend/.env，再运行：
backend/.venv/Scripts/python backend/main.py
```

本地后端需要 MySQL、AI 模型密钥、MCP 密钥和 Ksuser OAuth 配置。生产 `.env` 未从服务器下载，也不会提交到 GitHub。

## 验证与打包

```powershell
npm run verify:baseline
npm run desktop:test
npm run frontend:build
npm run frontend:test
npm run desktop:smoke
npm run desktop:pack
npm run desktop:build
```

桌面冒烟测试会检查主界面、服务器接口未登录响应、登录跳转是否仍在同一窗口、渲染器是否隔离 Node.js、断网恢复页和重连链接。安装包构建默认关闭代码签名自动发现；发布到正式渠道时应配置 Windows 代码签名证书。

## 服务器同步说明

服务器是运行基准。2026-10-06 通过 SSH 检查了 `/work/StockAnalyzerPro`、Gunicorn `stock-analyzer.service` 和 `/work/html`，并下载了后端有效源码与网页构建文件。服务器没有 Vue 源码，线上 JS/CSS/HTML 快照作为最终网页版本保存。生产数据库、`.env`、模型缓存和运行时数据不进入仓库。

服务器连接示例（不要把密码写入脚本或提交记录）：

```powershell
plink -ssh whisper@106.14.221.14 -P 22 -pw <PASSWORD> -L 3306:127.0.0.1:3306
```

## 安全边界

Electron 启用 `contextIsolation`、sandbox 和禁用 Node 集成；只允许线上站点、Ksuser OAuth 域名和 API 域名在应用窗口内导航，其他 HTTPS 链接使用系统浏览器打开，非 HTTPS 和带凭据 URL 会被拒绝。服务器密钥、数据库密码、AI/MCP 密钥和 OAuth secret 只能通过本地环境变量配置。

## 免责声明

行情、模型分析和策略工作台内容仅供研究参考，不构成投资建议。投资有风险，决策请结合自身情况审慎判断。

