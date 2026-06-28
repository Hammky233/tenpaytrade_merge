# 实现计划 — T010

## 任务 ID

T010

## 目标

评估是否将当前本地 Babel 运行时编译改为预编译构建，以降低启动成本和打包体积。

## 理解分析

### 当前架构

前端位于 `scripts/webui/static/`，使用 **Babel Standalone** 在浏览器端实时编译 JSX：

```
index.html:
  <script src="react.production.min.js">     ←    11 KB
  <script src="react-dom.production.min.js"> ←   129 KB
  <script src="babel.min.js">                ← 3,069 KB ⚠️ 占 static/ 的 94%
  <script type="text/babel" src="app.js">    ←    51 KB (JSX 源码)
```

启动流程：
1. 浏览器解析 react / react-dom（小）
2. 下载并解析 **babel.min.js（3.0 MB）**——最大单文件开销
3. Babel 运行时将 `app.js` 中的 JSX 编译为 `React.createElement(...)` 
4. 编译后的代码才执行

### 问题

| 维度 | 当前（Babel 运行时） | 理想（预编译） |
|------|---------------------|----------------|
| static/ 总大小 | 3.2 MB | ~200 KB（−3.0 MB） |
| 启动 CPU 开销 | 解析 3 MB + 编译 51 KB JSX | 仅加载执行 |
| PyInstaller 产物 | 含 3 MB Babel | 不含 Babel（≈ −3 MB） |
| 构建步骤 | 无 | 需一步构建 |

### 备选方案

1. **维持现状**（运行时 Babel）
2. **esbuild 预编译** — Node.js 生态最快的 JSX 编译器（Rust 编写）
3. swc 预编译 — Rust 版 JSX 编译器，生态小于 esbuild
4. Rollup/Vite 构建 — 全功能打包器，对本项目单一 JSX 文件过重

## 预计变更的文件

### 评估结论输出（无论是否引入构建）

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `docs/T010_EVALUATION.md` | **新增** | 详细评估报告 |
| `docs/02_DECISIONS.md` | 修改 | 更新 ADR-006 记录评估结论 |
| `docs/03_TASKS.md` | 修改 | T010 状态 → 已实施待审批（最终"已完成"由审查通过后由审查代理更新） |

### 若推荐引入 esbuild 预编译（额外变更）

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `scripts/webui/package.json` | 修改 | 添加 esbuild devDependency + build script |
| `scripts/webui/static/index.html` | 修改 | `<script type="text/babel" src="app.js">` → `<script src="app.js">` |
| `scripts/webui/static/babel.min.js` | **删除** | 不再需要 |
| `scripts/webui/app.jsx` | **新增** | JSX 源码（新文件，不参与 PyInstaller 打包） |
| `scripts/webui/static/app.js` | 修改 | 构建产物——esbuild 编译后的纯 JS，**提交到仓库**，供离线运行和 PyInstaller 打包 |
| `scripts/webui/.gitignore` | 修改 | `node_modules/` 已有，不需要添加 `app.js` 到忽略列表（它是提交的产物） |

#### 边界规则

| 角色 | 文件 | 是否提交 | 是否入包（PyInstaller） |
|------|------|----------|------------------------|
| **源码** | `scripts/webui/app.jsx` | ✅ 提交 | ❌ 排除（`--exclude` 或位于 `static/` 外） |
| **构建产物** | `scripts/webui/static/app.js` | ✅ 提交 | ✅ 打包（位于 `static/` 内） |
| **构建工具** | `node_modules/` | ❌ 不提交 | ❌ 不打包 |
| **HTML 加载** | `index.html` 加载 `static/app.js`（纯 JS），通过 `<script>` 而非 `<script type="text/babel">` | — | — |

> **`static/app.js` 提交到仓库**：确保任何检出仓库的用户无需运行构建即可运行 GUI（PyInstaller 直接打包 `static/`），也便于代码审查查看编译后的实际输出。构建工具（esbuild）仅作为开发依赖，不进入运行时或打包产物。|


## 实现策略

### 阶段 1：评估（本文档批准后执行）

1. **定量测量**
   - 测量 pywebview 在有无 Babel 时的首屏渲染时间
   - 确认 esbuild 输出格式与 pywebview Chromium 版本兼容
   - 验证移除 Babel 后功能完整（无 JSX 编译运行时错误）

2. **定性分析**  
   - 维护成本：构建步骤对开发流程的影响
   - 离线能力：是否引入 CDN 依赖（不引入）
   - 打包体积：PyInstaller 产物大小变化

3. **撰写评估报告** `docs/T010_EVALUATION.md`

### 阶段 2：执行（按评估结论）

- 若推荐 esbuild：执行文件变更
- 若推荐维持现状：仅更新 ADR-006 记录权衡

## 架构影响

前端技术路线不变（React 18 + 本地文件加载），但 **ADR-006 需更新决策内容**。

若评估结论为引入 esbuild 预编译，`docs/02_DECISIONS.md` 的 ADR-006 需改写：

| 字段 | 当前内容 | 更新后内容 |
|------|----------|-----------|
| **选定的方案** | "当前阶段将 React/Babel 等前端依赖放入本地静态目录本地加载" | "使用 esbuild 构建时预编译 JSX，静态产物离线加载，不依赖 CDN" |
| **理由** | 离线可用 + 符合 pywebview 架构 | 同左 + 运行时移除 3 MB Babel 开销，启动更快 |
| **后果** | 运行时 Babel 增加启动和解析成本 | 引入 Node/esbuild 作为开发时构建工具；运行时不依赖 Node/npm；PyInstaller 只包含构建产物（`static/`），不包含源码或构建工具 |
| **新增条目** | — | 新增一项：开发流程变更——修改前端源码（`app.jsx`）后需运行 `npm run build` 生成 `static/app.js` |

## 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| esbuild 输出兼容性 | 低 | `--target=es2015`，pywebview Chromium ≥ 73 |
| 需要 Node.js NPM 构建 | 低 | 开发环境已有 Node.js (已有 package.json) |
| 修改 JSX 需要手动构建 | 低 | 构建 < 50ms；可加 `--watch` 模式 |
| 团队不熟悉构建流程 | 低 | 简单文档说明 |

## 测试策略

- 构建后 app.js 为纯 JS，浏览器直接运行无报错
- 启动 `gui_app.py` 验证全功能正常
- 执行 `tests/` 全量回归确认 Python 侧无影响

## 考虑的替代方案

| 方案 | 不推荐理由 |
|------|------------|
| 维持现状 | Babel 3 MB 开销无收益，是 ADR-006 已记录的架构 debt |
| swc | 功能与 esbuild 重叠但社区较小，对本项目无额外优势 |
| Rollup/Vite | 配置复杂，本项目仅 1 个 JSX 文件，不需要 bundle 或 code splitting |
| TypeScript 编译 | 前端未用 TS，引入增加复杂度无收益 |

## 决策一致性

- 与 ADR-005（基础功能不依赖网络）一致——构建工具在开发机运行，离线运行不受影响
- 与 ADR-006（GUI 前端本地化，无 CDN）一致——预编译后所有资源仍在本地
- 若引入构建，需更新 ADR-006 反映决策变化

## 预估范围

- 评估报告：约 1 页 markdown
- 如需执行变更：～5 个文件变更，总增减 < 50 行代码（主要删除 babel.min.js 3 MB）
- 不涉及 Python 代码变更，不涉及核心业务逻辑
