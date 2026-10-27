---
name: linux-perf-tuning
display_name: "Linux 性能调优"
display_name_en: "Linux Performance Tuning"
description: "Linux 系统性能调优端到端流程。当出现 load 高但 CPU 空闲、CPU 使用率异常（%usr/%sys/%si/%st 高）、内存告警、磁盘 IO 慢（await 高、IOPS 打满）、网络丢包重传，或新机器上线需要建性能基线时使用。覆盖 USE 方法论、三板斧首查、决策树、12 条误判、变更纪律、三层验收、回滚方案、新机器基线 14 项检查单，对接 alert-core / VictoriaMetrics / PromQL。不适用于需要深入内核源码/eBPF 高级用法的问题。"
description_zh: "Linux 系统性能调优端到端流程：USE 方法论、三板斧首查、决策树、误判清单、变更纪律、三层验收与回滚方案。"
description_en: "An end-to-end Linux performance tuning workflow: USE methodology, fast first checks, decision trees, misdiagnosis lists, change discipline, layered verification and rollback planning."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
    when_to_use:
      - 服务器性能异常，需要定位瓶颈在 CPU / 内存 / IO / 网络哪个子系统
      - load 高但 CPU 空闲，或 CPU 某段（%usr/%sys/%si/%st）异常
      - 内存告警、OOM、swap 抖动导致业务卡顿
      - 磁盘 await 超参考线、IOPS 打满、云盘限流
      - 新机器上线前的性能基线检查
      - 云上实例性能不达标（steal、云盘限流）
    trigger_words:
      - 性能调优
      - load 高
      - CPU 慢 / CPU 高
      - IO 慢 / 磁盘慢
      - 内存告警
      - OOM
      - 新机器上线
      - 性能基线
      - 延迟毛刺
      - await 高
      - softirq / 软中断高
      - steal 高
---

# linux-perf-tuning — Linux Perf Tuning

## 定位

给 39 台生产服务器（Ubuntu 20.04+ / 内核 6.x）的性能异常提供**可复用的排查 + 调优 + 验收 + 回滚**闭环。默认按「观测 → 定位 → 假设 → 最小改动 → 验证」推进，绝不跳过基线采集。

## 铁律（不可绕过）

1. **先基线再动手**：任何调优前先跑 `scripts/baseline_collect.sh`，改前改后各一份，同口径对比。
2. **一次只改一个参数**：同时改三个，效果无法归因，回滚无法定位。
3. **改前写清"怎么证明有效"**：指定观察指标和目标值，不用"感觉流畅了"验收。
4. **改动必须留回滚路径**：所有参数改动有备份文件、有恢复命令，写在工单里。
5. **生产先灰度**：单机 → 观察一个业务高峰 → 再扩大范围。
6. **优先应用层，最后加硬件**：80% 性能问题在应用（烂 SQL / 缓存击穿 / 线程池），调内核参数通常是止痛药。

## 一、核心方法论

### USE 方法（每个资源看三维度）

| 资源 | Utilization | Saturation | Errors |
|------|-------------|------------|--------|
| CPU | %usr/%sys | run queue、上下文切换 | steal |
| 内存 | used/available | swap io、direct reclaim | OOM |
| 磁盘 | %util、带宽 | IO 队列深度、await | IO error、只读挂载 |
| 网络 | 带宽占比 | backlog、drop | retrans、CRC |

**核心思想**：利用率没满不代表没饱和，饱和了不代表已出问题，三维一起看。

### load average 的正确读法

`ps -eLo stat | grep -c '^R'`（运行态）、`ps -eLo stat | grep -c '^D'`（不可中断睡眠，绝大多数在等磁盘）。

- R 多 D 少 → 往 CPU 查
- D 多 R 少 → 往 IO 查
- 1min > 15min → 恶化中；1min < 15min → 在恢复
- 参考线：load/核数 < 0.7 正常，持续 > 1.5 且伴随延迟上升要介入

### CPU 使用率五分解

| 段 | 高时查什么 |
|----|-----------|
| %usr | 应用真在算：算法、序列化、压缩、死循环 |
| %sys | 系统调用频繁：小 IO、内存拷贝、锁竞争 |
| %wa | 磁盘慢 / IO 量大 / 存储链路问题 |
| %si | 高包量网络：网卡中断集中单核，需 RPS/RSS 调优 |
| %st | 云主机宿主机超卖，找云厂商 |

### 内存：看 available 不看 free

`free -h` 里 `available` 才是内核估算"不触发 swap 还能给应用用多少"，这是判断内存压力的关键指标。buff/cache 大不是泄漏。

**周期性卡顿优先怀疑**：Dirty 页集中回写（`grep Dirty /proc/meminfo` 观察曲线）+ 定时任务叠加。

### 磁盘 IO 四指标

| 指标 | 说明 |
|------|------|
| `r/s` `w/s` | IOPS，与标称对比 |
| `rkB/s` `wkB/s` | 带宽，与标称对比 |
| `r_await` `w_await` | **最关键**：请求平均延迟（含排队，ms） |
| `aqu-sz` | 队列深度，持续 > 盘并行度 = 饱和 |

**await 判断**：
- await 高 + aqu-sz 高 → 盘被打满，减 IO 或换快盘
- await 高 + aqu-sz ≈ 0 + 带宽没满 → **盘本身劣化**（SSD 掉速、坏道、存储网络），赶紧迁移数据

**不同介质 await 参考线**：NVMe < 0.2ms 正常 / > 1ms 关注；SATA SSD < 0.5ms / > 3ms；云盘 0.5~2ms / > 5ms；机械 7200 转 8~15ms / > 25ms。

**吞吐公式**：`吞吐 = IOPS × 平均 IO 大小`。用 `rkB/s ÷ r/s` 算平均读大小——如果是 4K 级而业务预期是大文件顺序读，说明访问模式变了（索引失效 / 缓存击穿 / 执行计划突变）。

## 二、三板斧首查（10 秒定位方向）

```bash
uptime                  # load 三值 + R/D 构成 → 判断类型
vmstat 1 3 | tail -1    # si/so 换页 + cs 切换 + wa 一屏看全
iostat -x -y 1          # 每设备 IOPS/await/util（-y 忽略首行历史均值）
```

## 三、排查决策树

```
业务变慢
├─ 1. uptime：load 相对核数如何？
│   ├─ load 高 + R 多 ─────────► CPU 型（分支 A）
│   ├─ load 高 + D 多 ─────────► IO 阻塞（分支 B）
│   └─ load 正常但仍慢 ────────► 应用/下游/网络（分支 C）
│
├─ A. CPU
│   ├─ mpstat：哪段高？
│   │   ├─ %usr 高 → pidstat -u → perf top → 业务函数
│   │   ├─ %sys 高 → strace -c -p <pid> → 系统调用分布
│   │   ├─ %si  高 → /proc/net/softnet_stat + ethtool -l eth0
│   │   └─ %st  高 → 云厂商/宿主机问题
│   └─ cs 高？→ pidstat -w 找切换大户 → 线程池/锁
│
├─ B. IO
│   ├─ iostat -x：哪块盘？await 超参考线？
│   │   ├─ IOPS/带宽打满 → iotop -oP → 备份/日志（错峰限速）or 业务进程（访问模式变）
│   │   └─ 量不高延迟高 → smartctl + 云监控限流 → 盘劣化/RAID 降级
│   └─ D 状态进程卡在哪？→ cat /proc/<pid>/wchan
│
└─ C. 非资源瓶颈
    ├─ sar -n DEV/TCP：网络层？
    ├─ 下游依赖慢：DB 慢日志 / Redis 延迟 / 第三方 API
    ├─ 锁/队列：应用线程池排队
    └─ GC：JVM GC 日志、内存回收风暴
```

**每个结论必须三件套**：指标异常 + 进程归属 + 时间线吻合，缺一不可。

## 四、分系统下钻要点

### CPU

```bash
mpstat -P ALL 1 3            # 每核分布，找单核满
pidstat -u 1 3               # 每进程 CPU
pidstat -w 1 3               # 每进程上下文切换
top -H -p <pid>              # 线程级
perf top -p <pid>            # 函数热点
cat /proc/interrupts         # 中断是否偏科
```

**可调动作**（按风险从低到高）：
- `renice +10 -p <pid>` / `nice -n 10 ./job.sh`（低风险）
- `systemctl set-property svc CPUQuota=200%`（中风险，别设太小）
- `taskset -cp 2-7 <pid>` 绑核，回滚 `taskset -cp 0-$(($(nproc)-1)) <pid>`
- `ethtool -L eth0 combined 8` 开多队列（%si 高时）
- `cpupower frequency-set -g performance`（延迟敏感场景）

### 内存

```bash
free -h
vmstat 1 5                   # si/so 换页速率
pidstat -r 1 5               # 每进程缺页
dmesg -T | grep -iE 'out of memory|oom'
grep -E 'MemAvailable|Dirty|SwapCached|Committed_AS' /proc/meminfo
sar -B 1 5                   # pgscand/s 扫描、pgstalt/s 直接回收
```

**关键 sysctl**：
```bash
sysctl -w vm.swappiness=1                # DB/缓存类建议 ≤ 10
sysctl -w vm.dirty_background_bytes=268435456  # 256MB 开始后台回写
sysctl -w vm.dirty_bytes=1073741824              # 1GB 才阻塞写
```

**THP**（DB/缓存类必须关）：
```bash
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag
# 持久化：GRUB_CMDLINE_LINUX 加 transparent_hugepage=never
```

### IO

```bash
iostat -x 1
iotop -oP -d 1                # 找 IO 大户
pidstat -d 1 3
cat /proc/<pid>/io            # 进程 IO 明细
smartctl -a /dev/sda | grep -E 'Reallocated|Pending|Uncorrect'
# NVMe:
smartctl -a /dev/nvme0n1 | grep -E 'Percentage Used|Available Spare'
df -h; df -i; mount | grep ' /data '
```

**调度器选择**：NVMe → `none`；SATA SSD → `mq-deadline`；桌面 → `bfq`。

**持久化**（`/etc/udev/rules.d/60-iosched.rules`）：
```
ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
ACTION=="add|change", KERNEL=="nvme[0-9]n[0-9]", ATTR{queue/scheduler}="none"
```

**应急限速**（不动 fstab 的软控）：
```bash
systemctl set-property backup.service 'IOWriteBandwidthMax=/dev/sda 20M'
```

### 网络

```bash
sar -n DEV 1 3; sar -n EDEV 1 3; sar -n TCP 1 3
ss -s; netstat -s | grep -iE 'retrans|listen|overflow'
cat /proc/net/softnet_stat    # 第 2/3 列增长 = 积压/丢包
ethtool -S eth0 | grep -iE 'drop|err|discard'
```

## 五、12 条常见误判

1. **把 buff/cache 当泄漏**——available 充足就正常。
2. **用 free 判断水位**——看 available + si/so + PSI + cgroup 限额。
3. **SSD 上 %util 下结论**——SSD 可并行处理，await 才是关键。
4. **只看平均值**——延迟用 P99/P999，`scripts/iostat_percentiles.sh` 算分位。
5. **iostat 首行当实时值**——第一段是开机累计均值，加 `-y` 或用第二段。
6. **load 高就重启**——D 状态堆积时重启掩盖问题，还可能丢未落盘数据。
7. **短测 SSD 下结论**——SLC 缓存没耗尽前数据偏乐观 3~10 倍，稳态跑 ≥ 30 分钟。
8. **同时改多个参数**——无法归因，回滚无法定位。
9. **拿网上脚本直接跑 sysctl**——内核/业务/发行版差异大，先看参考线。
10. **高峰期跑 fio**——压测流量与业务叠加，压测本身变故障源。
11. **跨机对比不校时**——`chronyc sources` 偏差 < 50ms 才能对时间线。
12. **只看机器不看依赖**——机器全绿但业务慢，瓶颈在下游概率远大于"隐藏问题"。

## 六、一页速查卡

| 症状 | 命令 | 判断 | 动作 |
|------|------|------|------|
| load 高 | `ps -eLo stat \| grep -c '^D'` | D 多 → IO 型 | `iostat -x 1` 找慢盘 |
| CPU %usr 高 | `pidstat -u 1` → `perf top` | 业务函数热点 | 火焰图给应用侧 |
| CPU %si 高 | `/proc/net/softnet_stat` | 第 2/3 列增长 | 开网卡多队列、irqbalance |
| CPU %st 高 | `vmstat 1` st > 5% | 持续存在 | 找云厂商 / 换规格 |
| 内存告警 | `free -h` | available 低 | `smaps_rollup` 归因 |
| 卡顿毛刺 | `vmstat 1` si/so 列 | 持续非零 | 调 swappiness / 扩内存 |
| 延迟毛刺 | `/proc/meminfo` Dirty | 周期性尖峰 | 脏页参数 + 日志异步 |
| OOM | `dmesg -T \| grep -i oom` | 看打分表 | 限制元凶而非调 oom_adj |
| 磁盘慢（量大） | `iostat -x` | IOPS/带宽满 | 限速 / 错峰 / 换访问模式 |
| 磁盘慢（低量高延迟） | `smartctl` / 云监控 | 盘劣化 / 限流 | 迁移数据 / 升规格 |
| 一切正常但慢 | `sar -n DEV`、下游慢日志 | 机器全绿 | 转应用/依赖排查 |

## 七、变更纪律 + 三层验收 + 回滚

### 变更纪律

- 一次一改，改前备份原值，改前写清目标指标。
- 灰度：单机 → 观察一个业务高峰 → 扩大到 10% → 全量。
- 所有参数改动带工单：改了什么、为什么、谁批的、怎么回滚。

### 三层验收

1. **参数生效（分钟级）**：`sysctl X`、`cat /sys/block/*/queue/scheduler`、`systemctl show -p`、`cat /proc/<pid>/limits`。
2. **系统指标（小时级）**：同口径、同负载时段对比变更前后同类命令输出。
3. **业务指标（覆盖一个高峰）**：P99/P95 达目标、错误率无上升、吞吐无下降、w_await 尖刺消失。

### 回滚表

| 改动 | 回滚 | 生效 |
|------|------|------|
| `sysctl -w` 临时 | `sysctl -w 参数=原值` | 即时 |
| `/etc/sysctl.d/99-*.conf` | 删文件 + `sysctl --system` | 即时+重启 |
| tuned profile | `tuned-adm profile <原profile>` | 秒级 |
| IO 调度器 | `echo 原值 > /sys/block/X/queue/scheduler` | 即时 |
| THP 临时 | `echo always > /sys/kernel/mm/transparent_hugepage/enabled` | 即时 |
| grub 参数 | 恢复 `/etc/default/grub` 备份 → `grub2-mkconfig` → 重启 | 需重启 |
| cgroup/ulimit | 恢复原值/原 limits 文件 | 下次启动服务 |
| 绑核 | `taskset` 恢复全核 | 即时 |

## 八、新机器上线基线 14 项（对接 Ansible）

由 `scripts/newhost_baseline_check.sh` 执行，全部通过才准上线。

| # | 项 | 命令 | 期望 |
|---|----|------|------|
| 1 | THP | `cat /sys/kernel/mm/transparent_hugepage/enabled` | DB/缓存 = never 或 madvise |
| 2 | IO 调度器 | `cat /sys/block/*/queue/scheduler` | NVMe=none，SATA SSD=mq-deadline |
| 3 | swappiness | `sysctl vm.swappiness` | DB/缓存 ≤ 10 |
| 4 | swap | `swapon --show` | 与角色策略一致 |
| 5 | 文件描述符 | `cat /proc/1/limits` + 服务进程 limits | 服务 ≥ 65535 |
| 6 | sysstat | `systemctl is-active sysstat` | active，采样 ≤ 1min |
| 7 | node_exporter | `curl -s localhost:9100/metrics \| head -3` | 有数据、版本已知 |
| 8 | 时钟 | `chronyc sources` | 偏差 < 50ms |
| 9 | CPU governor | `cpupower frequency-info` | 延迟敏感 = performance |
| 10 | irqbalance | `systemctl is-active irqbalance` | 按规范开启或已手动绑核 |
| 11 | 盘健康 | `smartctl -a /dev/sda \| head -15` | SMART PASSED，新盘 0 重映射 |
| 12 | 挂载参数 | `mount \| grep data` | 与 fstab 一致，带 noatime |
| 13 | 内核参数基线 | `sysctl -a > /tmp/sysctl_baseline.txt` | 已归档供 diff |
| 14 | conntrack | `sysctl net.netfilter.nf_conntrack_max` | 网关/NAT 显式设置过 |

## 九、与现有基础设施集成

### 告警指标（对接 alert-core / VictoriaMetrics）

```promql
# load / 核数
node_load1 / count(node_cpu_seconds_total{mode="idle"}) by (instance)
# IO 等待占比
rate(node_cpu_seconds_total{mode="iowait"}[5m])
# 每设备读延迟 ms
1000 * rate(node_disk_read_time_seconds_total[1m]) / rate(node_disk_reads_completed_total[1m])
# 内存可用率
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes
# swap 换入速率（页/秒）
rate(node_vmstat_pswpin[5m])
# conntrack 使用率
node_nf_conntrack_entries / node_nf_conntrack_entries_limit
# 磁盘使用率 & inode
1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}
1 - node_filesystem_files_free{fstype!~"tmpfs|overlay"} / node_filesystem_files{fstype!~"tmpfs|overlay"}
```

### 五连巡检（每日人工跑）

```bash
uptime
vmstat 1 3 | tail -1
iostat -x -y 1 3 | awk 'NR>2 && $NF+0>0'
free -h | awk 'NR==2{print "available:",$7}'
dmesg -T | tail -5
```

### 进阶工具（需要时）

- `biolatency` / `biosnoop`：IO 延迟直方图 / 逐条事件
- `opensnoop` / `offcputime -p <pid> 30`：谁在 open / 线程在等
- `runqlat`：进程等 CPU 直方图
- `tcpretrans`：实时 TCP 重传及来源进程

## 十、参考案例索引（详细见 references/cases.md）

| # | 症状 | 根因 | 关键点 |
|---|------|------|--------|
| 1 | load 150，CPU 8% idle | NFSv3 挂载卡 D 状态 | load 高先看 R/D 构成 |
| 2 | 每 5 秒规律性毛刺 | 顺序写大日志 + 脏页集中回写 | 周期性怀疑定时任务与内核回写 |
| 3 | Java 每周随机一台长 GC | THP=always 触发 compaction | 集群配置漂移是随机单点故障首嫌 |
| 4 | 网关 %si 打满单核 | 短连接高频小包 + 单队列网卡 | 监控要有 pps 不能只带宽 |
| 5 | 云盘 w_await 2→40ms | 云盘 IOPS 规格触顶限流 | 云主机慢必须查云监控限流 |

## 十一、边界（不适用场景）

- 需要读内核源码级分析 / eBPF 高级用法 / 内核 bug 定位 —— 不在本文展开。
- 云厂商控制台操作（升规格、换盘、换 AZ）—— 走工单系统，不在本 skill。
- 容器 K8s 节点调优 —— 节点级 sysctl 生效，但 ulimit/cgroup 限额要在 Pod resources 与容器运行时配；容器 CPU 数可能与节点不同，数据要拿节点视角复核。

## 资源

- `scripts/baseline_collect.sh`：只读基线采集（15 秒完成，无副作用）
- `scripts/iostat_percentiles.sh`：60 秒采样，输出指定设备 await P50/P95/max
- `scripts/newhost_baseline_check.sh`：新机器上线 14 项检查，退出码 0=全过 / 1=有失败
- `references/cases.md`：五个完整复盘案例（现象→判断→根因→修复→验证→复盘）
- `references/commands.md`：完整命令速查 + eBPF 工具清单
