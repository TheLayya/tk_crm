# TikTok Monitor CRM

TikTok 账号监控与运营管理系统。

## 技术栈

- 后端：FastAPI、SQLAlchemy、APScheduler、SQLite（`backend/`，端口 8001）
- 前端：Vue 3、Element Plus、ECharts、Vite（`frontend/`，端口 5174）
- 模块：监控账号 / 运营账号 / 项目 / 部门 / 角色 / 成员 / 代理节点（HTTP/HTTPS/SOCKS5）/ 导入导出 / 备份

## 本地启动（Windows，开发环境）

以下两个代码块分别在仓库根目录的新终端中执行（第一个块结束于 `backend/`，第二个块需要从仓库根目录重新 `cd frontend`）。Git Bash 与 CMD 均可（CMD 下把 `./` 换成 `.\`）。注意：仅启动服务两种 shell 通用；下方"对抗审查协作模式"一律以 Git Bash 为准执行。

```bash
cd backend
python -m venv .venv312
./.venv312/Scripts/python.exe -m pip install -r requirements.txt
./.venv312/Scripts/python.exe -m alembic upgrade head
./.venv312/Scripts/python.exe run.py
```

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

默认账号：`admin` / `admin123456`，仅供本机开发使用。开发服务器默认只绑定 `127.0.0.1`；如需局域网/移动端访问，先修改默认密码与 `backend/.env` 中的 JWT 密钥，再显式改回 `--host 0.0.0.0`。

---

## 对抗审查协作模式（核心工作流，强制）

> 用户指令：使用 orchestration 智能编排 + Codex 对抗审查，没有问题以后再开工，循环以往。

### 流程

1. **开工前先了解现状**：主代理（Claude）检查项目现状、目标实现与参照项目（如 `TheLayya/proxy_acc`），先输出一份现状摘要（涉及模块/文件清单 + 差距 + 方案）再动手。
2. **编排审查任务**：编排分为两条路径，按环境可用性选择：
   - **基线路径（Windows + Git Bash 必可用）**：主代理直接发起单路或多路 `codex exec`（见工具速查），关注点独立时可多路并行（如并发模型 / 安全 / 兼容性各一路）。
   - **编排路径（环境支持时优先）**：Orca orchestration / dmux 或 `scripts/orchestrate-worktrees.js`（依赖 tmux + git worktree + Node，需在 Git Bash 或 WSL 下运行，CMD 不支持）。**可用性检测**：`command -v tmux`、`node --version`、`git worktree list`（成功即具备 worktree 枚举能力）、`test -f ~/.claude/scripts/orchestrate-worktrees.js`，任一失败即回退基线路径；**运行时强制回退**：实际创建 worktree 失败（创建/检出/写入失败）时，立即放弃编排路径改走基线路径，不得因编排工具故障阻塞审查；所选路径与检测结果在交接文档中记录。
3. **Codex 对抗审查**：审查方**只做独立审查，不直接修改文件**：
   - `/codex challenge [关注点]` — 对抗模式：像攻击者 + 混沌工程师一样找生产故障（边界、竞态、安全洞、资源泄漏、静默数据损坏）。
   - `/codex review` — 独立 diff 审查，带 pass/fail 门禁（见下）。
   - `/codex consult` — 自由提问（会话可续）。
   - Codex 输出必须完整呈现（CODEX SAYS 块 + GATE 判定），不得截断或先入为主总结。
4. **主代理修复**：Claude 根据审查报告修改代码；修复范围保持窄、可辩护。
5. **验证**：每轮修改后必须执行，全部通过才算本轮完成。**先 `cd backend` 执行后端检查**（以下后端命令均为相对 `backend/` 的路径），后端全部通过后 **`cd ../frontend` 再执行前端构建**。**逐条执行，任一命令失败立即停止本轮（不继续后续命令），并记录每个退出码**：
   - `./.venv312/Scripts/python.exe -m compileall app` 无报错；
   - `./.venv312/Scripts/python.exe -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80` 全过（`--cov-fail-under=80` 使覆盖率不足时非零退出，杜绝假通过）；
   - `./.venv312/Scripts/python.exe -m mypy app --strict` 0 错误；
   - 前端（在 `frontend/` 下）：`npm run build` 通过。
   - 测试/静态检查工具统一安装（**验证序列第一条，先于 compileall 执行**）：`./.venv312/Scripts/python.exe -m pip install pytest pytest-cov mypy`（项目提供 `requirements-dev.txt` 时改执行 `pip install -r ../requirements-dev.txt`——该文件位于仓库根目录；若项目把它放在 `backend/` 下则用相对当前目录路径），新增功能必须补测试。
   - 退出码记录约定：已执行命令记录实际退出码；因"失败即停"未执行的命令记录为 `NOT RUN`。
6. **循环**：存在任何 `[P1]` → 修复后进入下一轮审查；0 个 `[P1]` 且 `[P2]` 已处理或按下方规则登记 → APPROVE，才进入下一项工作。**零问题结果同样必须显式声明**：`[P1] none; [P2] none; GATE PASS; APPROVE`。**未收敛判定（按连续轮次）**：连续 3 轮审查均存在 `[P1]` 且数量未下降 → 本轮工作状态标记为 **BLOCKED**，暂停后续改造，向用户汇报剩余问题由用户裁决（经用户同意可继续迭代，每轮仍记录）；Claude 与 Codex 意见冲突时同样交用户决策。
7. **记录**：每轮审查结论（问题、修复、验证结果）写入 `docs/handover/` 交接文档，并在本文件末尾"审查历史"小节追加一行。**"审查历史"小节是唯一允许随轮次更新的部分**；正文（流程/门禁/铁律/环境注意事项）不随轮次修改（避免污染下一轮审查输入）。

### 门禁口径（统一映射）

| Codex 标记 | 对应级别 | 处置 |
|-----------|---------|------|
| `[P1]` | CRITICAL / HIGH | **必须修复**，存在即 GATE FAIL，进入下一轮 |
| `[P2]` | MEDIUM / LOW | 收敛轮内尽量顺手修完；确需延后的逐条登记，不算 FAIL |

**P2 延后登记**必须包含：问题描述、延后理由、计划处理轮次。登记位置固定为交接文档中的"延后登记"小节（一条一行，字段以 `|` 分隔）。延后超过 1 轮仍未处理的，该登记项升级为阻塞项，本轮工作状态即进入 **BLOCKED**（与步骤 6 同一终态：暂停后续改造，交用户裁决）。

### 审查失败判定（禁止假 PASS）

以下任一情况出现时，本轮审查判定为**未完成**（不得当作 PASS），修复环境后重跑：

- codex 进程非零退出、超时或输出为空。超时由主代理的工具调用 `timeout` 参数实施（300000ms，Claude Code 的 Bash/PowerShell 工具均支持），超时即失败；
- 审查方报告因无法读取文件而未给出结论；
- 审查输出非空但**缺少 CODEX SAYS 块或 GATE 判定**（正常结论必须显式给出 `[P1] ...; [P2] ...; GATE PASS/FAIL` 结构，零问题时写 `[P1] none; [P2] none; GATE PASS; APPROVE`；仅有问题列表而无 GATE 同样判格式不完整）→ 判格式不完整，本轮未完成；
- **GATE 一致性核对**：主代理必须核对问题列表与汇总数量、GATE 结果是否一致；发现列出 `[P1]` 却声明 `GATE PASS` 等矛盾时，一律按 GATE FAIL 处理；
- 审查结束后发现审查方产生了新的工作树改动——该轮作废并查明原因。判定方法：审查开始前先 `mkdir -p .orchestration/<轮次>`（Git Bash 命令；`<轮次>` 为占位符，执行时替换为具体轮次名，如 `round-9`），再记录基线（`git status --short --ignored` 快照，保存到 `.orchestration/<轮次>/baseline.txt`），审查结束后对比增量（**比对时排除 `.orchestration/` 目录自身的变更**），**只追究审查方新增的改动**，审查前已存在的未提交改动不计入；Codex 单进程 read-only 调用天然满足此约束。多路并发审查时，各路使用独立 git worktree 隔离，或按轮次串行比对。

### 铁律

- 审查优先于修改，未完成审查前不继续扩大改造范围。
- 不改变既有业务语义（登录、导入导出、权限判定等）；仅当审查明确指出存在兼容性 bug 时才允许调整语义，且必须在交接文档中注明。
- 每轮修改后必须验证并记录审查结论，禁止未验证就宣称完成。
- 审查只读：Codex 运行在 read-only 沙箱，禁止它直接改文件。

### 环境注意事项（OCA 编辑器实测）

- 本机 Codex CLI（0.149.0）由 OCA 本地代理托管模型，shell 命令执行被环境策略阻断（`blocked by policy`）。**因此审查内容（目标文件全文或 diff）必须直接内嵌进 prompt**，不要让 Codex 自己去跑 `git diff` 或读文件。
- **内嵌规范**：先把 prompt 写入临时文件（UTF-8），再用 `codex exec -s read-only -- "$(cat 临时文件)"` 传入（引号包裹保证内容不被转义/截断；命令替换去除末尾换行不影响语义）。单次内嵌以 prompt 文件 UTF-8 字节数 ≤ **12000** 为界（为 Windows 命令行长度上限留足余量，实测 10KB 内嵌稳定运行），超出则按文件/模块拆分为多路分段审查，逐段汇总结果。
- codex 不可用或环境策略变更时，回退为 Claude 子代理（code-reviewer / security-reviewer）审查，并在交接文档中注明本轮为非 Codex 审查。**回退路径适用同等门禁**：子代理只授予只读工具（Read/Grep/Glob，不授予 Write/Edit/Bash 写操作），任务中注明"只审不改"；同样适用工具 timeout 参数（300000ms）、退出码与空输出检查，输出按 `[P1]`/`[P2]` 口径标记，缺少结论结构同样判本轮未完成。

### 工具速查

| 工具 | 用途 |
|------|------|
| `/codex review` | 独立审查（[P1] 门禁） |
| `/codex challenge` | 对抗审查（试图攻破） |
| `/codex consult` | 自由提问，会话可续 |
| `codex exec -s read-only -- "$(cat prompt.txt)"` | OCA 环境下的审查调用形式（prompt 内嵌内容，Bash 工具 timeout=300000） |
| `bash ~/.claude/scripts/orchestrate-codex-worker.sh <task> <handoff> <status>` | 派发 Codex worker（git worktree 隔离，Git Bash/WSL） |
| `node ~/.claude/scripts/orchestrate-worktrees.js plan.json --execute` | tmux + git worktree 多路编排（Git Bash/WSL） |
| `node ~/.claude/scripts/orchestration-status.js <out.json>` | 导出控制面快照 |

### 审查历史

| 轮次 | 日期 | 结论 | 处置 | 交接文档 |
|------|------|------|------|----------|
| 第 1 轮 | 2026-08-22 | 5 [P1] + 6 [P2]（启动命令跨 shell、验证门禁无强制退出、门禁口径不统一、编排依赖未声明、假 PASS 风险等） | 全部修复（`--cov-fail-under=80`、门禁映射表、失败判定、超时机制、内嵌规范等） | [docs/handover/2026-08-22-claude-md-adversarial-review.md](docs/handover/2026-08-22-claude-md-adversarial-review.md) |
| 第 2 轮 | 2026-08-22 | 4 [P1] + 6 [P2]（覆盖率不达标仍可假通过、编排执行矩阵、超时无机制、内嵌转义/长度风险等） | 全部修复（`--cov-fail-under=80`、基线/编排双路径、timeout 参数、临时文件内嵌规范、只读校验等） | 同上 |
| 第 3 轮 | 2026-08-22 | 3 [P1] + 4 [P2]（历史表与正文矛盾、工作树基线未定义、CMD 口径不一致、回退路径无等价门禁等） | 全部修复（历史小节例外声明、审查前基线快照、Git Bash 为准声明、回退同门禁等） | 同上 |
| 第 4 轮 | 2026-08-22 | 2 [P1] + 3 [P2]（验证缺失败即停、30000 字节内嵌超 Windows 命令行上限、3 轮规则定义、延后登记格式、ignored 文件基线） | 全部修复（逐条验证失败即停、内嵌上限降为 12000 字节、连续 3 轮 [P1] 未下降才 BLOCKED、延后登记小节、`--ignored` 基线） | 同上 |
| 第 5 轮 | 2026-08-22 | 1 [P1] + 4 [P2]（第 4 轮记录滞后、验证目录、回退只读强制、基线快照位置、输出结构校验） | 全部修复（补第 4 轮记录、验证段 `cd backend`、回退只读工具集、基线存 `.orchestration/<轮次>/baseline.txt`、缺结论结构判未完成） | 同上 |
| 第 6 轮 | 2026-08-22 | 1 [P1] + 3 [P2]（验证目录与前端构建矛盾、两种 BLOCKED 定义、格式校验不完整、基线文件自变更） | 全部修复（前端 `cd ../frontend`、BLOCKED 统一终态、GATE 结构校验、排除 `.orchestration/` 自身变更） | 同上 |
| 第 7 轮 | 2026-08-22 | 2 [P1] + 3 [P2]（第 6 轮记录滞后、零问题格式与失败判定矛盾、依赖安装顺序、NOT RUN 约定、编排可用性检测） | 全部修复（补第 6 轮记录、零问题显式格式 `[P1] none; GATE PASS; APPROVE`、pip 安装前置、`NOT RUN` 约定、编排路径可用性检测） | 同上 |
| 第 8 轮 | 2026-08-22 | 2 [P1] + 3 [P2]（基线目录未创建、GATE 一致性无核对、requirements-dev 路径、worktree 能力未检测） | 全部修复（`mkdir -p .orchestration/<轮次>`、GATE 一致性核对按 FAIL 处理、`../requirements-dev.txt` 路径、`git worktree list` 检测） | 同上 |
| 第 9 轮 | 2026-08-22 | 1 [P1] + 3 [P2]（worktree 检测不足、mkdir 为 Git Bash 语法、`<轮次>` 占位符、CODEX SAYS 与格式校验不一致） | 全部修复（运行时强制回退基线、命令注明 Git Bash、占位符替换说明、完整性检查补 CODEX SAYS 块） | 同上 |
| 第 10 轮 | 2026-08-22 | **0 [P1] + 0 [P2]，APPROVE**（收敛确认：worktree 回退、Git Bash 范围、占位符处理、CODEX SAYS/GATE 校验均已明确一致） | 无需处置 | 同上 |

---

## 功能差距（与参照项目 proxy_acc 对比，待办）

参照项目 `TheLayya/proxy_acc`（节点管理系统）有、本项目暂无的概念：

- **节点生成二维码**：为带中转信息的节点生成 `socks5://` 代理二维码（`QRCodeDialog.vue`），支持 Shadowrocket 等客户端扫码导入。本项目代理节点管理（`ProxyNodeManage`）无二维码能力。
- **终端资产 / 设备管理**：设备 CRUD（手机/电脑）、与节点一对一绑定、完整历史轨迹（`backend/app/{api,models,services}/device.py` + `frontend/src/views/devices/`）。本项目无设备模块。

新增以上功能时，按"对抗审查协作模式"流程执行。
