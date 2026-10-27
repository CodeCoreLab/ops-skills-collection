#!/usr/bin/env python3
"""scrub_logs.py — 日志/归档凭据脱敏（Python 版，避开 shell/perl 正则陷阱）

相比 bash 版修复的 5 个真实踩坑：
  1. 绝不穿透符号链接（is_file() 会跟随链接 → 可能改写线上配置！）
  2. 键名单取「全部配置源并集」（只用 secrets 文件会漏 env.sh 独有变量）
  3. 排除 sudo 审计行（COMMAND=…）——其"值"是文件路径，纯假阳性
  4. 值首字符排除 '/' —— 路径不是凭据
  5. 递归扫描子目录（审计归档常有子目录，顶层扫描会漏）

用法:
  # 预览（默认模式，零落盘）
  sudo python3 scrub_logs.py <目标目录或文件> [--keys <配置源1> <配置源2> ...]
  # 实际脱敏（必须显式）
  sudo python3 scrub_logs.py <目标目录或文件> --apply

**默认 dry-run，必须显式 `--apply` 才写盘**（2026-10-15 变更，见下）。
理由：本脚本是**就地改写**（`write_text` 覆盖原文件，gz 重新压缩）。
原实现默认直接写盘，一次误跑即不可逆地改写归档日志证据；
`systemd-credential-leak-audit/SKILL.md` 的既有示例（第 676 行）也确实是直接执行——
这是典型的「破坏性操作默认开启」反模式。

`--dry-run` 仍被接受（向后兼容），但在新默认下它是空操作。

默认键名单来源: 自动探测同目录下的 env.sh / env.secrets.sh / systemd.env
"""
from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path

MARK = "<REDACTED>"
DEFAULT_KEY_SOURCES = ("env.sh", "env.secrets.sh", "systemd.env")
SKIP_SUBSTR = ("COMMAND=", "REDACTED")


# ---------------------------------------------------------------- 键名单
def build_keys(sources: list[Path]) -> list[str]:
    keys: set[str] = set()
    for s in sources:
        if not s.is_file():
            continue
        for ln in s.read_text(errors="replace").splitlines():
            m = re.match(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=", ln)
            if m:
                keys.add(m.group(1))
    return sorted(keys)


def build_patterns(keys: list[str]):
    alt = "|".join(re.escape(k) for k in keys)
    # 值首字符须为字母/数字/+ —— 排除以 / 开头的文件路径
    pat = re.compile(rf"({alt})[=:]\s*([A-Za-z0-9+][A-Za-z0-9+/=_.:@%~-]{{11,}})")
    pat_url = re.compile(r"([?&]key=)([A-Za-z0-9_-]{20,})")
    return pat, pat_url


# ---------------------------------------------------------------- IO
def is_gz(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return f.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def read_text(p: Path) -> str:
    try:
        return gzip.open(p, "rt", errors="replace").read() if is_gz(p) else p.read_text(errors="replace")
    except OSError:
        return ""


def write_text(p: Path, txt: str) -> None:
    if is_gz(p):
        with gzip.open(p, "wt") as gz:
            gz.write(txt)
    else:
        p.write_text(txt)


def count_hits(txt: str, pat, pat_url) -> int:
    n = 0
    for line in txt.splitlines():
        if any(s in line for s in SKIP_SUBSTR):
            continue
        n += len(pat.findall(line)) + len(pat_url.findall(line))
    return n


def scrub(txt: str, pat, pat_url, mark: str) -> str:
    out = []
    for line in txt.splitlines(keepends=True):
        if any(s in line for s in SKIP_SUBSTR):
            out.append(line)              # sudo 审计行 / 已脱敏行：原样保留
            continue
        line = pat.sub(lambda m: f"{m.group(1)}={mark}", line)
        line = pat_url.sub(lambda m: f"{m.group(1)}{mark}", line)
        out.append(line)
    return "".join(out)


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="+", help="目标目录或文件")
    ap.add_argument("--keys", nargs="*", default=None, help="配置源文件（键名单来源）")
    ap.add_argument("--apply", action="store_true",
                    help="实际就地写入（默认 dry-run，不写盘）")
    ap.add_argument("--dry-run", action="store_true",
                    help="显式预览（向后兼容；已是默认行为）")
    ap.add_argument("--mark", default=MARK)
    args = ap.parse_args()

    # 默认 dry-run；仅 --apply 才写盘。--dry-run 保留以兼容既有调用。
    do_apply = bool(args.apply) and not bool(args.dry_run)
    if args.apply and args.dry_run:
        print("⚠  同时给出 --apply 与 --dry-run：按更安全的一侧处理 → dry-run\n")

    # 键名单
    if args.keys:
        sources = [Path(k) for k in args.keys]
    else:
        sources = []
        for t in args.target:
            base = Path(t) if Path(t).is_dir() else Path(t).parent
            for name in DEFAULT_KEY_SOURCES:
                if (base / name).is_file():
                    sources.append(base / name)
        # 常见回退位置
        for fallback in ("/opt/workbuddy/.scripts/config",):
            for name in DEFAULT_KEY_SOURCES:
                p = Path(fallback) / name
                if p.is_file() and p not in sources:
                    sources.append(p)

    keys = build_keys(sources)
    print(f"[键名单] {len(keys)} 个（来源: {', '.join(str(s) for s in sources) or '无'}）")
    if not keys:
        print("❌ 未找到任何键 → 拒绝执行（避免误伤/漏扫）")
        return 2
    pat, pat_url = build_patterns(keys)

    # 收集目标文件
    files: list[Path] = []
    for t in args.target:
        p = Path(t)
        if p.is_dir():
            # 关键：递归；且 is_symlink() 的链接一律跳过（防穿透写入线上文件！）
            for f in sorted(p.rglob("*")):
                if f.is_symlink():
                    print(f"  ⏭ 跳过符号链接（防穿透）: {f}")
                    continue
                if f.is_file():
                    files.append(f)
        elif p.is_file():
            if p.is_symlink():
                print(f"  ⏭ 跳过符号链接（防穿透）: {p}")
                continue
            files.append(p)
    print(f"[目标] {len(files)} 个文件\n")

    total = 0
    print("[扫描]")
    for f in files:
        n = count_hits(read_text(f), pat, pat_url)
        if n:
            print(f"  ⚠ {str(f):<64} {n}")
            total += n
    print(f"  --- 未脱敏合计: {total}\n")

    if total == 0:
        print("✅ 无需脱敏")
        return 0

    if not do_apply:
        print("(dry-run 默认模式：未修改任何文件)")
        print("  确认无误后加 --apply 执行就地脱敏。")
        return 0

    print("[脱敏]（就地替换，保留变量名与行结构作证据）")
    done = 0
    for f in files:
        txt = read_text(f)
        before = count_hits(txt, pat, pat_url)
        if before == 0:
            continue
        write_text(f, scrub(txt, pat, pat_url, args.mark))
        after = count_hits(read_text(f), pat, pat_url)
        print(f"  {str(f):<64} {before} -> {after}")
        done += before
    print(f"  --- 合计脱敏: {done}\n")

    print("[终态复检]（排除 REDACTED 自身，避免自指假阳性）")
    left = 0
    for f in files:
        n = count_hits(read_text(f), pat, pat_url)
        if n:
            print(f"  ❌ {str(f):<64} {n}")
            left += n
    print("  ✅ 0 残留" if left == 0 else f"  ❌ 残留合计 {left}")
    return 0 if left == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
