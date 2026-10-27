#!/usr/bin/env python3
"""test_skill_routing.py — monorepo-split 的三案例实测（skill-authoring-standards 铁律 9）。

三案例：
  1. 明确点名 —— 用户说了触发词
  2. 自然表达 —— 用户不点名，靠 description 路由
  3. 信息不完整 —— 缺关键参数，skill 应标记缺失而非编造

判定方式：把 description 与兄弟 skill 的 description 一起做关键词匹配，
看用户原话更接近哪个 skill。这是可复现的代理判定，
不是真实模型路由（后者不可复现，故只做词面覆盖度检验）。
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SKILLS_DIR = Path.home() / ".workbuddy" / "skills"
TARGET = "monorepo-split"

FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"    [{'OK' if ok else 'FAIL'}]   {name}   {detail}")


def load_desc(name: str) -> str:
    p = SKILLS_DIR / name / "SKILL.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*[\"']?(.*?)[\"']?\s*$", text, re.M)
    return m.group(1) if m else ""


def tokens(s: str) -> set:
    """中英混合切词：英文按单词，中文按 2-gram。"""
    s = s.lower()
    en = set(re.findall(r"[a-z0-9]{2,}", s))
    zh = re.findall(r"[一-鿿]+", s)
    for seg in zh:
        for i in range(len(seg) - 1):
            en.add(seg[i:i + 2])
    return en


def score(desc: str, user: str) -> float:
    t = tokens(desc)
    u = tokens(user)
    if not t:
        return 0.0
    return len(t & u) / len(u)


def main() -> int:
    print("=" * 70)
    print(f"三案例实测 — {TARGET}")
    print("=" * 70)

    desc = load_desc(TARGET)
    check("SKILL.md 存在且有 description", bool(desc), f"len={len(desc)}")

    siblings = ["github-repo-push", "git-push-risk-gate", "gitea-push",
                "architecture-optimizer", "devops-repo-cleanup"]
    sibling_desc = {s: load_desc(s) for s in siblings}

    # ---- 案例 1：明确点名 ----
    print("[案例1] 明确点名：用户说了触发词")
    c1 = "用 monorepo-split 把 xmtool 拆成每个工具单独一个仓库"
    s = score(desc, c1)
    check("本 skill 得分 > 0", s > 0, f"score={s:.3f}")
    beaten = [k for k, v in sibling_desc.items() if score(v, c1) >= s]
    check("无兄弟 skill 得分不低于本 skill", not beaten, str(beaten))

    # ---- 案例 2：自然表达 ----
    print("[案例2] 自然表达：不点名，靠 description 路由")
    cases2 = [
        "我想每个工具单独一个项目仓库而不是合并到一起",
        "这个monorepo拆开，一个项目一个仓",
        "拆仓但要保留原来的git提交历史",
        "把subtree接进来的那个子目录抽出来成独立仓库",
    ]
    for c in cases2:
        s = score(desc, c)
        beaten = [k for k, v in sibling_desc.items() if score(v, c) >= s and s > 0]
        check(f"命中：「{c[:22]}…」", s > 0 and not beaten,
              f"score={s:.3f} beaten={beaten}")

    # ---- 案例 3：信息不完整 ----
    print("[案例3] 信息不完整：缺关键参数应标记缺失而非编造")
    # 检查 SKILL.md 是否显式要求在缺 prefix 时问用户
    skill_text = (SKILLS_DIR / TARGET / "SKILL.md").read_text(encoding="utf-8")
    check("有「未找到 subtree merge 就停下来问用户」的规则",
          "停下来问用户" in skill_text or "改用 cherry-pick" in skill_text)
    check("有前置门四问", "前置门" in skill_text)
    check("有「信息不足」/缺失相关处理", "未找到" in skill_text)

    # 脚本层面：缺 --prefix 必须报参数错误而非瞎猜
    import subprocess
    r = subprocess.run(
        [sys.executable, str(SKILLS_DIR / TARGET / "scripts" / "mono_split.py"), "C:/tmp"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    check("缺 --prefix 时退出码非 0（argparse 拒绝）", r.returncode != 0, f"rc={r.returncode}")
    check("错误信息提到 --prefix", "--prefix" in (r.stderr or ""), (r.stderr or "")[-120:])

    print("=" * 70)
    print(f"失败 {FAILED} 项")
    print("=" * 70)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
