#!/usr/bin/env bash
# iostat_percentiles.sh - 采集 iostat 并计算指定设备 await 分位数
#
# 用法:
#   ./iostat_percentiles.sh [设备名] [采样总秒数] [采样间隔秒]
#   ./iostat_percentiles.sh                  # 默认 sda, 60s, 1s
#   ./iostat_percentiles.sh nvme0n1 120 2    # NVMe 120 秒每 2 秒
#
# 说明:
#   只读，无副作用。iostat 首行是开机累计均值会被 -y 忽略。
#   平均值会掩盖毛刺，必须看分位数才能判断是否达标。
#
# 退出码:
#   0 - 采样完成
#   1 - 设备不存在或无样本
#   2 - iostat 不可用

set -u

DEV="${1:-sda}"
SECONDS_TOTAL="${2:-60}"
INTERVAL="${3:-1}"

if ! command -v iostat >/dev/null 2>&1; then
  echo "ERROR: iostat 未安装（apt install sysstat）" >&2
  exit 2
fi

if ! ls "/sys/block/${DEV}" >/dev/null 2>&1; then
  echo "ERROR: 设备 ${DEV} 不存在，请检查 /sys/block/" >&2
  exit 1
fi

SAMPLES=$(( SECONDS_TOTAL / INTERVAL ))
if [ "${SAMPLES}" -lt 2 ]; then
  echo "ERROR: 采样次数过少（<2），请增加 SECONDS_TOTAL 或减小 INTERVAL" >&2
  exit 1
fi

echo "采集设备: ${DEV}"
echo "采样配置: 每 ${INTERVAL}s 一次, 共 ${SAMPLES} 次, 总 ${SECONDS_TOTAL}s"
echo

# 一次 iostat 采样，落文件后交给 awk 做完整处理
TMPFILE=$(mktemp /tmp/iostat_XXXXXX)
trap 'rm -f "${TMPFILE}"' EXIT

iostat -x -y "${INTERVAL}" "${SAMPLES}" > "${TMPFILE}" 2>/dev/null

awk -v dev="${DEV}" '
  function pct(arr, n, p,    i, j, idx, t) {
    if (n == 0) return 0
    for (i = 1; i <= n; i++)
      for (j = i+1; j <= n; j++)
        if (arr[i] > arr[j]) { t = arr[i]; arr[i] = arr[j]; arr[j] = t }
    idx = int((n-1) * p / 100.0) + 1
    if (idx > n) idx = n
    if (idx < 1) idx = 1
    return arr[idx]
  }

  /^[[:space:]]*Device[[:space:]]/ {
    for (i = 1; i <= NF; i++) {
      if ($i == "Device")          dev_col = i
      if ($i == "r/s")             rs_col  = i
      if ($i == "w/s")             ws_col  = i
      if ($i == "r_await" || $i == "read_await") ra_col = i
      if ($i == "w_await" || $i == "write_await") wa_col = i
      if ($i == "aqu-sz" || $i == "avgqu-sz")    aqu_col = i
      if ($i == "%util")          util_col = i
    }
    next
  }

  dev_col && $dev_col == dev {
    ra   = (ra_col   && $ra_col+0   > 0) ? $ra_col+0   : 0
    wa   = (wa_col   && $wa_col+0   > 0) ? $wa_col+0   : 0
    aqu  = (aqu_col  && $aqu_col+0  > 0) ? $aqu_col+0  : 0
    util = (util_col && $util_col+0 > 0) ? $util_col+0 : 0
    rs   = (rs_col   && $rs_col+0   > 0) ? $rs_col+0   : 0
    ws   = (ws_col   && $ws_col+0   > 0) ? $ws_col+0   : 0

    total_n++
    if (rs > 0) rs_arr[total_n] = rs
    if (ws > 0) ws_arr[total_n] = ws
    if (ra > 0) ra_arr[total_n] = ra
    if (wa > 0) wa_arr[total_n] = wa
    aqu_arr[total_n] = aqu
    util_arr[total_n] = util
  }

  END {
    if (total_n == 0) {
      printf "WARNING: 采样期间设备 %s 无任何 IO 样本，请检查设备名或业务流量\n", dev
      exit 0
    }

    # 计算非零样本数
    ra_n = 0; wa_n = 0
    for (i = 1; i <= total_n; i++) {
      if (ra_arr[i] + 0 > 0) ra_n++
      if (wa_arr[i] + 0 > 0) wa_n++
    }

    # 重新构造仅含非零值的紧凑数组
    ra_cn = 0; wa_cn = 0
    for (i = 1; i <= total_n; i++) {
      if (ra_arr[i] + 0 > 0) ra_c[++ra_cn] = ra_arr[i]
      if (wa_arr[i] + 0 > 0) wa_c[++wa_cn] = wa_arr[i]
    }

    printf "总样本数: %d  有读 IO: %d  有写 IO: %d\n\n", total_n, ra_cn, wa_cn
    printf "%-10s | %-5s | %-40s | %s\n", "指标", "样本", "P50/P95/P99/max", "说明"
    printf "%-10s-|-%-5s-|-%-40s-|-%s\n", "", "", "", "--------"

    if (ra_cn > 0) {
      printf "%-10s | %-5d | P50=%.2f  P95=%.2f  P99=%.2f  max=%.2f\n",
             "r_await", ra_cn,
             pct(ra_c, ra_cn, 50), pct(ra_c, ra_cn, 95),
             pct(ra_c, ra_cn, 99), pct(ra_c, ra_cn, 100)
    } else {
      printf "%-10s | %-5d | (无读 IO)\n", "r_await", 0
    }

    if (wa_cn > 0) {
      printf "%-10s | %-5d | P50=%.2f  P95=%.2f  P99=%.2f  max=%.2f\n",
             "w_await", wa_cn,
             pct(wa_c, wa_cn, 50), pct(wa_c, wa_cn, 95),
             pct(wa_c, wa_cn, 99), pct(wa_c, wa_cn, 100)
    } else {
      printf "%-10s | %-5d | (无写 IO)\n", "w_await", 0
    }

    # 队列深度与 util 也看分位
    if (total_n > 0) {
      printf "\n%-10s | %-5d | P50=%.2f  P95=%.2f  P99=%.2f  max=%.2f  (队列深度)\n",
             "aqu-sz", total_n,
             pct(aqu_arr, total_n, 50), pct(aqu_arr, total_n, 95),
             pct(aqu_arr, total_n, 99), pct(aqu_arr, total_n, 100)
      printf "%-10s | %-5d | P50=%.2f  P95=%.2f  P99=%.2f  max=%.2f  (%%util)\n",
             "%util", total_n,
             pct(util_arr, total_n, 50), pct(util_arr, total_n, 95),
             pct(util_arr, total_n, 99), pct(util_arr, total_n, 100)
    }
  }
' "${TMPFILE}"

echo
echo "参考线:"
echo "  NVMe SSD    : <0.2ms 正常 / >1ms 关注"
echo "  SATA SSD    : <0.5ms 正常 / >3ms 关注"
echo "  云盘        : 0.5~2ms 正常 / >5ms 关注"
echo "  机械盘 7200 : 8~15ms 正常 / >25ms 关注"
echo
echo "判断逻辑:"
echo "  await 高 + aqu-sz 高       → 盘被打满，减 IO 或换快盘"
echo "  await 高 + aqu-sz ≈ 0     → 盘本身劣化（SSD 掉速 / 坏道 / 存储网络）"
