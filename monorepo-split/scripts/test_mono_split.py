#!/usr/bin/env python3
"""test_mono_split.py — mono_split 的自测。

分层：
  外部检查 —— 真实 git 仓库跑完整拆分流程，验证提交数与 blob 集合（外部可复现）
  项目检查 —— CLI 契约、退出码契约
  自建测试 —— 探测逻辑、边界条件

用例全绿才算通过。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

RESULTS: list = []
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global FAILED
    RESULTS.append((name, ok, detail))
    if not ok:
        FAILED += 1
    print(f"    [{'OK' if ok else 'FAIL'}]   {name}   {detail}")


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {(r.stdout or '') + (r.stderr or '')}")
    return (r.stdout or "").strip()


def make_source(repo: Path, n: int = 3, subdir: str = "") -> str:
    """构造一个源仓，返回 tip sha。"""
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", ".")
    git(repo, "config", "user.email", "t@t.local")
    git(repo, "config", "user.name", "t")
    if subdir:
        (repo / subdir).mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        target = repo / subdir / f"f{i}.txt" if subdir else repo / f"f{i}.txt"
        target.write_text(f"v{i}\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"src commit {i}")
    return git(repo, "rev-parse", "HEAD")


def make_monorepo(mono: Path, src: Path, prefix: str) -> str:
    """构造 monorepo 并用 git subtree add 接入源仓，返回 merge sha。"""
    mono.mkdir(parents=True, exist_ok=True)
    git(mono, "init", "-q", ".")
    git(mono, "config", "user.email", "t@t.local")
    git(mono, "config", "user.name", "t")
    (mono / "base.txt").write_text("base\n", encoding="utf-8")
    git(mono, "add", "-A")
    git(mono, "commit", "-q", "-m", "mono base")
    git(mono, "remote", "add", "src", str(src))
    git(mono, "fetch", "-q", "src")
    git(mono, "subtree", "add", "--prefix", prefix, "src/master", "-m", f"Add '{prefix}/' from commit 'tip'")
    return git(mono, "rev-parse", "HEAD")


# ------------------------------------------------------------ 外部检查

def test_external_real_split():
    """真实 git 仓库跑完整拆分：源历史必须完整保留、内容零损坏。"""
    print("[1] 外部检查：真实仓库完整拆分（git 子命令，非 mock）")
    tmp = Path(tempfile.mkdtemp(prefix="mono-split-test-"))
    try:
        src = tmp / "src"
        mono = tmp / "mono"
        out = tmp / "out"

        src_tip = make_source(src, n=3)
        merge = make_monorepo(mono, src, "sub")
        src_count = int(git(src, "rev-list", "--count", "HEAD"))
        check("源仓构造出 3 个提交", src_count == 3, f"got={src_count}")
        check("monorepo 的 merge 是两父",
              len(git(mono, "log", "-1", "--format=%P", merge).split()) == 2)

        r = subprocess.run(
            [sys.executable, str(HERE / "mono_split.py"), str(mono),
             "--prefix", "sub", "--out", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        check("拆分脚本退出码 0", r.returncode == 0, f"rc={r.returncode}")

        if r.returncode != 0:
            print(r.stdout[-1500:])
            print(r.stderr[-800:])
            return

        final_count = int(git(out, "rev-list", "--count", "HEAD"))
        check("源历史 3 个提交全部接回", final_count == 3, f"got={final_count}")

        src_blobs = sorted(l.split()[2] for l in git(src, "ls-tree", "-r", "HEAD").splitlines() if l.strip())
        out_blobs = sorted(l.split()[2] for l in git(out, "ls-tree", "-r", "HEAD").splitlines() if l.strip())
        check("blob 集合完全一致（内容零损坏）", src_blobs == out_blobs,
              f"src={len(src_blobs)} out={len(out_blobs)}")

        top = git(out, "ls-tree", "--name-only", "HEAD").splitlines()
        check("提取后路径已提到根（无 sub/ 前缀）",
              all(not n.startswith("sub/") for n in top), str(top[:5]))
        check("提取后 base.txt 不在（那是 monorepo 的文件）", "base.txt" not in top)

        msgs = git(out, "log", "--format=%s").splitlines()
        check("源提交信息保留", "src commit 1" in msgs, str(msgs[:3]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_external_no_subtree_merge():
    """没有 subtree merge 结构时必须退出码 3，不能瞎猜。"""
    print("[2] 外部检查：非 subtree 历史必须明确失败（退出码 3）")
    tmp = Path(tempfile.mkdtemp(prefix="mono-split-nosub-"))
    try:
        mono = tmp / "mono"
        mono.mkdir(parents=True)
        git(mono, "init", "-q", ".")
        git(mono, "config", "user.email", "t@t.local")
        git(mono, "config", "user.name", "t")
        (mono / "a.txt").write_text("a\n", encoding="utf-8")
        git(mono, "add", "-A")
        git(mono, "commit", "-q", "-m", "plain")
        r = subprocess.run(
            [sys.executable, str(HERE / "mono_split.py"), str(mono), "--prefix", "sub", "--out", str(tmp / "out")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        check("退出码 3（未找到 subtree merge）", r.returncode == 3, f"rc={r.returncode}")
        check("输出目录未被创建", not (tmp / "out").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_external_output_exists_guard():
    """输出目录已存在时必须拒绝覆盖（防误删既有仓库）。"""
    print("[3] 外部检查：输出目录已存在时拒绝覆盖")
    tmp = Path(tempfile.mkdtemp(prefix="mono-split-guard-"))
    try:
        src = tmp / "src"
        mono = tmp / "mono"
        out = tmp / "out"
        make_source(src, n=2)
        make_monorepo(mono, src, "sub")
        out.mkdir()
        (out / "IMPORTANT.txt").write_text("do not lose\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(HERE / "mono_split.py"), str(mono), "--prefix", "sub", "--out", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        check("退出码 2（预检失败）", r.returncode == 2, f"rc={r.returncode}")
        check("既有文件未被删除", (out / "IMPORTANT.txt").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------ 项目检查

def test_cli_contract():
    print("[4] 项目检查：CLI 契约")
    r = subprocess.run(
        [sys.executable, str(HERE / "mono_split.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = r.stdout
    check("--prefix 必填", "--prefix" in out)
    check("--dry-run 存在", "--dry-run" in out)
    check("--out 存在", "--out" in out)
    check("--source-tip 存在", "--source-tip" in out)
    check("帮助含「接回」说明", "接回" in out or "历史" in out)


def test_dry_run_no_write():
    print("[5] 项目检查：--dry-run 不做任何写操作")
    tmp = Path(tempfile.mkdtemp(prefix="mono-split-dry-"))
    try:
        src = tmp / "src"
        mono = tmp / "mono"
        out = tmp / "out"
        make_source(src, n=2)
        make_monorepo(mono, src, "sub")
        before = git(mono, "rev-parse", "HEAD")
        r = subprocess.run(
            [sys.executable, str(HERE / "mono_split.py"), str(mono), "--prefix", "sub",
             "--out", str(out), "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        check("退出码 0", r.returncode == 0, f"rc={r.returncode}")
        check("输出目录未创建", not out.exists())
        check("原仓库 HEAD 未变", git(mono, "rev-parse", "HEAD") == before)
        # 日志走 stderr（logging 默认），stdout 只有 --help 之类
        combined = (r.stdout or "") + (r.stderr or "")
        check("输出含「计划」字样", "计划" in combined, combined[-200:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_source_no_hardcoded_secrets():
    print("[6] 项目检查：源码不含硬编码凭据")
    import re
    for name in ("mono_split.py", "test_mono_split.py"):
        text = (HERE / name).read_text(encoding="utf-8")
        pats = [
            r"ghp_[A-Za-z0-9]{20,}",
            r"github_pat_[A-Za-z0-9_]{20,}",
            r"(?i)password\s*=\s*['\"][^'\"]+['\"]",
            r"(?i)token\s*=\s*['\"][A-Za-z0-9]{20,}['\"]",
        ]
        hits = [p for p in pats if re.search(p, text)]
        check(f"{name} 无硬编码凭据", not hits, str(hits))


def test_compile():
    print("[7] 外部检查：py_compile")
    r = subprocess.run(
        [sys.executable, "-m", "py_compile", str(HERE / "mono_split.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    check("py_compile 退出码 0", r.returncode == 0, r.stderr[-300:])


def main() -> int:
    print("=" * 66)
    print("mono_split.py 自测")
    print("=" * 66)
    test_compile()
    test_external_real_split()
    test_external_no_subtree_merge()
    test_external_output_exists_guard()
    test_cli_contract()
    test_dry_run_no_write()
    test_source_no_hardcoded_secrets()
    print("=" * 66)
    print(f"检查项共 {len(RESULTS)} 项，失败 {FAILED} 项")
    print("=" * 66)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
