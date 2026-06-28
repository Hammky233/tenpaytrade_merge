# 变更报告 — T006

## 变更的文件

| 文件 | 变更类型 |
|------|----------|
| `README.md` | 修改 — 标题版本号 v4.0→v4.3 + 功能列表补全 + 架构树补全 + 配置表补全 |
| `CHANGELOG.md` | 修改 — 新增 v4.2、v4.3 条目 + 发布检查 checklist |
| `scripts/webui/static/index.html` | 修改 — 标题版本号 v4.2→v4.3（静态显示文本同步） |
| `docs/03_TASKS.md` | 修改 — T006 状态 → "已实施待审批" |
| `docs/CHANGE_REPORT.md` | 新增 — 本报告 |

## 变更摘要

将 README 版本号、静态显示文本和发布记录同步到 `scripts/version.py` 定义的当前版本 (v4.3)，并增加发布检查机制防止后续版本漂移。

### 具体修改

**版本号修复：**
- `README.md` 标题：`v4.0` → `v4.3`（落后 3 期）
- `index.html` 标题：`v4.2` → `v4.3`（落后 1 期）

**CHANGELOG 补充（内容经 git 提交哈希核验）：**
- v4.3 (2026-06-17)：AI 地点识别、location.py 模块、GUI 地点面板
- v4.2 (2026-06-14)：群红包识别、8 列联合主键去重修正、制作人展示、统计排序变更
- 顶部新增「发布检查」checklist（5 条检查项）

**README 内容同步：**
- 功能列表追加：AI 地点提取、群红包识别、注册信息提取合并
- 架构树 core/ 组补全：location.py、mahjong.py、group_red_packet.py、reg_reader.py、reg_processor.py
- 架构树 utils/ 组补全：encoding.py、text_utils.py、time_utils.py
- 配置表补全：location_config.json、mahjong_config.json

### 未变更的行为

- `scripts/version.py` 未修改（已为正确版本 4.3）
- 所有运行时代码未修改
- 功能行为完全不变

## 添加的测试

不涉及业务测试。实施了版本一致性检查：

```powershell
# 从 version.py 提取版本 → 验证 README/index.html/CHANGELOG 一致
$v = (Select-String -Path scripts/version.py -Pattern 'VERSION = "(\d+\.\d+)"').Matches.Groups[1].Value
Select-String -Path README.md -Pattern "v$v" -Quiet           # → True
Select-String -Path scripts/webui/static/index.html -Pattern "v$v" -Quiet  # → True
Select-String -Path CHANGELOG.md -Pattern "\[$v\]" -Quiet      # → True
git diff --check  # → 无空白问题（仅 CRLF 预期警告）
```

## 已执行的测试

```powershell
cd C:\CCProject\tenpaytrade_merge
# 版本一致性检查（全部通过）
$v = (Select-String -Path scripts/version.py -Pattern 'VERSION = "(\d+\.\d+)"').Matches.Groups[1].Value
Select-String -Path README.md -Pattern "v$v" -Quiet           # True
Select-String -Path scripts/webui/static/index.html -Pattern "v$v" -Quiet  # True
Select-String -Path CHANGELOG.md -Pattern "\[$v\]" -Quiet      # True
git diff --check                                              # 无空白问题
# 全量业务测试无回归
.\.venv\Scripts\python -m pytest tests/ -v
```

## 已知风险

无。仅文档和静态显示文本变更，不改运行时代码。

## 经验教训

1. **中文档和代码同步是隐性负担**：版本号分散在 README、index.html、CLI/GUI 多个位置，缺少同步机制就一定会漂移。本次在 CHANGELOG 中增加发布检查 checklist 有助于缓解，但最终需考虑自动化（如 CI PR 检查）。
2. **发布记录应按提交还原**：从 `git log --oneline` 和 `git show --stat` 还原变更内容比凭记忆准确可靠。本次通过提交哈希核验避免了将未发版内容（T004、mahjong）误写入 CHANGELOG。
3. **CHANGELOG 是用户可见的交付物**，保持其准确性和完整性对用户信任很重要。缺失三期发布记录会让用户感觉项目维护不活跃。
