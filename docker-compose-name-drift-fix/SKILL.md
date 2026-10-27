---
name: docker-compose-name-drift-fix
display_name: "Docker Compose 容器名漂移修复"
display_name_en: "Docker Compose Name Drift Fix"
description: "Docker Compose 容器名漂移 / 「容器未运行」误报的诊断与修复。当健康检查、监控告警 或巡检报告声称某容器「未运行 / not running / absent」，但 `docker ps -a` 里容器其实 在跑（只是名字不对）时使用。典型触发：健康检查脚本用硬编码容器名 `docker ps --filter name=<期望名>` 查不到；compose 文件被移动到子目录后项目名变成 目录名；同机多 compose 项目互相干扰；`docker compose down` 拆错项目。 也覆盖配套的「配置降级」隐性故障（compose `${VAR}` 无默认值 + 残缺 .env → 变量静默为空）。 触发词：容器未运行、容器名漂移、container not running、compose 项目名、 monitor-console 容器告警、健康检查误报、configs-backend。"
description_zh: "诊断与修复 Docker Compose 容器名漂移导致的「容器未运行」误报，以及 compose 变量无默认值引发的配置降级故障。"
description_en: "Diagnose and fix false 'container not running' reports caused by Docker Compose container name drift, plus the silent config degradation that comes from compose variables with no default."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
---

# docker-compose-name-drift-fix — 诊断与修复

## 何时用

| 触发信号 | 说明 |
|---|---|
| 健康检查/监控报「容器未运行」，但 `docker ps -a` 里容器**在跑** | 名字漂移导致的**误报** |
| 容器名是 `configs-backend-1` 这类**目录名**前缀，而非期望的服务名 | compose 项目名 = 目录名 |
| compose 文件被重构移动到子目录后，监控开始报错 | 项目名随目录变 |
| 同机多个 compose 项目，想精准拆某一个 | 用 `-p <项目名>` |

**核心判据**：报「未运行」≠ 真宕机。先 `docker ps -a` 看实况，再看**期望名 vs 实际名差在哪**。

---

## 根因模型

Compose 容器名 = `<项目名>-<服务名>-<序号>`。**项目名来源优先级**：

1. `docker compose -p <名字>`（CLI 显式）
2. compose 文件顶部的 `name:` 字段
3. `COMPOSE_PROJECT_NAME` 环境变量
4. **compose 文件所在目录名**（默认，最易漂移）

> ⚠️ 常见事故：compose 文件被从 `monitor-console/docker-compose.yml` 重构到
> `monitor-console/configs/docker-compose.yml`（如「模块化」重构），目录名从
> `monitor-console` → `configs`，项目名随之改变，容器名从 `monitor-console-backend-1`
> → `configs-backend-1`。**任何硬编码 `monitor-console-backend-1` 的监控脚本立即失效。**

---

## 标准流程

### Step 1 — 核实实况（只读，别急着动手）

```bash
# 容器到底在不在？（按名字模糊查，不要只信精确 filter）
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

# 报错项实际名字可能是什么？按关键词宽匹配
docker ps -a --filter "name=<关键词>" --format "{{.Names}}\t{{.Status}}"

# 列出所有 compose 项目及其 config 文件（一眼看出项目名漂移）
docker compose ls -a

# 查某容器的真实项目名 / config 路径 / 工作目录
docker inspect <实际容器名> --format \
  '{{index .Config.Labels "com.docker.compose.project"}} | {{index .Config.Labels "com.docker.compose.project.config_files"}} | {{index .Config.Labels "com.docker.compose.project.working_dir"}}'
```

### Step 2 — 定位期望名（谁硬编码了它）

```bash
# 期望名来自哪个监控/健康检查脚本
grep -rln "<期望容器名>" /opt /etc 2>/dev/null | grep -vE "node_modules|/data/|\.log"
# 例：healthcheck_monitor.py 里 container="monitor-console-backend-1"
```

### Step 3 — 甄别是否附带「配置降级」（关键，别只修名字）

**compose 里无默认值的 `${VAR}` 在缺 `.env` 时会静默为空**，服务带错配置运行——比宕机更隐蔽。

```bash
# 看 compose 依赖哪些变量
grep -oE '\$\{[A-Z_]+\}' <compose文件> | sort -u
# 逐变量核对：在哪个 .env？值非空吗？
for v in ORIGINAL_API_BASE INFLUX_TOKEN SECRET_KEY; do
  l=$(docker inspect <容器名> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep "^$v=" | cut -d= -f2-)
  echo "  $v = ${#l} chars  $([ -z "$l" ] && echo '⚠️ 空!')"
done
```
- 比对**多个 .env 文件的键集**：残缺的那个（键少/值空）就是错误来源。
- **权威 .env 判定**：键集最全、值非空、mtime 稳定（非最近被误写）的那个。
- `SECRET_KEY` 的 sha256 指纹可用来确定容器到底加载了哪个 .env。

### Step 4 — 改前备份（铁律：暂停→备份→修改→验证→恢复）

```bash
TS=$(date +%Y%m%d_%H%M%S)
cp -a <compose目录>/.env                <compose目录>/.env.bak_$TS
cp -a <compose目录>/docker-compose.yml  <compose目录>/docker-compose.yml.bak_$TS
```

### Step 5 — 修复（两件套：钉项目名 + 补全配置）

```bash
# (a) 钉项目名 —— 在 compose 顶部加 name:（消除目录名依赖）
#     已存在 name: 则跳过；目标 = 期望容器名的前缀
python3 - <<'PY'
p="/opt/workbuddy/<...>/configs/docker-compose.yml"
t=open(p,encoding="utf-8").read()
if not t.startswith("name:"):
    open(p,"w",encoding="utf-8").write("name: monitor-console\n\n"+t)
PY

# (b) 补全配置 —— 用权威 .env 覆盖残缺 .env
cp -a <项目根>/.env <compose目录>/.env && chmod 600 <compose目录>/.env

# (c) 校验语法
cd <compose目录> && docker compose config --quiet && echo OK
```

### Step 6 — 精准重建（不伤同机其他项目）

```bash
cd <compose目录>
# 拆旧项目（用旧项目名，不是目录名之外的猜测）
docker compose -p <旧项目名> down --remove-orphans
# 以钉住的名称重建
docker compose up -d --build
```

### Step 7 — 终态验证（五查）

```bash
docker ps -a --filter "name=<新前缀>" --format "table {{.Names}}\t{{.Status}}"   # 名称+healthy
for v in <关键变量>; do docker inspect <容器> --format '...' | grep "^$v="; done   # env 非空
curl -s http://127.0.0.1:<backend端口>/health                                    # 服务可用
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<frontend端口>/        # 200
docker ps -q | wc -l                                                             # 总数未减少
```

### Step 8 — 防复发（监控脚本侧）

- **首选**：修 compose（钉 `name:`），监控脚本不动 → 名字从此稳定。
- **备选**：修监控脚本，改成**宽匹配**或环境变量可配：
  ```python
  # 弱化：name 前缀 + 服务名，容忍项目名变化
  ["docker","ps","--filter","name=<服务名>","--filter","status=running"]
  ```
- **刷新清单**：若项目有 `MANIFEST.json` 之类索引，重建它（`build_system_manifest.py`）。

---

## 雷区

1. **把「名字漂移误报」当成「服务宕机」去重启** → 重启出来的还是错误配置（若同时有配置降级）。
   必须先 `docker ps -a` 确认真实状态。
2. **只修名字、漏修配置** → 容器名对了、监控绿了，但服务仍在用空 API_BASE 运行。
   **名称漂移常与配置降级同时发生**（都源于一次不当的重部署），务必两查。
3. **`docker compose down` 不加 `-p`** → 在错误目录执行会拆掉**当前目录项目**，可能误伤。
   明确指定 `-p <目标项目名>`。
4. **compose 目录名 ≠ 项目名时**（如 `configs/`）→ 不要假设 `docker compose down` 能拆对；
   看 `docker compose ls -a` 的 NAME 列。
5. **sed 掩码会骗你**：`sed 's/=(.{0,6}).*/=\1…/'` 会把空值也显示成非空。
   判断空值用 **`${#var}` 长度**，不用正则替换后的肉眼看。
6. **备份井喷**：每次改动都 `cp` 备份，目录会堆几十个 `.bak_*`。约定只保留最近 3 个，
   旧的手工/脚本清理（走回收站，非 `rm`）。

---

## 实战场次（2026-10-06，monitor-console）

- **告警**：`container:monitor-console-backend/frontend` 未运行（关键 2/25）。
- **根因**：compose 移到 `configs/` → 项目名 `configs` → 容器 `configs-*-1`；
  健康脚本硬编码 `monitor-console-*-1`。同时 `configs/.env` 残缺（仅 SECRET_KEY）→
  `ORIGINAL_API_BASE`/`INFLUX_TOKEN`/`AIOPS_AI_*`/`ALERT_CORE_ADMIN_TOKEN` 全空。
- **修复**：钉 `name: monitor-console` + 用 `monitor-console/.env`（13 键）覆盖 + 精准重建。
- **验收**：`monitor-console-backend-1`(healthy)/`-frontend-1`；env 全非空；
  18001=ok、18080=200；健康检查 **25/25**；其他 12 容器未受影响。
