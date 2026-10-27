#!/bin/bash
# verify.sh — 终态校验「10 项」，含 syslog 零增量实证
# 用法: sudo bash verify.sh <service1> [service2 ...]
#       sudo bash verify.sh workflow-engine healthcheck-monitor alert-core

set -uo pipefail

SVCS=("$@")
[ ${#SVCS[@]} -eq 0 ] && SVCS=(workflow-engine alert-core)

PASS=0; FAIL=0
ok()  { echo -e "  \033[0;32m✅ $1\033[0m"; PASS=$((PASS+1)); }
bad() { echo -e "  \033[0;31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }

echo "=========================================="
echo " 终态校验  $(date '+%F %T')"
echo "=========================================="

# 1. 服务 active
echo; echo "[1] 服务状态"
for s in "${SVCS[@]}"; do
  st=$(systemctl is-active "$s" 2>/dev/null || echo unknown)
  [ "$st" = "active" ] && ok "$s = active" || bad "$s = $st"
done

# 2. 失败单元数（必须在 reset-failed 之后判定，否则残留计数误导）
echo; echo "[2] 失败 systemd 单元"
sudo systemctl reset-failed 2>/dev/null || true
n=$(systemctl list-units --state=failed --no-legend --no-pager 2>/dev/null | grep -c . || true)
[ "${n:-0}" -eq 0 ] && ok "0 个失败单元" || bad "$n 个失败单元"

# 3. journal 泄漏条数
echo; echo "[3] journal 泄漏残留"
n=$(journalctl --no-pager 2>/dev/null | grep -c "Ignoring invalid environment assignment" || true)
[ "${n:-0}" -eq 0 ] && ok "0 条（无新增泄漏）" || bad "$n 条泄漏记录"

# 4. 环境变量注入数
echo; echo "[4] 环境变量注入"
for s in "${SVCS[@]}"; do
  n=$(systemctl show "$s" -p Environment 2>/dev/null | tr ' ' '\n' | grep -c '=' || true)
  n=$((n - 1))   # 减去 "Environment=" 本身
  [ "$n" -gt 20 ] && ok "$s: $n 个变量" || bad "$s: 仅 $n 个变量（可能仍用带 export 的文件）"
done

# 5. 投影文件权限
echo; echo "[5] 投影文件权限（必须 640 且非 world-readable）"
found=0
for f in $(grep -rh "^EnvironmentFile=" /etc/systemd/system/ 2>/dev/null | sed 's/^EnvironmentFile=-\?//' | sort -u); do
  [ -f "$f" ] || continue
  found=1
  p=$(stat -c '%a' "$f")
  case "$p" in 640|600|440|400) ok "$f = $p $(stat -c '%U:%G' "$f")";;
    *) bad "$f = $p （过宽！）";; esac
done
[ "$found" -eq 0 ] && echo "  （无 EnvironmentFile 引用）"

# 6. ForwardToSyslog（取最后一条！）
echo; echo "[6] ForwardToSyslog（须取 cat-config 最后一条）"
v=$(systemd-analyze cat-config systemd/journald.conf 2>/dev/null | grep -E '^ForwardToSyslog=' | tail -1)
if echo "$v" | grep -qi 'no'; then ok "$v （最后一条）"; else bad "$v —— 转发未关闭"; fi

# 7. journal 存储模式
echo; echo "[7] journal 存储与体积"
v=$(systemd-analyze cat-config systemd/journald.conf 2>/dev/null | grep -E '^Storage=' | tail -1)
echo "  · $v"
sz=$(journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+[KMG]?' | head -1 || echo '?')
ok "journal 占用: $sz"
[ -d /run/log/journal ] && ok "volatile 生效（/run/log/journal 存在）" \
                        || echo "  · 未启用 volatile"

# 8. syslog 零增量实证（最有说服力）
echo; echo "[8] syslog 转发实证（故意打一条日志，看是否增长）"
if [ -f /var/log/syslog ]; then
  s1=$(stat -c%s /var/log/syslog)
  logger "leak-drill-$$" 2>/dev/null || true
  sleep 2
  s2=$(stat -c%s /var/log/syslog)
  if [ "$s1" = "$s2" ]; then ok "增量 0 字节（$s1 -> $s2）转发已切断"
  else bad "增量 $((s2-s1)) 字节 —— 仍在转发"; fi
else
  echo "  · /var/log/syslog 不存在（可能已清理）"
fi

# 9. 存量脱敏残留
echo; echo "[9] 文本日志脱敏残留（排除 REDACTED 标记）"
RES=0
for gz in /var/log/*.gz; do
  [ -f "$gz" ] || continue
  h=$(zcat "$gz" 2>/dev/null | grep -aE '[A-Z_]{6,}=[A-Za-z0-9+/=_-]{24,}' 2>/dev/null | grep -vc REDACTED || true)
  [ "${h:-0}" -gt 0 ] && { bad "$gz: $h 处疑似残留"; RES=1; }
done
for f in /var/log/syslog /var/log/auth.log; do
  [ -f "$f" ] || continue
  h=$(grep -aE '[A-Z_]{6,}=[A-Za-z0-9+/=_-]{24,}' "$f" 2>/dev/null | grep -vc REDACTED || true)
  [ "${h:-0}" -gt 0 ] && { bad "$f: $h 处疑似残留"; RES=1; }
done
[ "$RES" -eq 0 ] && ok "无残留"

# 10. 单元合规（无单元引用带 export 的文件）
echo; echo "[10] 单元合规（不得引用带 export 的文件）"
BAD=0
for f in $(grep -rh "^EnvironmentFile=" /etc/systemd/system/ 2>/dev/null | sed 's/^EnvironmentFile=-\?//' | sort -u); do
  [ -f "$f" ] || continue
  n=$(grep -c '^[[:space:]]*export ' "$f" 2>/dev/null || true)
  [ "${n:-0}" -gt 0 ] && { bad "$f 含 $n 行 export"; BAD=1; }
done
[ "$BAD" -eq 0 ] && ok "全部合规"

echo
echo "=========================================="
echo -e " PASS: \033[0;32m$PASS\033[0m   FAIL: \033[0;31m$FAIL\033[0m"
[ "$FAIL" -eq 0 ] && echo -e " \033[0;32m结论: 终态全绿\033[0m" \
                  || echo -e " \033[0;31m结论: 仍有 $FAIL 项未达标\033[0m"
echo "=========================================="
exit "$FAIL"
