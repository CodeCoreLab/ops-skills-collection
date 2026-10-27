#!/bin/bash
# generate_projection.sh — 把 shell 凭据脚本投影为 systemd 可直接解析的纯 KV 文件
# 用法: bash generate_projection.sh <源shell文件> <输出文件> [owner:group]
# 示例: bash generate_projection.sh env.secrets.sh systemd.env root:workbuddy
#
# 投影规则:
#   export K=V        -> K=V          (剥 export 前缀)
#   K=V # 注释        -> K=V          (引号感知剥行内注释)
#   K="V" / K='V'     -> K=V          (剥包裹引号)
#   K='$X'            -> K=$$X        (systemd 中 $ 需转义)
#   # 整行注释        -> 丢弃
#   空行              -> 丢弃

set -euo pipefail

SRC="${1:?用法: $0 <源shell文件> <输出文件> [owner:group]}"
DST="${2:?缺少输出文件}"
OWNER="${3:-root:root}"

[ -f "$SRC" ] || { echo "❌ 源文件不存在: $SRC"; exit 1; }

# 引号感知剥离行内注释：只有不在引号内、且前一字符是空白/行首的 # 才是注释
strip_inline_comment() {
  awk '{
    out=""; q=""; esc=0
    for (i=1; i<=length($0); i++) {
      c = substr($0, i, 1)
      if (esc)          { out = out c; esc = 0; continue }
      if (c == "\\")    { out = out c; esc = 1; continue }
      if (q != "")      { if (c == q) q = ""; out = out c; continue }
      if (c == "\"" || c == "'"'"'") { q = c; out = out c; continue }
      if (c == "#" && (i == 1 || substr($0, i-1, 1) ~ /[ \t]/)) break
      out = out c
    }
    sub(/[ \t\r]+$/, "", out)
    print out
  }'
}

# 剥包裹引号
unquote() {
  awk -F= '{
    k = $1; v = substr($0, index($0,"=")+1)
    if (length(v) >= 2) {
      f = substr(v,1,1); l = substr(v,length(v),1)
      if ((f == "\"" && l == "\"") || (f == "'"'"'" && l == "'"'"'")) v = substr(v,2,length(v)-2)
    }
    print k "=" v
  }'
}

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

grep -v '^\s*$' "$SRC" \
  | strip_inline_comment \
  | sed 's/^[[:space:]]*export[[:space:]]\+//' \
  | grep -v '^[[:space:]]*#' \
  | grep '=' \
  | unquote \
  | awk -F= '{
      k=$1; v=substr($0, index($0,"=")+1)
      # systemd: 值中的 $ 转义为 $$（否则被当变量引用）
      gsub(/\$/, "$$", v)
      gsub(/\r/, "", v)
      print k "=" v
    }' > "$TMP"

# 权限铁律：绝不可 644
install -o "${OWNER%%:*}" -g "${OWNER##*:}" -m 640 "$TMP" "$DST"

echo "✅ 投影完成: $SRC -> $DST"
echo "   变量数: $(grep -c '=' "$DST")"
echo "   权限  : $(stat -c '%a %U:%G' "$DST")"

# 自检断言
BAD=0
n=$(grep -c '^[[:space:]]*export ' "$DST" || true); [ "$n" -gt 0 ] && { echo "   ❌ 仍有 $n 行 export 残留"; BAD=1; }
n=$(grep -c ' #' "$DST" || true); [ "$n" -gt 0 ] && { echo "   ⚠️  $n 行疑似含行内注释"; BAD=1; }
n=$(grep -c '"' "$DST" || true);  [ "$n" -gt 0 ] && { echo "   ⚠️  $n 行含引号"; BAD=1; }
[ "$BAD" -eq 0 ] && echo "   ✅ 自检通过（无 export / 无注释 / 无引号）"

echo
echo "下一步（切换单元）："
echo "  把单元里的 EnvironmentFile= 指向 $DST，然后："
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl restart <service>"
echo "    sudo systemctl show <service> -p Environment | tr ' ' '\\n' | grep -c '='"
exit 0
