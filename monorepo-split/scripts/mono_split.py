#!/usr/bin/env python3
"""mono_split.py — 把 monorepo 中的一个子树拆成独立仓库，**并接回子树自己的提交历史**。

背景
----
monorepo 用 `git subtree add` 接入子项目时，会产生一个**两父 merge 提交**：

    *   <merge>  Add 'prefix/' from commit '<src-tip>'
    |\
    | * <src-c3>
    | * <src-c2>
    | * <src-c1>
    * <mono-base>

此时源项目的提交历史在 monorepo 里是**可达**的。但直接跑

    git filter-repo --subdirectory-filter <prefix>

会把源历史压成**一个提交**（实测：xmtool 19 个源提交 → 1 个），历史断链。

本脚本按「路径映射 → 重建 merge → 提取子目录」三步接回源历史。

核心机理（2026-10-27 实测得出，见 SKILL.md 核心事实表）
---------------------------------------------------------
  filter-repo 提取子目录时，只有**改动全部落在前缀路径内**的提交才会被保留。
  源项目文件在仓库根目录时，其提交改的是根路径，与 monorepo 的前缀路径不重合，
  于是全部被丢弃、压成 1 个 squash 提交。

  所以必须先把源历史的路径**映射**成 monorepo 里的前缀路径，
  让「源提交的改动路径」与「merge 提交树里的前缀路径」对齐，
  提取时源提交才不会再变成空提交而被丢弃。

用法
----
    python mono_split.py <monorepo路径> --prefix <子树路径> [--name <新仓名>]
                         [--source-tip <sha>] [--out <输出目录>] [--dry-run]

    --prefix       monorepo 内该子树的路径，如 xmtool/src/RemoteDesktopPlus
    --source-tip   源历史 tip（默认自动从 merge 提交的第二父推导）
    --out          输出目录（默认 <monorepo父目录>/<prefix末段>-split）
    --name         新仓名（用于日志）
    --dry-run      只探测与打印计划，不做任何写操作

退出码
------
    0  成功
    2  参数/预检失败
    3  未找到 subtree merge 结构（不是 subtree 接入的历史）
    4  历史接回后校验失败（源历史丢失或内容不一致）
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("mono_split")

EXIT_OK = 0
EXIT_PRECHECK = 2
EXIT_NO_SUBTREE = 3
EXIT_VERIFY = 4

MERGE_SUBJECT_RE = re.compile(r"^Add '(?P<prefix>.+)' from commit '(?P<sha>[0-9a-f]{7,40})'")


class SplitError(Exception):
    def __init__(self, msg: str, code: int, hint: str = ""):
        super().__init__(msg)
        self.code = code
        self.hint = hint


def run_git(repo: Path, args: list, check: bool = True, timeout: int = 600) -> str:
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise SplitError("git 不在 PATH 中", EXIT_PRECHECK, "安装 git 或修正 PATH") from e
    except subprocess.TimeoutExpired as e:
        raise SplitError(f"git {' '.join(args)} 超时（{timeout}s）", EXIT_PRECHECK) from e
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if check and r.returncode != 0:
        raise SplitError(
            f"git {' '.join(args)} 失败（exit={r.returncode}）",
            EXIT_PRECHECK,
            detail=out[:500],
        )
    return out


def git_out(repo: Path, args: list, timeout: int = 600) -> str:
    """只取 stdout（不混 stderr），用于取 sha 这类精确输出。"""
    r = subprocess.run(
        ["git"] + args,
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if r.returncode != 0:
        raise SplitError(
            f"git {' '.join(args)} 失败（exit={r.returncode}）",
            EXIT_PRECHECK,
            detail=((r.stdout or "") + (r.stderr or ""))[:500],
        )
    return (r.stdout or "").strip()


# ---------------------------------------------------------------- 探测

def find_subtree_merge(repo: Path, prefix: str) -> Tuple[str, str, str]:
    """找出把 prefix 接入主线的两父 merge 提交。

    返回 (merge_sha, parent1, parent2)。找不到则抛 EXIT_NO_SUBTREE。
    """
    prefix = prefix.strip("/")
    log.info("扫描提交历史，寻找 subtree merge 提交…")
    # 找所有 merge 提交（含 subject 匹配与树结构匹配两条线索）
    merges = git_out(repo, ["rev-list", "--merges", "--all"]).splitlines()
    candidates = []
    for m in merges:
        subj = git_out(repo, ["log", "-1", "--format=%B", m]).strip()
        mt = MERGE_SUBJECT_RE.match(subj)
        if mt and mt.group("prefix").strip("/") == prefix:
            candidates.append((m, mt.group("sha"), subj))
    if not candidates:
        # 兜底：按树结构找 —— 树里有 prefix/ 且提交有两个父
        for m in merges:
            names = git_out(repo, ["ls-tree", "-r", "--name-only", m]).splitlines()
            if any(n.startswith(prefix + "/") for n in names):
                parents = git_out(repo, ["log", "-1", "--format=%P", m]).split()
                if len(parents) == 2:
                    candidates.append((m, parents[1], "（按树结构匹配）"))
                    break
    if not candidates:
        raise SplitError(
            f"未找到 prefix={prefix!r} 的 subtree merge 提交",
            EXIT_NO_SUBTREE,
            "该子树可能不是用 git subtree add 接入的（无两父 merge）；"
            "请确认历史形态后改用 filter-branch/cherry-pick 手工迁移",
        )
    # 取最新的一个
    candidates.sort(key=lambda c: git_out(repo, ["log", "-1", "--format=%ct", c[0]]), reverse=True)
    merge, src_tip, _ = candidates[0]
    parents = git_out(repo, ["log", "-1", "--format=%P", merge]).split()
    log.info("命中 merge 提交: %s", merge[:12])
    log.info("  父1(主线): %s", parents[0][:12])
    log.info("  父2(源):   %s", parents[1][:12])
    return merge, parents[0], parents[1]


def count_commits(repo: Path, ref: str) -> int:
    return int(git_out(repo, ["rev-list", "--count", ref]))


def blob_multiset_md5(repo: Path, ref: str) -> str:
    """blob sha 多重集的 md5。

    刻意不用「逐行 diff 树路径」：git ls-tree 对非 ASCII 路径会加引号，
    文本级 sed/diff 会产生假阳性。blob sha 是内容本身，与路径编码无关。
    """
    out = git_out(repo, ["ls-tree", "-r", ref])
    shas = sorted(line.split()[2] for line in out.splitlines() if line.strip())
    return hashlib.md5("\n".join(shas).encode("ascii")).hexdigest()


# ---------------------------------------------------------------- 主流程

def split(repo: Path, prefix: str, out_dir: Path, source_tip: Optional[str],
          dry_run: bool) -> int:
    prefix = prefix.strip("/")

    # ---- 预检 ----
    if not repo.is_dir():
        raise SplitError(f"仓库路径不存在: {repo}", EXIT_PRECHECK)
    if not (repo / ".git").is_dir():
        raise SplitError(f"不是 git 仓库: {repo}", EXIT_PRECHECK)
    if count_commits(repo, "HEAD") == 0:
        raise SplitError("仓库没有任何提交", EXIT_PRECHECK)

    merge, p1, p2 = find_subtree_merge(repo, prefix)
    src_tip = source_tip or p2
    src_count_before = count_commits(repo, src_tip)

    log.info("源历史提交数（接回前）: %d", src_count_before)
    log.info("源 tip 的树顶层: %s", git_out(repo, ["ls-tree", "--name-only", src_tip]).splitlines()[:6])

    if dry_run:
        log.info("[dry-run] 计划：")
        log.info("  1) 复制仓库到 %s", out_dir)
        log.info("  2) 路径映射：源历史全部路径加前缀 %r", prefix)
        log.info("  3) 重建 merge：父2 换成映射后的源 tip")
        log.info("  4) 提取子目录 %r", prefix)
        log.info("  5) 校验：提交数 %d，blob 多重集一致", src_count_before)
        return EXIT_OK

    # ---- 步骤 1: 复制到输出目录 ----
    if out_dir.exists():
        raise SplitError(
            f"输出目录已存在: {out_dir}",
            EXIT_PRECHECK,
            "为防覆盖既有仓库，换 --out 或先手工确认后删除",
        )
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    # 只复制 .git（对象库+ refs），**不复制工作区**。
    # 工作区里是 monorepo 的全部文件（含其他子项目），filter-repo 只重写历史、
    # 不会清理工作区 —— 直接 copytree 会把 pmvault/ team-planner/ 等
    # 无关目录留在产物里，推送时被当成未跟踪文件混进去。
    log.info("复制 .git 到 %s（不复制工作区）", out_dir)
    out_dir.mkdir(parents=True)
    shutil.copytree(repo / ".git", out_dir / ".git", symlinks=True)
    # 去掉嵌套仓库备份与多余远端，避免复制出脏状态
    for junk in list(out_dir.glob(".git/rdp-nested-backup")):
        shutil.rmtree(junk, ignore_errors=True)
    work = out_dir
    # 清掉从 monorepo 带来的远端（推送到新仓由调用方另行配置）
    for r in git_out(work, ["remote"]).splitlines():
        if r.strip():
            run_git(work, ["remote", "remove", r.strip()], check=False)

    # ---- 步骤 2: 路径映射（源历史加前缀）----
    # 用分支引用而非裸 sha：filter-repo 只更新它能对应到的 ref，
    # 裸 sha 传进去不会更新该 sha，映射结果会「看不到」。
    mapped_branch = "mapped-src-tmp"
    run_git(work, ["branch", mapped_branch, src_tip])
    run_git(work, [
        "filter-repo",
        "--filename-callback", "return b'%s/' + filename" % prefix,
        "--refs", mapped_branch,
        "--replace-refs", "delete-no-add",
        "--force",
    ])
    mapped_tip = git_out(work, ["rev-parse", mapped_branch])
    mapped_count = count_commits(work, mapped_branch)
    log.info("路径映射完成: %d 个提交 → %d 个提交", src_count_before, mapped_count)
    if mapped_count != src_count_before:
        raise SplitError(
            f"路径映射后提交数变化（{src_count_before} → {mapped_count}）",
            EXIT_VERIFY,
            "映射不应增删提交，检查 filename-callback 是否误伤路径",
        )
    mapped_names = git_out(work, ["ls-tree", "-r", "--name-only", mapped_branch]).splitlines()
    if not any(n.startswith(prefix + "/") for n in mapped_names):
        raise SplitError(
            f"映射后源 tip 树里没有 {prefix}/ 前缀路径",
            EXIT_VERIFY,
            f"实际顶层: {mapped_names[:6]}",
        )

    # 源侧 blob 清单：**必须在提取前采集**。
    # 步骤 4 的 filter-repo 会清理未被任何 ref 引用的对象，
    # 映射用的临时分支届时已不存在，事后再查会得到空集（假阴性）。
    src_shas = sorted(
        line.split()[2]
        for line in git_out(work, ["ls-tree", "-r", mapped_branch]).splitlines()
        if line.strip()
    )
    log.info("映射后源侧 blob 数: %d", len(src_shas))

    # ---- 步骤 3: 重建 merge（父2 → 映射后的源 tip）----
    tree = git_out(work, ["rev-parse", f"{merge}^{{tree}}"])
    msg = git_out(work, ["log", "-1", "--format=%B", merge])
    new_merge = git_out(work, ["commit-tree", tree, "-p", p1, "-p", mapped_branch, "-m", msg])
    log.info("重建 merge: %s → %s（父2 换成映射后的 %s）",
             merge[:12], new_merge[:12], mapped_tip[:12])
    run_git(work, ["replace", merge, new_merge])

    # ---- 步骤 4: 提取子目录 ----
    run_git(work, [
        "filter-repo",
        "--subdirectory-filter", prefix,
        "--replace-refs", "delete-no-add",
        "--force",
    ])

    # ---- 步骤 4.5: 重建工作区 ----
    # 只复制了 .git，工作区是空的。filter-repo 改写的是历史，
    # 不会把新 HEAD 的内容铺到工作区 —— 必须显式 checkout，
    # 否则产物工作区空着，后续裁剪治理文件与脱敏都无从下手。
    run_git(work, ["checkout", "-f", "HEAD"], check=False)
    run_git(work, ["reset", "--hard", "HEAD"], check=False)
    work_files = [p for p in work.rglob("*")
                   if p.is_file() and ".git" not in p.parts]
    log.info("工作区已重建: %d 个文件", len(work_files))
    dirty = git_out(work, ["status", "--porcelain"])
    if dirty.strip():
        log.warning("工作区有残留改动（%d 行）", len(dirty.splitlines()))

    # ---- 步骤 5: 校验 ----
    final_count = count_commits(work, "HEAD")
    final_shas = sorted(
        line.split()[2] for line in git_out(work, ["ls-tree", "-r", "HEAD"]).splitlines()
        if line.strip()
    )

    log.info("最终提交数: %d（源历史 %d）", final_count, src_count_before)
    log.info("最终 blob 数: %d（源侧 %d）", len(final_shas), len(src_shas))

    if final_count < src_count_before:
        raise SplitError(
            f"历史接回不完整：最终 {final_count} 个提交 < 源历史 {src_count_before} 个",
            EXIT_VERIFY,
            "检查步骤 2 的路径映射是否让源提交落在前缀路径内",
        )
    if src_shas != final_shas:
        raise SplitError(
            "blob 集合不一致：内容可能损坏",
            EXIT_VERIFY,
            f"源侧 {len(src_shas)} 个 vs 最终 {len(final_shas)} 个",
        )

    # 清掉临时分支与 replace ref
    run_git(work, ["branch", "-D", mapped_branch], check=False)
    run_git(work, ["replace", "-d", merge], check=False)

    log.info("✅ 历史接回成功：%d 个源提交全部保留，内容零损坏", final_count)
    log.info("输出仓库: %s", work)
    log.info("下一步: 用 github-repo-push skill 推送到 GitHub")
    return EXIT_OK


def main() -> int:
    ap = argparse.ArgumentParser(
        description="把 monorepo 中的子树拆成独立仓库并接回源提交历史",
    )
    ap.add_argument("repo", help="monorepo 本地路径")
    ap.add_argument("--prefix", required=True, help="子树在 monorepo 内的路径，如 xmtool/src/RemoteDesktopPlus")
    ap.add_argument("--name", help="新仓名（仅日志用）")
    ap.add_argument("--source-tip", help="源历史 tip（默认自动推导）")
    ap.add_argument("--out", help="输出目录（默认 <monorepo>/../<prefix末段>-split）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不做写操作")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    repo = Path(args.repo).resolve()
    prefix = args.prefix
    if args.out:
        out_dir = Path(args.out).resolve()
    else:
        leaf = prefix.rstrip("/").split("/")[-1]
        out_dir = repo.parent / f"{leaf}-split"

    try:
        code = split(repo, prefix, out_dir, args.source_tip, args.dry_run)
        return code
    except SplitError as e:
        log.error("%s", e)
        if getattr(e, "hint", ""):
            log.error("处置建议: %s", e.hint)
        if getattr(e, "detail", ""):
            log.error("细节: %s", e.detail)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
