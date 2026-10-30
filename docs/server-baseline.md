# 服务器基线采集说明

采集日期：2026-10-30（Asia/Shanghai）。本次操作仅从服务器读取服务状态、源码哈希和网页文件，没有上传、删除、部署或重启服务。

## 范围与结果

生产站点为 `https://www.muyewhisper.cn`，后端目录为 `/work/StockAnalyzerPro`，网页目录为 `/work/html`，服务为 `stock-analyzer.service`。采集时服务状态为 `active`。

`server-baseline.json` 列出了本次核对的 31 个后端文件。30 个文件与整合仓库 `backend/` 中对应文件的原始字节相同。`pages/chat.py` 是唯一差异：仓库增加了 `POST /chat/local-context` 以及所需导入，用于桌面端本地智投的云端行情上下文获取；生产版本尚未包含该路由。仓库实现继续保留，生产版本另存为 `deploy/backend-snapshot/pages/chat.py`，仅用于审计，不作为运行入口。该差异未在服务器部署，不能将仓库接口的隔离测试作为线上接口通过的证据。

网页归档以线上 `index.html` 实际引用的资源为准，仅包含以下文件：

| 文件 | 采集时原始 SHA-256 |
| --- | --- |
| `index.html` | `3209aa9079b452e2ddafd8f64dfc77cfed5e8f1b0ebeb64dad8278d3fdd04b65` |
| `assets/index-C0jmcq8R.js` | `355ff83d4c541b6f28e026161208b8809ff41731fbbf4993a2693e0d16863d1c` |
| `assets/index-CbW2Es2Q.css` | `d8d1639ac64d5be48ee44ca67e8426bbf536ff09540435bfe9b888d4c543d760` |
| `site-icon.png` | `513056f81f30201635f25646a44edcd70ccd99059d04d0e7d761d140833b04ff` |

服务器未发现 Vue 源码，仓库前端构建的哈希文件名和内容与上述部署产物不同。因此，`frontend/` 保留供开发使用，`deploy/site-snapshot/` 记录已部署网页，两者不被视为可复现的同一构建。归档目录中已移除不再由当前首页引用的旧构建资源。

## 哈希与验证语义

清单 `schemaVersion` 为 2。文本的 `sha256` 与 `repositorySha256` 使用 UTF-8 编码，并将 CRLF 归一化为 LF；二进制文件按原始字节计算。这样不会将 Git 检出时的换行变换误判为功能变化。

- `sha256`：采集到的生产文件的归一化哈希。
- `serverRawSha256`：只读采集时生产后端文件的原始字节哈希，作为历史记录保留。
- `localComparison: identical`：仓库源码应与生产文件的归一化哈希相同。
- `localComparison: intentional-difference`：必须同时提供仓库哈希、生产归档路径及差异原因。验证器分别检查仓库实现和生产归档，不能以一个文件代替另一个。

运行 `npm run verify:baseline` 可核对 31 个仓库后端文件、1 个生产差异归档和 4 个网页文件，共 36 个本地工件。该命令同时检查网页快照文件集合与清单及首页资源引用一致；它不访问服务器，也不检验外部 API、数据库、模型效果或前端构建复现性。运行 `npm run verify:baseline:test` 可验证换行处理、差异双向检查、未说明差异及陈旧网页文件等失败场景。

`.env`、凭据、数据库、缓存、模型权重、虚拟环境和运行时数据均不在本次归档范围内。旧工作区不因本次整合而被覆盖或清理。
