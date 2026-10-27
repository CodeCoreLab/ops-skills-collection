---
name: code-audit-and-fix
display_name: "一体化代码质量中枢"
display_name_en: "Code Audit and Fix Hub"
description: "一体化代码质量中枢（多文件/多模块级）：审计 + 分级修复 + 重构 + 依赖审计 + 架构评审 + 健康度量化 + 技术债治理 + 运维脚本审计。四层 × 40 项语言规则 × 24 项修复标签（噪声/冗余/重复/结构/可靠性）× 10 个修复动词 × 七维清单 × P0/P1/P2/P3 四级分级 × 健康评分 1-10 + CAC/Bus Factor/DICE/ROI/7R/T-shirt 量化。触发：「代码审计」「全量审查」「技术债评估」「重构」「依赖审计」「架构评审」「健康度评分」「运维脚本审计」「上下游核验」「自动修复」「清理死代码」「消除重复」。**反触发（勿用本 skill）**：单文件/单函数的小改、纯查语法、只要一段代码的解释、以及自查性质的「帮我看看这段对不对」——直接改或用宿主 `CODE_REVIEW_CHECKLIST.md`。互斥边界：单 PR/单片段的 review 由用户显式调 `/code-review-router`（在 `skills/code-review-master/` 下，被设为 user-invocable-only，agent 无法自动加载）；整仓死代码批量清扫 `deadcode-scanner`（本技能 `dead_code` 标签只做审查范围内的标注+删除）；技术债专项治理 `tech-debt-manager`；纯安全专项**本机无独立 skill**，走本技能 `references/review-checklist.md` §3.4④。"
description_zh: "一体化代码质量中枢：审计、分级修复、重构、依赖审计、架构评审、健康度量化、技术债治理与运维脚本审计。"
description_en: "An all-in-one code quality hub: audit, tiered fixes, refactoring, dependency audit, architecture review, health scoring, tech-debt governance and ops script auditing."
version: 3.8.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    title: code-audit-and-fix
    version: 3.8.0
    summary: 一体化代码质量中枢（多文件/多模块级）。三阶段流程（阻断判定→并行深审 W1‖W2‖W3→优化报告）× P0 早停门 × 40 项语言规则 × 24 项修复标签 × 10 个修复动词 × 七维清单（含 L1–L6 执行顺序视图）× P0-P3 四级分级 × Conventional Comments × 健康评分 1-10 + CAC/Bus Factor/DICE/ROI/7R/T-shirt。入口只放门禁与导航，细则在 references/ 按档位加载。
---

# code-audit-and-fix — 一体化代码质量中枢

**定位**：多文件/多模块级代码质量的统一入口。三阶段（阻断判定 → 并行深审 → 优化报告）× 双引擎（精确 grep / 数据流追踪）× 40 项语言规则 × 24 项修复标签 × 10 个修复动词 × P0-P3 四级分级。

**核心能力**：代码审计 · 缺陷修复 · 重构简化 · 依赖审计 · 架构评审 · 技术债治理 · 上下游核验 · 测试生成

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
  → 汇聚：去重 + 置信度标注（§1.3，见 workflow.md）

阶段 C · 优化与报告（无 P0/P1 时完整执行）
  C1 性能/可维护性/测试覆盖细化 → §3.4 ⑤⑥③
  C2 技术债量化（DICE/ROI）+ 健康评分 → §2.4 / §5
  C3 报告 → §9.2 模板（output-template.md）

阶段 D · 自动修复（用户说「自动修复/清理/去冗余」时）
  D1 打标签 + 定动词 → §10.2 / §10.3（fix-taxonomy.md）
  D2 过滤 → §10.5 三张表（可自动 / 待人工 / 禁自动）
  D3 自动堆逐点改 + §10.6 四项验证
  D4 人工堆出方案不改码 → 报告双视角呈现（§10.8）
```

### 档位判定与最小必读集（成本单一源）

| 档位 | 触发条件 | 必读文件 | 跳过 |
|---|---|---|---|
| **轻量** | 改动 <100 行且无敏感标签 | `SKILL.md` 本篇即足（门禁 §B） | 全部 references |
| **标准** | 100–400 行，常规业务 | `workflow.md` + `review-checklist.md` | `dependency-arch.md`（无依赖变更时）、`ops-audit.md`、`output-template.md`（用宿主清单口径） |
| **对抗** | >400 行或含敏感标签 | `workflow.md` + `review-checklist.md` + `dependency-arch.md` + `debt-and-rules.md` + `output-template.md` | `ops-audit.md`（非运维脚本） |
| **运维脚本** | 用户说运维脚本审计 | `ops-audit.md` + `workflow.md` | 其余按档位 |
| **自动修复** | 用户说「自动修复」「清理死代码」「消除重复」「去冗余」 | `fix-taxonomy.md` + `debt-and-rules.md` | `dependency-arch.md`、`ops-audit.md`（无依赖/运维脚本问题时） |

**敏感标签**：`auth` `pay` `credential` `secret` `token` `db` `sql` `schema` `admin` `permission` `upload` `download` `api`

**PR 规模**：≤400 行正常；400–1000 行按模块分组并行；>1000 行拒绝合并必须拆分。一个 PR 只做一件事，重构与功能分离。

### 编号对照（§N 编号不变，按此定位）

| 编号 | 主题 | 文件 |
|---|---|---|
| §1 | 执行流程 / 并行分组 / 聚合规则 / 三路分发 / 验收循环 | `references/workflow.md` |
| §2 | 依赖审查 / 上下游核验 / 整体健康评分 | `references/dependency-arch.md` |
| §3 | 两遍法 / Self-Review / 反馈质量 / 七维清单（含 L1–L6 执行顺序视图）/ OWASP | `references/review-checklist.md` |
| §4 | 分层依赖 / 微服务 / 坏味道 / 可观测性 / ADR / ROI / 7R / CAC | `references/dependency-arch.md` |
| §5 | DICE / ROI / 门禁 / 配额六分类 / Bus Factor | `references/debt-and-rules.md` |
| §6 | 语言扫描规则库（**40 项**：PY 18 / GO 7 / JAV 4 / JS 7 / UNIV 4） | `references/debt-and-rules.md` |
| §7 | 缺陷分级 / 判定细则 / 根因约束 / 测试生成 / T-shirt | `references/debt-and-rules.md` |
| §8 | 运维脚本审计模式（6 类高发 + 修复铁律） | `references/ops-audit.md` |
| §9 | 工具降级 / 报告输出模板 | `references/output-template.md` |
| §10 | 修复标签体系（24 标签 / 10 动词 / 自动修复边界 / 行为变更声明与验证） | `references/fix-taxonomy.md` |
| 版本沿革 | v1.0 → v3.8 | `references/CHANGELOG.md` |

---

## B. 硬门禁（以下四条不许省，省了必犯错）

### B1 证据门槛（Finding Proof Gate）

上报 P0/P1 前必须给出**最小证明**：可达的执行/状态转换路径、失败示例或测试、或具体契约不匹配。证据不可知 → 报为**待验证假设**，不定级 P0。

- 单引擎（仅 grep）命中、语义未确认 → 标「待验证假设」，禁止直接定 P0
- 无日志/调用链/SQL 证据 → 禁写「根因」，只写候选原因（三分离原则，见 `review-checklist.md` §①）
- 无证据却报 P0 = 审查失败，比漏报更伤信任

### B2 早停与批准

- **批准标准**：确定是整体改进即可批准，不因「不完美」拒绝——P2/P3 不阻塞结论
- **阻断红线**：P0/P1 存在即不批准；正确性/安全性/设计劣化必修；无测试守护的高风险新行为必补测
- **不阻断**：纯 P3 风格偏好、可写得更漂亮但无缺陷、影响范围外的既有问题（转 follow-up）、作者已接受并跟踪的低风险测试缺口
- **早停**：P0 扫出即出阻断报告（结论+位置+证据+修复方向），不等优化层

### B3 分级呈现

P0/P1（阻断组）与 P2/P3（可选组）**分组呈现，禁止混排**；每条独立成条目。级别映射与注释前缀见 `debt-and-rules.md` §7。

### B4 验收循环（P0/P1 修复后必走）

```
修复 → 最小验证 → 通过 → 后置核验
              └→ 不通过 → 回修（≤3 轮）→ 仍不过 → 停止盲改，回溯根因，升级人工
```

- 验证须对得上目标：P0 安全 → 攻击向量测试通过；P1 异常 → 异常路径测试 exit 0；脚本 → `py_compile` + 最小路径实跑；配置/部署 → 产物打开 + restart 后探活
- **禁止**：验证不通过却报「已修复」；第 3 轮后继续盲改
- 未闭环的修复在总结中单列，不混入「已修复」计数

### B5 W3 Spec 轴自取证（用户不给 spec 时）

W3 不因「无 spec」直接跳过，按序自取证据，取到即用并标注来源：

1. PR/commit message 声明的意图 → 标注 `[spec:commit]`
2. Issue / 需求单链接或正文 → `[spec:issue]`
3. 仓库内 `docs/`、`*.md`、OpenAPI、migration、测试用例名（tests reveal intent） → `[spec:repo]`
4. 三者皆无 → 跳过 W3，报告 ⚠️ 标「忠实度未审（无需求上下文）」，**并明确列出所需最小输入**：需求单链接 / 验收标准 / 变更意图各一行

### B6 自动修复门禁（打标签 → 定动词 → 才动手）

**双轴判定，不得混用**：

| 轴 | 出处 | 决定 |
|---|---|---|
| 级别 P0/P1/P2/P3 | §7 | 能不能动、是否阻断、验证强度 |
| 标签（噪声/冗余/重复/结构/可靠性） | §10 `fix-taxonomy.md` | 怎么动（修复动词）、能否自动执行 |

**动手前四问**（任一为「否」→ 不改码，只出方案）：

1. 标签定了吗？—— 每条发现必须落到 §10 的 24 个标签之一（闭集，不新造）
2. 动词定了吗？—— 每条修复必须落到 10 个动词之一（remove/inline/extract/replace/merge/simplify/add/guard/type_guard/parameterize）
3. 允许自动吗？—— 查 §10.5 三张表；判据是**可逆性 / 语义唯一解 / 发布面不变 / 可验证**，不是「会不会改行为」
4. 验证得了吗？—— 修复后跑 §10.6 四项验证；有意行为变更须单列变更点 + 补测试

**八条硬规则**：① 噪声→直接删 ② 冗余→简化 ③ 重复→提取 ④ 结构→仅建议 ⑤ 可靠性→必须修 ⑥ **可改变行为** ⑦ **可引入新依赖** ⑧ 保持代码风格。

**禁项**：不删公开 API/导出符号、不做生产环境写入/删数据/改凭据投放、不在单次修复中跨 >10 个文件、不自行 `pip install` 锁定第三方版本、不改与本次修复无关的格式、不把可靠性修复与噪声清理混成一次提交。

**自动执行判据**（不是「会不会改行为」）：**可逆性**（改错能一次回滚）· **语义唯一解**（无「二选一」的业务判断）· **发布面不变**（不改公共签名/导出符号/依赖版本约束/lockfile）· **可验证**（有现成手段判定对错）。四条任一不满足 → 出方案不改码。

**不变量**：修复**可以改变行为**，也可以**引入新依赖**——这两条都不构成拒绝理由。约束落在：① 等价性重构（噪声/冗余/提取）行为应不变，实际变了要停下说明；② 有意行为变更（可靠性类）必须在报告**单列变更点**（改前 → 改后）并补「没有这次修复就会失败」的测试；③ 新依赖：标准库可直接引入，第三方库锁定版本（改 lockfile）属发布面变更 → 人工确认；④ 行为变化意外发生时 → 回滚该修复点，不静默生效。

**互斥边界**：整仓死代码批量清扫走 `deadcode-scanner`；本技能的 `dead_code` 标签只做**本次审查范围内**的标注 + 删除。

---

## C. 回归样例组（改本技能后必跑）

改动 `SKILL.md` 或任一 `references/*.md` 前留快照，改后跑 `references/regression-cases.md` 的 **6 组**固定案例（早停门 / 证据门槛 / 分级呈现+PY-07 双模 / W3 自取证 / 形态模误报边界 / 标签-动词映射与自动修复边界），输出与预期一致才采纳；不一致先回滚再定位。

---

## 版本

当前 **v3.8.0**（版本号只在此处 front matter 与本行出现，不再正文重复）。沿革见 `references/CHANGELOG.md`。
