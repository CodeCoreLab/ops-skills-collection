# 真实案例：workbuddy 服务器 P0-NEW 凭据泄漏（2026-09-18）

本文件是 `systemd-credential-leak-audit` skill 的实战溯源记录，供对照参考。
**案例价值**：一个字母（`export` 前缀）造成 326 条凭据明文泄漏，波及 70+ 变量，
含可解密全部密文的 `MASTER_KEY`，且靠常规巡检完全看不见。

---

## 1. 发现经过

在实施「环境变量注入」整改时，顺手看 `journalctl`，撞见：

```
systemd[1]: workflow-engine.service: Ignoring invalid environment assignment
    'export MASTER_KEY=prsVlqnBygQESGoDHE33ASdti44rPaCIYQGwkqdX/vs=':
    /opt/workbuddy/.scripts/config/env.secrets.sh
```

**当时的状态**：这个问题**不在任何整改清单里**。P0 清单 16/16 已清零，
P1 第一批 12 项已闭环 —— 但没人发现凭据正被系统日志持续记录下来。

**结论**：清单式整改有盲区。必须主动做「泄漏面探测」而非只照单执行。

---

## 2. 根因链

```
env.secrets.sh 每行带 export（35 行）
        │
        ▼
单元 EnvironmentFile= 指向该文件
        │
        ▼
systemd 不执行 shell → 判定整行非法
        │
        ▼
journal warning 级记录「完整原始行，含明文值」  ← 泄漏点
        │
        ▼
journald ForwardToSyslog=yes（默认值）
        │
        ├──▶ /var/log/syslog          326 条
        └──▶ /var/log/auth.log        连带
                    │
                    ▼
logrotate 归档 → syslog.2.gz / auth.log-*.gz   ← 二次深埋，grep 不到
```

**独立泄漏通道**：`/var/log/auth.log` 另有 8/31 的
`sudo bash -c 'export VMA_TOKEN=...'` **命令行审计记录** ——
这是 sudo 审计的正常行为，与 EnvironmentFile 无关，但同样把凭据写进了日志。

---

## 3. 泄漏的变量（部分，均为明文）

| 变量 | 危害等级 |
|------|---------|
| `MASTER_KEY` | 🔴 **最高** —— 可解密全部 `ENC_*` 密文，等于所有凭据失效 |
| `WIKI_ADMIN_PASSWORD` | 🔴 后台管理密码 |
| `LLM_API_KEY` | 🔴 LLM 调用额度 |
| `ZABBIX_TOKEN` | 🟡 监控读写 |
| `ALERT_MYSQL_PASSWORD` | 🔴 数据库 |
| `RELAY_TOKEN` / `VMA_TOKEN` | 🟡 告警链路 |
| `AIREPORT_SESSION_SECRET` | 🟡 会话伪造 |
| `LLM_P5_KEY1~4` | 🟡 曾被人工资讯名单漏掉 |

> **教训**：脱敏必须**从 secrets 文件动态提取全部变量名**。
> 人工名单首轮漏了 `LLM_P5_KEY1~4`，改用动态提取（73 个变量名）后才穷举命中。

---

## 4. 四层修复与实测数据

### Layer 1 — 消除产生源

```bash
render_systemd_env.sh  env.secrets.sh -> systemd.env
```

| 项 | 值 |
|----|-----|
| 输出 | `/opt/workbuddy/.scripts/config/systemd.env` |
| 变量数 | 73 |
| 权限 | 640 root:workbuddy |
| workflow-engine 生效变量 | **11 → 84** |
| 关键变量注入 | 42 个 ✅ |

**首版踩坑**：投影文件残留 2 处行内注释 ——
`GLOAM_PREROUTER_MODEL=/opt/... # 注释`、`LLM_CONFIG_PULL_SSH=0 # 注释`。
systemd 会把注释**并入变量值**。→ 重写生成器，加**引号感知**的注释剥离。

### Layer 2 — 切断扩散

```ini
# /etc/systemd/journald.conf.d/zz-workbuddy-hardening.conf   ← zz- 是关键
[Journal]
Storage=volatile
RuntimeMaxUse=64M
MaxRetentionSec=6h
ForwardToSyslog=no
```

**踩坑**：首版用 `90-` 前缀，**不生效**。

```
/etc/systemd/journald.conf.d/90-workbuddy-hardening.conf     ← 先加载
/usr/lib/systemd/journald.conf.d/syslog.conf                 ← 后加载，设 yes，覆盖！
```

drop-in 按**全路径字符串**排序跨目录生效，`/usr` > `/etc`（`u` > `e`）。→ 必须 `zz-`。

**二次踩坑**：验证时 `grep ... | head -1` 取到编译期默认值，误判"未生效"。
→ 必须 `| tail -1`。

| 实测 | 结果 |
|------|------|
| syslog 增量 | **0 字节** |
| journal 磁盘 | 204.8M → **16.0M** |

**三次踩坑**：`Storage=volatile` 后 `/var/log/journal/` 目录仍在 →
实为 rotate 遗留文件未清，`/run/log/journal/` 已有活跃目录说明已生效。
→ `journalctl --vacuum-time=1s` + 归档 `user-1002.journal`。

### Layer 3 — 清理存量

穷举位置（**归档 gz 最易漏**）：

| 位置 | 命中 |
|------|------|
| /var/log/auth.log | 11 |
| /var/log/syslog.2.gz | 104 |
| /var/log/auth.log-2026...gz | 58 |
| /var/log/morning_inspection.log | 1 |
| user journal | 2 |
| **合计** | **176 处** |

**复检踩坑**：首轮复检报"syslog 剩 40 处" —— 实为**自己刚写入的
`<REDACTED-20260918>` 标记**被正则二次匹配（假阳性）。
→ 复检脚本必须 `grep -vc 'REDACTED'`。

终态：**0 残留**。

### Layer 4 — 防再犯

- 单元合规校验（无单元引用带 `export` 的文件）
- 投影文件自检（无 export / 无行内注释 / 无引号）
- `.gitlab-ci.yml` security stage
- `.pre-commit-config.yaml` + `.scripts/hooks/block_credentials.sh`

---

## 5. 可复用的排查顺序

```bash
# ① 30 秒自查（最高优先级）
sudo journalctl --no-pager | grep -c "Ignoring invalid environment assignment"

# ② 有命中 → 一键探测
sudo bash scripts/probe_envfile.sh /opt/<app>/.scripts/config/env.secrets.sh

# ③ 生成投影文件
bash scripts/generate_projection.sh env.secrets.sh systemd.env root:workbuddy

# ④ 切单元 + 验证变量数
sudo systemctl daemon-reload && sudo systemctl restart <svc>
sudo systemctl show <svc> -p Environment | tr ' ' '\n' | grep -c '='

# ⑤ 关转发（zz- 前缀！）
sudo systemctl restart systemd-journald

# ⑥ 脱敏
sudo bash scripts/scrub_logs.sh env.secrets.sh --dry-run   # 先看
sudo bash scripts/scrub_logs.sh env.secrets.sh             # 再改

# ⑦ 终态 10 项校验
sudo bash scripts/verify.sh workflow-engine health-check
```

---

## 6. 通用性

本案例**不限于 workbuddy**。任何满足以下条件的系统都有同样风险：

- 用 shell 脚本（`.sh`）承载环境变量，且带 `export`
- systemd 单元用 `EnvironmentFile=` 引用它
- journald 保持默认 `ForwardToSyslog=yes`

**自查一句话**：`grep -rl '^\s*export ' /etc/systemd/system/ --include='*.service'` 看不到，
要查单元引用的**目标文件**本身。这是它隐蔽的原因 —— 单元文件看起来完全正常。
