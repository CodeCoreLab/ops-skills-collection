---
name: code-audit-and-fix
display_name: "一体化代码质量中枢"
display_name_en: "Code Audit and Fix Hub"
description: "一体化代码质量中枢（多文件/多模块级）：审计 + 分级修复 + 重构 + 依赖审计 + 架构评审 + 健康度量化 + 技术债治理 + 运维脚本审计。四层 × 40 项语言规则 × 24 项修复标签（噪声/冗余/重复/结构/可靠性）× 10 个修复动词 × 七维清单+并发专项 × P0/P1/P2/P3 四级分级 × 三态判定（确认/待验证/已否定）× 健康评分 1-10 + CAC/Bus Factor/DICE/ROI/7R/T-shirt 量化。触发：「代码审计」「全量审查」「技术债评估」「重构」「依赖审计」「架构评审」「健康度评分」「运维脚本审计」「上下游核验」「自动修复」「清理死代码」「消除重复」「处理审查意见」。**反触发（勿用本 skill）**：单文件/单函数的小改、纯查语法、只要一段代码的解释、以及自查性质的「帮我看看这段对不对」——直接改或用宿主 `CODE_REVIEW_CHECKLIST.md`。互斥边界：单 PR/单片段的 review 由用户显式调 `/code-review-router`（在 `skills/code-review-master/` 下，被设为 user-invocable-only，agent 无法自动加载）；整仓死代码批量清扫 `deadcode-scanner`（本技能 `dead_code` 标签只做审查范围内的标注+删除）；技术债专项治理 `tech-debt-manager`；纯安全专项**本机无独立 skill**，走本技能 `references/review-checklist.md` §3.4④。"
description_zh: "一体化代码质量中枢：审计、分级修复、重构、依赖审计、架构评审、健康度量化、技术债治理与运维脚本审计。"
description_en: "An all-in-one code quality hub: audit, tiered fixes, refactoring, dependency audit, architecture review, health scoring, tech-debt governance and ops script auditing."
version: 4.2.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    title: code-audit-and-fix
    version: 4.2.0
    summary: 一体化代码质量中枢（多文件/多模块级）。三阶段流程（阻断判定→并行深审 W1‖W2‖W3→优化报告）× P0 早停门 × 40 项语言规则 × 24 项修复标签 × 10 个修复动词 × 七维清单+并发专项（L1–L6 顺序视图）× P0-P3 四级分级 × 三态判定（确认/待验证/已否定）× 发现者/验证者分离 × 反合理化表 × 不报反清单 × 接收审查侧流程 × Conventional Comments × 健康评分 1-10 + CAC/Bus Factor/DICE/ROI/7R/T-shirt。入口只放门禁与导航，细则在 references/ 按档位加载。
---

# code-audit-and-fix — 一体化代码质量中枢

**定位**：多文件/多模块级代码质量的统一入口。三阶段（阻断判定 → 并行深审 → 优化报告）× 双引擎（精确 grep / 数据流追踪）× 40 项语言规则 × 24 项修复标签 × 10 个修复动词 × P0-P3 四级分级 × 三态判定。

**核心能力**：代码审计 · 缺陷修复 · 重构简化 · 依赖审计 · 架构评审 · 技术债治理 · 上下游核验 · 测试生成 · 审查意见处理（接收侧）

---

## 0. 宿主规则优先（L0，权威源唯一）

本机 `~/.workbuddy/` 已有常驻规则与清单。**冲突时不双写，按此表归口**：

| 主题 | 权威源 | 本技能角色 |
|---|---|---|
| 5 维快筛、P0 阻断项（覆盖前必 Read / 备份 / 验证） | 宿主 `CODE_REVIEW_CHECKLIST.md` | 只引用，不复述 |
| 代码生成纪律（Ponytail / 改根因 / 定稿纪律 / 洁癖分级） | 宿主 `rules/codegen.md` | 只引用，不复述 |
| 架构约束、安全红线、术语 | 宿主 `rules/{architecture,security,core,glossary}.md` | 只引用，不复述 |
| 审查方法论（本篇 §A/§B）、量化模型（DICE/ROI/CAC/7R/Bus Factor）、语言规则库 | **本技能 `references/`** | 唯一权威源 |

**写结论前先读宿主清单**：P0 阻断项（如「覆盖前必须 Read」）由宿主定义，本技能不再重列。若宿主清单缺失，才回落到本技能口径并显式标注。

---

## A. 执行流程（三阶段）

```
阶段 A · 阻断判定（串行，快速通道）
  A1 定范围 → 全量 / Git 变更 / 代码片段（片段模式跳过 §2 依赖核验）
  A2 定档位 → 轻量 / 标准 / 对抗（见下表）
  A3 扫阻断类规则（§6 中标 P0/P1 者优先）
  ⛔ 早停门：扫出 P0 → 立即输出阻断报告，跳过阶段 C（用户明确要求全量时除外）

阶段 B · 深度审查（并行分组）
  W1 静态规则组 ‖ W2 语义分析组 ‖ W3 Spec 忠实轴（有需求上下文时）
  → 汇聚：去重 + 置信度标注 + 三态判定（§1.3，见 workflow.md）
  → P0/P1 候选由独立上下文验证者证伪式复核（发现者 ≠ 验证者，§1.2）

阶段 C · 优化与报告（无 P0/P1 时完整执行）
  C1 性能/可维护性/测试覆盖细化 → §3.4 ⑤⑥③
  C2 技术债量化（DICE/ROI）+ 健康评分 → §2.4 / §5
  C3 报告 → §9.2 模板（output-template.md，含三态统计与已否定清单）

阶段 D · 自动修复（用户说「自动修复/清理/去冗余」时）
  D1 打标签 + 定动词 → §10.2 / §10.3（fix-taxonomy.md）
  D2 过滤 → §10.5 三张表（可自动 / 待人工 / 禁自动）
  D3 自动堆逐点改 + §10.6 四项验证
  D4 人工堆出方案不改码 → 报告双视角呈现（§10.8）

阶段 E · 审查意见处理（用户贴来他人审查意见 / 用户对本技能报告有异议时）
  E1 六步核验（READ→UNDERSTAND→VERIFY→EVALUATE→RESPOND→IMPLEMENT）→ workflow.md §1.5
  E2 采纳走验收循环（§B4）；反驳给技术理由+证据，回写「已否定候选」
```

### 档位判定与最小必读集（成本单一源）

| 档位 | 触发条件 | 必读文件 | 跳过 |
|---|---|---|---|
| **轻量** | 改动 <100 行且无敏感标签 | `SKILL.md` 本篇即足（门禁 §B） | 全部 references |
| **标准** | 100–400 行，常规业务 | `workflow.md` + `review-checklist.md`（含 §3.0 反合理化表/反清单/防假阳性） | `dependency-arch.md`（无依赖变更时）、`ops-audit.md`、`output-template.md`（用宿主清单口径） |
| **对抗** | >400 行或含敏感标签 | `workflow.md` + `review-checklist.md` + `dependency-arch.md` + `debt-and-rules.md` + `output-template.md` | `ops-audit.md`（非运维脚本） |
| **运维脚本** | 用户说运维脚本审计 | `ops-audit.md` + `workflow.md` | 其余按档位 |
| **自动修复** | 用户说「自动修复」「清理死代码」「消除重复」「去冗余」 | `fix-taxonomy.md` + `debt-and-rules.md` | `dependency-arch.md`、`ops-audit.md`（无依赖/运维脚本问题时） |
| **意见处理** | 用户贴来审查意见要求逐条处理 | `workflow.md` §1.5（接收审查侧） + 宿主 `rules/codegen.md` | 其余按需 |

**敏感标签**：`auth` `pay` `credential` `secret` `token` `db` `sql` `schema` `admin` `permission` `upload` `download` `api`

**PR 规模**：≤400 行正常；400–1000 行按模块分组并行；>1000 行拒绝合并必须拆分。一个 PR 只做一件事，重构与功能分离。

### 编号对照（§N 编号不变，按此定位）

| 编号 | 主题 | 文件 |
|---|---|---|
| §1 | 执行流程 / 并行分组 / 发现者验证者分离 / 三态判定 / 聚合规则 / 三路分发 / 验收循环 / **接收审查侧（§1.5）** / **指纹与覆盖终态（§1.4）** | `references/workflow.md` |
| §2 | 依赖审查 / 上下游核验 / 整体健康评分 | `references/dependency-arch.md` |
| §3 | 反合理化表 / 不报反清单 / 防假阳性三原则 / 两遍法 / Self-Review / 反馈质量 / 七维清单+并发专项（§3.4⑧）/ 规约三级映射（§3.5）/ OWASP | `references/review-checklist.md` |
| §4 | 分层依赖 / 微服务 / 坏味道 / 可观测性 / ADR / ROI / 7R / CAC | `references/dependency-arch.md` |
| §5 | DICE / ROI / 门禁 / 配额六分类 / Bus Factor | `references/debt-and-rules.md` |
| §6 | 语言扫描规则库（**40 项**：PY 18 / GO 7 / JAV 4 / JS 7 / UNIV 4） | `references/debt-and-rules.md` |
| §7 | 缺陷分级 / 判定细则 / **impact 校准锚点（§7.1）** / 根因约束 / 测试生成 / T-shirt | `references/debt-and-rules.md` |
| §8 | 运维脚本审计模式（6 类高发 + 修复铁律） | `references/ops-audit.md` |
| §9 | 工具降级 / 报告输出模板（含三态统计 / 已否定候选 / 生命周期 verdict） | `references/output-template.md` |
| §10 | 修复标签体系（24 标签 / 10 动词 / 自动修复边界 / 行为变更声明与验证） | `references/fix-taxonomy.md` |
| 版本沿革 | v1.0 → v4.2 | `references/archive/CHANGELOG.md` |

---

## C. 回归样例组（改本技能后必跑）

改动 `SKILL.md` 或任一 `references/*.md` 前留快照，改后跑 `references/regression-cases.md` 的 **11 组**固定案例（早停门 / 证据门槛 / 分级呈现+PY-07 双模 / W3 自取证 / 形态模误报边界 / 标签-动词映射与自动修复边界 / 三态判定+发现者验证者分离 / 接收审查侧六步 / 验证计划可证伪 / impact 校准锚点 / 覆盖终态+指纹稳定），输出与预期一致才采纳；不一致先回滚再定位。

## D. 外部实践吸收登记（2026-10-27 立，v4.1 增补）

| 来源 | 吸收内容 | 落点 |
|---|---|---|
| alibaba/open-code-review | precision-over-noise 取舍口径 | §3.0.2 不报反清单 |
| alibaba/loongcollector code-review | 防假阳性三原则 · review-plan 勾选式计划 · 并发与生命周期评估组 | §3.0.3 · §3.4⑧ |
| 阿里 Java 手册（黄山版） | 规约三级（强制/推荐/参考）→ P0-P3 映射 · 安全规约 11 条并集 · 远程调用超时/弱依赖降级/慢服务隔离 | §3.5 · §3.4④⑤②③ · L3 |
| Cloudflare security-audit-skill | 发现者/验证者分离 · 三态 verdict（confirmed/needs_validation/rejected）· needs_validation 不带严重度 · 纵深防御缺口=加固建议 · 已否定留档 | §1.2 · §1.3 · §9.2 |
| Cloudflare security-audit-skill（2026-11-24 二次吸收，一手仓库核验） | **impact 校准锚点表 + high/medium 唯一判别句**（级别不超已演示 impact）· **覆盖声称须由账本+独立 critic 位证明**（架构总结/agent 数不是证据）· **四终态**（完整产物+双校验器 ／ incomplete+确切 reason 且首段披露）· **指纹跨状态稳定**（不含行号/波次/verdict）· **rejected 只压单条主张不冻结文件**· 预算先预留 critic 与验证者 | §7.1 锚点表 · §1.4.1–1.4.4 · §9.2 |
| trailofbits differential-review | 反合理化表（7 借口×强制动作）· 风险分级触发器 · 代码库规模三档策略 | §3.0 · §3.0.1 |
| Anthropic Claude Code pipeline | fresh-context 审查者 · 审查收敛控制（3 轮上限/diff-only 复审/报类不报行）· Pre-existing 分组 · Important/Nit/Pre-existing 三级呈现 | §1.2 · §1.3 · §9.2 |
| obra/superpowers | 接收审查侧六步流程（READ→…→IMPLEMENT）· 分诊规则 · YAGNI 核验 | §1.5 · §B7 |
| lemon-bug-analyser（公众号「小檬姐精测」2026-11-21 拆解） | 验证计划可证伪：prediction + pass_if/fail_if 双判据（只有 pass_if = 找样本自证）· inconclusive 第三态（采不到约定字段→停住等补采，禁模糊成疑似） | §1.2 验证计划可证伪 |

**未吸收项（有意不做）**：open-code-review 的确定性管道架构（本技能是方法论 skill，无执行引擎，管道由宿主子代理机制承担）；Cloudflare 的 artifact promotion 11 步与 coverage-ledger 完整规范化（为多租户 fleet + 完全不可信目标代码设计，单机审自研代码收益 < 成本；**注意：coverage「判据」已吸收，见 §D 末行，不要连判据一起否掉**）；superpowers 的 subagent-driven-development 全流程（超本技能边界，属开发流程编排）。

---

## 版本

当前 **v4.2.0**（版本号只在此处 front matter 与本行出现，不再正文重复）。沿革见 `references/archive/CHANGELOG.md`。

## 详细参考

| 内容 | 文件 |
|------|------|
| B. 硬门禁（以下四条不许省，省了必犯错） | [B-硬门禁-以下四条不许省-省了必犯错.md](references/B-硬门禁-以下四条不许省-省了必犯错.md) |
