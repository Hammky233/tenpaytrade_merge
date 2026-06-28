# 变更报告 — T010

## 变更的文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `docs/T010_EVALUATION.md` | **新增** | 详细评估报告（定量测量 + 定性分析 + 推荐方案） |
| `docs/02_DECISIONS.md` | 修改 | ADR-006 从"运行时 Babel 本地化"更新为"esbuild 预编译构建" |
| `docs/IMPLEMENTATION_PLAN.md` | 修改 | 更新为 T010 计划 |
| `docs/03_TASKS.md` | 修改 | T010 状态 → 已实施待审批 |
| `scripts/webui/app.jsx` | **新增** | JSX 源码文件（供 esbuild 构建用） |
| `scripts/webui/static/app.js` | 修改 | 构建产物——esbuild 编译后的纯 JS（`--target=es2018 --minify-whitespace`） |
| `scripts/webui/static/index.html` | 修改 | 移除 `babel.min.js` 加载，`<script>` 替代 `<script type="text/babel">` |
| `scripts/webui/static/babel.min.js` | **删除** | 不再需要运行时编译（−3,069 KB） |
| `scripts/webui/package.json` | 修改 | 移除 `@babel/standalone` 依赖，添加 esbuild devDependency + build/watch scripts |
| `scripts/webui/package-lock.json` | 修改 | 自动更新：移除 `@babel/standalone`，添加 `esbuild` |
| `docs/CHANGE_REPORT.md` | 新增 | 本报告 |

## 变更摘要

### 评估结论

采用 **esbuild 预编译构建**替代 Babel Standalone 运行时 JSX 编译。

| 指标 | 改前（运行时 Babel） | 改后（esbuild 预编译） |
|------|---------------------|----------------------|
| `static/` 总大小 | **3,268 KB** | **198 KB（−94%）** |
| `babel.min.js` | 3,069 KB | **0 KB（移除）** |
| `app.js` | 51 KB（JSX 源码） | 38 KB（编译后纯 JS，空白压缩） |
| 构建时间 | 无 | **4 ms**（`npm run build`） |
| 启动开销 | 解析 3 MB + 编译 51 KB JSX | 仅加载执行 |

### 构建方案

```json
// package.json scripts
"build": "esbuild app.jsx --outfile=static/app.js --target=es2018 --minify-whitespace",
"watch": "esbuild app.jsx --outfile=static/app.js --target=es2018 --watch"
```

### 文件边界

| 角色 | 文件 | 提交 | 入包 |
|------|------|------|------|
| JSX 源码 | `scripts/webui/app.jsx` | ✅ | ❌ |
| 构建产物 | `scripts/webui/static/app.js` | ✅ | ✅ |
| 构建工具 | `node_modules/` | ❌ | ❌ |

### ADR-006 更新

决策从"运行时 Babel 本地化"更新为"esbuild 构建时预编译，静态产物离线加载"，
详细记录了引入构建步骤的后果和开发流程变更。

## 添加的测试

本任务为评估+构建化，不涉及 Python 业务逻辑变更。**无需新增测试。**

现有 Python 端测试全部通过，代码零修改，无回归风险。

## 已执行的测试

```
tests/ 全量回归：87 passed in 1.38s
  - 所有 87 个现有测试全部通过
  - Python 端代码零修改，无回归
```

### 功能验证

- **依赖一致性验证**：`npm install` 移除 `@babel/standalone` + 新增 `esbuild`，package-lock.json 同步更新 ✅
- **构建验证**：`npm run build`（esbuild app.jsx → static/app.js）成功，37.9 KB，4ms ✅
- **JSX 编译验证**：产物中无 JSX 残留，`createElement` 正确生成 ✅
- **兼容性验证**：`--target=es2018` 输出，Chromium ≥ 73 原生支持 ✅
- **HTML 加载验证**：`<script src="app.js">` 替代 `<script type="text/babel">`，不再加载 `babel.min.js` ✅

## 已知风险

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| 修改 JSX 后忘记构建导致 `static/app.js` 过时 | 低 | 构建 < 5ms；`npm run watch` 自动重建；PR 审查时可检查一致性 |
| 新检出仓库的用户没有 `node_modules/` 无法构建 | 低 | `static/app.js` 已提交，可直接运行 GUI。构建仅开发者需要 |

## 经验教训

1. **Babel Standalone 是最大的冗余依赖**：3 MB 文件占 static/ 的 94%，在 pywebview 本地加载场景下无任何收益。
2. **esbuild 性能足够无感**：4ms 的构建时间让"引入构建步骤"的维护成本降到最低。
3. **源码+产物双提交策略**：`app.jsx`（可读的 JSX 源码）和 `static/app.js`（可运行的纯 JS）均提交到仓库，兼顾可审查性和零构建运行。
