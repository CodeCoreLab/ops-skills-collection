#!/usr/bin/env bash
# baseline_collect.sh - 采集系统性能基线
#
# 用法:
#   ./baseline_collect.sh [输出目录]
#
# 说明:
#   纯只读命令，无副作用，可生产直接执行。
#   所有输出统一 tee 到日志文件，方便 diff 对比。
#   默认输出到 /tmp/baseline_<host>_<timestamp>/
#
# 退出码:
#   0 - 采集完成
#   1 - 权限或依赖缺失

set -u

OUT="${1:-/tmp/baseline_$(hostname)_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "${OUT}" || { echo "无法创建输出目录 ${OUT}" >&2; exit 1; }
exec > >(tee "${OUT}/run.log") 2>&1

echo "=== baseline_collect.sh ==="
echo "host     : $(hostname)"
echo "kernel   : $(uname -r)"
echo "uptime   : $(uptime -s 2>/dev/null || echo 'n/a')"
echo "started  : $(date '+%Y-%m-%d %H:%M:%S')"
echo "output   : ${OUT}"
echo

# ---- 0. 环境 ----
echo "== uname =="; uname -a
echo "== os-release =="; cat /etc/os-release 2>/dev/null | grep -E '^(NAME|VERSION|PRETTY)=' || true

# ---- 1. 整机概览 ----
echo "== uptime =="; uptime
echo "== nproc =="; nproc
echo

# ---- 2. CPU ----
if command -v mpstat >/dev/null 2>&1; then
  echo "== mpstat -P ALL 1 3 =="; mpstat -P ALL 1 3
else
  echo "WARN: mpstat 未安装（sysstat 包）"
fi

echo "== pidstat -u 1 3 =="
if command -v pidstat >/dev/null 2>&1; then
  pidstat -u 1 3
else
  echo "WARN: pidstat 未安装（sysstat 包）"
fi

echo "== top procs (CPU) =="
ps -eo pid,user,pcpu,pmem,rss,comm --sort=-pcpu | head -15

echo "== top procs (MEM) =="
ps -eo pid,user,pmem,rss,comm --sort=-rss | head -15

echo "== 上下文切换速率 =="
cat /proc/stat | awk '/^ctxt/{print "ctxt_total:",$2}'

echo

# ---- 3. 内存 ----
echo "== free -h =="; free -h
echo "== meminfo key =="
grep -E 'MemTotal|MemFree|MemAvailable|Buffers|^Cached|SwapTotal|SwapFree|Dirty|Writeback|Committed_AS|CommitLimit|AnonPages' /proc/meminfo

echo "== THP =="
cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo "THP 不存在"
echo "== PSI =="
for p in cpu memory io; do
  echo "-- /proc/pressure/${p} --"
  cat /proc/pressure/${p} 2>/dev/null || echo "PSI 不存在（内核 < 4.20）"
done

echo

# ---- 4. IO ----
if command -v iostat >/dev/null 2>&1; then
  echo "== iostat -x 1 3 =="; iostat -x 1 3
else
  echo "WARN: iostat 未安装（sysstat 包）"
fi

echo "== IO 调度器 =="
for d in /sys/block/*/queue/scheduler; do
  [ -f "${d}" ] && echo "${d}: $(cat "${d}")"
done

echo "== read_ahead =="
for d in /sys/block/*/queue/read_ahead_kb; do
  [ -f "${d}" ] && echo "${d}: $(cat "${d}")"
done

echo "== /proc/diskstats 快照 =="
cat /proc/diskstats

echo

# ---- 5. 网络 ----
if command -v sar >/dev/null 2>&1; then
  echo "== sar -n DEV 1 3 =="; sar -n DEV 1 3
else
  echo "WARN: sar 未安装（sysstat 包）"
fi

echo "== ss -s =="; ss -s 2>/dev/null || echo "ss 不可用"
echo "== softnet_stat =="; cat /proc/net/softnet_stat 2>/dev/null || true

echo

# ---- 6. 进程 ----
echo "== 进程总数 =="
ps -e --no-headers | wc -l
echo "== 线程总数 =="
ps -eLf --no-headers | wc -l
echo "== pid_max =="
cat /proc/sys/kernel/pid_max

echo "== ulimit -n =="
ulimit -n

echo "== /proc/1/limits =="
cat /proc/1/limits 2>/dev/null | head -20

echo

# ---- 7. 内核参数 ----
echo "== sysctl key =="
sysctl vm.swappiness vm.dirty_ratio vm.dirty_background_ratio \
       net.core.somaxconn net.ipv4.tcp_max_syn_backlog \
       net.netfilter.nf_conntrack_max 2>/dev/null || true

echo "== 完整 sysctl 快照 =="
sysctl -a 2>/dev/null > "${OUT}/sysctl_full.txt" && echo "完整 sysctl 保存至 ${OUT}/sysctl_full.txt"

echo

# ---- 8. 存储与挂载 ----
echo "== df -h =="; df -h
echo "== df -i =="; df -i
echo "== mount =="; mount

echo

# ---- 9. 硬件与中断 ----
echo "== /proc/interrupts 摘要 =="
awk 'NR>2 {printf "%-8s %s\n", $1, $NF}' /proc/interrupts 2>/dev/null | head -30

echo "== 网卡队列 =="
for i in $(ls /sys/class/net/ 2>/dev/null); do
  [ "${i}" = "lo" ] && continue
  q=$(ethtool -l "${i}" 2>/dev/null | grep -i 'combined\|current' | head -1)
  [ -n "${q}" ] && echo "${i}: ${q}"
done

echo

# ---- 10. 时钟 ----
echo "== chronyc sources =="
chronyc sources 2>/dev/null | head -5 || echo "chronyc 不可用"

echo

# ---- 11. 最近内核事件 ----
echo "== dmesg -T tail -30 =="
dmesg -T 2>/dev/null | tail -30 || echo "dmesg 需要 root"

echo
echo "=== baseline 采集完成 ==="
echo "输出目录: ${OUT}"
echo "日志文件: ${OUT}/run.log"
