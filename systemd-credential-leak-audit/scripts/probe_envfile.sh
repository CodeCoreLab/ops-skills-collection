#!/bin/bash
# probe_envfile.sh — 一键探测 systemd EnvironmentFile 凭据泄漏面
# 用法: sudo bash probe_envfile.sh [secrets_file]
# 退出码: 0=未发现泄漏  1=发现泄漏

set -uo pipefail

SECRETS="${1:-}"
RED='\033[0;31m'; YEL='\033[0;33m'; GRN='\033[0;32m'; NC='\033[0m'

echo "=========================================="
echo " systemd EnvironmentFile 凭据泄漏探测"
echo " $(date '+%F %T')"
echo "=========================================="

# ---------- 1. journal 泄漏条数（最直接信号） ----------
echo
echo "[1] journal 中的非法环境赋值记录"
CNT=$(journalctl --no-pager 2>/dev/null \
      | grep -c "Ignoring invalid environment assignment" || true)
CNT=${CNT:-0}
if [ "$CNT" -gt 0 ]; then
  echo -e "  ${RED}❌ 发现 $CNT 条 —— 凭据正在被明文写入日志${NC}"
  EXIT=1
else
  echo -e "  ${GRN}✅ 0 条${NC}"
  EXIT=0
fi

# ---------- 2. 涉及的文件 ----------
echo
echo "[2] 涉及的文件及泄漏行数"
journalctl --no-pager 2>/dev/null \
  | grep "Ignoring invalid environment assignment" \
  | grep -oP "(: \K/\S+)$" 2>/dev/null | sort | uniq -c | sort -rn | head -20 \
  || echo "  （无）"

# ---------- 3. 泄漏的变量名（去重） ----------
echo
echo "[3] 泄漏的变量名（按变量名去重）"
journalctl --no-pager 2>/dev/null \
  | grep -oP "assignment '\K(export )?[A-Z_][A-Z0-9_]*(?==)" \
  | sed 's/^export //' | sort -u | tee /tmp/_leaked_keys.txt | head -40
LEAKED=$(wc -l < /tmp/_leaked_keys.txt 2>/dev/null || echo 0)
echo "  ---- 共 $LEAKED 个泄露变量名（已存 /tmp/_leaked_keys.txt）"

# ---------- 4. 单元引用的 EnvironmentFile ----------
echo
echo "[4] 被单元引用的 EnvironmentFile 及 export 前缀检查"
grep -rh "^EnvironmentFile=" /etc/systemd/system/ /usr/lib/systemd/system/ 2>/dev/null \
  | sed 's/^EnvironmentFile=-\?//' | sort -u | while read -r f; do
    [ -f "$f" ] || { echo "  ⚠️  不存在: $f"; continue; }
    n=$(grep -c "^[[:space:]]*export " "$f" 2>/dev/null || echo 0)
    if [ "$n" -gt 0 ]; then
      echo -e "  ${RED}❌ $n 行 export: $f${NC}"
    else
      echo -e "  ${GRN}✅ 无 export: $f${NC}"
    fi
  done

# ---------- 5. journald 转发链 ----------
echo
echo "[5] journald 配置（取最后一条生效值）"
if command -v systemd-analyze >/dev/null 2>&1; then
  for k in ForwardToSyslog Storage RuntimeMaxUse MaxRetentionSec; do
    v=$(systemd-analyze cat-config systemd/journald.conf 2>/dev/null \
        | grep -E "^${k}=" | tail -1)
    if [ "$k" = "ForwardToSyslog" ] && echo "$v" | grep -qi "yes"; then
      echo -e "  ${RED}❌ $v  (泄漏会扩散到 syslog)${NC}"
    else
      echo "  · ${v:-$k 未显式设置}"
    fi
  done
  echo "  · drop-in 文件:"
  ls -1 /etc/systemd/journald.conf.d/ 2>/dev/null | sed 's/^/      /'
else
  echo "  （systemd-analyze 不可用）"
fi

# ---------- 6. 存量日志残留 ----------
echo
echo "[6] 存量日志残留扫描"
if [ -n "$SECRETS" ] && [ -f "$SECRETS" ]; then
  grep -oP '^\s*(export\s+)?\K[A-Z_][A-Z0-9_]*(?==)' "$SECRETS" | sort -u > /tmp/_sens_keys.txt
  echo "  变量名清单: $(wc -l < /tmp/_sens_keys.txt) 个 (来自 $SECRETS)"
  RES=0
  for logf in /var/log/syslog /var/log/syslog.1 /var/log/auth.log /var/log/morning_inspection.log; do
    [ -f "$logf" ] || continue
    h=$(grep -aE "$(paste -sd'|' /tmp/_sens_keys.txt)=[A-Za-z0-9+/=_-]{8,}" "$logf" 2>/dev/null \
        | grep -vc 'REDACTED' || true)
    [ "${h:-0}" -gt 0 ] && { echo -e "  ${RED}❌ $logf: $h 处残留${NC}"; RES=1; EXIT=1; }
  done
  # 归档 gz 极易漏
  for gz in /var/log/*.gz; do
    [ -f "$gz" ] || continue
    h=$(zcat "$gz" 2>/dev/null \
        | grep -aE "$(paste -sd'|' /tmp/_sens_keys.txt)=[A-Za-z0-9+/=_-]{8,}" 2>/dev/null \
        | grep -vc 'REDACTED' || true)
    [ "${h:-0}" -gt 0 ] && { echo -e "  ${RED}❌ $gz: $h 处残留${NC}"; RES=1; EXIT=1; }
  done
  [ "$RES" -eq 0 ] && echo -e "  ${GRN}✅ 文本日志无残留${NC}"
else
  echo "  （未提供 secrets 文件，跳过）"
fi

echo
echo "=========================================="
[ "$EXIT" -eq 0 ] && echo -e "${GRN}结论: 未发现泄漏${NC}" \
                  || echo -e "${RED}结论: 发现泄漏，按 SKILL.md 四层修复${NC}"
echo "=========================================="
exit "$EXIT"
