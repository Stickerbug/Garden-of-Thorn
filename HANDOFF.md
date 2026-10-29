# Garden of Thorn（GTN）项目转接文档

> 更新时间：2026-10-29（中国标准时间）
> 
> 这份文档供下一位 AI 接续开发使用。当前会话已暂停继续开发；请先阅读本文件，再决定是否执行后续工作。

## 一、必须遵守的用户约束

- 用户使用中文沟通。
- **未经用户明确说“上传并部署”，不得上传、推送或重启线上服务。**
- 用户说“撤回”时，默认只撤回最近一次本地改动；不要擅自重置整个工作区。
- 用户说“不要直接显示”时，优先改为按钮、弹窗或按需展开。
- 完成普通修改后先停在本地提交，等待用户验收。
- 线上部署后必须检查健康接口，并恢复 healthcheck 定时器。
- 不要清理工作区中已有的 `.zcode/`、`HANDOFF.md`、`deploy-*`、`tmp_*` 等历史辅助文件，除非用户明确要求。

## 二、项目与环境

- 项目目录：`D:\gtn`
- 技术栈：Python 3.13、Flask、Flask-SocketIO、eventlet、SQLite、原生 JavaScript。
- 本地虚拟环境：`D:\gtn\.venv`
- 本地数据库默认：`D:/var/lib/gtn/gtn.sqlite3`
- 本地服务端口：`127.0.0.1:5000`
- 常用本地启动：

```powershell
Set-Location D:\gtn
$env:GTN_DB_PATH = 'D:/var/lib/gtn/gtn.sqlite3'
$env:SECRET_KEY = 'dev-fixed-secret-2026'
$env:GTN_SESSION_COOKIE_SECURE = '0'
.venv\Scripts\python.exe app.py
```

- 常用健康检查：

```powershell
curl.exe -sS http://127.0.0.1:5000/api/healthz
curl.exe -sS http://127.0.0.1:5000/api/version
```

- 定向测试：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ocean_sapphire_playability.py -q
.venv\Scripts\python.exe -m pytest tests/test_ocean_sapphire_playability.py tests/test_client_shortcut_rules.py -q
node --check static/js/game.js
python -m py_compile game_engine.py game_engine_2v2.py
```

## 三、当前 Git 状态

- 本地分支：`main`
- 本地最新提交：`06e9634 fix(ocean): refresh sapphire playability assets`
- 该提交包含：
  - `static_version.txt` 追加 `-sapphire-playability-2`，强制浏览器重新获取当前 `game.js`。
  - `tests/test_ocean_sapphire_playability.py` 增加“基本 + 尖牙”真实牌回归测试。
- 最近相关提交：
  - `73cd4e6 fix(community-ops): show voter nicknames on demand`
  - `f31fcb6 fix(community-ops): hide voter ids behind action`
  - `2ea83a3 feat(community-ops): show poll voter ids`
  - `1c8a97f fix(reality): preserve bingbang draft copies`
  - `026eb9e fix(reality): clamp cognitive bias at final recovery`
  - `dd7de24 fix(reality): honor adjusted draft totals`
  - `0ee2d8b fix(reality): copy third played card for juggle`
  - `95029ae fix(fancy): keep event setup processing`
  - `befde88 feat(lobby): show entertainment special modes`
- 当前还有一个**预先存在的未提交 tracked 修改**：`app.py` 中的 `GTN_STATIC_VERSION += '-community-poll-voter-toggle-1'`。不要在不核对内容的情况下丢弃或覆盖它。
- 工作区有多项历史未跟踪文件和部署临时文件；不要用 `git clean -fd`。

## 四、线上状态

- SSH：`root@gtn.stickerbug.top`
- 线上代码目录：`/opt/gtn-release`
- 线上服务：`gtn-release.service`
- 健康检查定时器：`gtn-release-healthcheck.timer`
- 最近线上提交：`9639d97 deploy-community-nickname`
- 最近确认状态：`gtn-release.service` active，`gtn-release-healthcheck.timer` active。
- 线上仓库存在一个历史未跟踪备份：`CHANGELOG.txt.bak-20260929`，不要删除。
- 线上当前已经包含社区运营投票“按按钮查看投票人昵称”的代码；本轮蓝宝石静态版本修复**尚未上传线上**。

### 线上部署规则

只有用户明确要求上传部署时才执行。执行时遵循：

1. 先停止 `gtn-release-healthcheck.timer`。
2. 只生成并应用必要文件的 UTF-8 无 BOM 补丁或 bundle；不要覆盖线上数据库。
3. 远端 `git apply --check` 通过后再应用、提交。
4. 重启 `gtn-release.service`，等待端口恢复。
5. 检查 `curl -sS -m 10 http://127.0.0.1:5000/api/healthz`、服务状态和远端提交。
6. 恢复 `gtn-release-healthcheck.timer` 并确认 active。

## 五、当前蓝宝石问题与结论

用户报告：手牌中已知有“基本”和“尖牙”，但“蓝宝石”仍然打不出去。

代码检查结论：

- `ocean:sapphire` 的设计条件是：从**当前手牌**选择一张可选的攻击牌；该牌必须是 `thorn`，不能带 `unique` 或 `exile`，也不能是蓝宝石本身或 `sublime` 牌。
- “牌组/牌堆里有基本和尖牙”不等于当前手牌满足条件；如果两张牌只在 deck 中，蓝宝石按设计不能使用。
- 服务端 `GameEngine` 和 `GameEngine2v2` 对真实 `Basic`、`Fang` 的回归测试均通过，当前条件下会识别两张牌。
- 之前已经有服务端权威判断和客户端预检移除修复（提交 `d96d48b`）。但该修复没有同步更新静态资源版本，浏览器可能继续缓存旧的客户端预检脚本，表现为合法蓝宝石被灰掉或无法点击。
- 本地提交 `06e9634` 只更新静态版本并补测试，目的是让客户端重新加载已经存在的 Sapphire 修复；它**没有上传线上**。

本轮验证结果：

- `tests/test_ocean_sapphire_playability.py`：11 passed，10 subtests。
- 与 `tests/test_client_shortcut_rules.py` 合并：20 passed，10 subtests。
- `node --check static/js/game.js`：通过。
- `python -m py_compile game_engine.py game_engine_2v2.py`：通过。
- 本地 `/api/healthz`：正常。
- 本地 `/api/version` 已包含 `sapphire-playability-2`。

下一位 AI 接续时的优先顺序：

1. 不要先修改游戏规则；先确认用户说的“有基本和尖牙”是**当前手牌**还是 deck。
2. 如果是当前手牌，且用户允许上传，再只部署 `static_version.txt` 的版本刷新补丁（服务器已有 `d96d48b` 客户端逻辑）。
3. 部署后让用户强制刷新页面或重新进入对局，再验证蓝宝石卡面是否可点、目标选择和攻击牌选择是否出现。
4. 只有在缓存刷新后仍失败，才继续抓取实际对局的手牌 payload、`def_id`、`instance_flags`、`disabled_flags` 和服务端拒绝原因；不要凭空放宽“手牌”规则。

## 六、已完成的重要功能背景

- 花样百出模式：恢复配装处理流程；事件 2、3、5、8、11 的配装提交/调度路径已有测试和修复。
- 操纵现实模式：
  - 事件 10 的回合回复降低值最终最低为 0。
  - 事件 12 选卡复制和放逐语义保留。
  - 事件 16 杂耍改为每回合第三张牌复制该牌的虚无/放逐版本加入手牌。
  - 事件 19 采用所有类型选择数总和，开局 10F、装备选择量 +7、其余选择量 0，并加入 5 张 sewage。
- 大厅娱乐模式会显示玩家选择的特殊模式。
- 社区运营投票：公共页面不显示投票人；运营页通过按钮按需显示玩家游戏昵称，不显示账号 ID。
- Afdian 充值未发放记录、蓝宝石/魔法珍珠等历史问题均有旧提交和部署记录，修改前先查 `git log` 与测试，不要重复实现。

## 七、接续工作建议

先运行：

```powershell
Set-Location D:\gtn
git status --short
git log --oneline -12
.venv\Scripts\python.exe -m pytest tests/test_ocean_sapphire_playability.py tests/test_client_shortcut_rules.py -q
```

如果用户没有明确说“上传并部署”，只做本地修改、测试和提交；最终报告本地提交号、测试结果，以及没有上传线上。