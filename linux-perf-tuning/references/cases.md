# 五个完整复盘案例

> 详细背景来自 Linux 系统性能调优实战（马哥Linux运维，2026-09-23），浓缩到"现象 → 判断 → 根因 → 修复 → 验证 → 复盘"六段式。

---

## 案例 1：load 150，CPU 却是 idle 的

**现象**：16 核机器 load1 148，`%usr` 仅 8%，接口偶发超时。加机器后问题依旧。

**判断**：
```bash
ps -eLo stat | grep -c '^D'   # = 142
ps -eLo stat | grep -c '^R'   # = 2
```
D 状态堆积压倒性，判定 **IO 型 load**。

**关键证据**：
```bash
iostat -x 1    # sdb w_await 210ms，%util 接近 100%
cat /proc/<pid>/wchan   # 全部指向 nfs_* 相关内核函数
mount | grep nfs        # 确认 NFSv3 挂载
```

**根因**：NFS 服务端存储抖动，客户端所有 Java 线程卡在不可中断 IO。

**修复**：
- 应急：把挂载点上的临时目录切到本地盘，先恢复业务
- 中期：推动 NFS 服务端排查存储链路

**验证**：
- 切走 10 分钟后 load 回落至 6，`wchan` 无 NFS 等待

**复盘**：
- load 报警必须区分 R/D 构成，不能看到 load 高就报 CPU
- NFS 类挂载必须有独立延迟告警（NFS 抖动本地无告警信号）

---

## 案例 2：规律性每 5 秒卡一下

**现象**：订单接口 P99 每隔固定几分钟出现毛刺，其他时间正常。

**判断**：毛刺有周期性，像定时任务或内核周期行为。

**关键证据**：
- 毛刺时刻 `iostat -x` 出现 200MB/s 突发写
- `/proc/meminfo` Dirty 峰值 3.2GB（内存 16GB 机器）
- 毛刺时刻与业务日志滚动时刻高度重合

**根因**：应用顺序写大日志 + 过期脏页集中回写叠加，形成突发刷盘风暴。`vm.dirty_ratio=20` 触发同步回写，业务线程被阻塞。

**修复**：
```bash
sysctl -w vm.dirty_background_bytes=268435456   # 256MB 开始后台回写
sysctl -w vm.dirty_bytes=1073741824             # 1GB 才阻塞写
```
同时日志切异步写入并限制单文件大小。

**验证**：
- 次周高峰 w_await 毛刺从 85ms 降至 6ms，接口 P99 恢复

**复盘**：
- 周期性毛刺优先怀疑定时任务与内核周期回写
- Dirty 曲线必须纳入监控（当前多数环境只看 free/available）

---

## 案例 3：JVM 频繁 Full GC 的幕后黑手是 THP

**现象**：Java 服务每周随机一台出现长 GC（STW 3-5 秒），间隔无规律，堆使用量正常。

**判断**：GC 日志显示 STW 时间异常，但 heap usage 曲线正常，排除内存泄漏。

**关键证据**：
- 问题机 THP = `always`，同集群其他机器 = `never`（装机模板漂移）
- `/proc/vmstat` 的 `compact_stall` 在 GC 时间点突增 10 倍

**根因**：THP 的内存碎片整理在 JVM 分配大段内存（Full GC 时尤甚）时同步触发 compaction，STW 被拉长。

**修复**：
```bash
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag
# 纳入 Ansible 上线基线校验
```

**验证**：修复后三个月无同类 GC。

**复盘**：
- 集群机器配置漂移是"随机单点故障"的第一嫌疑人
- THP 检查必须纳入新机器上线基线（`scripts/newhost_baseline_check.sh` 第 1 项）

---

## 案例 4：网关机器 %si 打满单核

**现象**：Nginx 网关 8 核机器，`top` 里某行 %CPU 300+，大半是 si（软中断）；业务 QPS 无增长但 P99 抖动。

**判断**：软中断集中在单核（si 集中在 CPU0）。

**关键证据**：
- `sar -n DEV 1` 显示 `rxpck/s` 120 万但 `rxkB/s` 很小 —— **小包量暴涨**
- `/proc/net/softnet_stat` 第二列（收包计数）持续增长
- `cat /proc/interrupts | grep eth0` 中断全落在 CPU0
- `ethtool -l eth0` 显示只有 1 个 combined 队列

**根因**：上游新上服务用短连接高频调用，网卡多队列未开启，单核处理全部收包。

**修复**：
```bash
ethtool -L eth0 combined 8        # 开 8 队列
systemctl restart irqbalance       # 确认中断均衡
```
中期：推动上游改长连接 / 连接池。

**验证**：
- 每核 si 降至 15% 以下
- `softnet_stat` 不再增长
- P99 恢复

**复盘**：
- 小包量（pps）与带宽是两个独立维度，监控里只有带宽没有 pps 是盲区
- 告警规则要加 `%si` 单核维度

---

## 案例 5：云盘 IOPS 触顶限流

**现象**：每天 02:00~02:30 批量任务变慢，`iostat` 显示 `w_await` 从 2ms 升至 40ms，但 `%util` 只有 60%。

**判断**：量没打满、延迟却高，本地看不出硬件原因，怀疑云侧。

**关键证据**：
- 云监控显示该盘 IOPS 曲线正好压在规格上限（4K 随机写 1 万 IOPS 触顶）
- 本地 `smartctl` 全部 PASSED，无异常

**根因**：云盘按规格限流，本地一切正常是"被限流后的表象"。

**修复**：
- 短期：把批量任务并发度调低（IOPS 压到规格 80% 以内换延迟稳定）
- 中期：提升盘规格或拆盘分摊

**验证**：
- 并发调低后 `w_await` 回到 3ms
- 任务总时长反而缩短 18%（限流排队消失，效率更高）

**复盘**：
- 云主机 IO 慢的排查清单必须加一步"看云监控限流"
- **低并发快速失败优于高并发排队**

---

## 通用教训

1. **本地指标全绿不代表真的没问题**——云侧、下游、网络层都需要独立排查
2. **周期性毛刺优先怀疑内核周期行为**（脏页回写、GC、cron）+ 应用定时任务
3. **集群配置漂移是"随机故障"首嫌**——Ansible / 基线检查必须落地
4. **告警规则不能只看单一指标**——load 要分 R/D，CPU 要分段，网络要 pps + 带宽双维
5. **回滚命令必须先写**——所有参数变更都有"改前原值 + 恢复命令"两张纸
