---
name: script-status-exit
display_name: "脚本状态化出口"
display_name_en: "Script Status Exit"
description: "给运维自动化脚本补 STATUS= 自证信号，根治 AB岗交接/审计材料的状态误判。当脚本运行后没有机器可读的状态输出、交接快照靠标题猜测任务成败、或排查自动化运行状态误判时使用。覆盖 Python/Node 两语言，含出口定位、STATUS 约定、SystemExit 陷阱、元数据登记。"
description_zh: "给运维自动化脚本补 STATUS= 自证信号，根治交接与审计材料中的状态误判，覆盖 Python 与 Node 两语言。"
description_en: "Add machine-readable STATUS= exit signals to ops automation scripts so handover snapshots and audit evidence stop misreporting outcomes, for both Python and Node."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
---
# script-status-exit — 脚本状态化出口（补 STATUS= 自证信号）

## 背景与目标
WorkBuddy 自动化脚本运行后，其最终输出的自然语言（title/output）被 AI 猜测成"成功/失败"，易误判。
根治办法：脚本自己打印一行机器可读状态码 `STATUS=OK|FAILED|PARTIAL|WARN`，下游生成器从 runs_json 深度遍历直读，**压过一切启发式**。

## STATUS 语义约定
```
STATUS=OK       # 全部成功（含正常跳过：节假日/无任务/无变更）
STATUS=PARTIAL  # 部分成功（多子系统任务，子项有失败但整体产出）
STATUS=FAILED   # 失败（异常/核心出口非零）
STATUS=WARN     # 成功但有可忽略告警（可选）
```
关键点：
- **正常跳过也算 OK**（节假日、无变更、dry-run），不是 FAILED。
- 生成器 `status_from_runs` 从 `runs_json` 递归 `_walk_text` 找 `\bSTATUS\s*=\s*(OK|FAILED|PARTIAL|WARN)\b`，所以 STATUS 行**必须独立成行、无尾随解释文本污染**（`STATUS=FAILED` 后接 `# 原因` 虽能匹配词边界，但保持纯净更稳）。
- 优先级：`STATUS直读` > 否定感知启发式 > `result_success`。

## 标准流程

### 1. 备份（先于编辑，铁律）
```
cp <file> <file>.bak_status_<YYYYMMDD>
```
**顺序失误案例**：曾先 Edit 后 cp，备份覆盖成改后版 → 用反推法重建 orig。必须在编辑**前**备份。

### 2. 定位脚本出口（三态判定位）
用 Grep 找出口，不要整读大文件：
- Python：`def main\|sys.exit\|if __name__\|return 0\|process.exit`
- Node：`process.exit\|if (require.main\|})()\|catch`

出口类型判断：
| 结构 | 补法 |
|---|---|
| `sys.exit(main())` / `def main→int` | `__main__` 收口：`_code=main(); print(f"STATUS={'OK' if _code==0 else 'FAILED'}"); sys.exit(_code)` |
| try/except 全包 main | try 尾 `print("STATUS=OK")`，except `print("STATUS=FAILED")` |
| 无 return 靠异常 | `try/except` 包裹 `__main__` |
| 多子系统有计数（`_fail_count`/`ok`/`fail`/results）| 用计数聚合：`PARTIAL if _fail_count>0 else OK` |
| `main()` 内 `sys.exit(N)` | **必须用 `try/except SystemExit`**，见坑② |
| Node 回调里 `process.exit` | 在 exit 前按业务状态（非推送状态）打 STATUS |

### 3. 聚合粒度（多子任务优先三级）
单脚本单结果 → OK/FAILED 两级。多岗位/多系统/多截图 → 按子项聚合 PARTIAL：
```python
# 通用：全成功=OK，有失败=PARTIAL
_succ = sum(1 for r in results if r.success)
status = "PARTIAL" if _succ < len(results) and results else "OK"
```
Node 同构。Webhook 推送是否成功通常**不入**状态（报错在 stdout 可见），状态表达"任务本身"。

### 4. 语法校验 + 端到端验证
```bash
python -m py_compile <file>                      # Python
<node> --check <file>.js                          # Node
python <file> --dry-run 2>&1 | tail -3            # 真跑一次，确认 STATUS= 落 stdout 末尾+退出码
```

### 5. 元数据登记（KNOWN loc 漂移根治）
生成器的 KNOWN 映射里 loc 必须是**真实文件**：
- 优先细到 `xxx.py`/`xxx.js`，不落空目录
- 可疑时 `find` 定位真实脚本（常漂移到 `zidonghuajiaoben/`、`scripts/` 子目录）
- 改完校验：`ast.literal_eval(KNOWN)` 无重复 key、`os.path.exists(loc)` 零 MISSING
- 生成器正本以自动化配置（`automation_update view` 的 `cwds`/prompt）与实跑产物落点为准；**改正本，不要碰副本**。loc 动态解析（运行时查 `index.db` 的 `automations.cwds[0]`），KNOWN 只剩 `(intent, subsystem)` 二元组 + 名称自检；任务搬家自动对齐，不用再手改 loc。

## 正源判定（遇到多份同名脚本先做这个）
不要猜哪份是正本，实测三步：
1. `md5sum` + `ls -la` 比大小与时间戳；
2. 看自动化配置（`automation_update view`）的 `cwds` 和 prompt 指向；
3. 按 prompt 的**原样命令**真实跑一次，产物落点即正源。
产物先 `cp -r` 备份再跑（派生数据可再生，但要留回滚点）。

## 坑清单（全部实踩）
1. **秒 vs 毫秒时间戳**：workbuddy.db `created_at` 是 13 位毫秒，按秒过滤命中 0 行 → `ts/1000` 转换。
2. **`except Exception` 抓不到 `SystemExit`**：`sys.exit(1)` 抛 `SystemExit`（BaseException 子类），须单独 `try/except SystemExit` 才能取退出码打 STATUS。
3. **正常跳过≠失败**：节假日/无变更/dry-run 应归 OK，别误判 FAILED。
4. **远端脚本误判**：KNOWN loc 指向空壳目录，SSH 远端查无 → 真实脚本可能在本地另一路径，先 `find` 核实再断言"远端生产"。
5. **Webhook 失败≠任务失败**：推送 errcode≠0 在 stdout 可见，不混入状态（除非脚本无其他产物）。
6. **STATUS 行纯净**：不尾随解释文本，保 `\bSTATUS=...\b` 词边界可匹配。
7. **备份顺序**：必须先备份后编辑，否则原始版被覆盖。
8. **汇总计数基数错配**：折叠高频噪音前后条数不同，若"直读数 = 全量 total − 可见口径的 heuristic"，减出的其实是**被折叠的噪音数**，会产出一个恰好等于噪音数、看着像真的伪数字。统计量必须同一口径（都用 `items` 全量或都用 `visible`），并做 `direct + heuristic == total` 自检。
9. **`python -c` 内联测试不可信**：`-c "..."` 的串经 shell 双引号转义，JSON 里的 `\n`、引号会被改写，测出的失败可能是假的（曾 4/5 用例返回 None，改写文件后全 PASS）。合成测试一律写文件再跑。

## 验证
- dry-run 真跑输出 `STATUS=OK` + 退出码 0
- 生成器 `status_from_runs` 模拟 8 种输出（OK/PARTIAL/FAILED 高低路径）全部解析且压过误导 title
- 快照重生成：KNOWN loc 修正后需**次日**才体现直读提升（今日 runs 早于补丁，属正常时序）
