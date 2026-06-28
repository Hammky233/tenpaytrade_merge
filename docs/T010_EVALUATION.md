# T010 评估报告 — JSX 运行时 Babel 的构建替代方案

## 1. 评估背景

当前 `scripts/webui/static/` 使用 Babel Standalone 在浏览器端实时编译 JSX。
本评估考察是否应改为预编译构建，以降低启动成本和打包体积。

约束条件：
- 不改变桌面 GUI 技术路线
- 不因构建优化破坏离线运行能力

## 2. 定量测量

### 2.1 文件体积对比

| 文件 | 当前（运行时 Babel） | 预编译（esbuild） |
|------|---------------------|-------------------|
| `babel.min.js` | 3,069 KB | **0 KB（移除）** |
| `react.production.min.js` | 11 KB | 11 KB（不变） |
| `react-dom.production.min.js` | 129 KB | 129 KB（不变） |
| `app.js` | 51 KB（JSX 源码） | **49 KB（编译后纯 JS）** |
| `style.css` | 8 KB | 8 KB（不变） |
| `index.html` | 0.5 KB | 0.5 KB（不变） |
| **static/ 合计** | **~3,268 KB** | **~198 KB（−94%）** |

### 2.2 构建性能（esbuild）

| 指标 | 值 |
|------|-----|
| 构建时间（无压缩） | **4 ms** |
| 构建时间（压缩） | **4 ms** |
| 构建时间（压缩+混淆） | **5 ms** |
| 额外依赖安装 | esbuild（~5 MB devDependency，不进入打包） |

### 2.3 JSX 编译验证

| 检查项 | 结果 |
|--------|------|
| JSX 语法残留（`<Component>`） | **0 处** ✅ |
| `React.createElement` 生成 | **43 处**（正确编译） |
| `async/await` 保留 | ✅（`--target=es2018` 原生保留） |
| `const`/箭头函数保留 | ✅（Chromium ≥ 73 原生支持） |

### 2.4 PyInstaller 产物影响

| 指标 | 当前 | esbuild 后 |
|------|------|-----------|
| 打包额外文件 | babel.min.js 3 MB | **无** |
| 预计 exe 体积 | 基线 | **−3 MB** |

## 3. 定性分析

### 3.1 启动时间

当前启动流程：加载 Babel (3 MB) → 解析 → 编译 51 KB JSX → 执行。
预编译后流程：加载 app.js (49 KB) → 执行。
移除 Babel 可节省：
- 文件 I/O：~3 MB 读取（pywebview 从本地磁盘加载）
- JS 解析时间：Chrome V8 解析 3 MB JS 的 CPU 时间
- 编译时间：Babel 运行时遍历 AST 编译 JSX 的时间

### 3.2 开发流程影响

| 场景 | 当前 | esbuild 后 |
|------|------|-----------|
| 初次检出后运行 | 无需额外操作 | 无需额外操作（`static/app.js` 已提交） |
| 修改前端代码 | 直接改 `app.js` | 改 `app.jsx` → 运行 `npm run build` |
| 代码审查 | Review JSX 语法 | Review `app.jsx`（源码）+ `static/app.js`（产物 diff 较小） |
| 调试 | 浏览器中 JSX 源码 | 浏览器中纯 JS（SourceMap 可映射回 JSX） |

> **构建耗时仅 4ms**，几乎无感。可以添加 `--watch` 模式在开发时自动重建。

### 3.3 离线能力

完全离线。所有资源仍在本地加载：
- `react.production.min.js`、`react-dom.production.min.js` 仍在 `static/` 内
- 构建产物 `static/app.js` 是纯 JS，直接通过 `<script>` 加载
- 不依赖 CDN，不通过网络加载任何资源

## 4. 兼容性验证

| 检查项 | 结果 | 说明 |
|--------|------|------|
| `--target=es2018` Chromium 兼容 | ✅ | pywebview 内嵌 Chromium ≥ 73，支持 ES2018 全部特性 |
| React UMD globals | ✅ | 输出仍引用 `React`、`ReactDOM` 全局变量 |
| pywebview bridge API | ✅ | 不涉及前端通信方式修改 |
| HTML 加载方式 | ✅ | `<script>` 标签加载（非 `type="text/babel"`） |

## 5. 推荐方案

**采用 esbuild 预编译构建**。

理由：
1. **体积**：移除 3 MB Babel，static/ 缩小 94%
2. **启动**：消除运行时编译开销
3. **构建成本**：4ms，几乎无感
4. **离线能力**：完全保持
5. **开发体验**：源码 `app.jsx`（JSX）+ 构建产物 `static/app.js`（纯 JS），两者均提交仓库

## 6. 构建方案设计

### package.json 变更

```json
{
  "scripts": {
    "build": "esbuild app.jsx --outfile=static/app.js --target=es2018 --minify-whitespace",
    "watch": "esbuild app.jsx --outfile=static/app.js --target=es2018 --watch"
  },
  "devDependencies": {
    "esbuild": "^0.28.1"
  }
}
```

> 使用 `--minify-whitespace`（仅压缩空白，不混淆变量名）以保持产物可读性。

### 构建命令

```bash
cd scripts/webui
npm install
npm run build
```

### 文件边界

| 角色 | 文件 | 提交 | 入包 |
|------|------|------|------|
| JSX 源码 | `scripts/webui/app.jsx` | ✅ | ❌（位于 `static/` 外） |
| 构建产物 | `scripts/webui/static/app.js` | ✅ | ✅ |
| HTML 加载 | `static/app.js`（`<script>`） | — | — |

### Git 提交策略

- `app.jsx`（源码）和 `static/app.js`（构建产物）**均提交到仓库**
- 确保检出的用户无需构建即可运行（`static/app.js` 始终是最新构建版本）
- 代码审查时审查 `app.jsx`，`static/app.js` 的 diff 仅包含 JSX→createElement 的等价转换

## 7. ADR-006 更新内容

需在 `docs/02_DECISIONS.md` 中更新 ADR-006：

| 字段 | 当前内容 | 更新后内容 |
|------|----------|-----------|
| 选定的方案 | "当前阶段将 React/Babel 等前端依赖放入本地静态目录本地加载" | "使用 esbuild 构建时预编译 JSX，静态产物离线加载，不依赖 CDN" |
| 理由 | 离线可用 + 符合 pywebview 架构 | 同左 + 运行时移除 3 MB Babel 开销，启动更快 |
| 后果 | 运行时 Babel 增加启动和解析成本 | 引入 Node/esbuild 作为开发时构建工具；运行时不依赖 Node/npm；PyInstaller 只包含构建产物（`static/`），不包含源码或构建工具；修改前端源码（`app.jsx`）后需运行 `npm run build` 生成 `static/app.js` |

---

本评估报告由实现代理在 T010 阶段 1 完成。
