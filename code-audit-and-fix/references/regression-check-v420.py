#!/usr/bin/env python3
"""regression-check-v420.py — code-audit-and-fix v4.2.0 改动验收（案例 10/11 可机检部分）

只校验「机制是否真的写进了权威源」，不校验 agent 行为（那部分需真实跑审查）。
判据全部来自 references/ 原文，脚本不发明新规则。

用法:
    python regression-check-v420.py <skill_dir>       # 正常校验
    python regression-check-v420.py --selftest-check <skill_dir>
                                                      # 校验「校验器自身」是否可信

退出码（三态，禁混淆）:
    0 = 全部 PASS
    1 = 有 FAIL（断言违约，即被校验内容不符合预期）
    2 = ERROR（工具自身故障：必检文件缺失、读取失败等）
        2026-11-24 修正：原实现把「文件缺失」也走 FAIL 通道，
        于是「校验器坏了」和「内容不对」输出形态相同、退出码相同，
        验收结论不可信（ERR-20261124-004）。现分离。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PASSES: list[str] = []
FAILS: list[str] = []
ERRORS: list[str] = []

# 缺了任一项就无法判定内容正确性的文件（缺失即工具故障，不是断言失败）
REQUIRED = [
    "SKILL.md",
    "references/debt-and-rules.md",
    "references/workflow.md",
    "references/output-template.md",
    "references/regression-cases.md",
    "references/archive/CHANGELOG.md",
]


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSES if cond else FAILS).append(
        f"{'PASS' if cond else 'FAIL'}  {name}  {detail}".rstrip()
    )


def error(msg: str) -> None:
    ERRORS.append(f"ERROR  {msg}")


def read(p: Path, required: bool = False) -> str:
    """读文件。缺失时：required → 记 ERROR（工具故障）；否则返回空串（不参与断言）。

    rr: 区分「工具坏了」与「内容不对」是验收可信的前提。
    """
    if not p.exists():
        if required:
            error(f"必检文件缺失：{p}")
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        error(f"必检文件读取失败：{p}（{exc}）")
        return ""


def main(skill: Path) -> int:
    skill_md = read(skill / "SKILL.md", required=True)
    debt = read(skill / "references" / "debt-and-rules.md", required=True)
    workflow = read(skill / "references" / "workflow.md", required=True)
    tmpl = read(skill / "references" / "output-template.md", required=True)
    regress = read(skill / "references" / "regression-cases.md", required=True)
    changelog = read(skill / "references" / "archive" / "CHANGELOG.md", required=True)

    # 前置：必检文件不齐 → 立即 ERROR 退出，不进入断言（避免「空串导致全 FAIL」误判）
    if ERRORS:
        print("\n".join(ERRORS))
        print(f"\n结果: ERROR（工具故障 {len(ERRORS)} 项，未执行断言）")
        return 2

    # ---------- 版本一致性（版本号只允许出现在 frontmatter 与正文一行） ----------
    vers = set(re.findall(r"^\s*version:\s*(\d+\.\d+\.\d+)$", skill_md, re.M))
    check("版本号 frontmatter 唯一且为 4.2.1", vers == {"4.2.1"}, f"found={vers}")
    check(
        "正文版本行同步 4.2.1",
        "当前 **v4.2.1**" in skill_md,
        "未见「当前 **v4.2.1**」",
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

    check(
        "§C 登记了三段式验收",
        "三段式验收" in skill_md and "工具故障" in skill_md,
    )
    check(
        "§C 登记了 selftest 用法",
        "--selftest-check" in skill_md,
    )
    check(
        "§C 登记了退出码三态",
        "退出码三态" in skill_md and "工具故障，未执行断言" in skill_md,
    )

    # ---------- 输出 ----------
    for e in ERRORS:
        print(e)
    print("\n".join(PASSES))
    if FAILS:
        print()
        print("\n".join(FAILS))
        print(f"\n结果: {len(PASSES)} 通过 / {len(FAILS)} 失败"
              + (f" / {len(ERRORS)} 工具故障" if ERRORS else ""))
        return 1
    print(f"\n结果: 全部 {len(PASSES)} 项通过")
    return 0


def selftest_check(skill: Path) -> int:
    """校验「校验器自身」是否可信（三段式验收的第三段 · 工具故障必须可辨）。

    2026-11-24 立，来源 ERR-20261124-004：校验器崩溃/工具故障与断言失败
    在输出形态和退出码上必须可区分，否则验收结论不可信。

    本函数校验三件事：
      A. 必检文件缺失 → 退出码 2（ERROR），且不输出任何 PASS/FAIL
         —— 证明「工具故障」不会被伪装成「断言失败」
      B. 正常目录 → 退出码 0/1（PASS/FAIL），且无 ERROR 行
         —— 证明干净路径不被工具故障污染
      C. 取行类断言不得使用位置索引 split()[N]
         —— 该类写法在目标行缺失时抛 IndexError（崩溃），而非报 FAIL

    用法: python regression-check-v420.py --selftest-check <skill_dir>
    """
    import subprocess
    import tempfile

    me = Path(__file__).resolve()
    ok = True

    def verdict(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        if not cond:
            ok = False
            print(f"FAIL  {name}  {detail}")
        else:
            print(f"PASS  {name}")

    # A. 必检文件缺失 → ERROR(2)，且 stdout 无 PASS/FAIL
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(
            [sys.executable, str(me), td],
            capture_output=True, text=True, timeout=120,
        )
        verdict("A1 空目录 → 退出码 2（工具故障）", r.returncode == 2, f"got={r.returncode}")
        verdict("A2 空目录 → 输出含 ERROR 行", "ERROR" in r.stdout, "未见 ERROR")
        # A3 判据必须含「未崩溃」：若脚本抛异常，stdout 也没有 PASS/FAIL 行，
        # 单看「无 PASS/FAIL」会让崩溃被误判为通过（2026-11-24 注入实测发现）。
        crashed = "Traceback (most recent call last)" in r.stderr
        verdict("A3 空目录 → 无 PASS/FAIL 行且未崩溃",
                "PASS  " not in r.stdout and "FAIL  " not in r.stdout and not crashed,
                "崩溃" if crashed else "把工具故障输出成了断言结果")

    # B. 正常目录 → 0 或 1，且无 ERROR
    r = subprocess.run(
        [sys.executable, str(me), str(skill)],
        capture_output=True, text=True, timeout=120,
    )
    verdict("B1 正常目录 → 退出码 ∈ {0,1}", r.returncode in (0, 1), f"got={r.returncode}")
    verdict("B2 正常目录 → 无 ERROR 行", "ERROR" not in r.stdout, "干净路径出现工具故障")

    # C. 静态检查：禁用位置索引取行
    src = me.read_text(encoding="utf-8")
    body = src.split('if __name__ == "__main__":')[0]
    bad = re.findall(r"\.split\([^)]*\)\[\s*\d+\s*\]", body)
    verdict("C1 无位置索引取行（split()[N]）", not bad, f"发现 {len(bad)} 处：{bad[:3]}")

    print(f"\n自检结果: {'全部通过' if ok else '有失败项'}")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--selftest-check":
        sys.exit(selftest_check(Path(args[1] if len(args) > 1 else ".")))
    sys.exit(main(Path(args[0] if args else ".")))
