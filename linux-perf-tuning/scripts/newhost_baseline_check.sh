#!/usr/bin/env bash
# newhost_baseline_check.sh - 新机器上线性能基线 14 项检查
#
# 用法:
#   sudo ./newhost_baseline_check.sh
#
# 说明:
#   只读检查，不修改任何配置。
#   期望值可通过环境变量覆盖，默认值适合 DB/缓存类服务。
#
#   可覆盖的环境变量:
#     EXPECTED_THP       - 期望的 THP 值 (never|madvise|always)，默认 never
#     EXPECTED_SWAPPINESS_MAX - swappiness 最大允许值，默认 10
#     EXPECTED_NOFILE_MIN     - 文件描述符下限，默认 65535
#     EXPECTED_ROLE       - 机器角色 (db|cache|web|batch)，影响部分期望值
#
# 退出码:
#   0 - 全部通过
#   1 - 有失败项（详见输出）
#   2 - 关键依赖缺失（如 smartctl）

set -u

EXPECTED_THP="${EXPECTED_THP:-never}"
EXPECTED_SWAPPINESS_MAX="${EXPECTED_SWAPPINESS_MAX:-10}"
EXPECTED_NOFILE_MIN="${EXPECTED_NOFILE_MIN:-65535}"
EXPECTED_ROLE="${EXPECTED_ROLE:-unknown}"

PASS=0
FAIL=0
WARN=0
FAIL_DETAILS=()

pass() { echo "  [PASS] $*"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); FAIL_DETAILS+=("$*"); }
warn() { echo "  [WARN] $*"; WARN=$((WARN+1)); }
info() { echo "  [INFO] $*"; }

divider() {
  local n="${1:-72}"
  printf '%*s\n' "$n" '' | tr ' ' '-'
}

echo
divider
echo " 新机器上线性能基线检查"
echo " host: $(hostname)   kernel: $(uname -r)   role: ${EXPECTED_ROLE}"
echo " 开始: $(date '+%Y-%m-%d %H:%M:%S')"
divider

echo
echo "1. THP 透明大页 (DB/缓存类应为 never 或 madvise)"
THP_ENABLED=$(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo "N/A")
THP_CURRENT=$(echo "${THP_ENABLED}" | awk '{for(i=1;i<=NF;i++) if ($i ~ /\[/) {gsub(/\[/,""); gsub(/\]/,""); print $i}}')
if [ "${THP_CURRENT}" = "${EXPECTED_THP}" ]; then
  pass "THP = ${THP_CURRENT} (期望 ${EXPECTED_THP})"
elif [ "${THP_CURRENT}" = "madvise" ] || [ "${THP_CURRENT}" = "never" ]; then
  warn "THP = ${THP_CURRENT} (可接受，但期望 ${EXPECTED_THP})"
else
  fail "THP = ${THP_CURRENT} (期望 ${EXPECTED_THP})，可能导致 JVM GC / DB 抖动"
fi

echo
echo "2. IO 调度器"
for d in /sys/block/*/queue/scheduler; do
  [ -f "${d}" ] || continue
  dev=$(echo "${d}" | awk -F'/' '{print $(NF-1)}')
  val=$(cat "${d}")
  cur=$(echo "${val}" | awk '{for(i=1;i<=NF;i++) if ($i ~ /\[/) {gsub(/\[/,""); gsub(/\]/,""); print $i}}')
  info "  ${dev}: ${cur}"
done

echo
echo "3. vm.swappiness (DB/缓存 ≤ ${EXPECTED_SWAPPINESS_MAX})"
SWAP=$(sysctl -n vm.swappiness 2>/dev/null || echo "N/A")
if [ "${SWAP}" != "N/A" ] && [ "${SWAP}" -le "${EXPECTED_SWAPPINESS_MAX}" ]; then
  pass "vm.swappiness = ${SWAP}"
else
  fail "vm.swappiness = ${SWAP} (期望 ≤ ${EXPECTED_SWAPPINESS_MAX})"
fi

echo
echo "4. swap 配置"
if command -v swapon >/dev/null 2>&1; then
  SWAP_LIST=$(swapon --show 2>/dev/null)
  if [ -z "${SWAP_LIST}" ]; then
    info "  未启用 swap（对 DB/缓存类可接受）"
  else
    echo "${SWAP_LIST}" | sed 's/^/  /'
  fi
fi

echo
echo "5. 文件描述符 (期望 ≥ ${EXPECTED_NOFILE_MIN})"
PROC1_NOFILE=$(grep -E '^Max open files' /proc/1/limits 2>/dev/null | awk '{print $4}')
SHELL_NOFILE=$(ulimit -n 2>/dev/null)
info "  /proc/1/limits: ${PROC1_NOFILE:-N/A}"
info "  shell ulimit -n: ${SHELL_NOFILE:-N/A}"
if [ -n "${PROC1_NOFILE}" ] && [ "${PROC1_NOFILE}" -ge "${EXPECTED_NOFILE_MIN}" ]; then
  pass "PID 1 nofile = ${PROC1_NOFILE}"
else
  warn "PID 1 nofile = ${PROC1_NOFILE}，需确认服务进程 limits 配置"
fi

echo
echo "6. sysstat 采集"
SYSSTAT=$(systemctl is-active sysstat 2>/dev/null || echo "inactive")
if [ "${SYSSTAT}" = "active" ]; then
  pass "sysstat active"
else
  fail "sysstat = ${SYSSTAT}，无法做事后回溯（必须装）"
fi

echo
echo "7. node_exporter (VictoriaMetrics 链路)"
if curl -s --max-time 2 "http://localhost:9100/metrics" 2>/dev/null | head -3 | grep -q "node_cpu"; then
  VERSION=$(curl -s --max-time 2 "http://localhost:9100/metrics" 2>/dev/null | grep "node_exporter_build_info" | head -1)
  pass "node_exporter 运行中: ${VERSION}"
else
  fail "node_exporter :9100 无响应（Prometheus 抓不到指标）"
fi

echo
echo "8. 时钟同步 (chronyc sources 偏差 < 50ms)"
if command -v chronyc >/dev/null 2>&1; then
  OFFSET=$(chronyc sources 2>/dev/null | awk 'NR>1 && /^[^+*#/]/ {print $4; exit}')
  if [ -z "${OFFSET}" ]; then
    warn "无法读取时钟偏差"
  else
    ABS_OFFSET=$(echo "${OFFSET}" | tr -d '-')
    if [ "${ABS_OFFSET%.*}" -lt 50 ] 2>/dev/null; then
      pass "时钟偏差 ${OFFSET}s (< 50ms)"
    else
      fail "时钟偏差 ${OFFSET}s (>= 50ms)"
    fi
  fi
else
  warn "chronyc 不可用，无法校验时钟"
fi

echo
echo "9. CPU governor (延迟敏感期望 performance)"
if command -v cpupower >/dev/null 2>&1; then
  GOV=$(cpupower frequency-info 2>/dev/null | grep -iE 'current policy|driver' | head -2)
  echo "${GOV}" | sed 's/^/  /'
  if echo "${GOV}" | grep -qi "performance"; then
    pass "governor = performance"
  else
    warn "governor 非 performance，延迟敏感场景建议切换"
  fi
else
  warn "cpupower 不可用"
fi

echo
echo "10. irqbalance"
IRQBAL=$(systemctl is-active irqbalance 2>/dev/null || echo "inactive")
if [ "${IRQBAL}" = "active" ]; then
  pass "irqbalance active"
else
  warn "irqbalance = ${IRQBAL}（若已手动绑核则忽略）"
fi

echo
echo "11. 盘健康 (SMART)"
if command -v smartctl >/dev/null 2>&1; then
  for d in /dev/sd[a-z] /dev/nvme[0-9]n[1-9]; do
    [ -b "${d}" ] || continue
    RESULT=$(smartctl -A "${d}" 2>/dev/null)
    if [ -z "${RESULT}" ]; then
      warn "  ${d}: smartctl 无返回"
      continue
    fi
    if echo "${RESULT}" | grep -qiE 'Reallocated_Sector|Pending_Sector|Uncorrect|Available Spare Threshold' ; then
      CRIT=$(echo "${RESULT}" | grep -iE 'Reallocated_Sector_Ct|Current_Pending_Sector|Uncorrectable' | awk '{print $1, $9, $10}')
      if echo "${CRIT}" | grep -qE '[1-9]'; then
        fail "  ${d}: 有重映射/待处理扇区 — 需迁移数据"
        echo "      ${CRIT}"
      else
        pass "  ${d}: 无重映射扇区"
      fi
    else
      info "  ${d}: smartctl 未返回关键健康字段"
    fi
  done
else
  fail "smartctl 不可用（smartmontools 包）— 无法评估盘健康"
fi

echo
echo "12. 挂载参数"
MOUNT_OPTS=$(mount 2>/dev/null | grep -vE '^(proc|sysfs|cgroup|tmpfs|devpts|overlay|squashfs)')
echo "${MOUNT_OPTS}" | awk '{print "  "$1" "$2" "$3" on "$4" type "$5" ("$6")"}' | head -20
if echo "${MOUNT_OPTS}" | grep -qE ' /data[[:space:]]| /opt[[:space:]]| /var[[:space:]]'; then
  if echo "${MOUNT_OPTS}" | grep -q "noatime"; then
    pass "data 挂载点含 noatime"
  else
    warn "data 挂载点未启用 noatime（增加小 IO 抖动）"
  fi
else
  info "未识别 data/opt/var 挂载点"
fi

echo
echo "13. 内核参数基线归档"
SNAPSHOT=/tmp/sysctl_baseline_$(hostname)_$(date +%Y%m%d).txt
sysctl -a 2>/dev/null > "${SNAPSHOT}"
info "  已归档至 ${SNAPSHOT} ($(wc -l < "${SNAPSHOT}") 行)"

echo
echo "14. conntrack 上限 (网关/NAT 需显式设置)"
CONNTRACK=$(sysctl -n net.netfilter.nf_conntrack_max 2>/dev/null || echo "N/A")
if [ "${CONNTRACK}" = "N/A" ]; then
  warn "conntrack_max 未配置（网关/NAT 建议显式设置）"
else
  info "  nf_conntrack_max = ${CONNTRACK}"
  if [ "${EXPECTED_ROLE}" = "gateway" ] || [ "${EXPECTED_ROLE}" = "nat" ]; then
    if [ "${CONNTRACK}" -ge 262144 ] 2>/dev/null; then
      pass "conntrack_max = ${CONNTRACK} (>= 262144)"
    else
      fail "conntrack_max = ${CONNTRACK} (网关期望 >= 262144)"
    fi
  else
    info "  非网关角色，默认值可接受"
  fi
fi

divider
echo " 检查完成: PASS=${PASS}  WARN=${WARN}  FAIL=${FAIL}"
echo " 结束: $(date '+%Y-%m-%d %H:%M:%S')"
divider
if [ ${#FAIL_DETAILS[@]} -gt 0 ]; then
  echo
  echo "失败项:"
  for item in "${FAIL_DETAILS[@]}"; do
    echo "  - ${item}"
  done
fi
divider

if [ "${FAIL}" -gt 0 ]; then
  exit 1
else
  exit 0
fi
