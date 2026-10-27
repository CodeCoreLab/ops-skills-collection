# 完整命令速查

## 整机快速三板斧（10 秒定位方向）

```bash
uptime                          # load 三值 + R/D 构成
vmstat 1 5 | tail -1            # r/b 队列、si/so 换页、cs 切换、us/sy/wa
iostat -x -y 1                  # 每设备 IOPS/await/util（-y 忽略首行历史均值）
free -h                         # available 为准
dmesg -T | tail -50             # 内核最近事件
```

## CPU

```bash
mpstat -P ALL 1 5               # 每核分布
pidstat -u 1 5                  # 每进程 CPU
pidstat -w 1 5                  # 每进程上下文切换
top -H -p <pid>                 # 线程级
perf top -p <pid>               # 函数热点
perf record -g -p <pid> -- sleep 30   # 火焰图数据
mpstat -I SUM 1 5               # 中断速率汇总
cat /proc/interrupts            # 中断分布
cat /proc/loadavg               # load 三值 + 运行/总任务数
cat /proc/pressure/cpu          # CPU PSI 压力
```

## 内存

```bash
free -h
cat /proc/meminfo | grep -E 'MemAvailable|Dirty|Writeback|SwapCached|Committed_AS'
vmstat 1 5                      # si/so 换页速率
sar -B 1 5                      # pgscand/s 扫描、pgstalt/s 直接回收
pidstat -r 1 5                  # 每进程缺页
smem -rs swap                   # 按 swap 排序（smem 包）
cat /proc/<pid>/status          # VmRSS/VmSwap
cat /proc/<pid>/smaps_rollup    # Pss/Uss 汇总
cat /proc/pressure/memory       # 内存 PSI
cat /proc/vmstat | grep -E 'allocstall|compact_stall'
dmesg -T | grep -iE 'out of memory|oom'
journalctl -k | grep -i oom
```

## 磁盘

```bash
iostat -x 1
iostat -x -y 1                  # 忽略首行历史均值
iotop -oP -d 1                  # 找 IO 大户（需要 root）
pidstat -d 1 5
cat /proc/<pid>/io              # 进程 IO 明细
smartctl -a /dev/sda            # 盘健康
smartctl -a /dev/nvme0n1        # NVMe 健康
storcli /c0 /eall /sall show    # RAID 卡（LSI/Broadcom）
lsscsi
df -Th; df -i
mount
cat /proc/pressure/io           # IO PSI
cat /sys/block/*/queue/scheduler
cat /sys/block/*/queue/read_ahead_kb
```

## 网络

```bash
sar -n DEV 1 5                  # 带宽 + pps
sar -n EDEV 1 5                 # 错误 + drop
sar -n TCP 1 5                  # TCP 连接状态
sar -n TCP,conn 1 5             # 连接速率
ss -s
ss -lnt                         # 监听端口
ss -ant | awk '{print $1}' | sort | uniq -c
netstat -s | grep -iE 'retrans|listen|overflow|listenoverflow'
cat /proc/net/softnet_stat      # 每核收包统计
ethtool -S eth0 | grep -iE 'drop|err|discard'
ethtool -l eth0                 # 队列数
ethtool -g eth0                 # 环形缓冲
cat /proc/net/sockstat
```

## 历史回溯（sar）

```bash
sar -u -f /var/log/sa/saXX      # CPU 历史
sar -r -f /var/log/sa/saXX      # 内存历史
sar -d -f /var/log/sa/saXX      # 磁盘历史
sar -n DEV -f /var/log/sa/saXX  # 网络历史
sar -B -f /var/log/sa/saXX      # 换页历史
ls /var/log/sa/                 # 历史数据文件列表（saYYMMDD）
```

## eBPF / bcc 进阶工具

```bash
yum install bcc-tools      # CentOS/RHEL
apt install bpfcc-tools    # Ubuntu

biosnoop          # 逐条 IO 事件（谁在读写）
biolatency        # IO 延迟直方图（分位）
biostacks         # IO 栈回溯
opensnoop         # 谁在频繁 open
offcputime -p <pid> 30    # 线程被调度出去后在等什么
runqlat           # 进程等待 CPU 的直方图
runqlen           # 运行队列长度直方图
tcpretrans        # 实时 TCP 重传及来源进程
tcpdrop           # TCP drop 事件
tcprtt            # TCP RTT 直方图
funccount         # 函数调用计数
profile           # 用户/内核采样
```

## /proc 关键文件速查

| 文件 | 内容 | 典型用途 |
|------|------|---------|
| `/proc/loadavg` | load 三值 + 运行/总任务数 | 脚本采集 load |
| `/proc/meminfo` | 内存全景 | available、Dirty、Committed_AS |
| `/proc/<pid>/status` | 进程状态、RSS、线程数 | 线程爆炸排查 |
| `/proc/<pid>/io` | 进程 IO 读写量 | 区分缓存读写与落盘读写 |
| `/proc/<pid>/wchan` | 进程当前阻塞的内核函数 | D 状态进程卡在哪 |
| `/proc/<pid>/smaps_rollup` | 进程内存汇总（Pss/Uss） | 内存归因 |
| `/proc/<pid>/limits` | 进程实际 ulimit | 验证 limits 配置 |
| `/proc/<pid>/cgroup` | 进程所属 cgroup | 容器归因 |
| `/proc/pressure/{cpu,memory,io}` | PSI 压力指标（内核 4.20+） | 比 load 更精准的饱和信号 |
| `/proc/net/softnet_stat` | 每核收包处理与积压 | 软中断排查 |
| `/proc/interrupts` | 每 CPU 每 IRQ 计数 | 中断是否偏科 |
| `/proc/vmstat` | 全部 VM 计数器 | allocstall、compact_stall |
| `/proc/diskstats` | 磁盘统计原始数据 | 计算 IOPS/延迟 |

## PSI（Pressure Stall Information）读法

```bash
# some：至少一个任务被阻塞的时间占比；full：所有任务同时被阻塞的占比
cat /proc/pressure/io
# some avg10=12.34 avg60=8.21 avg300=5.02 total=987654321
# full avg10=3.21 avg60=2.11 avg300=1.05 total=123456789
```

- `some avg10 > 0`：至少一个任务最近 10 秒被阻塞过
- `full avg10 > 0`：**所有任务同时被阻塞**，业务延迟必然受影响
- CentOS 7（3.10 内核）无 PSI；Ubuntu 20.04+ 默认可用

## 常用 sysctl 参考值（DB/缓存类）

```ini
# /etc/sysctl.d/99-perf-tuning.conf

# ---------- 内存 ----------
vm.swappiness = 1
vm.dirty_background_ratio = 5
vm.dirty_ratio = 10
vm.overcommit_memory = 0
# 大内存机器用绝对值更精确：
# vm.dirty_background_bytes = 268435456   # 256MB
# vm.dirty_bytes = 1073741824             # 1GB

# ---------- IO ----------
vm.dirty_expire_centisecs = 3000          # 脏页最长存活 30s
vm.dirty_writeback_centisecs = 500        # 回写线程唤醒周期 5s

# ---------- 网络 ----------
net.ipv4.tcp_max_syn_backlog = 8192
net.core.somaxconn = 8192
net.netfilter.nf_conntrack_max = 262144   # 网关/NAT 必需
```

## tuned 统一管理

```bash
yum install -y tuned || apt install -y tuned
systemctl enable --now tuned
tuned-adm list                              # 可用 profile
tuned-adm active                            # 当前 profile
tuned-adm profile throughput-performance    # 切换
tuned-adm verify                            # 校验生效
```

## IO 调度器 udev 持久化

文件：`/etc/udev/rules.d/60-iosched.rules`

```
ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
ACTION=="add|change", KERNEL=="nvme[0-9]n[0-9]", ATTR{queue/scheduler}="none"
```

## ulimits 示例

文件：`/etc/security/limits.d/20-nofile.conf`

```
*   soft nofile 65535
*   hard nofile 65535
root soft nofile 65535
root hard nofile 65535
```

## fio 压测模板

```bash
yum install -y fio || apt install -y fio

# 4K 随机读 IOPS（稳态跑 30 分钟以上）
fio --name=randread --ioengine=libaio --direct=1 --rw=randread \
    --bs=4k --iodepth=32 --numjobs=1 --size=1G --runtime=1800 \
    --time_based --group_reporting --filename=/data/fio_randread.tmp

# 1M 顺序写吞吐
fio --name=seqwrite --ioengine=libaio --direct=1 --rw=write \
    --bs=1M --iodepth=8 --numjobs=1 --size=2G --runtime=60 \
    --time_based --group_reporting --filename=/data/fio_seqwrite.tmp

# 4K 随机写延迟分布
fio --name=randlat --ioengine=libaio --direct=1 --rw=randwrite \
    --bs=4k --iodepth=1 --numjobs=1 --size=512M --runtime=1800 \
    --time_based --group_reporting --filename=/data/fio_randlat.tmp

# 清理（生产环境谨慎，压测文件不要留）
rm -f /data/fio_*.tmp
```

**注意**：生产环境压测必须错峰 + 用独立盘，严禁在业务高峰跑。
