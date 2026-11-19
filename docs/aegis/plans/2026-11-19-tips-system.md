# Tips 系统（主界面 / 大厅 / 选牌 / 配装 左下角小贴士）计划

- 日期：2026-11-19
- 状态：**已实现并本地验证**（未提交、未部署）
- 触发背景：需要在不打断操作的前提下，把散落在策划表里的玩法小贴士展示给玩家；四个界面左下角统一一个「Tips:」位置，内容从可编辑文件读取，等概率抽取且 50 次内不重复。

## 0. 实现结果（2026-11-19，与计划稿的差异）

已按本计划落地，实测通过的最终形态如下（下文 §1–§11 是当时的计划稿，保留作决策记录；两者冲突处以本节为准）：

| 项 | 最终实现 |
|---|---|
| 数据 | `static/data/tips.json`，126 条、8 位作者；每条 `{id, author, text:{zh}}`；`MAX_TEXT_LEN` 由 120 放宽到 **160**（wiki 那条本身就很长），CSS `-webkit-line-clamp: 3` 兜底 |
| 导入 | 源头是 `docs/tips/tips-source.tsv`（作者 + 正文两列，从策划表人工导出）；`scripts/tips_from_csv.py` 生成 JSON，`--check` 只校验 |
| 语言 | 实际只有中文文案，`zh` 之外的三种语言统一回落 `zh`；`onLang` 只重渲染不重抽 |
| 富文本 | **不自写解析器**：复用 `game.js:4845` 的 `colorizeCardText(seg, {terms:false})` 渲染 `[[card:]]`/`[[icon:]]`，再调 `game.js:4740` 的 `bindInlineCardChips(el, {interactive:true})` 绑卡牌 chip 悬停预览 |
| 卡表时序 | `CARD_DEFS` 是异步填充的（`game.js:12492`/`12507`），所以在 `refreshCardDataViews()`（`game.js:12483`）末尾加第三个钩子 `onCardsReady()`，卡表就绪后重渲染当前 tip，否则中文卡名解析不成 chip |
| 作者 | 桌面 `mouseenter` 显示、`mouseleave` 隐藏；移动端 `touchstart` 长按 400ms 显示、1.8s 后自动隐藏，`touchend/touchcancel/touchmove` 取消 |
| 裸链接 | `tips.json` 里那条 wiki 链接：先切出 URL 再 `decodeURI` 显示（中文路径短得多），> 64 字符退化成 `host/…`；`href` 保留原始编码 |
| 标签 | 统一 `Tips:`（半角冒号，与需求原文一致）；去掉了 `text-transform: uppercase`，避免显示成 `TIPS:` |
| 缓存破坏 | 容器带 `data-version="{{ static_version }}"`，`tips.js` 从容器上取，fetch 成 `/static/data/tips.json?v=<version>`（`document.documentElement` 上没有这个属性） |
| 登录页避让 | 桌面 `bottom: 84px`；移动端断点（≤720px）**88px**——64px 时实测与 `.home-footer` 重叠 12px |
| 测试 | `tests/test_tips.py` 13 个用例全绿（含 500 次内连续 50 次不重复、20000 次频次 ±40% 两条算法性质测试） |
| 浏览器验证 | Playwright（系统 Edge，`channel="msedge"`）实跑：四个视图都显示、`view-card-gallery` 正确隐藏、卡牌 chip 与悬停预览、作者气泡、长按/短按、链接解码、`?v=` 生效、桌面与移动端与 `.home-footer` 均不相交 |

## 1. 目标与非目标

**目标**

1. 在 `view-login`（主界面）、`view-lobby`（对战大厅）、`view-draft`（选牌）、`view-event-select`（配装）四个界面的**左下角**显示一条 `Tips: <内容>`。
2. 内容来源是一个**纯文本可编辑文件**（JSON），改文件即可换内容，不需要动 JS。
3. 抽取**等概率**（在「当前可选池」内均匀），且**任意连续 50 次抽取内不出现重复**。
4. 刷新页面不重置抽取历史（localStorage 持久化），避免「刷一下又看到同一条」。
5. 支持 `zh / en / fr / ja` 四语言（缺失则回落中文），切换语言时当场重渲染而不是重新抽。
6. 非阻塞：不遮挡任何可点击元素，不参与布局（`position: fixed` + `pointer-events: none`）。

**非目标（本期不做）**

- 不做后台「Tips 管理页」；编辑仍走文件 + 部署（P2 可选热改，见 §7）。
- 不做按场景/按 tags 定向投放（本期全池等概率；`tags` 字段先预留不参与筛选）。
- 不做点击展开、翻页、收藏、分享。
- 不改动战斗内（`view-game`）——战斗界面信息密度已满，本期不显示。

## 2. 现状基线（已核实）

| 项 | 事实 |
|---|---|
| 视图容器 | `templates/index.html`：`view-login` 529 行、`view-solo` 684 行、`view-lobby` 764 行、`view-draft` 823 行、`view-event-select` 835 行、`view-game` 887 行 |
| 视图切换 | `static/js/game.js:8097` `function showView(viewId)`，切视图时给 `.view` 加 `hidden`；`activeViewId` 是脚本内局部绑定（不在 `window` 上） |
| 语言 | `static/js/game.js:2668` `const SUPPORTED_LANGS = new Set(['zh','en','fr','ja'])`；`currentLang`（`game.js:2672`，取自 localStorage `gtn_lang`）；切换入口 `function applyLang(lang)`（`game.js:7115`） |
| 资源版本 | 模板里所有静态资源都带 `?v={{ static_version }}`（`index.html:10-17`）；`game.js` 在 `index.html:1551` 引入，`</body>` 在 1557 行 |
| 静态数据约定 | 已有 `static/data/*.json`（`moderation_rules.json` 等），前端按需 fetch，无构建步骤 |
| 左下角占用 | `static/css/style.css:4519` `.home-footer { position: fixed; left: 24px; right: 24px; bottom: 40px; }` —— 登录页左下角有版权/ICP，Tips 必须抬高到 `bottom: 84px` 才不压字 |
| 环境变量约定 | `app.py` 统一用 `os.environ.get('GTN_*')`（如 `GTN_CHANGELOG_PATH`），P2 热改沿用此风格 |
| 测试 | `tests/test_*.py` 共 323 个，以「源码断言 + 真实函数调用」为主；浏览器侧有 `tests/local_solo_browser_check.py`、Playwright 用例 |

## 3. 数据文件

### 3.1 位置

`static/data/tips.json`（运行时唯一数据源，随包发布；`?v={{ static_version }}` 保证部署后不吃旧缓存）。

选它而不是塞进 `game.js` 的理由：可编辑、可 diff、可校验、可热改（P2 换成服务端文件只需改 fetch 地址）。

### 3.2 格式

```json
{
  "schema": 1,
  "version": "2026-11-19.1",
  "updated_at": "2026-11-19",
  "tips": [
    {
      "id": "t0001",
      "text": {
        "zh": "腐化值每回合会缓慢回落，别急着一次把牌打完。",
        "en": "Corruption decays each turn — don't dump your whole hand at once.",
        "fr": "…",
        "ja": "…"
      },
      "tags": ["battle"]
    }
  ]
}
```

规则（由校验脚本强制）：

- `id` 必填且全文件唯一，建议 `t` + 4 位序号；**手工编辑时不要复用/改动已发布的 id**（id 是抽取历史的主键，改了等于让老玩家重新见到旧条目）。
- `text` 允许两种写法：对象（多语言）或字符串（等价于只有 `zh`）。加载时统一归一化成对象。
- 单条 `zh` 长度 8–120 字符（超长在左下角会撑成三行以上，破坏观感）；禁止换行、禁止 HTML 标签。
- 同一语言内文本去重（完全相同的两条视为错误）。
- `version` 每次改内容必须 bump（用于让客户端知道「池子变了」，见 §4.3）。
- 建议规模 30–80 条；< 50 条时「50 次内不重复」自动退化为「N 次内不重复」（见 §4.1 说明）。

### 3.3 初始内容从哪来

策划表：`https://docs.qq.com/sheet/DSkxFbWhOTk9tcURE?...&tab=4jy4bt` 的 **「Tips列表」** 标签页。

**已核实：该页面是纯 JS 应用，`web_fetch` 只能拿到标签名列表和「加载中，请稍候。」，拿不到单元格内容。** 因此初始导入必须由人工导出一份 CSV/TSV，放到 `docs/tips/tips-source.csv`，再由脚本转换：

```
id,zh,en,fr,ja
,腐化值每回合会缓慢回落……,,
```

`scripts/tips_from_csv.py` 负责：读 CSV → 去空行/去重 → 分配 id → 归一化成 §3.2 的 JSON → 校验（长度/唯一/字符）→ 写 `static/data/tips.json`。
CSV 只是导入用的中间物，**运行时不读 CSV**；之后日常编辑直接改 JSON。

## 4. 抽取算法

### 4.1 语义

「等概率」= 在**当前可选池**里均匀抽一条；「50 次内不重复」= 最近 50 次出现过的 id 不再进入可选池。

不用「洗牌袋 + 每 50 次重洗」的做法：袋边界上（第 50 次与第 51 次）会撞同一 id，严格意义上违反「50 次内不重复」。直接用**最近队列过滤**，语义精确、代码更短。

```
recent = 最近抽取的 id 列表（按时间倒序，容量上限 min(50, N-1)）
candidates = 全部 id - recent
抽 = candidates 中等概率随机取一个
```

- 容量取 `min(50, N-1)` 而不是固定 50：当 N ≤ 50 时保证「N 次内不重复」（数学上能做到的最强），且候选池永不为空。
- N ≥ 51 时严格保证任意连续 50 次无重复。
- 复杂度 O(N)，N ≤ 几百，可忽略。

### 4.2 状态持久化

localStorage key `gtn_tips_state_v1`：

```json
{ "v": 1, "file": "2026-11-19.1", "recent": ["t0007", "t0031", "…"], "lastShownAt": 1763550000000 }
```

- 页面加载时读回 `recent`；`file` 与当前 JSON 的 `version` 不一致时**保留 recent**（内容版本变了不代表玩家看过的不算数），只丢弃已不存在的 id。
- 写失败（隐私模式 / 配额满）时降级为内存态：本次会话仍满足 50 次不重复，刷新后重置。
- 不写服务端：纯展示内容，跨设备同步没有价值，也不该为此增加请求和隐私面。

### 4.3 何时抽

- `onView(viewId)` 进入四个目标视图之一时抽一次。
- 节流：距上次抽取 < **30 秒**则复用当前这条（避免在选牌/配装之间来回切时把池子瞬间耗掉）。常量 `MIN_INTERVAL_MS = 30000`。
- 同一视图内不自动轮播（会分散注意力，也会让 50 次规则失去意义）。
- 语言切换走 `onLang(lang)`：用当前 tip 的多语言字段重渲染；该语言缺失则回落 `zh`；**不重新抽**。

## 5. UI 规格

### 5.1 结构（放在 `templates/index.html` 的 `</body>` 前、`game.js` 之前）

```html
<link rel="stylesheet" href="/static/css/tips.css?v={{ static_version|default('dev')|urlencode }}">

<div id="gtn-tips" class="gtn-tips hidden" role="note" aria-live="polite">
  <span class="gtn-tips-label" id="gtn-tips-label">Tips</span>
  <span class="gtn-tips-text" id="gtn-tips-text"></span>
</div>

<script src="/static/js/tips.js?v={{ static_version|default('dev')|urlencode }}"></script>
```

`tips.js` 放在 `game.js` 之前，保证 `game.js` 初始化时调用 `showView('view-login')` 已经能命中钩子；同时 `tips.js` 自己在 `DOMContentLoaded` 时读一次 `.view:not(.hidden)` 的 id 兜底（防脚本顺序变化）。

### 5.2 样式要点

| 项 | 值 |
|---|---|
| 定位 | `position: fixed; left: 24px; bottom: 24px; z-index: 60;` |
| 登录页避让 | `.gtn-tips[data-view="view-login"] { bottom: 84px; }`（`.home-footer` 在 `bottom: 40px`，高约 24px） |
| 尺寸 | `max-width: min(520px, 46vw)`；`padding: 10px 14px`；`border-radius: 10px` |
| 配色 | 底 `rgba(12,14,20,.72)` + `backdrop-filter: blur(6px)`；描边 `rgba(214,178,92,.28)`；正文 `#e8e2d2` |
| 排版 | 正文 13px / 行高 1.6；`Tips` 标签 11px、字重 600、`letter-spacing: .08em`、金色 `#d6b25c`、后面跟一个全角/半角冒号（zh 用「：」，其他语言用 `: `） |
| 交互 | `pointer-events: none`（绝不挡点击）；出现 `opacity 0→1 200ms`；`prefers-reduced-motion` 下取消过渡 |
| 移动端 | `@media (max-width: 720px)`：`left/right: 12px; bottom: 12px; max-width: none; font-size: 12px;`，登录页 `bottom: 64px` |
| 隐藏 | 非目标视图加 `.hidden`（`display: none`），不做淡出残留 |

### 5.3 可访问性

- `role="note"` + `aria-live="polite"`：读屏会在切换后念出，但不打断当前朗读。
- 文字对比度：`#e8e2d2` on `rgba(12,14,20,.72)` 约 12:1，达标。
- 不用 `aria-hidden`，也不做成 `tabindex` 可聚焦元素（纯展示，不给键盘用户制造空焦点）。

## 6. 代码改动清单

| 文件 | 改动 |
|---|---|
| `static/data/tips.json` | 新增：数据文件 |
| `static/js/tips.js` | 新增：约 150 行，IIFE 暴露 `window.GtnTips = { onView, onLang }`；负责 fetch、归一化、抽取、渲染、持久化 |
| `static/css/tips.css` | 新增：约 60 行 |
| `templates/index.html` | 3 处：css link、容器 div、script 标签 |
| `static/js/game.js` | 2 行钩子：`showView()` 末尾 `if (window.GtnTips) window.GtnTips.onView(viewId);`；`applyLang()` 内 `if (window.GtnTips) window.GtnTips.onLang(lang);` |
| `scripts/tips_from_csv.py` | 新增：CSV → JSON + 校验（也可单独跑校验：`python scripts/tips_from_csv.py --check`） |
| `docs/tips/tips-source.csv` | 新增：从策划表导出的原始 CSV（留档，便于以后整表重导） |
| `static_version.txt` | 追加 `-tips-system-1` |
| `tests/test_tips.py` | 新增：数据与集成断言（见 §8） |

`tips.js` 结构（关键函数签名）：

```js
(function () {
  const VIEWS = new Set(['view-login', 'view-lobby', 'view-draft', 'view-event-select']);
  const STATE_KEY = 'gtn_tips_state_v1';
  const MIN_INTERVAL_MS = 30000;
  let tips = [];        // [{id, text:{zh,en,fr,ja}}]
  let byId = new Map();
  let current = null;
  let lastView = null;
  let pendingView = null;

  function normalize(raw) { /* 字符串 → {zh}; 过滤空文本; 补 id */ }
  function load() { /* fetch('/static/data/tips.json?v=…') → normalize → 渲染 pendingView */ }
  function pick() { /* §4.1 最近队列过滤 + 均匀随机 */ }
  function render(tip) { /* 按 currentLang 取文本，缺失回落 zh；写 DOM；去掉 hidden */ }
  function onView(viewId) { /* 目标视图才处理；节流；抽 + 渲染 */ }
  function onLang(lang) { /* 只重渲染 */ }
  window.GtnTips = { onView, onLang };
})();
```

`currentLang` 在 `game.js` 里是脚本内绑定，`tips.js` 拿不到 —— 用 `document.documentElement.lang`（`applyLang` 里已设置，`game.js:7119`）作为语言来源，零耦合。

## 7. 分阶段实施

**P0 数据落地（0.5 天，阻塞项）**

1. 你从策划表「Tips列表」导出 CSV（或直接把文本贴给我），放到 `docs/tips/tips-source.csv`。
2. 写 `scripts/tips_from_csv.py`，生成 `static/data/tips.json`。
3. 人工过一遍文案：长度、标点、是否泄露未上线机制。

**P1 前端核心（0.5 天）**

1. `tips.css` + 容器 + 脚本引入。
2. `tips.js`：fetch / 归一化 / 抽取 / 渲染 / 持久化。
3. `game.js` 两行钩子。
4. 本地起服务，人工走四个界面 + 语言切换 + 刷新。

**P2 可选：免部署热改（0.5 天，视需要）**

新增 `GET /api/tips`：若 `os.environ.get('GTN_TIPS_PATH')` 指向的文件存在且 mtime 比包内文件新，返回该文件内容（带 `Cache-Control: no-cache`），否则返回包内 JSON。`tips.js` 优先 fetch `/api/tips`，失败回落静态文件。这样运维改 `/etc/gtn/tips.json` 后玩家刷新即生效，不必走 10 分钟发布流程。
代价：多一个接口、多一条缓存路径、多一处「文件不合法时静默回落」的排查面 —— 所以列为可选，默认不做。

**P3 打磨（0.5 天）**

- 移动端横屏实测（游戏有 aspect-ratio lock，需确认不压 HUD）。
- 空池/加载失败时静默隐藏（不显示「Tips: undefined」）。
- 与 `#gtn-tips` 可能重叠的既有元素复查：登录页 `.home-footer`、大厅左下角聊天/战绩面板、选牌页卡池底部。

## 8. 测试

`tests/test_tips.py`（Python 侧，符合现有风格）：

1. `static/data/tips.json` 可解析；`schema == 1`；`tips` 非空。
2. 每条 `id` 唯一、非空；`text.zh` 非空；长度 8–120；无换行/HTML。
3. 同语言内无重复文本。
4. `static/js/tips.js` 含 `MIN_INTERVAL_MS`、`gtn_tips_state_v1`、四个视图 id；`game.js` 含 `GtnTips.onView` 与 `GtnTips.onLang` 两处钩子。
5. `templates/index.html` 含 `id="gtn-tips"`、`tips.css`、`tips.js` 三处引用。
6. `static_version.txt` 含 `tips-system-1`。
7. 算法性质测试（用 Python 复刻 §4.1 逻辑，纯函数）：池 60 条跑 500 次，断言任意连续 50 次无重复、且每个 id 出现频次落在期望的 ±30% 内。

浏览器侧（Playwright，可选但建议）：

8. 登录页可见 `#gtn-tips`，且其矩形与 `.home-footer` 矩形不相交。
9. 连续进大厅 → 选牌 → 配装，三条文案互不相同（节流 30s 内会复用，测试时用 `?tips_debug=1` 关闭节流）。
10. 切到 `en` 后文案变成英文（或回落中文），且不触发新抽取（对比 `gtn_tips_state_v1` 的 `recent` 长度不变）。

## 9. 上线与回滚

- 走常规发布：`git archive` 打包 → `scp -O` → `bash /tmp/gtn_update.sh <tgz> <sha>`（含 300 秒公告窗口）。
- 回滚：纯前端新增 + 两行钩子，回滚即 `git revert` 后重新发布；无数据库变更、无协议变更。
- 灰度：无需。功能失败时最坏表现是「不显示 Tips」，不影响登录与对局 —— 但必须保证 `tips.js` 里所有 DOM 操作都在 `try/catch` 内，且 `GtnTips.onView` 调用点用 `if (window.GtnTips)` 守卫，绝不能让一个展示模块把 `showView` 打挂。

## 10. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| `tips.js` 抛错拖垮 `showView` | 整个游戏切视图失败（最严重） | 钩子用 `try { GtnTips.onView(id) } catch (e) {}` 包裹；模块内部全 `try/catch`；`load()` 失败静默隐藏 |
| 登录页左下角与 `.home-footer` 重叠 | 版权/ICP 被压字 | `[data-view="view-login"]` 抬到 `bottom: 84px`；测试 8 断言矩形不相交 |
| 移动端横屏遮挡卡牌/按钮 | 影响操作 | `pointer-events: none` + 720px 断点收窄；P3 实测 |
| 文案过长撑成多行 | 观感差、遮挡加重 | 校验脚本卡 120 字符；CSS `max-width` + `line-clamp: 3` 兜底 |
| 玩家清 localStorage | 50 次规则重置 | 可接受：纯展示，无公平性影响 |
| 内容泄露未上线机制 | 剧透 | P0 人工过文案 |

## 11. 待确认

1. **文案来源**：需要你导出「Tips列表」为 CSV（或直接贴文本）。表里现在大概多少条？是否有英文/日文版本，还是先只做中文、其余语言回落中文？
2. **编辑方式**：改 JSON + 重新部署（P1）够用，还是需要「服务器上改文件、玩家刷新即生效」（P2）？
3. **展示范围**：`view-solo`（单人模式准备页，里面也有「我方/对方配装倾向」）要不要也算一处？本期默认**不加**。
