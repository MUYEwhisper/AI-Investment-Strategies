# QIANDUAN

一个基于 Vue 3 + TypeScript + Vite 的前端项目，提供「自选股管理 + 板块分析可视化 + AI 流式对话」的交互体验。

## 项目特性

- 自选股区
  - 支持按股票名/代码添加股票。
  - 支持删除股票、查看个股详情与关键指标。
  - 内置过渡动画与交互状态控制。
- 板块分析区
  - 展示资金关注度与市场情绪饼图。
  - 支持一键刷新板块模拟数据。
  - Chart.js 采用运行时动态加载，避免安装依赖受限时阻塞页面功能。
- AI 对话区
  - 支持多会话历史管理（新建、切换、删除）。
  - 支持 SSE 流式响应与推理模式切换。
  - 对话历史持久化到浏览器 LocalStorage。

## 技术栈

- 前端框架：Vue 3（Composition API）
- 构建工具：Vite
- 语言：TypeScript
- 状态管理：Pinia
- 路由：Vue Router
- 单元测试：Vitest + Vue Test Utils + jsdom
- 端到端测试：Playwright
- 代码质量：ESLint + Oxlint + Prettier

## 运行环境

- Node.js：^20.19.0 或 >=22.12.0
- npm：建议使用与 Node 版本匹配的最新稳定版

## 快速开始

1. 安装依赖

```bash
npm install
```

2. 启动开发环境

```bash
npm run dev
```

3. 本地预览生产构建

```bash
npm run build
npm run preview
```

## 可用脚本

```bash
npm run dev          # 启动开发服务器
npm run build        # 类型检查 + 生产构建
npm run build-only   # 仅执行 Vite 构建
npm run preview      # 预览构建产物
npm run type-check   # 仅执行 vue-tsc 类型检查
npm run test:unit    # 运行 Vitest 单元测试
npm run test:e2e     # 运行 Playwright E2E 测试
npm run lint         # 执行 Oxlint + ESLint（自动修复）
npm run format       # 使用 Prettier 格式化 src/
```

## AI SSE 接入说明

聊天区默认请求地址：/chat/endpoint

开发环境下，Vite 会将 /chat 代理到：http://localhost:8000

如需指定完整后端地址，可在项目根目录创建 .env.local：

```bash
VITE_AI_CHAT_ENDPOINT=http://localhost:8000/chat/endpoint
```

前端发送请求体示例：

```json
{
  "prompt": "用户输入",
  "stream": true,
  "sse": true,
  "thinking": true
}
```

前端支持解析以下 SSE 事件：

- start
- reasoning
- tool_call
- tool_result
- message
- error
- end

## 目录结构

```text
QIANDUAN/
  src/
    App.vue                # 主页面（自选股、板块分析、AI 对话）
    main.ts                # 应用入口
    router/index.ts        # 路由配置
    stores/counter.ts      # Pinia 示例 store
    __tests__/App.spec.ts  # 单元测试示例
  e2e/
    vue.spec.ts            # Playwright E2E 示例
  vite.config.ts           # Vite 配置（含 /chat 代理）
  vitest.config.ts         # Vitest 配置
  playwright.config.ts     # Playwright 配置
```

## 测试说明

- 单元测试

```bash
npm run test:unit
```

- 端到端测试

```bash
npx playwright install
npm run test:e2e
```

说明：当前 e2e/vue.spec.ts 为示例用例，请根据现有页面结构与文案调整断言后再用于稳定回归。

## CI 说明

仓库包含 GitHub Actions 工作流：

- 触发条件：push 到 master
- 执行内容：npm ci -> npm run build
- 产物上传：dist

## 开发建议

- 推荐 IDE：VS Code + Vue Official (Volar)
- 推荐浏览器插件：Vue.js devtools
- 提交前建议至少执行：npm run lint && npm run test:unit

