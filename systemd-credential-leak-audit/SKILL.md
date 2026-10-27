---
name: systemd-credential-leak-audit
display_name: "systemd 凭据泄漏审计与修复"
display_name_en: "systemd Credential Leak Audit"
description: "systemd 凭据泄漏进日志的排查与修复（含 EnvironmentFile 失效 + 命令行参数泄漏 + journald 扩散 + 存量脱敏 + 防再犯五层）。 当出现以下任一信号时触发：journalctl 里有 \"Ignoring invalid environment assignment\"、 journal/syslog/auth.log 里出现明文 token/密钥/密码、systemd 服务拿不到环境变量、 怀疑 EnvironmentFile 不生效、需要做凭据泄漏面专项审计、日志脱敏清理、 ExecStart 里把 token 当命令行参数传（-xxx.headers='Token: ...'）、 /proc/<pid>/cmdline 可读明文凭据、ProtectProc=invisible 不生效、 drop-in 配置被覆盖不生效（ForwardToSyslog / Storage / RuntimeMaxUse）、 修复过程中新增的备份/临时文件自己变成了新的明文副本、 需要判定 git 历史提交里的凭据是否已流出本机、 权限收紧（640 root:root）后要复核非 root 用户的任务是否失能。 核心价值：① EnvironmentFile 遇上 export 前缀不仅失效，还会把明文凭据写进 journal； ② 把 token 写进 ExecStart 命令行参数，会同时泄漏到 /proc/<pid>/cmdline 与 journal —— 比 EnvironmentFile 更隐蔽； ③ 修复动作自身（cp -a 备份含凭据文件）会制造新明文副本，脱敏必须覆盖备份； ④ token 泄漏判定为「未流出」时可按用户决策不轮换，但必须做暴露面全景核查与身份矩阵回归。 配套脚本：probe_envfile.sh（探测）/ generate_projection.sh（投影文件）/ scrub_logs.py（脱敏）/ verify.sh（终态校验）。"
description_zh: "systemd 凭据泄漏进日志的排查与修复：EnvironmentFile 失效、命令行参数泄漏、journald 扩散、存量脱敏与防再犯五层。"
description_en: "Troubleshoot and fix systemd credentials leaking into logs across five layers: broken EnvironmentFile, command-line argument leaks, journald spread, scrubbing existing data and preventing recurrence."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    location: user
    agent_created: "true"
---

# systemd-credential-leak-audit — systemd 凭据泄漏审计与修复

## 何时用

**高危信号（立即排查）**：

```bash
# ① EnvironmentFile 遇 export → 明文写 journal
sudo journalctl --no-pager 2>/dev/null | grep -c "Ignoring invalid environment assignment"

# ② 命令行参数带凭据 → /proc/<pid>/cmdline + journal 双泄漏
grep -rh 'ExecStart=' /etc/systemd/system/*.service 2>/dev/null \
  | grep -iE '(token|password|passwd|secret|api[_-]?key|headers)=\S*(token|[a-f0-9]{16,})'
```

任一返回值 > 0 → **凭据正在明文泄漏**，按本 skill 修复。

其他触发场景：

| 场景 | 说明 |
|------|------|
| 服务拿不到环境变量 | `EnvironmentFile=` 指向了 `.sh` 文件（带 `export`）→ 全部失效 |
| drop-in 改了不生效 | 跨目录排序陷阱（见 §3） |
| 日志里翻到明文密钥 | 存量清理（见 §4） |
| 需要做泄漏面专项审计 | 全流程走一遍 |

---

## ⚠️ 六个必须避开的雷区（血泪教训，先读这节）

这六条全部来自实战翻车，**任何一条踩中都会造成二次事故**：

### 雷区 0 —— 命令行参数是比 EnvironmentFile 更隐蔽的泄漏向量

`EnvironmentFile` 的泄漏是"写入失败时的副作用"；**命令行参数泄漏是无条件的** —— 只要凭据出现在 `ExecStart` 里，它就必然同时存在于两个地方：

```
ExecStart=/path/bin/app -notifier.headers='X-Push-Token: <48位token>'
                                    ↓
        /proc/<pid>/cmdline   ← 明文，进程生命周期内一直可读
        journal               ← 明文，程序启动时把 flag dump 出来
```

**实证（2026-09-30，vmalert）**：

```bash
$ tr '\0' ' ' < /proc/1176148/cmdline
/opt/victoriametrics/bin/vmalert -notifier.url=http://127.0.0.1:9997 \
  -notifier.headers=X-Push-Token: 9cbb0e72d9aa3d3a369edb5a2bf3b3308bef557dfae5334c  ← 完整明文

$ journalctl -u alert-vmalert | grep -o 'X-Push-Token: [a-f0-9]*'
X-Push-Token: 9cbb0e72d9aa3d3a369edb5a2bf3b3308bef557dfae5334c              ← vmalert 主动 dump

$ sudo -u workbuddy cat /proc/1176148/cmdline | grep -o 'X-Push-Token: [a-f0-9]*'
X-Push-Token: 9cbb0e72...                                                   ← 普通用户也能读
```

**为什么 `ProtectProc=invisible` 挡不住（重要，别踩）**：

`alert-vmalert.service.d/hide-proc.conf` 里已经写了 `ProtectProc=invisible`，**但实测无效**：

```bash
$ systemctl show alert-vmalert -p ProtectProc
ProtectProc=invisible          ← 配置生效了

$ sudo -u workbuddy cat /proc/1176148/cmdline    # 仍能读到
```

根因：`ProtectProc=invisible` 只隐藏**目录列举**（`ls /proc` 看不到），**不拦截显式指定 PID 的读取**。真正要挡住需要：

| 措施 | 效果 | 代价 |
|------|------|------|
| `/proc` 挂载加 `hidepid=2` | 彻底挡住跨用户读取 | 需改 `/etc/fstab` + remount，**影响全机所有进程，不建议** |
| `ProcSubset=pid` + `ProtectProc=invisible` | 隐藏 `/proc/<pid>/` 下的非 pid 文件 | 对 cmdline 本身无效 |
| **不把凭据放进命令行** | 根治 | **推荐，见下方修法** |

**根治修法**：改用「文件传参」型 flag，让 **只有路径进 cmdline**：

```bash
# ❌ 泄漏：值进 cmdline
-notifier.headers='X-Push-Token: ${ALERT_CORE_PUSH_TOKEN}'
-datasource.headers='Authorization: Bearer ${TOKEN}'
-remoteWrite.headers='X-Api-Key: ${KEY}'

# ✅ 安全：只有路径进 cmdline（token 落文件）
-notifier.bearerTokenFile=/opt/app/.push_token
-datasource.bearerTokenFile=/opt/app/.ds_token
```

```bash
install -o root -g root -m 640 /dev/null /opt/app/.push_token
# 写入后校验：ls -la 应为 -rw-r----- root root
```

**VictoriaMetrics 系（vmalert / vmagent / vminsert 等）可用 flag 速查**：

| 泄漏写法 | 替换为 | 版本要求 |
|---|---|---|
| `-notifier.headers='X-Push-Token: ...'` | `-notifier.bearerTokenFile=<path>` | 需接收端认 Bearer |
| `-datasource.headers='...'` | `-datasource.bearerTokenFile=<path>` | v1.x 均有 |
| `-remoteWrite.headers='...'` | 用 `-remoteWrite.config` 文件 | 较新版本 |

⚠️ **改前必查接收端**：`bearerTokenFile` 发的是 `Authorization: Bearer <token>`，而自定义 header 方案（如 `X-Push-Token`）接收端可能**只认自定义 header**。此时需**双向改**（发送端换 flag + 接收端加 Bearer 兼容分支），**任一侧漏改即 401 断链路**。改前务必只读确认接收端鉴权代码：

```bash
grep -n 'Authorization\|Bearer\|X-Push-Token\|_token_ok' /opt/app/app/main.py
```

**自查命令（加入日常巡检）**：

```bash
# 扫描所有单元的命令行凭据泄漏
for u in /etc/systemd/system/*.service; do
  if grep -qE 'ExecStart=.*(token|secret|password|api[_-]?key|headers)' "$u" 2>/dev/null \
     && grep -qE '[a-f0-9]{24,}' "$u" 2>/dev/null; then
    echo "❌ $u 命令行含疑似凭据"
  fi
done

# 扫描运行中进程的 cmdline
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null \
    | grep -qoE '(token|secret|password|api[_-]?key)[=:][A-Za-z0-9]{16,}' \
    && echo "❌ PID $pid: $(tr '\0' ' ' < /proc/$pid/cmdline | cut -c1-120)"
done
```

> **已泄漏 token 必须轮换**：一旦进了 journal 与 `/proc`，该 token 应视为已失效，修复前先轮换。

### 雷区 1 —— 绝不穿透符号链接（最危险）

```python
# ❌ 错误：is_file() 会跟随符号链接；write_text 会写到链接目标
for f in A.iterdir():
    if f.is_file():      # 符号链接指向的文件 → is_file() == True
        f.write_text(scrub(f.read_text()))   # 改写了线上真实配置！
```

**实证**：审计归档里有个 `cp -a` 从符号链接创建的"备份"，它本身还是链接 →
脱敏时穿透写入了线上 `/opt/.../configs/.env`，把 5 个真值替换成 `<REDACTED>`，
文件 1019→783 字节，**直接打断生产链路**。

```python
# ✅ 正确：显式排除符号链接
if f.is_symlink():
    continue
```

另外 `Path.rglob()` / `find -type f` **不会**跟随符号链接（安全），
但 `iterdir()` + `is_file()`、`os.walk` 默认 `followlinks=False` 也要留意。

### 雷区 2 —— 键名单必须取「全部配置源并集」

只读 `env.secrets.sh` 会漏掉 `env.sh` 独有的变量（实测 35 vs 73，漏一半）。

```bash
# ✅ 三源并集
for s in env.sh env.secrets.sh systemd.env; do
  grep -oP '^\s*(export\s+)?\K[A-Z_][A-Z0-9_]*(?==)' "$s"
done | sort -u
```

同时**校验来源数量**：若某个源提取出 0 个键，说明路径或正则有问题，应中止而非继续。

### 雷区 3 —— 排除 sudo 审计行（否则满屏假阳性）

`auth.log` / journal 里的 `COMMAND=/usr/bin/grep MASTER_KEY= /opt/app/.env`
会被 regex 当成 `MASTER_KEY=<值>`，**而"值"其实是文件路径**。
实测这类假阳性占报告命中的绝大多数（26 处日志 + 18 处 journal 全是它）。

```bash
grep -v 'COMMAND='      # ✅ 先排除
```

再配合「值首字符不得为 `/`」，双保险：

```python
re.compile(rf"({alt})[=:]\s*([A-Za-z0-9+][A-Za-z0-9+/=_.:@%~-]{{11,}})")   # 首字符排除 /
```

### 雷区 4 —— 符号链接权限恒为 777，别当"过宽权限"报

```
lrwxrwxrwx root root  configs/.env -> real.env      ← 777 是内核语义，无意义
```
用 `find -type f` 扫（跳过链接）；若必须显式检查，加 `! -type l`。

### 雷区 5 —— 不要留"脱敏前"的明文副本

「先备份再脱敏」听起来稳妥，但那备份**就是明文凭据的第二份拷贝**，
等于把刚修好的泄漏又存了一遍（实测副本含 33MB / 101 处明文）。

```bash
# ✅ 正确姿势
#   1. 就地脱敏（保留变量名 + 行结构 = 足够作证据）
#   2. 记录「文件名 + 命中数」到清单（manifest）作留证
#   3. 绝不留存未脱敏副本
```

> 同理：CI 里的 `--dry-run` 输出、临时 key 清单（`_sens_keys.txt`）用后即删。

#### 5.1 高危变体：**修复动作自身产生新明文副本**（2026-09-30 实测）

改一个含明文凭据的脚本时，若用 `cp -a <file> <file>.bak_<ts>` 做备份，
**这个 `.bak` 就是修改前的明文版本** —— 修好了主文件，却在旁边存了一份泄漏。

**实测一次踩中 3 处**：`.env.bak_loopback_*`、`.env.bak_pretoken_*`、脚本 `.bak_<ts>`
（均为「修改前」状态，各自含 1 处 48 位明文 token）。

**修复前/后的标准动作**：

```bash
# 改前：备份（对凭据类文件，备份必须择一）
#   方案 A（推荐）：不留备份，改错了从 git / 上游重新取
#   方案 B：备份后立即脱敏，并把脱敏版作为"回滚参考"
cp -a <file> <file>.bak_<ts>
sed -i -E 's/(TOKEN|KEY|SECRET)=.*/\1=<REDACTED>/I' <file>.bak_<ts>

# 改后：全机复检（这一步绝不能省，且必须覆盖 .bak / 归档 / 副本）
T="<凭据值>"
grep -rlF "$T" /opt /etc 2>/dev/null | grep -vE 'venv/|node_modules|__pycache__'
#   预期只剩「设计必需的凭据位」（如 .env + token 文件），多一个都是新泄漏
```

**判定哪些该保留**：现役应用真正读取的位置（systemd `EnvironmentFile=` 指向的 `.env`、
`bearerTokenFile` 指向的 token 文件）—— **这些是必需位，不脱敏**；
其余一切出现（`.bak`、`_archive/`、副本、`--dry-run` 产物）**一律脱敏**。

#### 5.2 判定「历史提交里的凭据」是否需要处置

git 历史含明文凭据时，**先判定是否已流出本机**，再决定动作：

```bash
# 1. 远端引用是否指向真实远端？
git remote -v                    # 若指向本地 bundle（/tmp/*.bundle）→ 未流出
git rev-parse origin/master 2>&1 # 与本地 master 比较

# 2. 含凭据的提交是否已在「远端的树」里
git merge-base --is-ancestor <bad_commit> origin/master && echo "已流出" || echo "未流出"
git grep -lF "<credential>" origin/master | wc -l    # 预期 0 = 未流出

# 3. 远端是否可达（不可达 = 无法推送 = 无流出风险）
git ls-remote <remote> 2>&1 | head -3
```

**判定表**：

| 情况 | 处置 |
|---|---|
| 未流出（远端为本地 bundle / 落后 / 不可达） | ✅ 只需**清理工作树 + 当前 HEAD**；**不做 `filter-repo`**（改全部 SHA、远端不可达无法同步，代价 > 收益） |
| 已流出到共享远端 | 🔴 **必须轮换凭据** + 按团队流程重写历史；仅重写无法收回已被 clone 的副本 |

> 关键认知：**「删掉当前文件」解决不了历史泄漏，「重写历史」也解决不了已 clone 的副本** ——
> 唯一真正有效的是**轮换凭据**。若业务决策不轮换，则必须显式记录该残留，不可假装已解决。

---

## 核心原理（必须理解，否则修不对）

### systemd `EnvironmentFile=` **不是 shell**

| 行为 | shell `source` | systemd `EnvironmentFile=` |
|------|----------------|----------------------------|
| 解析 `export K=V` | ✅ 正确设为 K=V | ❌ **整行非法** |
| 解析 `K=V # 注释` | 注释被剥离 | ❌ **注释并入变量值** |
| 解析 `$VAR` 引用 | 展开 | ❌ **按字面写入** |
| 解析 `K=$OTHER` | 展开 | 非法（systemd 要求 `K=` 后是字面） |
| 遇到非法行 | 通常报错 | **忽略该行 + journal warning 级记录完整原始行** |

**致命点**：最后一行——systemd 为了"帮助排查"，把**含明文值的完整原始行**以 warning 级别写进 journal。于是：

```
journal ──(ForwardToSyslog=yes 默认)──> /var/log/syslog ──> 也可能进 auth.log
```

一次 `export` 前缀的错误，就造成 **journal + syslog + auth.log 三处泄漏**，且 `journalctl` 是普通用户可读的（视 `journal` 目录权限）。

### 修复思路：**环境投影文件**

把「shell 脚本」投影为「systemd 可直接解析的纯 KV 文件」：

```
env.secrets.sh (shell, 带 export/注释/引用)  ──render──>  systemd.env (纯 KV)
        ↑ 人工维护、可 source                             ↑ 机器生成、权限 640、只给 systemd 读
```

---

## 修复五层（按顺序执行）

### Layer 0 — 消除命令行参数泄漏（新增，最优先）

命令行泄漏**无条件发生**（不像 EnvironmentFile 只在解析失败时泄漏），所以**先查这层**。

**Step 0.1 扫描**

```bash
# 全单元扫描
grep -rn 'ExecStart=' /etc/systemd/system/*.service 2>/dev/null \
  | grep -iE '(token|secret|password|api[_-]?key|headers)=' \
  | grep -E '[a-f0-9]{24,}|[A-Za-z0-9+/]{32,}={0,2}'

# 运行中进程扫描（含 drop-in 合并后的真实命令行）
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
  echo "$cmd" | grep -qoE '(token|secret|password|api[_-]?key)[=:][A-Za-z0-9]{16,}' \
    && echo "❌ PID $pid: ${cmd:0:140}"
done
```

**Step 0.2 判断接收端能接受什么形态**

```bash
# 只读确认接收端鉴权分支（示例：alert-core）
grep -n 'Authorization\|Bearer\|X-Push-Token\|_token_ok' /opt/app/app/main.py
```

三种结局：

| 接收端支持 | 修法 | 风险 |
|---|---|---|
| 原生 Bearer | 发送端改 `-xxx.bearerTokenFile`，一端改完 | 🟢 低 |
| 仅自定义 header（如 `X-Push-Token`） | **双向改**：发送端 `bearerTokenFile` + 接收端加 Bearer 兼容分支 | 🟡 中，任一侧漏改即 401 |
| 无法改接收端 | 退而求其次：`/proc` 挂 `hidepid=2`（影响全机，慎用） | 🔴 高 |

**Step 0.3 落地（以 vmalert 为例）**

```bash
# 落 token 文件
install -o root -g root -m 640 /dev/null /opt/app/.push_token
printf '%s' "$ALERT_CORE_PUSH_TOKEN" > /opt/app/.push_token
chmod 640 /opt/app/.push_token && ls -la /opt/app/.push_token   # 断言 -rw-r-----

# 改单元（删 headers，加 bearerTokenFile）
sed -i "s|-notifier.headers='X-Push-Token: \${ALERT_CORE_PUSH_TOKEN}'|-notifier.bearerTokenFile=/opt/app/.push_token|" \
  /etc/systemd/system/app.service
systemctl daemon-reload && systemctl restart app
```

**Step 0.4 验证（四项全过才算成功）**

```bash
# 1. 新进程 cmdline 无凭据
tr '\0' ' ' < /proc/$(pgrep -f 'app.*port'|head -1)/cmdline | grep -c 'X-Push-Token'   # 期望 0

# 2. journal 无新泄漏（限定时间窗，避开历史脏数据）
journalctl -u app --since '5 min ago' | grep -c 'X-Push-Token'                        # 期望 0

# 3. 链路未断 —— 关键：看接收端是否返回 200
tail -20 /opt/app/logs/app.log | grep -c ' 401 '                                      # 期望 0
curl -s http://127.0.0.1:<port>/healthz

# 4. 发送端注册的实际地址/凭证形态正确
curl -s http://127.0.0.1:<port>/metrics | grep -E 'alerts_sent_total|notifier'
```

**⚠️ 执行顺序铁律：接收端必须先改**

```
✅ 正确：接收端加 Bearer 兼容 → 重启 → 鉴权测试通过 → 发送端切 bearerTokenFile → 重启
❌ 错误：先改发送端 → vmalert 发 Bearer、接收端不认 → 401 断链路窗口
```

**⚠️ 第 3 项 401 计数的误判陷阱（本次实战踩坑）**

`grep -c ' 401 '` 会**把你自己的鉴权测试请求也算进去**。改完后若见 401 不为 0，先别回滚，按此判定：

```bash
# 判据 1（决定性）：发送端是否真的发出过请求？
curl -s http://127.0.0.1:<vmalert_port>/metrics | grep '^<svc>_alerts_sent_total'
#   若 addr 匹配且值为 0 → 发送端从未 POST → 所有 401 均非它产生 → 必为测试/他人残留

# 判据 2：401 的来源端口是否稳定递增（单进程顺序特征）
grep ' 401 ' /opt/app/logs/app.log | grep -oE '127\.0\.0\.1:[0-9]+' | tail -8
#   端口 52902→52968 递增 = 我方测试脚本顺序连发；若散布多 IP 才是真故障

# 判据 3：数量是否与你的测试用例数吻合
#   例：8 项测试含 6 项预期 401 → 恰好 6 条 = 自证
```

**结论**：`alerts_sent_total=0` 是判定的银弹 —— 发送端一次都没发，就不可能是发送端导致 401。

**⚠️ token 不轮换时的残留处置**

若业务/用户决策**不轮换 token**（接受历史泄漏既成事实），则：

| 残留位置 | 可否清除 | 处置建议 |
|---|---|---|
| `/proc/<old_pid>/cmdline` | ✅ 进程重启即消失 | 已完成（重启后旧 cmdline 随进程消亡） |
| journal 历史明文行 | ❌ **不支持按行删除** | 唯一手段 `journalctl --vacuum` 会连排障能力一并丢弃 → **判定不处理，但要显式记录** |
| `.env` / token 文件的明文 | ✅ 改 640 root:root | 见下方暴露面核查 |

**暴露面全景核查（改后必做，五处）**：

```bash
stat -c '%U:%G %a %s' /opt/app/.push_token                    # root:root 640
stat -c '%U:%G %a %s' /opt/app/.env                           # root:root 640（token 另一处明文位置！）
sudo -u <gcuser> test -r /opt/app/.push_token && echo yes || echo no   # no
P=$(systemctl show <svc> -p MainPID --value)
sudo -u <gcuser> sh -c "tr '\0' '\n' < /proc/$P/environ" 2>&1 | head -1 # Permission denied
cd /opt/app && git check-ignore -v .push_token .env           # 确认 .gitignore 覆盖
```

> **别遗漏 `.env`**：token 往往同时存在于 `EnvironmentFile` 指向的 `.env` 与新建的 `.push_token`。两处都要 640 root:root。
> **看 journal 可读性**：`groups <gcuser>` 若含 `systemd-journal`（常见），则 journal 泄漏对**该普通用户始终可读** —— 这是历史残留的真实暴露面，记录时不得回避。

> **默认应轮换 token**：已进 journal 与 `/proc` 的 token 应视为失效（见雷区 0 末尾铁律）。若用户决策不轮换（见上表），至少确认 journal 已按 Layer 2 收敛（`Storage=volatile` 或 `--vacuum`）+ 关键进程已重启（旧 cmdline 随进程消失），并把不轮换决策显式记录。

---

### Layer 1 — 消除产生源（投影文件）

**Step 1.1 确认是否存在带 `export` 的 EnvironmentFile**

```bash
# 找出所有被单元引用的 EnvironmentFile
grep -rh "^EnvironmentFile=" /etc/systemd/system/ /usr/lib/systemd/system/ 2>/dev/null \
  | sed 's/^EnvironmentFile=-\?//' | sort -u

# 逐个检查首字符（- 前缀表示文件不存在不报错）
for f in $(grep -rh "^EnvironmentFile=" /etc/systemd/system/ 2>/dev/null | sed 's/^EnvironmentFile=-\?//' | sort -u); do
  [ -f "$f" ] || continue
  n=$(grep -c "^[[:space:]]*export " "$f" 2>/dev/null)
  [ "$n" -gt 0 ] && echo "❌ 高危 $n 行 export: $f"
done
```

**Step 1.2 生成投影文件**

用 `scripts/generate_projection.sh`（核心逻辑，**引号感知剥离行内注释** —— 这是踩过坑的关键）：

```bash
# 关键函数：切掉行尾注释，但不能误伤引号内的 # （如 URL 里的 #、密码里的 #）
strip_inline_comment() {
  awk '{
    out=""; q=""; esc=0
    for (i=1; i<=length($0); i++) {
      c = substr($0, i, 1)
      if (esc) { out = out c; esc = 0; continue }
      if (c == "\\") { out = out c; esc = 1; continue }
      if (q != "") { if (c == q) q = ""; out = out c; continue }
      if (c == "\"" || c == "'"'"'") { q = c; out = out c; continue }
      # ← 只有不在引号内、且前面是空白/行首的 # 才是注释
      if (c == "#" && (i == 1 || substr($0, i-1, 1) ~ /[ \t]/)) break
      out = out c
    }
    sub(/[ \t]+$/, "", out); print out
  }'
}
```

投影规则：

| 输入 | 输出 | 说明 |
|------|------|------|
| `export K=V` | `K=V` | 剥 `export` 前缀 |
| `K=V # 注释` | `K=V` | 剥行内注释（引号感知） |
| `K="V"` | `K=V` | 剥包裹引号 |
| `K='$X'` | `K=$$X` | systemd 中 `$` 需转义为 `$$` |
| `# 整行注释` | 丢弃 | |
| 空行 | 丢弃 | |

**权限铁律**：`640`，属主 `root:workbuddy`（或服务运行用户），**绝不可 644**。

```bash
install -o root -g workbuddy -m 640 /dev/null /opt/<app>/.scripts/config/systemd.env
```

**Step 1.3 切换单元**

```ini
# 旧（错误）
EnvironmentFile=/opt/<app>/.scripts/config/env.sh
EnvironmentFile=-/opt/<app>/.scripts/config/env.secrets.sh

# 新（正确）
EnvironmentFile=/opt/<app>/.scripts/config/systemd.env
```

**切换后必须验证变量数**（最直观的成功信号）：

```bash
sudo systemctl daemon-reload && sudo systemctl restart <svc>
sudo systemctl show <svc> -p Environment | tr ' ' '\n' | grep -c '='   # 变量个数
```

> 实战参考：workbuddy `workflow-engine` 切换后 **11 → 84 个变量**。

**Step 1.4 单元合规校验（纳入 CI）**

```bash
# 断言：没有任何单元引用带 export 的文件
grep -rl "^[[:space:]]*export " /opt/<app>/.scripts/config/ 2>/dev/null | while read f; do
  grep -q "EnvironmentFile=.*$(basename $f)" /etc/systemd/system/*.service && echo "❌ $f 被单元引用且带 export"
done
```

---

### Layer 2 — 切断扩散（journald）

**Step 2.1 关闭 syslog 转发 + 限制 journal 体积**

⚠️ **这里有个必须知道的坑**：drop-in 的加载顺序是**按全路径字符串排序、跨目录生效**的。

```
/etc/systemd/journald.conf.d/90-workbuddy-hardening.conf
/usr/lib/systemd/journald.conf.d/syslog.conf          ← 全路径排序在 /etc 之后！
```

`syslog.conf` 里写的是 `ForwardToSyslog=yes`，**会覆盖** `/etc` 下 `90-` 的设置。因为字符串 `/usr/...` > `/etc/...`（`u` > `e`）。

**解法：用 `zz-` 前缀**，保证最后加载：

```
/etc/systemd/journald.conf.d/zz-workbuddy-hardening.conf
```

内容：

```ini
[Journal]
Storage=volatile          # 不落盘，内存中（重启即清）
RuntimeMaxUse=64M
MaxRetentionSec=6h
ForwardToSyslog=no        # 关键：切断 syslog 泄漏面
```

**Step 2.2 验证必须取「最后一条」**

```bash
# ❌ 错误：grep 取第一条，往往是编译期默认值
sudo systemd-analyze cat-config systemd/journald.conf | grep ForwardToSyslog | head -1

# ✅ 正确：取最后一条（后加载的胜出）
sudo systemd-analyze cat-config systemd/journald.conf \
  | grep '^ForwardToSyslog' | tail -1
```

**Step 2.3 实证「syslog 不再增长」**（最有说服力的验证）

```bash
sz1=$(stat -c%s /var/log/syslog)
logger "leak-drill-$(date +%s)"      # 故意产生一条日志
sleep 2
sz2=$(stat -c%s /var/log/syslog)
[ "$sz1" = "$sz2" ] && echo "✅ syslog 增量 0 字节（转发已切断）" || echo "❌ 仍在转发"
```

**Step 2.4 清理残留 journal**

```bash
# Storage=volatile 生效后，/var/log/journal/ 里的旧文件是 rotate 遗留，需主动清
sudo journalctl --vacuum-time=1s
# 确认活跃日志已迁至内存
ls -ld /run/log/journal/ && echo "✅ volatile 生效"
```

---

### Layer 3 — 清理存量（脱敏）

**铁律：变量名必须从 secrets 文件动态提取，不能靠人工名单。**

> 实战教训：首轮用人工名单漏了 `LLM_P5_KEY1/2/3/4`。

```bash
# 1. 动态提取全部变量名（含 ENC_ 解密后的逻辑名）
grep -oP '^\s*(export\s+)?\K[A-Z_][A-Z0-9_]*(?==)' /opt/<app>/.scripts/config/env.secrets.sh \
  | sort -u > /tmp/_sens_keys.txt
wc -l /tmp/_sens_keys.txt   # 确认数量（实战：73 个）

# 2. 生成匹配正则（只匹配「变量名 = 值」或「变量名: 值」形态）
#    值长度 >= 8 才算真泄漏，避免误伤 KEY=1 这种布尔
```

**必须穷举的日志位置**（易漏归档）：

```bash
/var/log/syslog
/var/log/syslog.1  /var/log/syslog.2.gz  /var/log/syslog.*.gz
/var/log/auth.log
/var/log/auth.log-*.gz          ← 极易漏
/var/log/<app>/*.log
/run/log/journal/               # volatile 模式下的活跃 journal
/var/log/journal/               # rotate 遗留
```

**脱敏方式（保留可审计，不破坏文件）**：

```bash
# 文本日志：原地替换为标记，保留行结构
sed -i "s/${VAR}=[^ ]\+/${VAR}=<REDACTED-$(date +%Y%m%d)>/g" "$logfile"

# 二进制 journal：导出→脱敏→重建（或在 journalctl 上加 --vacuum 后归档原件）
journalctl --file user-1002.journal --no-pager -o json \
  | jq -c 'if .MESSAGE then .MESSAGE |= gsub("...";"<REDACTED>") else . end' \
  | journalctl --file - --output=export   # 具体见 scripts/scrub_logs.py
```

**二次复检（必做）**：

```bash
# ⚠️ 关键：排除自己刚写入的 REDACTED 标记（否则假阳性）
for k in $(cat /tmp/_sens_keys.txt); do
  hits=$(sudo grep -a "${k}=[A-Za-z0-9+/=_-]\{8,\}" "$logfile" 2>/dev/null \
         | grep -vc 'REDACTED')
  [ "$hits" -gt 0 ] && echo "❌ 仍有 $hits 处: $k"
done
```

---

### Layer 4 — 防再犯

| 措施 | 实现 |
|------|------|
| CI 凭据扫描 | `.gitlab-ci.yml` 加 `security` stage，`grep -nE '(api[_-]?key\|token\|password\|secret)\s*=\s*["'\''][^"'\'']{12,}'` |
| **CI 命令行泄漏扫描** | `grep -rn 'ExecStart=' /etc/systemd/system/ \| grep -iE '(token\|secret\|password\|headers)=' \| grep -E '[a-f0-9]{24,}'` —— 命中即失败 |
| pre-commit 拦截 | `.scripts/hooks/block_credentials.sh` → 拦截 `*.env` `*.secrets.sh` 等被 `git add` |
| `.gitignore` 加固 | 追加 `*secrets*` `*.env` `!*.env.example` `.venv*/` `testenv/` `site-packages/` `*.so` |
| 单元合规校验 | 见 Layer 1 Step 1.4，纳入 CI |
| 投影文件自检 | 断言无 `export`、无行内注释残留 |
| **日常巡检** | 把雷区 0 的两条扫描命令加进巡检脚本，每周跑一次 |

⚠️ **CI 扫描的假阳性陷阱**：以下都是**安全**的，别误报——

```python
print("token = ...")              # 输出，不是赋值
if line.startswith("API_KEY=")    # 判断，不是赋值
API_KEY=your_key_here             # .env.example 占位符
```

---

## 配套脚本

| 脚本 | 用途 |
|------|------|
| `scripts/probe_envfile.sh` | 一键探测：export 前缀文件 + journal 泄漏条数 + 泄漏变量清单 |
| `scripts/generate_projection.sh` | 生成 systemd.env 投影文件（引号感知剥注释，已过 6 项边界测试） |
| `scripts/scrub_logs.py` | **脱敏首选**（Python，已规避全部 5 个雷区：符号链接防护 / 键并集 / sudo 行豁免 / 递归子目录 / gz 魔数识别） |
| `scripts/verify.sh` | 10 项终态校验（含 syslog 零增量实证） |

### scrub_logs.py 用法

> ⚠ **2026-10-15 起默认 dry-run**：不加 `--apply` 只预览命中、不写盘。
> 原实现默认就地改写（`write_text` 覆盖 + gz 重压），一次误跑即不可逆改写归档证据。

```bash
# 预览（默认模式，零落盘）
sudo python3 scrub_logs.py /var/log /opt/app/.state/_audit

# 实际脱敏（必须显式 --apply；键名单自动从同目录 env.sh/env.secrets.sh/systemd.env 探测）
sudo python3 scrub_logs.py /var/log /opt/app/.state/_audit --apply

# 显式指定键名单来源
sudo python3 scrub_logs.py /opt/app/.state/_audit --apply \
     --keys /opt/app/.scripts/config/env.sh /opt/app/.scripts/config/env.secrets.sh
```

已验证行为（Linux 端到端测试）：

| 场景 | 期望 | 实测 |
|------|------|------|
| 目录内含指向线上配置的符号链接 | 跳过、不穿透 | ✅ 线上文件完好 |
| sudo 审计行 `COMMAND=… grep KEY= /path` | 保留不误伤 | ✅ |
| 真凭据 `ZABBIX_TOKEN=<hex>` | 替换为 `<REDACTED>` | ✅ |
| 嵌套子目录中的凭据 | 递归处理 | ✅ |
| 符号链接本身 | 保留不删除 | ✅ |

> 为什么用 Python 不用 perl/sed：
> POSIX 字符类 `[[:space:]]` 直接内联进 `perl -pe "s/$RE/…/"` 会报
> `Unmatched [ in regex`（shell 变量插值 + perl 解析叠加），且引号嵌套极易出错。
> Python 的 `re` 无此问题，也便于加符号链接等安全护栏。

---

## 排错速查

| 现象 | 根因 | 修 |
|------|------|-----|
| **`/proc/<pid>/cmdline` 有明文 token** | **token 作为 ExecStart 参数传入** | **见雷区 0，改 `-xxx.bearerTokenFile`** |
| **`ProtectProc=invisible` 设了但 cmdline 仍可读** | **invisible 只隐藏目录列举，不拦截显式 PID 读取** | **不能靠它挡，须消除命令行凭据** |
| **journal 里程序主动 dump 出 flag 值** | **启动时打印 command-line flags** | **同上，值不进命令行即不会 dump** |
| `systemctl show -p Environment` 变量数远少于预期 | EnvironmentFile 带 `export` | 用投影文件 |
| `systemctl show -p Environment` 只有 1-2 个变量 | 它**只显示单元内联变量**，读不到 EnvironmentFile 注入的 | 改读 `/proc/<pid>/environ`（需 root） |
| 改了 drop-in 没生效 | 跨目录排序，`/usr` 排在 `/etc` 后 | 加 `zz-` 前缀 |
| `cat-config` 显示的值不对 | 看了首条（编译默认） | `tail -1` |
| `Storage=volatile` 后 `/var/log/journal/` 还有文件 | rotate 遗留 | `journalctl --vacuum-time=1s` |
| 脱敏后复检仍报命中 | 匹配到自己写的 REDACTED 标记 | 复检排除 `REDACTED` |
| 变量值含 `#` 被截断 | 注释剥离太粗暴 | 引号感知剥离 |
| 变量值含 `$` 变成空 | systemd 把 `$` 当变量引用 | 投影时 `$` → `$$` |
| 脱敏后服务挂掉 / 配置变小 | **穿透符号链接改写了线上文件** | 见雷区 1，立即用备份恢复 |
| 报告大量"泄漏"但看着都是路径 | sudo 审计行假阳性 | 见雷区 3 |
| 改 `bearerTokenFile` 后链路 401 | 接收端只认自定义 header，未加 Bearer 兼容 | 见雷区 0，双向改 |
| `logrotate` 报 `duplicate log entry` | 新建了同日志的 drop-in | logrotate **不允许重复定义**，就地改原文件 |
| `logrotate` 对 group-writable 目录拒转 | 缺显式 `su` | 加 `su <user> <group>` + `create` |
| 生产服务 `Restart=always` 陷入崩溃循环 | 端口未释放 / 配置缺失 | 回滚到已知good态，再离线分析 |

---

## 实战基线（可对照）

### 基线 1：workbuddy 服务器 2026-09-18（EnvironmentFile 类）

| 指标 | 整改前 | 整改后 |
|------|--------|--------|
| journal 泄漏条数 | 326 | **0** |
| 涉及敏感变量 | 70+ | 0 |
| workflow-engine 环境变量 | 11 | **84** |
| journal 磁盘占用 | 204.8 M | **16.0 M** |
| syslog 转发增量 | 持续增长 | **0 字节** |
| 存量残留 | 176 处 | **0** |

### 基线 2：vmalert 命令行参数泄漏 2026-09-30（命令行类，已修复）

| 项 | 实测 |
|---|---|
| 泄漏位置 | `/proc/<pid>/cmdline` + `journalctl -u alert-vmalert` 双处 |
| 泄漏内容 | `X-Push-Token: <48 位明文>` |
| 可读性 | **普通用户 `workbuddy` 可读**（`sudo -u workbuddy cat /proc/<pid>/cmdline`） |
| 已有防护 | `ProtectProc=invisible`（drop-in），**实测无效** |
| 平台 | Ubuntu，`/proc` 挂载 `rw,nosuid,nodev,noexec,relatime`，**无 hidepid** |
| 修法 | vmalert 改 `-notifier.bearerTokenFile` + alert-core 加 Bearer 兼容分支（双向改） |
| **落地结果** | ✅ 已修复。`cmdline_token_hit=0`；journal 新增明文 `0`（残留 1 条改前历史行，判定不处理）；8/8 双凭证鉴权测试通过；`vmalert_alerts_sent_total` 正常 |
| **token 处置** | **用户决策不轮换**，仅改注入方式；`.push_token` = `root:root 640 49B`，`workbuddy` 不可读 |
| **验证踩坑** | 收尾见 `recent_401=6` 曾疑断链路 → 取证为**我方鉴权测试残留**（`alerts_sent_total=0` 银弹 + 端口递增 + 6 项预期 401 精确对应） |

> 两个基线说明：**EnvironmentFile 类和命令行类是两条独立路径，必须分别审计**。前者查 journal warning，后者查 `ExecStart` 与 `/proc/*/cmdline`。
>
> **命令行的隐蔽性被本次实证确认**：`ProtectProc=invisible` 只隐藏**其他用户的进程目录条目**，对**显式指定 PID 的读取**完全不拦。真正能挡的是 `ProcSubset=pid` + 正确的 `ProtectProc` 组合，或 `/proc` 挂载 `hidepid=2`。**不要指望 `ProtectProc` 单独生效。**
