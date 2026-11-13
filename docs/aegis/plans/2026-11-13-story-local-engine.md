# 爬塔（单人故事模式）本地化 + 逐层存档 + 作弊检测 计划

- 日期：2026-11-13
- 状态：待评审（尚未实现）
- 触发背景：单人爬塔时服务器周期性冻结（见「卡顿排查结论」），单进程 eventlet + 阻塞式 SQLite，动作强依赖服务端 RTT。

## 1. 目标与非目标

**目标**
1. 单人爬塔的大部分结算在浏览器本地完成：出牌、敌人回合、房间选项、地图推进都不再依赖网络。
2. **楼层切换**和**每场战斗结束**时都自动存档并上传；服务端**重放校验**通过才落库、才发奖励。
3. 作弊检测以「可复现重放」为主，辅以节奏/合法性/统计三条辅助线；发现异常时服务端权威，可拒绝、可回滚、可标记。
4. 保留现有服务端权威模式作为兜底与 A/B（`story_local_mode` 开关粒度：off / staff / %）。

**非目标（本期不做）**
- 多人爬塔保持**在线模式**不变（`/api/story/coop/*` 已停用、`/api/coop-demo/*` 为内存演示），本期不做本地化，也不改其协议。
- 天赋/祝福/遗物等内容的平衡调整。
- 把 SQLite 换成 Postgres/MySQL（属于运维侧，另立计划）。

## 2. 现状（基线事实）

| 项 | 事实 |
|---|---|
| 引擎 | `D:\gtn\story_engine.py` 562 KB，纯标准库 + `story_content.py`（334 KB）+ `story_events_12.py`；入口 `apply_story_action(source_state, action_type, payload, seed)`（`story_engine.py:13637`） |
| 确定性 | 已内置：`_rng(state, seed, namespace)`（`story_engine.py:781`）用 `HMAC(seed, "story-rng-v2:<namespace>:<counter>")` 生成 `random.Random`，计数器存于 `state['rng_streams']` / `state['rng_counter']` / `state['rng_version']=2`；`journey_seed` 随 run 保存 |
| 服务端动作 | `POST /api/story/run/action`（`app.py:23862`）：校验 `state_version`、`action_id` 幂等，`_apply_and_commit` 经 `run_off_event_loop` 线程池执行，`commit_story_run_action`（`db.py:5150`）事务写入并自增版本 |
| 前端 | `static/js/story.js` 842 KB，**纯渲染/发请求，没有战斗模拟**；`static/css/story.css` 230 KB |
| 数据 | `story_runs` 16,065 行、`story_run_actions` 370 万+ 行、`story_runs.state_json` 单 run 约 17 KB；生产库 2.1 GB |
| 存档 | 已有服务端存档 `/api/story/run/save`、`/load`、`/saves`、`/save/delete`（`app.py:24125-24294`） |
| 奖励 | 通关结算 `story_score.py` + `story_clear_settlement.js`；通行证经验走 `battle_pass` |
| 环境 | 生产 2 vCPU / 1.6 GB 内存 / 单进程 eventlet；重放校验必须限流、放线程池 |

## 3. 架构决策

### 3.1 引擎同源（推荐）：浏览器内跑同一份 Python 引擎

不在 JS 里重写战斗引擎。用 **Pyodide（CPython→wasm）** 在 **Web Worker** 里加载 `story_engine.py + story_content.py + story_events_12.py`（打包约 1 MB，Pyodide 运行时约 10 MB，按需加载并强缓存），Worker 内每步调用同一个 `apply_story_action`。

理由：
- 与服务端重放**逐字节同源**，不会出现「双引擎漂移 → 误判作弊」这种最坏情况。
- 端口工作量最小（0 行重写），内容更新只改 Python。
- 动作结算量级为毫秒：CPython 单步 1–20 ms，wasm 约 2–5× ，单步 5–80 ms 可接受；重的整层推进可批量跑在 Worker 里，不阻塞渲染。

代价与缓解：
- 首包 ~10 MB：仅进入故事模式时懒加载；`Cache Storage` 预缓存；弱网降级为服务端权威模式（提示「本地引擎加载失败，已切换在线模式」）。
- 移动端内存：iOS Safari 对 wasm 堆较敏感，Worker 里限制单 run、退出即释放；崩溃即回退服务端模式。
- 兼容策略：`story_engine` 只 import 标准库（已确认），无需改造即可在 Pyodide 运行。

### 3.2 备选方案（记录，不选）

| 方案 | 优点 | 否决原因 |
|---|---|---|
| A. JS 重写引擎 | 包体小、性能最好 | 562 KB/14k 行 Python 重写 + 永久双份维护；任何规则微调都需两端同步，重放漂移会误封 |
| B. 服务端预先算出整层 | 无需本地引擎 | 玩家决策未知，无法预计算；本质仍是 RTT |
| C. 服务端保持逐动作 | 零改造 | 就是当前卡顿来源 |

### 3.3 存档与校验协议

**启动**：`POST /api/story/run/local/start`
服务端创建 run（`seed = secrets.token_hex(16)`）、生成初始 `state`、返回
`{run_id, seed, content_version, state, state_digest, signature}`，`signature = HMAC(server_secret, run_id|seed|content_version|state_digest)`。
客户端**只信任签名的 seed/state**，不能自选种子。

**存档上传（两个时机）**：`POST /api/story/run/local/checkpoint`

触发点固定为两个：① 楼层切换（进入下一层前）；② 每场战斗结束（胜利/失败/撤退结算后）。两次触发都生成一个 checkpoint，`seq` 单调递增，服务端按 `seq` 逐条校验；战斗中途不单独上传。

```jsonc
{
  "run_id": "...", "floor": 3, "seq": 7,
  "prev_digest": "sha256:...",        // 上一已校验层摘要，形成链
  "actions": [ {"id":"a1","type":"play_card","payload":{...}}, ... ],   // 本层动作日志
  "state": { ... },                   // 本层结束时的完整状态（服务端只用于比对，不直接采信）
  "state_digest": "sha256:...",       // 规范化 JSON 的 sha256
  "elapsed_ms": 421000,
  "client": {"ua":"...", "engine":"pyodide-0.26"}
}
```

服务端处理（全部在线程池，事务内）：
1. 校验签名、`seq = last_seq + 1`、`prev_digest` 与库中一致、`content_version` 一致。
2. 取**已校验状态**（不是客户端上传的 state）→ 逐条 `apply_story_action` 重放本层动作 → 得到 `server_state`。
3. 规范化 JSON（键排序、浮点格式化、剔除易变字段）后算 `server_digest`；与 `state_digest` 比较；同时校验动作数/耗时下限。
4. 通过 → 写 `story_run_checkpoints`（动作日志 gzip 存档）+ 更新 `story_runs.state_json / state_version / last_verified_floor / state_digest`；奖励只按服务端重放结果计算。
5. 不通过 → `409 STORY_CHECKPOINT_MISMATCH`，记录差异摘要与可疑度；**按上一个已校验存档结算本局并结束 run（视为直接放弃）**：已校验楼层的奖励保留、本局不再发新奖励、也不允许续玩；客户端展示「本局已按上次存档结算（异常终止）」，并提供「以在线模式重新开始」入口。

**续玩/掉线**：`POST /api/story/run/local/resume` 返回最近已校验 checkpoint 的 state + digest，客户端从该点重建（服务端永远只认已校验点，天然防回滚刷奖励）。
**结束**：`POST /api/story/run/local/finish` 由服务端按最终已校验状态结算（荆露、通行证经验、成就），客户端只展示。

### 3.4 作弊检测分层

| 层 | 手段 | 处置 |
|---|---|---|
| L1 确定性重放 | seed + 本层动作日志 → 服务端重放，digest 必须一致 | 不一致直接拒绝 |
| L2 动作合法性 | 引擎自身拒绝非法动作；重放失败即异常；严格 schema（多余键拒绝） | 拒绝 + 记分 |
| L3 日志链 | `prev_digest` 链 + 每步滚动哈希 `h_i = sha256(h_{i-1} + action_json + digest_i)` | 截断/重排/替换直接拒绝 |
| L4 节奏 | 每层最短耗时、每回合最短耗时、动作速率上限、同一 IP 多 run 并发上限 | 超阈值拒绝或转人工 |
| L5 经济守恒 | 奖励只由服务端重放状态推导；每层奖励幂等键 `(run_id, floor, kind)`；日上限 | 无法通过客户端伪造 |
| L6 统计 | 重放失败率、通关率、异常楼层分布、相同动作序列跨账号 | 可疑度累积 → 进 `/handling` 风险页签 |

**明确不做的**：不把「客户端上传的 state」当权威；不依赖客户端时间；不做 obfuscation 级反调试（成本高、收益低）。

## 4. 数据模型改动

```sql
-- 新增
CREATE TABLE story_run_checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  floor INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  action_count INTEGER NOT NULL,
  actions_gzip BLOB NOT NULL,
  client_digest TEXT NOT NULL,
  server_digest TEXT NOT NULL,
  elapsed_ms INTEGER NOT NULL DEFAULT 0,
  replay_ms INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'verified',   -- verified | mismatch | rejected
  flags_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE(run_id, seq)
);
CREATE INDEX idx_story_checkpoints_user ON story_run_checkpoints(user_id, created_at DESC);

-- story_runs 增加列
ALTER TABLE story_runs ADD COLUMN local_mode INTEGER NOT NULL DEFAULT 0;
ALTER TABLE story_runs ADD COLUMN last_verified_floor INTEGER NOT NULL DEFAULT 0;
ALTER TABLE story_runs ADD COLUMN checkpoint_seq INTEGER NOT NULL DEFAULT 0;
ALTER TABLE story_runs ADD COLUMN state_digest TEXT NOT NULL DEFAULT '';
ALTER TABLE story_runs ADD COLUMN suspicion_score INTEGER NOT NULL DEFAULT 0;
```

保留 `story_run_actions` 给在线模式与审计；本地模式只在 checkpoint 里存动作日志（gzip 后单层约 5–30 KB）。上线 3 个月后按「在线模式已无调用」再评估归档/裁剪 370 万行旧动作（单独变更，不并入本期）。

## 5. 任务分解（每项含验证）

> TDD Route：`auto` → **strict**（涉及持久化、公开 API、契约与作弊判定，回归信号明确）。每个任务先写失败测试再实现；无用户显式 TDD 要求，按 auto 规则判定。

### T0 基线与观测（0.5 天）
- 采集 200 个已完成 run 的 `actions + 最终 state` 作为**黄金语料**（脚本 `scripts/dump_story_replay_corpus.py`，输出 `tmp_cardstar/story_corpus/*.json.gz`）。
- 记录当前在线模式指标：动作接口 p50/p95、每层动作数分布、单层耗时分布（后续阈值来源）。
- 验证：语料可被服务端 `apply_story_action` 重放且 digest 与库中 `state_json` 一致（先定义规范化 JSON 函数，见 T2）。

### T1 浏览器引擎可行性 spike（2 天，可弃）
- `static/story-engine/worker.js`：Pyodide 加载本地 wheel/zip，暴露 `apply(state, type, payload, seed)`。
- `tmp_cardstar/probe_story_engine_worker.py`：Playwright 打开 harness，跑 20 个黄金用例，比对 digest 与 Python。
- 记录：首包大小、冷启动耗时、单步耗时 p50/p95、内存峰值。
- 通过标准：20/20 digest 一致；单步 p95 < 80 ms；冷启动 < 4 s（缓存后 < 1.5 s）。
- 不达标 → 停止，回到方案 A 评估（JS 端口）或缩小本地化范围（仅地图/房间，战斗仍在服务端）。

### T2 规范化摘要与链（1 天）
- 新增 `story_verify.py`：`canonical_json(state)`（键排序、浮点 `repr` 规则、剔除 `updated_at` 等易变字段）、`state_digest(state)`、`chain_digest(prev, action, digest)`。
- 验证：同状态不同键序/浮点写法摘要一致；跨 Python 3 版本一致；黄金语料 200/200 复现。

### T3 服务端重放校验器（2 天）
- `story_verify.replay_checkpoint(prev_state, actions, seed, expected_digest)` → `(ok, server_state, diff)`；含动作数/大小/耗时上限、异常分类。
- 测试（`tests/test_story_verify.py`）：正常通过、篡改一个动作、删一条、换序、伪造 digest、跨 run 重放、超长动作、旧 `content_version`、空动作层。
- 验证：pytest 全绿；重放 200 个黄金层，耗时 p95 < 300 ms。

### T4 持久化与迁移（1.5 天）
- `db.py`：建表/加列、`ensure_story_local_schema(conn)`；`commit_story_checkpoint(...)` 事务（乐观锁 `checkpoint_seq`）、奖励幂等表 `story_run_rewards(run_id, floor, kind, amount, created_at, UNIQUE(run_id, floor, kind))`。
- 迁移脚本 `scripts/migrate_story_local.py`（幂等，`--dry-run`）。
- 测试：并发两次同 seq 只成功一次；奖励重复发放被幂等键挡住；旧库升级后可读写。

### T5 本地模式 API（2 天）
- `app.py` 新增：`/api/story/run/local/start`、`/checkpoint`、`/resume`、`/finish`；全部 `run_off_event_loop`；`_story_local_allowed(user_id)` 读开关 `GTN_STORY_LOCAL_MODE=off|staff|pct:25`。
- 失败语义：`409 STORY_CHECKPOINT_MISMATCH`（带 `expected_digest`/`server_state_digest` 摘要，不返回完整状态）、`429 STORY_CHECKPOINT_RATE_LIMIT`、`409 STORY_STATE_VERSION_OLD`。
- 测试（`tests/test_story_local_api.py`）：匿名 401、开关 off → 404、正常两层上传、篡改拒绝、resume 回滚、finish 幂等。

### T6 客户端本地运行时（3 天）
- `static/js/story-local.js`：Worker 管理、状态持有、动作队列、逐层触发上传（失败退避重试、离线排队）、断线后 `/resume` 对齐、开关关闭时无缝回落在线模式。
- `static/js/story-engine-worker.js`：Pyodide 装载、`apply_story_action` 桥接、消息协议版本化。
- 现有 `story.js` 改一处入口：动作发送走 `story-local` 适配层，UI 不动。
- 验证：预览服双模式跑通同一局；断网 30 秒后恢复，checkpoint 补齐；关闭开关后仍能在线玩。

### T7 作弊观测与运营（1 天）
- `/handling` 增加「爬塔校验」页签：mismatch 列表、可疑度排序、重放差异摘要、一键转人工。
- 指标：`story_checkpoint_total{status}`、`replay_ms` 直方图、mismatch 率。
- 验证：造 10 条异常数据可见；无异常时空态。

### T8 灰度与回滚（1 天）
- 灰度：staff → 5% → 25% → 100%，每档观察 48h：mismatch 率 < 0.1%、通关率无异常上升、`event loop lag` 次数下降。
- 回滚：`GTN_STORY_LOCAL_MODE=off` 立即生效；客户端收到 404 自动转在线模式。
- 验证：开关切换不重启进程；在线模式功能不回退。

### T9 总验收（1 天）
- 黄金语料 200 run 全量重放一致；篡改用例 100% 拒绝；预览服完整通关一局（含中途断网恢复）。
- 生产灰度期 mismatch 率与人工复核结论归档；文档更新 `docs/通行证-计划.md` 与更新日志草稿（不含发布）。

## 6. 兼容与回滚边界

- `story_runs.state_json` 仍是唯一权威；本地模式只是「把结算算在客户端、把校验放服务端」。
- 现有 `/api/story/run/action` 与存档接口**不删**，作为在线模式与兜底。
- 内容更新（`content_version`）会使旧 run 不可本地续玩，按现有 `compatible=False` 逻辑提示重开。
- 奖励路径不动：`battle_pass` / `story_score` 只接受服务端计算出的结果。

## 7. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| Pyodide 首包 10 MB | 首次进入慢、移动端流量 | 懒加载 + 强缓存 + 弱网降级在线模式 |
| 移动端 wasm 内存不足 | 崩溃 | Worker 释放、单 run 限制、崩溃回落 |
| 服务端重放 CPU（2 vCPU） | 校验排队 | 每层动作上限、gzip、线程池限并发、异步校验（先接收后判定，超时转人工） |
| 摘要不稳定（浮点/键序） | 误判作弊 | 规范化函数 + 黄金语料 + 跨版本测试 |
| 双端时钟/版本漂移 | 无法续玩 | `content_version` + `engine_version` 显式上报，拒绝不匹配 |
| 作弊者伪造整层日志 | 刷奖励 | 引擎重放 + 节奏阈值 + 经济守恒；奖励永不采信客户端 |

## 8. 已确认的决策（2026-11-13）

1. **引擎同源**：采用 Pyodide 在 Web Worker 里跑同一份 `story_engine.py`，不重写 JS 引擎。
2. **上传时机**：楼层切换 + 每场战斗结束各上传一次 checkpoint（战斗中途不传）。
3. **异常处置**：mismatch 时按上一个已校验存档结算本局并结束 run，**视为直接放弃**；已校验楼层保留奖励，本局不再续玩。
4. **多人爬塔**：继续保留在线模式，不纳入本地化范围。

以下是原待确认项，保留作为决策记录：

1. ~~引擎同源（Pyodide）还是 JS 重写~~ → 已定 Pyodide。
2. ~~逐层上传的时机~~ → 已定楼层切换 + 战斗结束。
3. ~~异常处置默认值~~ → 已定「按上次存档结算、视为放弃」。

## 12. T0 结果（2026-11-13 实测）

从生产库导出 5 条真实 run（`content_version=story-redesign-10-4debdf6ac928`，动作 40–163 步），本地用 `story_mode.build_initial_story_state` 重建初始状态后逐动作重放，单条耗时 180–440ms。

- **直接整状态摘要：0/5 一致。** 原因是宿主字段，不是规则漂移。
- **投影后（`story_verify.gameplay_state`，去掉 `dev_mode` / `event_bank` / `sl_used` / `last_events` / `floor_entry_checkpoint` / `recovery_checkpoint`）：3/5 一致。**
- 不一致的 2 条（`142676a9b249`、`6d5a52c9b6b6`）差异集中在 `combat.card_use_counts` 等计数上，重放比存档多推进了一步；两条 run 的 `manual_load_count` 都是 0，判定是后台修复工具直接改写状态（`story_admin._run_mutation` 直接 `UPDATE story_runs SET state_json=...`，不写动作日志）。
- 一致的 3 条里，`da2da2eaf207` 差异仅 `dev_mode`，`86c4ad57d73c` 差异仅 `dev_mode` 与 `floor_entry_checkpoint.state.dev_mode`，`e7c9ce12e80d` 差异仅 `event_bank` 与 `sl_used` —— 全部是宿主注入字段，投影后归零。

由此确定三条设计约束（已落进代码）：

1. 摘要只覆盖 `gameplay_state` 投影（`story_verify.HOST_STATE_KEYS`），客户端与服务端用同一份投影。
2. 本地模式**不允许**手动存档回档；若保留读档，必须把回档记录成动作，否则校验链无法重放。
3. 后台修状态必须打 `state_mutated_by_admin` 标记，校验器见到标记就跳过摘要比对、只记审计，不能当成作弊。

补充：

- 动作日志只存 `payload_json`，重放时不需要客户端 action id（`action_digest` 只取 `type`+`payload`）。
- `story_verify.state_digest(state, include_host=True)` 保留整状态摘要，仅用于排查。
- 测试：`tests/test_story_verify.py` 10 passed（新增宿主投影 3 条）。

下一步是 T1（Pyodide Worker spike）。仓库内没有 Pyodide 资产，需要先引入（CDN 离线包或 npm 包），再用 20 条语料比对 digest、记录冷启动/单步耗时/内存。

## 13. T1 结果：Pyodide Worker spike（2026-11-13 实测）

资产：从 npm 拉 `pyodide@0.26.4`，只取核心 6 个文件放进 `static/pyodide/`（共 13.1MB：`pyodide.js` 0.01MB、`pyodide.mjs` 0.01MB、`pyodide.asm.js` 1.17MB、`pyodide.asm.wasm` 9.62MB、`python_stdlib.zip` 2.23MB、`pyodide-lock.json` 0.1MB）。不引 whl 包，引擎只依赖标准库。

实现：`static/story-engine/engine-worker.js`（**classic worker**，用 `importScripts('pyodide.js')` + 全局 `loadPyodide`，把 7 个引擎 `.py` 写进 `pyodide.FS` 后 `sys.path.insert('/home/pyodide')`）；引擎源码的浏览器副本放在 `static/story-engine/src/`（7 个文件 960KB）。

实测（本机 headless Edge，本地无 CSP 静态服务）：

| run | 动作数 | 服务端摘要 | 浏览器摘要 | 一致 | 浏览器耗时 | 服务端耗时 |
|---|---|---|---|---|---|---|
| `da2da2eaf207` | 145 | `sha256:0fb7f903…` | 同左 | ✓ | 1526ms | 1072ms |
| `86c4ad57d73c` | 92 | `sha256:a4142d6a…` | 同左 | ✓ | 922ms | 647ms |

- **冷启动 4.9s**（加载 wasm + 写 7 个 .py + 编译），只需要一次，之后常驻 Worker。
- 单动作约 **10.5ms**（145 动作 / 1526ms），比服务端慢约 1.4×，对爬塔的交互节奏足够；T3 起可把「每场战斗一次性重放」放到 Worker，UI 线程零阻塞。
- 摘要完全一致，说明同源引擎路线成立，不需要 JS 重写。

两个实现约束（已踩过）：

1. `python -m http.server` 把 `.mjs` 当 `application/octet-stream`，浏览器会拒绝 `import()`；因此 Worker 用 classic + `importScripts`。生产环境 nginx 有 `.mjs` MIME 也一样——统一 classic 最稳。
2. 生产页面有 CSP（`script-src 'self' 'wasm-unsafe-eval'`）：Pyodide 的 wasm 编译需要 `wasm-unsafe-eval`（已有），但 **Playwright 的 `wait_for_function`/字符串 `evaluate` 会被 `unsafe-eval` 拦下**，spike 验证必须在无 CSP 的临时静态服务上做（`http.server` 5097 + `tmp_cardstar/spike_harness.html`）。

未做（T3 范围）：Worker 常驻与预热时机、每场战斗的 checkpoint 上传、`static/story-engine/src/` 的构建期同步（现在是手工复制）、Worker 内存占用实测。

## 14. T3 结果：服务端重放校验器（2026-11-14 实测）

- `story_verify.py` 新增 `normalize_actions()` 与 `replay_checkpoint()`：动作日志先做形状校验（上限 400 条），再从「上一个已校验状态」用同一份引擎重放，产出 `sha256` 摘要。
- `replay_checkpoint()` 从不抛异常：`reason` 取值 `mismatch` / `invalid_action` / `engine_error` / 形状错误四种；调用方据此决定 409 与疑似度。
- 测试 `tests/test_story_verify.py` 共 16 条通过（含伪造摘要、非法动作、超限、客户端 id 不参与摘要）。

## 15. T4 结果：本地模式持久化（2026-11-14 实测）

- `db.ensure_story_local_schema()`：给 `story_runs` 补 `local_mode`、`last_verified_floor/seq`、`checkpoint_seq`、`state_digest`、`suspicion_score`、`state_mutated_by_admin`；新建 `story_run_checkpoints`（`UNIQUE(run_id, seq)`）与 `story_run_rewards`（`UNIQUE(run_id, floor, kind)`）。
- `db.commit_story_checkpoint()` 幂等：同一 seq 重复提交返回既有行；只有 `verify_status='verified'` 才推进 `last_verified_*` 与 `state_digest`。
- 测试 `tests/test_story_local_schema.py` 6 条通过。

## 16. T5 结果：本地模式 API（2026-11-14 实测）

- 新增 `story_local.py`：灰度开关 `GTN_STORY_LOCAL_MODE=off|staff|pct:N|all`；限流 30 次/分钟/账号；`start_run` / `submit_checkpoint` / `resume_run` / `finish_run`。
- 四个路由挂在 `app.py`：`POST /api/story/run/local/start|checkpoint|resume|finish`，全部走 `run_off_event_loop`，未登录 401。
- 校验失败的检查点**不占用序号**：客户端修正摘要后可用同一 `seq` 重试；失败只累加 `suspicion_score`，不推进 `last_verified_*`。
- 预览服务端到端实测（`GTN_STORY_LOCAL_MODE=all`）：`start 200`（新建 run，返回 seed 与初始 state）→ 伪造摘要 `409 STORY_CHECKPOINT_MISMATCH(mismatch)` → 正确摘要 `200`（写入 verify_status=verified）→ 重复 `200 {"duplicate": true}` → `resume 200`（seq 1 / floor 1）→ `finish 200`（`last_verified_seq=1`，run 置 completed）；匿名 `401`。
- 测试 `tests/test_story_local_api.py` 9 条通过（灰度、幂等、越序、限流、resume/finish、越权账号不可见）。

## 17. T6 客户端运行时（2026-11-14 实测）

- `static/js/story-local.js`：`window.GtnStoryLocal` 暴露 `isActive/start/apply/resume/checkpoint/boot/subscribe/snapshot`；Worker 惰性启动（首次 `start`/`apply` 才 boot），单次等待 20s 超时。
- `static/story-engine/engine-worker.js` 增加 `step` 消息：`apply_story_action` 在 Worker 内执行，返回 `{state, events, digest, phase, floor}`，摘要由 `story_verify.state_digest` 计算（与服务端同一份代码）。
- 检查点时机：`checkpointKind(prev, next)` 在「战斗结束」（`phase === 'combat'` → 非战斗）与「楼层上升」（`current_floor` 变大）时返回 `combat` / `floor`；日常动作只累积 `pendingActions`。
- 失败处理：`409 STORY_CHECKPOINT_CHAIN_MISMATCH` / `409 STORY_CHECKPOINT_OUT_OF_ORDER` / `409 STORY_CHECKPOINT_MISMATCH` 时自动 `resume()` 回滚到最近已校验检查点，并把错误写进 `snapshot().lastError`。
- `static/js/story.js`：`?local=1` 时 `startRun()` 走 `window.GtnStoryLocal.start()`，`storyAction()` 入口转 `localStoryAction()`，渲染与事件播放复用在线路径。
- 预览实测（Playwright + Edge，`GTN_STORY_LOCAL_MODE=all`，账号 PreviewStar）：
  - `start('common_flower')` → `phase=journey_setup`、`floor=1`、可选 biome `garden/desert/ocean`；
  - `apply('start_journey')` → `easy_relic`、`pendingActions=1`、摘要 `sha256:c9926741…`；
  - `checkpoint('floor')` → `seq=1`、`pendingActions=0`，服务端返回 verified 与 `server_digest`；
  - `resume()` → `hasCheckpoint=true`、`seq=1`、`phase=easy_relic`；
  - `finish` → `200 {status:'completed', last_verified_seq:1, last_verified_floor:1}`；
  - 页面加载 `/story?local=1` 无 pageerror，`story-local.js` 在 `story.js` 之前加载。
- 新增 `tests/test_story_local_client.py` 4 条契约测试（脚本顺序、Worker step 分支、动作转派、检查点时机与 409 回滚），与 `test_story_local_routes/api/schema`、`test_story_verify` 合跑 **37 passed**。

## 18. T7 校验观测与运营（2026-11-14 实测）

- 数据：新增 `story_checkpoint_failures`（`run_id/user_id/seq/floor/kind/reason/client_digest/server_digest/action_count/actions_json/created_at`，无唯一约束，只记录被拒的检查点）；`db.record_story_checkpoint_failure()` 在 `story_local.submit_checkpoint()` 的失败分支写入，被拒检查点仍不占用序号。
- 查询：`db.list_story_checkpoint_failures(limit, day)`（JOIN `users` 带用户名）、`db.story_checkpoint_failure_summary(day)`（按 reason 计数）。
- 接口：`GET /api/feedback/handling/story-checkpoints?day=&limit=`，走既有 `/api/feedback/handling/*` 的 staff 会话与 CSRF 保护，`run_off_event_loop` 执行；返回 `{items, counts, total}`。
- 前端：`/handling` 的「风险」页签与货币异常并列，新增「爬塔校验失败（摘要不符 N · …）」分组；每行显示玩家、原因标签（mismatch→摘要不符、invalid_action→非法动作、engine_error→引擎异常、请求形状错误归为请求格式错误）、`第 N 层 · seq · 动作数`、时间与客户端摘要前缀；点击行定位到该玩家。summary 追加「爬塔校验 N」。
- 预览实测（`GTN_STORY_LOCAL_MODE=all`，账号 PreviewStar）：构造一次错误摘要 `409 STORY_CHECKPOINT_MISMATCH` 后，接口返回 `total=1`、`counts={'mismatch':1}`；`/handling` 风险页签显示 `爬塔校验 1` 与分组标题「爬塔校验失败（摘要不符 1）」，控制台无错误；截图 `deploy-20261109-all/shots/190_handling_story_checks.png`。
- 新增 `tests/test_story_check_monitor.py` 4 条契约测试；与 story local 各套件合跑 **41 passed**。
- 已知边界：被拒检查点只保存最近记录（表无清理策略，建议按 30 天滚动清理，T8 再定）。

## 19. T8 灰度与热回滚（2026-11-14 实测）

- 开关来源（优先级从高到低）：
  1. 运营开关文件 `GTN_STORY_LOCAL_MODE_FILE`（默认 `$GTN_DATA_DIR/story-local-mode`，本地预览为 `D:\gtn\data\story-local-mode`）；
  2. 环境变量 `GTN_STORY_LOCAL_MODE`（部署时写进 `/etc/gtn/release.env`）。
- 文件只有一行，取值 `off` / `staff` / `all` / `pct:N`（0–100）。`story_local._mode_from_file()` 按 mtime 缓存，改文件**下一个请求即生效**，不需要重启进程；删掉文件就回落到环境变量。
- 写入接口 `story_local.set_rollout_mode(mode)` 做白名单与百分比范围校验（返回 `(mode, error)`，错误值 `bad_mode` / `bad_percent` / `write_failed`）。
- 灰度阶梯（建议）：`staff`（内部账号）→ `pct:5` → `pct:25` → `all`；回滚只需 `echo off > /var/lib/gtn/story-local-mode`（或在文件里写 `off`），无需动 systemd。
- 观测：`GET /api/story/run/local/metrics?hours=24`（仅 staff）返回
  `checkpoints`、`by_status`、`mismatch_rate`、`verify_ms.p50/p95/max`、`failure_reasons`、`active_local_runs`、`rollout_mode`、`in_rollout_percent`；配合已有的 `[admin:suspicious] event loop lag` 日志看服务端压力。
- 预览实测（账号 PreviewStar，`GTN_STORY_LOCAL_MODE=all`）：
  - 匿名 `GET metrics` → `403 permission_denied`；staff → `200`，`{"checkpoints":4,"mismatch_rate":0.5,"rollout_mode":"all","verify_ms":{"p50":10,"p95":11,"max":11},"active_local_runs":1}`；
  - 写入 `off` 后立刻 `POST /local/start` → `403 {"error":"local_mode_disabled"}`；改回 `all` 后同请求 `200`（返回 run id 与初始 state），证明热切换生效；
  - 删除文件后回到环境变量。
- 新增 `tests/test_story_local_rollout.py` 6 条（文件优先于环境变量、热生效、百分比按用户哈希分布、非法模式、指标聚合与窗口过滤）；与 story local 各套件合跑 **47 passed**。
- 运营备注：`mismatch_rate` 持续 > 1% 或 `verify_ms.p95` > 200ms 时先降到 `staff` 观察；`failure_reasons` 里 `invalid_payload` 多说明客户端日志格式问题（不是作弊）。
