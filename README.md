# 智能投资平台（Windows 11 桌面版）

这是 MUYEwhisper 的智能投资决策项目整合仓库。桌面客户端适用于 64 位 Windows 11，主窗口加载生产站点 `https://www.muyewhisper.cn/`，并提供独立的本地智投页面。仓库同时保留 Vue 3 前端源码、Flask 后端源码、线上构建快照和可审计的服务器基线清单；源码实现和当前线上部署的差异见下文。

## 项目结构

- `frontend/`：Vue 3 + TypeScript + Vite + Pinia + Vue Router 前端源码。
- `backend/`：Flask API，包含认证、股票、板块、聊天 SSE、策略工作台、模拟交易和桌面端上下文接口。
- `desktop/`：Electron Windows 客户端。生产模式不启动本地 Python 或 MySQL，直接加载线上站点。
- `deploy/site-snapshot/`：2026-10-30 从线上 `/work/html` 取得的首页及其实际引用的 JS、CSS 和图标。
- `deploy/backend-snapshot/pages/chat.py`：2026-10-30 线上聊天路由源码，用于核对仓库保留的桌面端接口差异，不作为本地应用入口。
- `docs/server-baseline.json`：服务器文件的 SHA-256 基线及同步结果。
- `scripts/`：基线校验和桌面冒烟脚本。

## 直接使用 Windows 应用

运行 [GitHub Releases](https://github.com/MUYEwhisper/AI-Investment-Strategies/releases/latest) 中最新的 Windows 安装包，按安装程序提示安装。应用需要网络连接获取登录、行情和 MCP 数据；本地模型由用户在“本地智投”页面点击安装后直接从 ModelScope 下载至本机，模型文件不包含在安装包内，也不经过应用服务器。

当前桌面客户端加载 `https://www.muyewhisper.cn/`。如果服务器暂时不可达，应用会显示重连页面，点击“重新连接”或按 `Ctrl + R` 即可恢复。

桌面端工作区新增“本地智投”。该页只保留“智投问答”，使用 `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` 在本机推理；股票、市场和新闻数据通过与云端模型相同的今日投资 MCP 服务取得。首次进入时若模型未安装或服务不可用，页面会提供自动安装/启动按钮，并显示 ModelScope 下载进度。模型安装到当前 Windows 用户的数据目录，卸载应用时保留模型文件。

本地模型服务使用随应用分发的轻量 llama.cpp 运行时和 ModelScope GGUF 量化权重。正式安装包只包含应用本体和推理运行时，不包含模型权重；下载完成后自动启动服务，并等待健康检查通过。本地问答仍会调用线上 `/chat/local-context` 获取 MCP 数据。

截至 2026-10-30，生产后端尚未包含 `/chat/local-context`，仓库保留此接口以支持桌面端云端上下文请求。因此，本地模型运行与云端行情上下文获取是不同的验证对象，当前线上环境不能据此认定本地智投的行情数据链路已经可用，也不能将桌面端描述为完全离线应用。

当前网页由 Vue 渲染桌面侧栏，分别显示市场总览、AI 投顾、策略工作台和账号中心，桌面下载入口会隐藏。Electron 保留对旧网页的侧栏注入兼容，仅对自己创建的侧栏同步导航状态；已有 Vue 侧栏由网页管理，避免旧同步逻辑覆盖视图切换。本地智投入口打开随客户端分发的页面，其余业务仍使用线上页面和服务器接口。

页面切换使用统一的短时长 Web Animations 动画，快速连续点击时会取消旧动画并保留最后一次导航；系统启用“减少动态效果”时会立即展示最终状态。列表新增、删除、会话切换和桌面市场/AI 视图也使用同一套动画生命周期。

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
npm run verify:baseline:test
npm run backend:test:local-context
npm run desktop:test
npm run frontend:build
npm run frontend:test
npm run desktop:smoke
npm run desktop:pack
npm run desktop:build
```

桌面冒烟测试会检查主界面、服务器接口未登录响应、登录跳转是否仍在同一窗口、渲染器是否隔离 Node.js、断网恢复页和重连链接。安装包构建默认关闭代码签名自动发现；发布到正式渠道时应配置 Windows 代码签名证书。

`backend:test:local-context` 需要安装 Flask 的 Python 环境。它替换行情、模型和认证依赖并禁止网络，只验证仓库路由契约。2026-10-30 的构建、测试计数、桌面兼容修复和验证范围见 [docs/validation-2026-10-30.md](docs/validation-2026-10-30.md)。本次未重新发布安装包，现有 Release 不包含此次源码修复。

## 服务器同步说明

服务器是已部署网页版的运行基准。2026-10-30 通过只读 SSH 检查了 `/work/StockAnalyzerPro`、`stock-analyzer.service` 和 `/work/html`，服务状态为 active。清单中的 31 个后端文件有 30 个与仓库文件原始字节一致；唯一功能差异为仓库 `pages/chat.py` 增加了 `/chat/local-context`。该路由继续保留，线上原文件单独归档，清单同时记录两者哈希和差异原因。本次更新没有部署、覆盖线上文件或重启服务。

网页快照仅保存当时首页实际引用的四个文件，不混入旧版构建。服务器没有 Vue 源码，当前 `frontend/` 的构建与线上快照不同，不能声称这些编译产物可由当前源码复现。生产数据库、`.env`、模型缓存和运行时数据不进入仓库。完整基线说明见 [docs/server-baseline.md](docs/server-baseline.md)。

`verify:baseline` 只核对本地源码、归档文件与清单，不连接生产服务器。为兼容 Git 的 Windows/Linux 换行处理，文本哈希将 CRLF 归一化为 LF；清单中另存只读采集时的 `serverRawSha256`，作为当时服务器原始字节的记录。验证成功表示本地归档符合已记录基线，不表示当前线上部署或 Vue 构建可复现性通过验证。

服务器连接示例（不要把密码写入脚本或提交记录）：

```powershell
plink -ssh whisper@106.14.221.14 -P 22 -pw <PASSWORD> -L 3306:127.0.0.1:3306
```

## 安全边界

Electron 启用 `contextIsolation`、sandbox 和禁用 Node 集成；只允许线上站点、Ksuser OAuth 域名和 API 域名在应用窗口内导航，其他 HTTPS 链接使用系统浏览器打开，非 HTTPS 和带凭据 URL 会被拒绝。服务器密钥、数据库密码、AI/MCP 密钥和 OAuth secret 只能通过本地环境变量配置。

## 免责声明

行情、模型分析和策略工作台内容仅供研究参考，不构成投资建议。投资有风险，决策请结合自身情况审慎判断。



