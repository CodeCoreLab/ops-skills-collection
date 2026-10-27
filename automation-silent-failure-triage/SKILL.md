---
name: automation-silent-failure-triage
display_name: "自动化未按计划运行的分诊与修复"
display_name_en: "Automation Silent Failure Triage"
description: "自动化任务「心跳告警 / 未按计划推送 / 该出结果却没出」的分诊与修复。区别于 `automation-health-validator`（主动巡检健康度），本 skill 面向**告警已经响了**的被动处置： 从 dead-man's-switch 心跳告警反查引擎执行记录 → 判定是「没触发」还是「触发了但失败」→ 定位失败子步骤 → 根因实测 → 最小修复 → 补跑闭环。 典型触发：巡逻报告未按计划推送、watchdog 心跳告警、cron/引擎任务没跑、报表缺失、 「最近成功推送 N 小时前」。核心方法：**先判触发再判成败**（查引擎 executions 表，不猜）。 也覆盖 LLM 候选链降级导致的「单端点重试吃满子进程超时预算」这类隐性放大器故障。"
description_zh: "自动化任务心跳告警、未按计划推送、该出结果却没出时的分诊与修复：先判触发再判成败，定位失败子步骤并补跑闭环。"
description_en: "Triage and repair automation tasks that raise heartbeat alerts, miss scheduled pushes or silently produce no output: check whether it triggered before checking whether it succeeded, then isolate the failing sub-step and close the loop with a re-run."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
---

# automation-silent-failure-triage — 自动化未按计划运行的分诊与修复

## 何时用

- dead-man's-switch / 心跳看门狗发出「未按计划推送 / 已超时 N 分钟」告警
- 用户说「报表没出来」「报告没推」「cron 没跑」「自动化断了」
- 某定时任务的产物缺失，但不确定是没触发还是执行失败

## 与相邻 skill 的分工

| skill | 场景 |
|-------|------|
| `automation-health-validator` | **主动**巡检自动化健康度（没告警时也跑） |
| **本 skill** | **被动**处置：告警已响，反查根因并修复 |
| `script-status-exit` | 给脚本补 STATUS= 自证信号（本 skill 的上游基建） |

## 本地 WorkBuddy 自动化（本机场景，先看这张表）

用户说「没看到 XX 推送通知」时，**先查本机 `<userhome>/.workbuddy/workbuddy.db`**，别急着上服务器。

```python
# 1) 今日所有运行（时间戳为毫秒）
SELECT r.created_at, r.status, r.result_success, r.failure_code, a.name
FROM automation_runs r LEFT JOIN automations a ON a.id=r.automation_id
WHERE r.created_at >= <今日0点毫秒时间戳> ORDER BY r.created_at;
```

**🔴 头号陷阱：`status` 列恒为 `ACCEPTED`，失败也是 `ACCEPTED`。**
判定成败**只能**看三段，缺一即误判：

| 字段 | 含义 |
|------|------|
| `result_success` | 0=失败 / 1=成功（1 也可能假成功，见下） |
| `failure_code` | 非空即失败：`automation-rate-limited` / `automation-request-refused` / `automation-model-config-failed` |
| `runs_json[0].success` + `output` | 真实执行结果与正文；**`result_success=1` 但 output 里自报失败** = 脚本层静默失败（如「status=OK 但数据骤降」） |

**平台层成功 ≠ 业务成功**。真实案例（2026-10-06）：索引维护任务 `result_success=1`、
status=ACCEPTED，但 output 明写「提取器 Bug 实际失败，files 3122→704、symbols 降 81%」——
代理商自报的 OK 是脚本自己写的状态码，与业务正确性脱钩。**必读 output 正文**。

**判定「没跑」的另一条线**：`automations.last_run_at` 为 NULL 且 `next_run_at` 在未来 →
任务刚建、尚未到首次触发，不算漏跑（用 `created_at` 区分）。

## 本地补跑（本机自动化无「重跑」API）

本机 WorkBuddy 自动化**没有**任务级「立即重跑」入口。补跑 = **直接按自动化 prompt 里的命令重跑底层脚本**，参数与自动化一致：

1. 从 `automations.prompt` / `cwds` 读出真实命令与工作目录（prompt 开头通常就写着 `cd <dir> && python <script>`）。
2. 用**托管解释器全路径**跑（`<userhome>/.workbuddy/binaries/python/versions/*/python.exe`），避免裸 `python` 解析到错误环境。
3. 若上次重跑用了 `--no-push` / `--dry-run`，补跑时**必须去掉该开关**才会真正推送。
4. 校验三件套：退出码 0 + 记录文件（如 `runs/run_<date>.json`）`status` 一致 + 推送回执 `errcode=0`。

> 推送默认走**测试通道**（`WECOM_CHANNEL=test`，key 取 `WECOM_WEBHOOK_TEST`，见 `env.local.sh`）。
> 改代码期禁推生产 key。

### 1. 确认调度真源（服务器场景；crontab 常是空的）

`crontab -l` 里凡标 `MIGRATED-TO-WORKFLOW-ENGINE` 的条目**已迁到 workflow engine**，
真实调度在 `/opt/workbuddy/5_engine/workflow_tasks/*.yaml`。

```bash
ps -ef | grep workflow_engine | grep -v grep       # 引擎是否存活
systemctl status workflow-engine --no-pager        # 有 systemd 单元时
crontab -l                                          # 看哪些行被注释/迁移
ls /opt/workbuddy/5_engine/workflow_tasks/          # 真实任务定义
```

### 2. 查引擎执行记录（决定性证据）

```bash
DB=/opt/workbuddy/.state/workflow_engine.db
sqlite3 $DB ".schema executions"
sqlite3 -header -column $DB \
  "SELECT id,task_name,started_at,finished_at,exit_code,duration_ms,output_path
   FROM executions ORDER BY id DESC LIMIT 30;"
```

- **没有目标时刻的行** → 根本没触发 → 查引擎进程/时间窗/lock 卡死/yaml 被禁用
- **有行但 exit_code != 0** → 触发了但失败 → 进第 3 步
- **有行 exit=0 但产物没推** → 脚本内部静默失败（推送段被吞）→ 读输出日志

### 3. 读失败输出日志

```bash
cat <output_path>          # executions 表里的 output_path 字段就是日志路径
```

- 引擎日志：`/opt/workbuddy/logs/workflow_engine.log`
- 成功/失败对比：`ls -lt /opt/workbuddy/.workflow_state/outputs/ | grep <task>`

### 4. 心跳 / 看门狗交叉验证

```bash
cat /opt/workbuddy/1_influx_reports/.last_patrol_push_ts    # 心跳文件
stat -c '%y' <心跳文件>                                      # 最后成功时间
```

心跳时间必须与 executions 表最后一次 exit=0 对齐；不齐说明"成功"是假的或心跳写入有 bug。

### 5. 手工补跑（server 引擎有触发 API，别手搓命令）

crontab 迁移后的 workflow engine **自带手工触发入口**，补跑用它而非手敲 shell
（保真：同 user / 同 env_file / 同 workdir / 同 args，且落到 executions 表留痕）：

```bash
# token 在 systemd 单元引用的 EnvironmentFile 里，勿硬编码
TOK=$(awk -F= '/^WORKFLOW_API_TOKEN=/{v=$2; sub(/^"/,"",v); sub(/"$/,"",v); print v}' \
      /opt/workbuddy/.scripts/config/systemd.env)
curl -s -X POST -H "Authorization: Bearer $TOK" \
     "http://127.0.0.1:19100/api/trigger/<task_name>"
# 返回 {"triggered": "<task_name>"} = 已排入线程池（异步），随后轮询 executions 表看结果
```

- 引擎 `--port` 绑 **127.0.0.1**，只能在目标机上发（或经 SSH 转发）
- 无 token 返回 `{"error": "unauthorized"}`；token 缺失才会退化为开放模式
- **补跑前先确认推送不是干跑**：`grep PUSH_WEBHOOK <env_file>`，`false` 时推送被跳过
- 补跑后必须核三件套：executions `exit_code=0` + 产物落盘属主正确 + 心跳时间戳刷新

## 已知放大器故障 1：LLM 候选链单端点垄断超时预算

**症状**：某报告生成子进程报「超时（Ns 止损）」，日志停在某步骤之后**无任何 LLM 命中记录**。

**机制**：`call_llm` 对单个候选端点做 `LLM_RETRY_MAX` 次重试 + 递增退避。若头部候选端点
（如第三方托管、无 SLA）**TCP 接得上但不回数据**（Read timeout），则
`timeout × retry_max + Σ退避` 可能**吃满甚至超过子进程止损窗口**，排在后面、几秒即可命中的
健康端点根本没轮到。

**实测口径**：`timeout=60, retry=3, backoff=[1,3,5]` → 60×3+4 ≈ **184s > 180s 止损** → 必失败。

**取证**（在服务器直接跑一次，别猜）：

```bash
cd <workdir>; set -a; source <env_file>; set +a
PYTHONPATH=/opt/workbuddy/0_shared:<workdir> /usr/bin/python3 -c "
import time; from llm_client import call_llm
t=time.time(); r=call_llm('hi', timeout=60); print(time.time()-t, bool(r))"
```

看 stderr 的 candidate 降级链，逐段计时。

**修复三选一（按最小改动优先）**：

| 方案 | 改动 | 适用 |
|------|------|------|
| ① 调小调用方 timeout | leaf 层单行（如 `ai_analyzer.py` 的 `call_llm(timeout=60)→20`） | 最快、可逆、不动共享库 ✅ 首选 |
| ② 让重试参数可配 | 共享 `llm_client.py` | 已实现（2026-10-06）：env `LLM_RETRY_MAX` / `LLM_RETRY_BACKOFF`，或 YAML `defaults.retry_max` / `defaults.retry_backoff`；默认 3 / [1,3,5] 不变 |
| ③ 换/移除劣化默认上游 | llm_endpoints.yaml 优先级 | 根治，但属配置决策需确认 |

## 已知放大器故障 2：部署目录属主漂移（root 手工补跑打死后半段）

**症状**：心跳冻结在上次成功时刻（或某个非计划时刻），看门狗报「未按计划推送」；
executions 表**有**目标时刻的行，但 `exit_code != 0`，日志尾部是裸 `PermissionError`
（`shutil.copy2` / `open(dst,'wb')`），且**推送段与心跳写入段完全没出现在日志里**。

**机制**：手工抢救补跑若以 **root** 执行，`os.makedirs(date_dir)` 会把当天目录建成
`root:root 755`；而定时任务由 **workbuddy** 用户（systemd `User=`）运行，
无权在该目录新建文件 → 部署步骤抛异常。若主流程**没有** try/except 兜住部署，
脚本就地退出，**后面「推送 + 写心跳」整段被跳过** → 心跳不更新 → 看门狗判超时。
即：一个权限异常伪装成「任务没跑」。`web/influxdb/<date>/` 这种按日期建目录的模式最易中招。

**取证**（对比历史目录属主，一眼看出异常日）：

```bash
ls -ld /opt/workbuddy/web/influxdb/*/            # 正常日期应全为 workbuddy:workbuddy
find /opt/workbuddy/web/influxdb -maxdepth 1 ! -user workbuddy -printf "%u:%g %p\n"
sudo -u workbuddy touch <date_dir>/.probe && rm -f <date_dir>/.probe   # 实测可写性
```

> ⚠️ 扫描残余 root 属主时只**修**与本次故障链相关的目录（如当天 web 目录）。
> 生产里长期存在的 root 属主代码/配置目录（`scripts/`、`configs/` 等）是既有基线，
> 以只读方式被使用，**不要顺手 chown**——那是超出范围的生产改造。

**修复**（两步，缺一不可）：

1. **纠正属主**：`chown -R workbuddy:workbuddy <date_dir>` + `chmod 755 <dir>`，
   再 `sudo -u workbuddy touch` 实测可写。
2. **补跑**（见上文「5. 手工补跑」）——只 chown 不补跑，告警不会消失（心跳仍冻结）。

**防复发（代码层）**：在部署函数开头加**可写性前置校验**，把隐蔽的 `PermissionError`
换成带修复命令的显式报错：

```python
if not os.access(date_dir, os.W_OK):
    print(f"  ERROR: 部署目录不可写 {date_dir} (owner uid={os.stat(date_dir).st_uid})。"
          f"通常由 root 手工补跑创建，修复：chown -R workbuddy:workbuddy {date_dir}",
          file=sys.stderr)
    raise ReportGenError(f"部署目录不可写: {date_dir}")   # 用本模块既有异常类型，勿新造
```

**防复发（流程层）**：手工抢救补跑**一律** `sudo -u <服务账号> ...`，禁直接以 root 跑
定时任务的脚本。否则每次抢救都在给下一次故障埋雷。

## 全量体检口径（2026-10-21，29 任务 682 次运行实证）

批量体检/盘点「哪些任务在跑、失败多少」时，字段可信度差异极大，按此口径取值：

### ⚠️ 口径陷阱 1：必须双过滤 `status='ACTIVE' AND deleted_at IS NULL`

**软删除靠 `deleted_at` 非空表达，删除后 `status` 可能仍是 `ACTIVE`。**
实测 51 条记录中 19 条已软删除，其中 **5 条 status 仍写 ACTIVE**。只按 status 统计会把
已删任务当成在跑 —— 曾据此误报「Token 9:30 停跑 18.6 天」，实际它 10-03 12:14 就被删了。

正确数字：**真正 ACTIVE = 29**（不是 34），调度异常 **0**（不是 2，那 2 个都是已删任务）。

> 若发现「ACTIVE 但长期不跑」，**第一动作是查 `deleted_at`**，不是查调度器。

### 字段可信度表

| 字段 | 可信度 | 判据 |
|------|--------|------|
| `automations.deleted_at` | **必须先查** | 非空 = 已软删除，直接从清单剔除 |
| `automations.last_run_at` | **全表不可信** | 34/34 与实际不符（28 个为空、6 个停在 08-31，最大偏差 54 天） |
| `automation_runs.MAX(created_at)` | 可信 | 判「任务是否在跑」只查此值 |
| `automations.next_run_at` | 可信（调度器侧） | 过期即真停跑 |
| `sessions.updated_at` | **不可当运行时长** | 会被任意后续操作刷新（曾误读成 510 分钟）→ 用 `last_activity_at` |
| `runs_json[0].finishedAt - startedAt` | 可信 | 任务耗时，覆盖 99.9% |

**失败归因必须分层看 `thread_title`**，不能只看 `result_success=0`。实测 51 次失败分布：

- **61.8%** = `Automation prompt interrupted: unknown_interrupted`（LLM/平台层，**修脚本零收益**）
- **32.4%** = rate-limited / request-refused（配额与限流）
- **5.8%** = 任务自身逻辑

> 结论：失败多 ≠ 脚本烂。先分类再定位，否则会把平台层限流当业务 bug 改。

**`succ=0` 且耗时 ≈ 5400s = 撞会话超时上限**，属被截断而非任务卡死（10-17 有 15 个任务同时如此）。

### ⚠️ 口径陷阱 2：grep 判「某功能是否存在」必须覆盖语言全部写法

`STATUS=OK` / `f"STATUS={x}"` / `'STATUS='+x` 三种写法，单一正则会漏。
一晚上踩两次：① 工时脚本 `:666` 有 `print(f"STATUS={'OK' if _code==0 else 'FAILED'}")`，
正则只匹配 `STATUS=` 直跟字面量 → 误判「缺 STATUS」；② 同类漏判波及多处。

**「退出码即结论」的脚本不需要 STATUS 字面量**：门禁类脚本（如 `run_gate.sh`
末尾 `exit $((FAIL_TOTAL>0?1:0))`）看 exit code 语义，不能只看有无 STATUS。

> 判据补强：**瘦身 prompt 前，先确认脚本自证真的被真实运行验证过**
> ——要有日志里的 STATUS 行 + 产物文件，不能只 grep 到字面量。

### 现成检查件

`~/.workbuddy/scripts/automation_inventory_audit.py`（只读，exit 0/1）
已封装上述口径陷阱，停跑阈值按频率分级（DAILY 2 天 / WEEKLY 9 天 / MONTHLY 35 天）。
**故障注入自测通过**（人为造「软删除但 ACTIVE」+「next_run_at 过期」→ 2/2 检出，exit=1）。

### 下线任务前三件必验

1. 目标脚本**物理存在**（路径指向真文件）
2. 有对应的计划任务 / automation 行
3. 无外部引用（crontab → wrapper → wrapper 内部引用 三层 + `workbuddy.db automations` 表）

反例 `gf-worktime-fallback.bat`：目标 `worktime-auto.js` 不存在 + 无计划任务 + 功能已迁移，
却带 3 类缺陷滞留（已备份至 `archive/orphan-worktime-fallback-20261021/` 后移除）。

### wrapper bat 三铁律（本机实测）

- **CRLF**：裸 LF → cmd 拼行（"X was unexpected at this time"）
- **纯 ASCII**：中文 `rem` 注释会被当命令执行
- **探活不用 `tasklist | find`**：tasklist 枚举全进程（1s，高峰 63s）；`find` 会被 MSYS
  `/usr/bin/find` 抢先命中 → 守卫**静默绕过**

## 修复纪律（生产脚本铁律）

1. **改前核对服务器文件未被并发改动**：诊断→修复之间若有人（另一会话/同事）改过目标文件，
   你的"改前 md5"假设就失效。上传前**先比对服务器当前 md5 与诊断时记录值**，不一致即中止并重新评估。
   > 实战教训：排查中途上游 `llm_endpoints.yaml` 被外部（用户）改过，与既定修复方案重叠 →
   > 若盲目照搬原计划会覆盖他人的正确决策。**发现外部改动优先服从它，只做非重叠部分。**
2. **备份**：`cp -a <file> <file>.bak_<date>_<reason>`
3. **就改一行**，改后 `diff` 备份确认只有预期差异
4. **语法校验**：`/usr/bin/python3 -m py_compile <file>`
5. **实测验证**：直接跑出问题的那个函数/子脚本，对比修复前后耗时
6. **补跑并验心跳**：手动触发整链，确认退出码 0 + 心跳文件更新
7. root 属主文件用 `sudo` + 复核落地内容（`sed -i` 对 root 文件可能静默失败）；
   上传后**恢复原属主/权限**（`chown`/`chmod` 对齐 stat 记录）

## 常见误判

| 误判 | 真相 |
|------|------|
| 「crontab 里没有 = 任务没配」 | 已迁 workflow engine，看 yaml |
| 「端点 curl 401 = 端点坏了」 | 401=可达但缺 key；**超时才是故障**。可达≠可用 |
| 「昨天好好的，今天没改代码怎么会坏」 | **上游依赖劣化**（第三方端点无 SLA）是常见外因 |
| 「看门狗没报警=没问题」 | 看门狗本身可能也是坏的，需单独验证它在发告警 |
| 「exit=0 就一定推成功了」 | 推送段可能被 try/except 吞掉，必读输出日志 |
| 「心跳停在上次成功时间 = 任务根本没触发」 | 也可能是**触发了、跑到后半段才崩**（如部署 PermissionError），
  异常把「推送+写心跳」整段带走 → 心跳冻结，伪装成没触发。**先查 executions 表有没有行** |
| 「补跑后心跳没动 = 补跑无效」 | 检查是否卡在部署阶段，或 `PUSH_WEBHOOK=false` 走了干跑 |
| 「权限修好就够了」 | 只 chown 不补跑，心跳仍冻结，看门狗照旧每 15 分钟告警 |
| 「链首有死端点必须立刻摘除」 | **连接拒绝**（快失败）的候选危害≈0——它 ~0s 失败并被熔断 N 秒，不会吃预算。
  真正有害的是**能连上但不回数据（Read timeout）**的候选。摘除快失败端点收益近零，可留在槽位待恢复 |
| 「候选链位置无关紧要」 | 有害端点（超时型）**排在越前危害越大**——它一人就能吃满预算。
  把它降到链尾 = 在成本上等价于根治 |
| 「改 yaml 要重启服务」 | 本仓 llm_client 的 yaml 缓存 TTL = **30s**（`_YAML_CACHE_TTL`），
  改后 30s 自动重载；重启只是求稳，非必需 |

## 闭环检查清单

- [ ] executions 表确认目标时刻的执行行存在
- [ ] exit_code 与输出日志一致
- [ ] 失败步骤定位到**具体行**（生成 / 部署 / 推送 / 心跳，哪一段断的）
- [ ] 根因经**实测复现**（不是推断）
- [ ] 修复单行 + 备份 + py_compile 通过
- [ ] 修复前后耗时对比有数字
- [ ] 补跑退出码 0（经引擎 `/api/trigger/<task>`，非手搓命令）
- [ ] 产物落盘且**属主正确**（`! -user <服务账号>` 扫描为空）
- [ ] 推送回执为真（日志里每个目标都「推送成功」，非干跑）
- [ ] 心跳文件时间戳更新
- [ ] 看门狗复跑一次输出 `watchdog OK`（用告警消除作闭环证据，而非推断）
- [ ] 未根治的隐患单独列出（如劣化上游需换 / 待补的流程约束）
