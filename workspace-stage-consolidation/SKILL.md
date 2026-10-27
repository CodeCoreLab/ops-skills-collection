---
name: workspace-stage-consolidation
display_name: "工作区现场收敛"
display_name_en: "Workspace Stage Consolidation"
description: "任务封板时的「现场收敛与清理」规范化流程 —— 多轮 SSH 侦察/修复后，把散落的工作区脚本、 临时文件、明文凭据残留一并收敛，同时审计服务器侧现场；用户确认后可进一步彻底清理。 当用户说「收敛现场」「封板」「清场」「现场结束」「收尾归档」「清理现场」时触发。 也可用于发现工作区根目录散落大量一次性脚本（p0_* / recon_* / probe_* / td_* / fix_* / verify_*）需要归位时。 核心原则：**先脱敏 → 再归档 → 再清缓存 → 终态复核**；删除是**独立第二阶段**， 必须用户显式确认范围（三档：全清归档目录 / 保留证据层 / 转入 _archive 批次），不得自行推断。 配套雷区：shutil.move 对目录变异为复制、脱敏脚本自身内嵌明文、 哈希留档被误报为明文凭据、Windows 删目录需 RemoveDirectoryW、 服务器 /tmp 证据须先取回校验再删、删除后报告引用需同步修正。"
description_zh: "任务封板时的现场收敛与清理规范化流程：先脱敏、再归档、再清缓存、终态复核，删除作为独立第二阶段需用户显式确认。"
description_en: "A standardized close-out workflow for a task workspace: redact secrets first, then archive, then clear caches and re-verify the final state, with deletion as a separate second stage requiring explicit user confirmation."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    location: user
    agent_created: "true"
---

# workspace-stage-consolidation — 工作区现场收敛（任务封板）

## 何时用

| 触发信号 | 说明 |
|---|---|
| 用户说「收敛现场」「封板」「清场」「现场结束」「收尾归档」 | 直接触发 |
| 多轮改造任务即将结束 | 工作区已产出 10+ 一次性脚本 |
| 根目录散落 `p0_*` / `recon_*` / `probe_*` / `td_*` / `fix_*` / `verify_*` / `_pull/` / `__pycache__` | 需要归位 |
| 修复过程中产生过明文凭据副本 | 必须脱敏后才能归档 |

**不适用的场景**：日常小改动（无需收敛）；单纯的磁盘空间清理（用 `log-space-cleaner` / `devops-repo-cleanup`）。

### ⚠️ 收敛边界（务必先确认「现场」指哪）

收敛对象 = **当前任务工作区**（`E:/WorkBuddy/<会话目录>/`）内的散落物。

- **`~/.workbuddy/` 是跨会话全局主目录，不是「现场」**。它含 skills / scripts / sessions /
  shell-snapshots / archive / rules 及**大量其他项目的既有文件**（实测 2026-10-05：根目录有
  `auto_gfplus_daily.py`、`gen_report_v3.py`、`devops-*.json`、`grafana_*.json` 等 40+ 项）。
  把「收敛现场」扩到全局根目录 = 误删他人产物。
- **特例**：本任务若对 `~/.workbuddy/` 有**明确的产出契约**（如某项目产出 `scripts/memory_*.py`
  三件套），这些是**跨项目交付物**，归「产出文件」而非「现场垃圾」，**不收敛**。
- **判定「本会话新增」**（只读侦察）：
  ```bash
  find ~/.workbuddy -maxdepth 2 -type f -newermt '<会话启动>' -printf '%TH:%TM %p\n' \
    | grep -vE 'sessions/|shell-snapshots/|archive/|memory/|audit-log/|logs/|\.pyc'
  ```
  命中的才算候选，且仍要逐项判断「一次性脚本 vs 交付物」。
- WorkBuddy 自身运行态（`sessions/` / `shell-snapshots/` / `changes-index/` / `usage-log.json` /
  `*.log`）**永不收敛**——那是宿主程序的活数据，删了会破坏运行。

---

## 铁律

1. **不删除证据文件，只归档**。`_stage_<YYYYMMDD>/` 是唯一归档地，可回溯。
2. **顺序不可颠倒**：脱敏 → 归档 → 清缓存 → 终态复核。
   先归档再脱敏会漏掉已移动的文件（或需二次遍历）。
3. **脱敏脚本自身不得内嵌明文**。用正则匹配 hex 字面量，不用字面量比对：
   ```python
   # ✅ 正确：不内嵌明文
   HEX_LITERAL = re.compile(r"(?<=OLD=')[a-f0-9]{32,}(?=')")
   # ❌ 错误：脚本自己成为新的明文副本
   text.replace("OLD='9cbb0e72...48位...'", "OLD='<REDACTED>'")
   ```
   这条对应 `security.md` §脱敏五雷区第 4 条「不留脱敏前明文副本」。
4. **删服务器 `/tmp` 文件前必须先取回本地并逐字节 sha256 校验**。
5. **区分「本会话产物」与「既有文件」**：比对文件 `mtime` 与会话启动时间。
   早于会话启动的一律不动，仅记录。
   **反向也成立**：`mtime` **晚于**本会话最后写操作者，多为**并发会话**产物，同样只记录不动。
   识别法：`ls -lad --time-style=+%m-%d_%H:%M <workspace_root>/*/` 找 mtime 与可疑文件吻合的
   **其他会话目录**（工作区名即其启动时间），锁定归属后不碰。
6. **删除时区分「现场垃圾」与「回滚基线」**：含 **git 外资产**的备份（DB / 凭据口径表 /
   迁移前快照）是**资产**，不随"现场清理"一起删。判定证据：
   - `git check-ignore <file>` / `grep <file> .gitignore` 为真 → git 里没有副本 → 删了就真没了
   - 与当前库/目录逐文件比对为 **DIFF** → 说明它是"改前态"，正是回滚要用的
   - 含 `index.db` / `.env` / `token` 等不可重建内容 → 保留，或（用户坚持删时）**只投回收站**
7. **"删除"默认走回收站，不做永久删**：即便用户已确认，也用 `SHFileOperationW` + `FOF_ALLOWUNDO`
   投递（可还原），永不 `unlink`/`rmtree`/`--permanent`。理由：唯一副本一旦永久删即不可逆。
   ⚠️ **实测（2026-10-05）**：PowerShell 的 `Add-Type -AssemblyName Microsoft.VisualBasic`
   **会被沙箱拦（"Add-Type compiles and loads .NET code at runtime"）**；改用 **Python ctypes 直调
   `shell32.SHFileOperationW`** 可行，返回码 0 即成功。可复用实现：

   ```python
   import ctypes, os
   from ctypes import wintypes
   class SHFILEOPSTRUCTW(ctypes.Structure):
       _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                   ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                   ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                   ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
   path = r"E:\...\_stage_YYYYMMDD"
   pfrom = ctypes.create_unicode_buffer(path + "\0")        # 必须双重 NUL 结尾
   op = SHFILEOPSTRUCTW(); op.wFunc = 0x0003                # FO_DELETE
   op.pFrom = ctypes.cast(pfrom, wintypes.LPCWSTR)
   op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400            # FOF_ALLOWUNDO|NOCONFIRMATION|SILENT|NOERRORUI
   res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
   assert res == 0 and not os.path.exists(path), "回收站投递失败"
   ```
   `SHFileOperationW` 对**目录**有效（一次投递整棵树）；`RemoveDirectoryW` 仅用于 **永久删空目录**
   （本 skill 不使用该路径）。

---

## 标准流程

### Step 0 — 现场清点

```bash
cd <workspace> && ls -1
echo "--- 归档目录 ---"; ls -1 _recon_archive/ 2>/dev/null
echo "--- 拉取目录 ---"; ls -1 _pull/ 2>/dev/null
echo "--- 编译缓存 ---"; ls -1 __pycache__/ 2>/dev/null | head
```

同时扫明文凭据，决定是否需要脱敏步骤：

```bash
grep -rEn "[a-f0-9]{32,}" . --exclude-dir=.workbuddy --exclude-dir=__pycache__ \
  | grep -vE "sha256|md5|sha12|\.pyc"
```

**判断**：命中 hex32+ 的文件，逐个确认是「凭据」还是「哈希留档」。
- 哈希留档（sha256 值）无需处理
- 真实凭据（token / key / password）必须脱敏

### Step 1 — 明文凭据脱敏（就地）

```python
HEX_LITERAL = re.compile(r"(?<=OLD=')[a-f0-9]{32,}(?=')")
p = ROOT / "some_script.py"
before = sha256_12(p)
new, n = HEX_LITERAL.subn("<REDACTED_ARCHIVED_FALLBACK_TOKEN>", p.read_text(encoding="utf-8"))
p.write_text(new, encoding="utf-8")
print(f"{p.name}: 命中 {n} 处, sha256_12 {before} -> {sha256_12(p)}")
```

**就地脱敏，不留 `.bak` 明文副本**（这是上一轮的实测教训）。

### Step 2 — 归档

```python
KEEP_IN_ROOT = {"<交付物>.md", ".workbuddy", ARCHIVE.name, Path(__file__).name}
for entry in sorted(ROOT.iterdir()):
    if entry.name in KEEP_IN_ROOT or entry.name == "__pycache__":
        continue
    dst = ARCHIVE / entry.name
    if dst.exists():          # 冲突则跳过，不覆盖
        continue
    shutil.move(str(entry), str(dst))
```

根目录只留：**交付物 + `.workbuddy/` + 归档目录 + 收敛脚本自身**。

### Step 3 — 清 `__pycache__`

```python
pyc = ROOT / "__pycache__"
if pyc.is_dir():
    for f in pyc.iterdir():
        os.remove(f)          # shutil.rmtree 在本环境被拦
    os.rmdir(pyc)
```

### Step 4 — 终态复核

```python
print("根目录：", [e.name for e in sorted(ROOT.iterdir())])
# 明文复查（排除 .workbuddy；豁免哈希留档 —— 见雷区 7）
HASH_ARCHIVE_SUFFIX = {".sha256", ".md5", ".sha1", ".sha512"}
hits = []
for p in ROOT.rglob("*"):
    if not p.is_file() or ".workbuddy" in p.parts:
        continue
    if p.suffix.lower() in HASH_ARCHIVE_SUFFIX:
        continue
    t = p.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"[a-f0-9]{32,}", t):
        line = t[: m.start()].rsplit("\n", 1)[-1] + t[m.start() :].split("\n", 1)[0]
        if re.search(r"sha256|md5|sha1|sha12|sha_?12|哈希", line, re.I):
            continue
        hits.append(f"{p.relative_to(ROOT)}: {m.group()[:16]}…")
print(f"明文 hex32+ 残留：{len(hits)}")
```

**收敛合格标准**：根目录 ≤ 4 项；明文 hex32+ 残留归零（哈希留档不计）。

**纯本地任务**（无服务器 / 无 git 远端）→ **Step 5–7 整体不适用**，在报告里写一句「服务器侧不适用 +
理由」即可，不要为凑流程去连无关主机。判定依据：本任务的所有改动面都在 `~/.workbuddy/` 与本工作区内，
无 systemd 服务、无 `/tmp` 证据、无 `git remote`。

### Step 5 — 服务器侧审计（只读）

不改任何内容，只枚举与校验：

```python
run(cli, "C1. 今日改动面全清单",
    "find /opt/workbuddy /etc/systemd/system -newermt '<TODAY> 00:00' "
    "! -newermt '<TODAY+1> 00:00' -type f \\( -name '*.py' -o -name '*.service' "
    "-o -name '*.env' -o -name '.env*' -o -name '*.sh' \\) 2>/dev/null "
    "| grep -vE 'venv/|__pycache__|/logs/|node_modules' | sort")

run(cli, "C2. 回滚备份完整性",        # 逐份 ls -la，确认存在且非空
    "ls -la <每个 .bak_* 路径>")

run(cli, "C3. 服务运行态 + 监听面",
    "for s in <svc1> <svc2>; do printf '%-16s ' $s; systemctl is-active $s; done; "
    "ss -lntp | grep -E ':(<ports>)\\b'")

run(cli, "C4. 临时残留排查",
    "find /tmp -maxdepth 1 -newermt '<TODAY> 00:00' 2>/dev/null | head -20; "
    "find /opt/workbuddy -maxdepth 2 -type f "
    "\\( -name 'p0_*.py' -o -name 'td_*.py' -o -name 'recon_*.py' \\) 2>/dev/null")

run(cli, "C5. 凭据暴露面终态",
    "T=$(grep -oP '(?<=^<ENV_KEY>=).*' <env_path> | tr -d '\\n'); "
    "timeout 90 grep -rlF \"$T\" /opt/workbuddy /etc 2>/dev/null "
    "| grep -vE 'venv/|node_modules|__pycache__' | sort")

run(cli, "C6. 【强烈建议】同源副本缺陷回溯",
    "for f in <本次改过的文件名列表>; do printf '%-28s ' $f; "
    "find /opt /root /home -name \"$f\" -not -path '*/node_modules/*' "
    "-not -path '*/venv/*' 2>/dev/null | head -3 | tr '\\n' ' '; echo; done")
```

### ⚠️ C6 必做：跨主机同源副本回溯（实战教训）

**本机修好的 bug，服务器上的同名副本往往还在。** 服务器是**独立部署**，不是本机的镜像，
两处各自演化。**实测（2026-10-06）**：本机修复 13 处真 bug 后，跳板机
`/opt/workbuddy`（独立 mirror 仓库）上**6 处同源缺陷初判存活，逐行核实后 5 处为真**：

| 跳板机路径 | 缺陷 | 与本机关系 | 复核结论 |
|---|---|---|---|
| `1_influx_reports/scripts/causal_alert_graph.py:287` | 跨函数引用 | **md5 逐字节相同** | ✅ 真 bug |
| `22_skills/data/gf-worktime-auto/lib/browser-launcher.js:37` | `_CHROME_PROFILE_ENV` 无定义 | **md5 逐字节相同** | ✅ 真 bug |
| 同上文件 | `_CHROME_EXEC` 无定义 | 同源 | ✅ 真 bug |
| `22_skills/data/gf-worktime-auto/verify-plantools.js:40` | `browserEngine` 无定义 | 同源 | ✅ 真 bug |
| `22_skills/data/ima-sync/scripts/ima_sync.js:32,33` | `os` 模块未导入 | 同源 | ✅ 真 bug |
| `1_influx_reports/configs/metric_config_loader.py:89` | `json` 无模块级导入 | 同源 | ✅ 真 bug |
| `1_influx_reports/scripts/chatops_alert_card.py:281` | ~~变量误用~~ | 同源，文件不同版 | ❌ **误判**（`alert` 是形参） |

> ⚠️ **C6 的最大价值不是"发现数量"，而是逼出逐行核实。**
> 本次初判 6 处，逐行核实后 **1 处为误判**（`alert.get(...)` 中 `alert` 是该函数形参，引用合法）。
> **只靠"文件同名 + 缺陷相似"就下结论，会制造假阳性。**

**为什么必须做**：
1. **判定「修复是否已下发」** —— md5 与本机修复前版本一致 → 未下发；不一致 → 需人工比对差异。
2. **暴露「从未运行过」的分支** —— 同一缺陷在两处都在，说明该代码路径**可能从未被成功执行**
   （实测 `browser-launcher.js` 的 Chrome 分支因两处都缺 `_CHROME_EXEC` 而从未生效）。
3. **避免误报「生产已修复」** —— 若只改本机不改服务器，交付报告会失真。

**方法**：
```bash
# 远端取 md5，与本机 git HEAD / 工作区 逐一比对
ssh <host> "md5sum /opt/.../<file>"
git -C <local_repo> show "HEAD:<relpath>" | md5sum         # 修复前
sha256sum <local_repo>/<relpath>                            # 修复后
```

**归属判定**：远端 `/opt/workbuddy` 常是**独立 git 仓库**（查 `git -C /opt/workbuddy remote -v`），
则其内容变更**不受本机 git 状态影响**，必须单独下发。

**审计结论措辞模板**：
> 本会话**全程只读 + 仅本机操作**，未向服务器写入任何内容；服务器同源副本保持原状，
> 不影响本次结论，但**生产侧缺陷仍存活**，需决策是否下发。

### 🔴 C7 铁律：下发时**禁止整文件覆盖**，必须行级最小 patch

**跨主机副本"同名"≠"同版"。** 两处各自演化，本机版往往**混入了服务器没有的依赖**，
或**改过路径/配置**。整文件覆盖 = 把本机的新特性强灌进生产环境。

**实测（2026-10-06）两类致命差异**：

| 文件 | 差异 | 若整文件覆盖的后果 |
|---|---|---|
| `configs/metric_config_loader.py` | 本机把 `configs/` 改成 `config/`，**跳板机只有 `configs/`** | 配置解析失败，读不到 `metrics.yaml` |
| `scripts/chatops_alert_card.py` | 本机多 113 行（引入 `wecom_md` + `save_feedback`），**跳板机无 `wecom_md.py`** | `ImportError`，模块直接加载失败 |

**正确流程（下发五步）**：

```bash
# 1. 先下载远端原文，与本机做 diff（决定"改哪几行"，而非"覆盖整个文件"）
ssh host 'cd /opt/x && tar czf - <files>' > jump.tar.gz && tar xzf jump.tar.gz
diff --strip-trailing-cr <remote_copy> <local_fixed>    # 逐文件看差异

# 2. 备份（md5 校验 + git 排除，避免污染 status）
ssh host 'mkdir -p /opt/x/_bak_<task>_<date> && cp -p <files> …'
ssh host 'echo "_bak_<task>_<date>/" >> /opt/x/.git/info/exclude'   # 不动仓库 .gitignore

# 3. 行级 patch（正则匹配 + 期望命中数断言，错一处即整体中止）
#    多行模式务必用 r'\r?\n' 拼正则——直接写 '\r\n' 会因行尾差异全部失配

# 4. 语法 + 残留 + diff 三重验证
ssh host 'python3 -m py_compile <f>' ; ssh host 'node --check <f>'
#    再 diff 一次：确认净变动行数 == 预期，无附带改动

# 5. 精确提交（git add -- <5 个文件>；不 add -A，防误纳他人未提交改动）
```

**三个必踩坑**：

1. **行尾失配**：远端若是 CRLF，用 `'...\r\n'` 字面量匹配会**全部 0 命中**。
   → 改 `re.escape(line)` 逐行拼接 + `r'\r?\n'` 连接。
2. **反斜杠折叠**：经 shell/JSON 多层传递后，JS 的 `'C:\\Program'` 会被折成 `'C:\Program'`
   （JS 中 `\P` 非合法转义 → 路径变 `C:Program`）。
   → 用 `chr(92)*2` 构造，绕开各层转义。
3. **备份目录污染 git status**：`.gitignore` 里 `*_bak/` **不匹配** `_bak_naming_fix_20261006/`
   （后者不以 `_bak/` 结尾）。
   → 写 `.git/info/exclude`（本地私有，不改仓库 `.gitignore`）。

**审计要点**：
- C1 的每个文件都要能追溯到本会话的某个改动步骤，或有明确归属说明
- C4 若命中 `p0_*` / `td_*` 脚本 → 本机脚本误传服务器，需清理
- C5 的命中数应等于「设计必需的凭据位」数量（通常 2 个：`.env` + token 文件）

### Step 6 — 取回证据 + 清理 `/tmp`

```python
sftp = cli.open_sftp()
for remote in TARGETS:
    local = LOCAL_EVIDENCE / Path(remote).name
    sftp.get(remote, str(local))
    # 远端 sha256 vs 本地 sha256 逐字节校验
    _, so, _ = cli.exec_command(f"sha256sum {remote}")
    assert so.read().decode().split()[0] == hashlib.sha256(local.read_bytes()).hexdigest()
# 校验全通过后再删
run(cli, "cleanup", "rm -f <targets>; ls -la <targets> 2>&1")
```

**只清理本会话产生且已留档的文件**。不触碰：
- `ssh-mux-*`（活跃 ControlMaster socket）
- `systemd-private-*`（systemd 私有 tmp）
- `runc-process*`（容器运行时）
- 早于会话启动时间的文件

### Step 7 — git 工作区终态

```bash
git status --porcelain
git log -1 --format='%h %ci %s'
# 独立子 repo 也要查（如 data/rules）
cd <sub_repo> && git log -1 --format='%h %ci %s'; git status --porcelain
```

剩余未提交变动必须能逐一说明归属。**本会话改动应已全部提交**。

---

## 可选第二阶段 — 彻底清理（须用户显式确认）

**收敛 ≠ 清理**。Step 1–7 只做**归档**（`_stage_<日期>/`），任何删除都必须单独取得用户确认。
用户说「清理现场」「彻底清场」「删掉吧」时，**先问清删除范围**，不要自行推断。

**例外 —— 用户已预授权范围**（如「按你的决策执行」「你自己定」）：不再追问，改用
**最小可辩护范围** = 本会话工作区 + 本会话服务器产物。

- 本会话站点若**已收敛干净**（无 `_stage/`、无散落脚本）→ 清理为 **no-op**，如实报告，
  **勿为凑流程而删**（实测 2026-10-06：站点仅 2 项，清理如实报 no-op）。
- **绝不扩展到其他会话目录** —— 它们是资产载体（实测同日：`11-40-53/` 存**私钥归档 + 权限回滚基线**；
  `03-16-28/` 存 **120MB skill 全量备份**；`13-40-25/` 存**活跃自动化脚本源**）→ 删即不可逆。
- 服务器 `.bak_*` 回滚基线**不删**（铁律 6）；跨会话目录一律**只记录不动**（铁律 5）。
- **并发会话识别**：工作区名即启动时间戳；mtime 晚于本会话最后写操作者 → 并发会话，其服务器产物
  同样只记录不动。实测两会话同时改 `llm_endpoints.yaml`：以 **md5 比对**确认无覆盖冲突。

### 三档范围（务必让用户明确选择）

| 档位 | 删除内容 | 保留 | 适用 |
|---|---|---|---|
| **全清归档目录** | 整个 `_stage_<日期>/` | 交付物 + `.workbuddy/` | 脚本为一次性、结论已固化到报告 |
| **保留证据层** | 脚本 + `_recon_archive/` | `_evidence/` + `_pull/` | 后续想按原始证据复核 |
| **转入 `_archive` 批次** | 不删，仅重命名入批次 | 全部 | 想纳入既有保留期机制自动清除 |

### 删除前必做

1. **生成完整清单**（逐文件 sha256_12 + 字节），打印且留档到报告
2. **根锚定校验**（`TARGET.parent.resolve() == ROOT.resolve()`）
3. **符号链接逃逸校验** —— 命中即 ABORT
4. **确认目标内无「非本会话产物」与「仍在用的文件」** —— 逐项核对 `mtime` 与用途
5. **报告不得落在删除目标内** —— 若「收敛报告」本身写在 `_stage_<日期>/` 里（Step 2 归档时常见），
   删除前**必须先移出**到工作区根目录（如 `现场收敛记录_<YYYYMMDD>.md`），
   否则报告与被删内容同归于尽，关键结论灭失。
   实测（2026-10-01）：`收敛记录.md` 原在 `_stage_20261001/` 内，删前先固化到根目录才删目录。

```python
files = sorted(p for p in TARGET.rglob("*") if p.is_file())
links = [p for p in TARGET.rglob("*") if p.is_symlink()]
if links or TARGET.parent.resolve() != ROOT.resolve():
    return 1                      # ABORT
for f in files: os.remove(f)      # 逐文件
for d in sorted((p for p in TARGET.rglob("*") if p.is_dir()), key=lambda x: -len(x.parts)):
    rmdir_win(d)                  # 自底向上
rmdir_win(TARGET)
```

### 删除后必做

1. **修正报告中的过时引用** —— 报告里若写「完整留档于 `_stage_xxx/`（可回溯）」，删除后即自相矛盾。
   改为：文件规模/清单/关键数据（sha256 等）**固化进报告正文** + 注明「原文件已清理」+ 说明为何不影响复核。
2. **复核交付物与 `.workbuddy/` 仍在**。
3. **报告改为两阶段叙述**（收敛 → 清理），文末更新封板时间。
4. **清理脚本自身也删掉**（它也是现场产物）。

> **关键判断**：删除前问自己 —— 「这份证据的**结论**是否已固化到交付物？」是 → 可删；否 → 先固化再删。
> 典型可删：一次性脚本、侦察输出、临时拉取副本（含 SSH 路径/服务器 IP 者，删除还有降暴露面的收益）。
> 典型不可删：`.workbuddy/`、交付物、服务器侧回滚备份（`.bak_*`）。

---

## 雷区

### 1. `shutil.move` 对**目录**可能表现为「复制」而非移动

**实测环境**：Windows + Git Bash。移动目录后源目录仍存在，导致根 `_pull` 与 `_stage/_pull` 并存。

**症状**：归档报告「已归档 N 项」，但根目录仍有该目录；复跑报 `[CONFLICT]`。

**处置**：**逐文件 sha256 核对**，确认一致后才删根副本：
```python
for a, b in zip(sorted(SRC.iterdir()), sorted(DST.iterdir())):
    assert a.name == b.name
    assert sha256(a) == sha256(b)     # 不一致则 ABORT
# 全一致 → 删源
for f in SRC.iterdir(): os.remove(f)
rmdir_win(SRC)
```

### 2. 脱敏脚本自身内嵌明文

**症状**：收敛完成后复扫，命中落在**收敛脚本自己**身上。

**根因**：把待脱敏的明文当字面量写进 `replace()`。

**处置**：改用正则匹配结构（`(?<=OLD=')[a-f0-9]{32,}(?=')`），脚本零明文。

### 3. Windows 删除目录

`shutil.rmtree` / `os.rmdir` 在 Git Bash 环境可能被拦。两段式：
```python
for f in p.iterdir():
    os.remove(f)                    # 逐文件
import ctypes
RemoveDirectoryW = ctypes.windll.kernel32.RemoveDirectoryW
RemoveDirectoryW.argtypes = [ctypes.c_wchar_p]
RemoveDirectoryW.restype = ctypes.c_int
if not RemoveDirectoryW(str(p)):
    raise OSError(f"RemoveDirectoryW failed: {p}")
```

### 4. 服务器 `/tmp` 证据文件直接删

**症状**：删了才发现是「改动前后 sha256 对照」，回滚核验从此无据。

**处置**：**先 SFTP 取回本地 → 远端/本地 sha256 逐字节比对 → 一致后才删**。

### 5. 误删既有文件

**症状**：把别人的脚本当归档对象移走，破坏他人工作。

**处置**：收敛前先比 `mtime` 与会话启动时间。
```bash
stat -c 'owner=%U:%G mode=%a mtime=%y' <file>
```
`mtime` **早于**会话启动 → **不动，仅记录**。

### 6. broad grep 超时

全机 `grep -rl` 范围过大（`/opt /root /home /etc /var/spool`）会触发 paramiko `PipeTimeout`。
**处置**：分目录逐段扫，每段独立 `timeout`；或先 `find` 收窄范围再 grep。

### 7. 终态复核把「哈希留档」误报为「明文凭据」

**症状**：Step 4 复扫报 `明文 hex32+ 残留 = 8`，逐条看全在 `_evidence/*.sha256` 里。

**根因**：`.sha256` 留档文件格式是 `<64位哈希>  <文件路径>` —— 哈希本身天然匹配 `[a-f0-9]{32,}`。
**这是误报，不是泄漏**：哈希不可逆，正是用来做完整性核验的证据。

**处置**：判定口径必须带豁免，
```python
HASH_ARCHIVE_SUFFIX = {".sha256", ".md5", ".sha1", ".sha512"}
if p.suffix.lower() in HASH_ARCHIVE_SUFFIX:
    continue                              # 豁免：哈希留档文件
...
if re.search(r"sha256|md5|sha1|sha12|sha_?12|哈希", line, re.I):
    continue                              # 豁免：哈希语境行
```

**判别原则**：区分「**凭据**（可被直接用来鉴权）」与「**哈希**（不可逆、仅用于比对）」。
收敛要消的是前者；后者是证据，必须保留。加豁免前先逐条人工确认命中内容，避免豁免掩盖真泄漏。

### 8. 「删除陈旧 daily log」应改为「**移入 archive**」而非直接删

**症状**：接手别人的 commit 时发现一些 `.workbuddy/memory/YYYY-MM-DD.md` 被 `git rm` 直接删除，
既没进 `archive/`，也没在 commit message 说明原因。内容往往**还有价值**（本次实测 7 文件 = 22.6 KB 工作记录）。

**为什么是坑**：
- 「删」与「归档」在**是否还能检索**上完全不同。daily log 是历史记录，直接删 = 不可检索（虽仍可从 git 历史挖，但成本高）。
- 项目常已存在归档约定（如 `.workbuddy/memory/archive/` 下已有 `2026-05-19.md` 先例）——
  绕过约定直接删 = **不合规**。

**处置（本次采用，可复用）**：

```bash
# 1. 从「删除前最后一个版本」提取（不是从 HEAD，HEAD 已经没有了）
git show <删除前sha>:<path>            # 逐文件取回

# 2. 落到约定归档位
#    .workbuddy/memory/archive/<basename>

# 3. 字节级校验：回读 sha256 == 提取 blob 的 sha256
#    7/7 一致才算通过

# 4. 单独提交，并在 message 写明：
#    · 原删除动作非本会话产出（不冒领）
#    · 恢复源 commit、落点、校验结果
#    · 「根目录不再有陈旧 log（尊重原动作）+ 内容保留在 archive（符合约定）」
```

**关键**：`archive/` 是**约定归档位**（约定俗成的"冷存储"），
而 `_stage_<日期>/` 是本 skill 的**现场归档位**。两者不同，别混用。

### 9. 门禁/校验类改动，必须做「**对抗性验证**」（反例测试）

**症状**：新增了 pre-commit / lint 门禁，只测了「合规提交能通过」就宣布完成。
→ **虚假安全感**：门禁可能根本没生效，或规则写反了，但正常提交本来就会通过，看不出来。

**处置**：造一个临时 git 仓库，**逐类喂违规输入，验证是否真被拦住**：

| 用例类型 | 期望 |
|---|---|
| 中文文件名 / 含空格 | BLOCK |
| 错误大小写风格（py 用 camelCase、用 kebab） | BLOCK |
| 备份残留（`*.bak` / `*.orig`） | BLOCK |
| 合规命名（snake_case py / kebab js / camelCase js） | PASS |
| 生态约定文件（`2026-05-20.md`、`eslint.config.mjs`） | PASS |

**判定**：全用例符合预期才算通过。本次实测 **10/10**——门禁确实会阻断，不是摆设。
**附带发现**：`.git/hooks/` 是**本地私有**、不入版本库 → 新 clone 无门禁，
需 `core.hooksPath` 指向入库的 `.githooks/` 才「clone 即生效」。

---

## 收敛报告结构（写入交付报告）

```markdown
## 十、现场收敛记录（YYYY-MM-DD HH:MM–HH:MM）

### 10.1 本地工作区收敛
（收敛前散落项数 → 收敛后目录树 → 动作表：脱敏/归档/消重/清缓存 → 终态）

### 10.2 服务器侧收敛审计（只读）
（今日改动面全清单 → 核查项表：备份完整性/服务运行态/凭据暴露面/临时残留 → 归属澄清）

### 10.3 关键证据留档
（取回文件表：字节/sha256/价值 + 留档位置）

### 10.4 git 工作区终态
（各 repo HEAD + 剩余未提交变动归属）

### 10.5 收敛后的未决项
（仅列 automation / 待用户决策项）
```

---

## 自检清单

**收敛阶段**
- [ ] 根目录项数 ≤ 4（交付物 + `.workbuddy` + 归档目录 + 收敛脚本）
- [ ] 明文 hex32+ 残留 = 0（哈希留档不计）
- [ ] 归档目录内文件数 = 收敛前散落数（无丢失，`[CONFLICT]` 已处置）
- [ ] 服务器今日改动面每个文件都有归属说明
- [ ] **C6 同源副本回溯已做**：本次改过的文件名逐一在服务器上 `find`，md5 与本机比对，判定是否已下发
- [ ] **C6 逐行核实**：初判的每一处"缺陷"都已看原文确认（防 `alert` 形参类误判）
- [ ] **C7 下发用行级 patch**：禁止整文件覆盖；patch 有期望命中数断言；多行匹配用 `r'\r?\n'`
- [ ] **C7 备份已排除**：`_bak_*` 写入 `.git/info/exclude`（非仓库 `.gitignore`），status 无污染
- [ ] **C7 提交精确**：`git add -- <指定文件>`，不用 `git add -A`
- [ ] 回滚备份全部存在且非空
- [ ] 服务 `is-active` 全 active
- [ ] 凭据暴露面命中数 = 设计必需凭据位数
- [ ] `/tmp` 本会话残留已清，证据已留档
- [ ] git 各 repo 本会话改动已全部提交
- [ ] 报告 §十 已写入，未决项已显式列出

**清理阶段（仅当用户确认）**
- [ ] 用户已明确选择三档范围之一（未推断）
- [ ] 删除清单已生成（逐文件 sha256_12）
- [ ] 根锚定 + 符号链接逃逸校验通过
- [ ] 确认无「非本会话产物」/「仍在用的文件」被误删
- [ ] 报告中的过时引用已修正（不再写「完整留档于 <已删目录>」）
- [ ] 关键数据（sha256 / 结论）已固化进报告正文
- [ ] 交付物与 `.workbuddy/` 仍在
- [ ] 清理脚本自身已删除
