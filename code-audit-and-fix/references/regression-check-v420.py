#!/usr/bin/env python3
"""regression-check-v420.py — code-audit-and-fix v4.2.0 改动验收（案例 10/11 可机检部分）

只校验「机制是否真的写进了权威源」，不校验 agent 行为（那部分需真实跑审查）。
判据全部来自 references/ 原文，脚本不发明新规则。

用法:
    python regression-check-v420.py <skill_dir>

退出码: 0 全过 / 1 有失败项
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FAILS: list[str] = []
PASSES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSES.append(f"PASS  {name}")
    else:
        FAILS.append(f"FAIL  {name}  {detail}")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main(skill: Path) -> int:
    skill_md = read(skill / "SKILL.md")
    debt = read(skill / "references" / "debt-and-rules.md")
    workflow = read(skill / "references" / "workflow.md")
    tmpl = read(skill / "references" / "output-template.md")
    regress = read(skill / "references" / "regression-cases.md")
    changelog = read(skill / "references" / "archive" / "CHANGELOG.md")

    # ---------- 版本一致性（版本号只允许出现在 frontmatter 与正文一行） ----------
    vers = set(re.findall(r"^\s*version:\s*(\d+\.\d+\.\d+)$", skill_md, re.M))
    check("版本号 frontmatter 唯一且为 4.2.0", vers == {"4.2.0"}, f"found={vers}")
    check(
        "正文版本行同步 4.2.0",
        "当前 **v4.2.0**" in skill_md,
        "未见「当前 **v4.2.0**」",
    )

    # ---------- 案例 10：impact 校准锚点（§7.1） ----------
    sec71 = ""
    m = re.search(r"#### 7\.1 .*?(?=\n### |\n## |\Z)", debt, re.S)
    if m:
        sec71 = m.group(0)
    check("§7.1 锚点节存在", bool(sec71), "debt-and-rules.md 未找到 #### 7.1")

    for anchor in ["critical", "high", "medium", "low", "informational"]:
        check(f"§7.1 含 {anchor} 锚点", f"| {anchor} " in sec71 or f"**{anchor}**" in sec71)

    check(
        "§7.1 含硬约束「级别不得超过 impact」",
        "不得超过已演示" in sec71 or "不得超过已演示的 impact" in sec71,
    )
    check(
        "§7.1 含 high vs medium 唯一判别句",
        "完全击破" in sec71 and "只是削弱" in sec71,
    )
    check(
        "§7.1 含「低一档」直觉校准",
        "低一档" in sec71,
    )
    check(
        "§7.1 把「缺最佳实践/纵深防御缺口」归 P3",
        "加固建议" in sec71 and "P3" in sec71,
    )
    check(
        "§7.1 含锚点冲突消歧（说不出攻击路径一律 P3）",
        "锚点冲突消歧" in sec71 and "说不出攻击路径" in sec71,
    )
    check(
        "§7.1 与三态判定正交（待验证不给 P0/P1）",
        "待验证" in sec71 and "不给 P0/P1" in sec71,
    )
    check(
        "§7.1 已入目录",
        "7.1 安全类命中的 impact 校准锚点" in debt,
    )

    # ---------- 案例 11：覆盖终态与指纹（§1.4） ----------
    sec14 = ""
    m = re.search(r"### 1\.4 .*?(?=\n### 1\.5|\n## |\Z)", workflow, re.S)
    if m:
        sec14 = m.group(0)
    check("§1.4 节存在", bool(sec14), "workflow.md 未找到 ### 1.4")

    for sub in ["1.4.1", "1.4.2", "1.4.3", "1.4.4"]:
        check(f"§1.4 含 {sub} 小节", f"{sub} " in sec14)

    check(
        "指纹禁含行号/级别/verdict 明确写出",
        re.search(r"禁止.*指纹含|指纹含", sec14) is not None
        and "行号" in sec14
        and ("verdict" in sec14 or "级别" in sec14),
    )
    check(
        "覆盖声称三项可点回（检查项/路径/执行者）",
        "检查项" in sec14 and "哪些路径" in sec14 and "谁跑的" in sec14,
    )
    check(
        "明确「agent 数量不是证据」",
        "agent 数量不是证据" in sec14,
    )
    check(
        "无 critic 位禁写「无遗留问题」",
        "无遗留问题" in sec14 and "禁止" in sec14,
    )
    check(
        "四终态：完整 / incomplete + 首段披露",
        "不完整" in sec14 and "首段" in sec14 and "reason" in sec14,
    )
    check(
        "rejected 只压单条主张（主张=范围，非文件=范围）",
        "被否定的主张 = 范围" in sec14,
    )

    # ---------- 报告模板强制段 ----------
    check(
        "模板首段含「覆盖终态与缺口」块",
        "覆盖终态与缺口" in tmpl,
    )
    check(
        "模板块位于执行摘要之前（真首段）",
        tmpl.find("覆盖终态与缺口") < tmpl.find("### 🎯 执行摘要")
        if "覆盖终态与缺口" in tmpl and "### 🎯 执行摘要" in tmpl
        else False,
    )
    check(
        "模板单条字段升七要素并含指纹",
        "七要素" in tmpl and "指纹：" in tmpl,
    )

    # ---------- 阶段 C 挂接 ----------
    check(
        "阶段 C 增加 C4 覆盖自检",
        "C4: 覆盖声称自检" in workflow,
    )

    # ---------- 回归基线数量一致 ----------
    cases = re.findall(r"^## 案例 (\d+) ·", regress, re.M)
    check(
        "回归案例数 = 11",
        len(cases) == 11,
        f"实际 {len(cases)} 个: {cases}",
    )
    check(
        "SKILL.md §C 声明 11 组",
        "**11 组**" in skill_md,
        "§C 仍写旧组数",
    )
    check(
        "汇总表含案例 10/11 行",
        "| 10 impact 校准锚点 |" in regress and "| 11 覆盖终态 + 指纹稳定 |" in regress,
    )
    check(
        "汇总表口径「十一项全通过」",
        "十一项全通过" in regress,
    )

    # ---------- 未吸收项表述已收窄 ----------
    check(
        "未吸收项不再整块否掉 coverage 判据",
        "机器化设施" not in skill_md,
        "仍含「机器化设施」旧表述",
    )
    check(
        "未吸收项点名 artifact promotion 与口径说明",
        "artifact promotion 11 步" in skill_md and "判据" in skill_md,
    )

    # ---------- CHANGELOG ----------
    check("CHANGELOG 含 v4.2.0 段", "**v4.2.0**（2026-11-24）" in changelog)
    check(
        "CHANGELOG 声明媒体 25% 说法不采信",
        "25%" in changelog and "不采信" in changelog,
    )


    # ---------- 基线头部描述同步 ----------
    check(
        "回归基线头部描述为十一组",
        "十一组案例覆盖" in regress,
        "头部仍写旧组数",
    )

    # ---------- 输出 ----------
    print("\n".join(PASSES))
    if FAILS:
        print()
        print("\n".join(FAILS))
        print(f"\n结果: {len(PASSES)} 通过 / {len(FAILS)} 失败")
        return 1
    print(f"\n结果: 全部 {len(PASSES)} 项通过")
    return 0


if __name__ == "__main__":
    d = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    sys.exit(main(d))
