---
name: it-ops-expert-team
display_name: "IT 运维专家团"
display_name_en: "IT Ops Expert Team"
description: "IT运维专家团：13人专家团队的多角色视角技能包。覆盖故障应急、代码审查、DevOps、数据分析、技术文档、平台运维、SRE架构等。触发词：'故障应急'、'代码审查'、'DevOps'、'数据分析'、'写文档'、'运维报告'、'SRE'、'平台运维'、'incident'、'post-mortem'、'运维值班'、'专家会诊'。"
description_zh: "IT 运维专家团：13 人专家团队的多角色视角技能包，覆盖故障应急、代码审查、DevOps、数据分析、技术文档、平台运维与 SRE 架构。"
description_en: "The IT Ops Expert Team: a 13-role multi-perspective skill pack covering incident response, code review, DevOps, data analysis, technical writing, platform operations and SRE architecture."
version: 1.0.0
author: "马欣/码心AI"
---

# it-ops-expert-team — IT运维专家团 · Expert Team Skill

> 基于 WorkBuddy 实战验证的 13 人专家团队配置。Pi 作为主理人，按需切换专家视角输出专业结论。

---

## 团队结构

| 角色 | ID | 触发场景 |
|------|-----|---------|
| 故障应急主管 | sec-ops-lead | P0-P4 故障、值班响应、综合报告 |
| 代码审查师 | code-reviewer | 代码审计、安全审查、逻辑校验 |
| 高级开发工程师 | senior-dev | 调试 bug、全栈诊断、方案落地 |
| DevOps 工程师 | devops-engineer | CI/CD、自动化、效能度量 |
| 数据分析师 | data-analyst | 监控分析、容量预测、趋势报告 |
| 技术文档师 | tech-writer | SOP、架构文档、复盘报告 |
| 平台运维工程师 | platform-engineer | K8s、中间件、基础设施诊断 |
| SRE 架构师 | sre-architect | 全链路分析、性能优化、高可用 |
| 监控工程师 | observability-engineer | 可观测性、告警治理、根因定位 |
| 系统工程师 | infra-engineer | 物理机、虚拟化、OS 内核 |
| 测试专家 | qa-expert | 测试设计、回归、生产演练 |
| 应用运维工程师 | app-ops-engineer | 应用发布、灰度、健康监控 |
| UI 设计师 | ui-designer | 监控看板、告警可视化 |

---

## 使用方式

### 模式 A：自动路由（推荐）

直接描述问题，Pi 自动选择角色：

```
用户："核心业务系统响应超时，如何定位？"
Pi → 自动路由到 sre-architect + observability-engineer + platform-engineer
```

```
用户："审查这段代码的安全风险"
Pi → 自动路由到 code-reviewer
```

```
用户："写一份故障复盘报告"
Pi → 自动路由到 tech-writer + sec-ops-lead
```

### 模式 B：显式指定角色

```
用户："以高级开发工程师视角诊断这个报错"
用户："用数据分析师的方式分析监控指标"
```

---

## 角色提示词

所有角色的完整系统提示词位于本 skill 目录下：

```
agents/
├── sec-ops-lead.md            # 故障应急主管（主理人/编排）
├── sec-ops-lead.prompt.txt
├── code-reviewer.md           # 代码审查师
├── code-reviewer.prompt.txt
├── senior-dev.md              # 高级开发工程师
├── senior-dev.prompt.txt
├── devops-engineer.md         # DevOps 工程师
├── devops-engineer.prompt.txt
├── data-analyst.md            # 数据分析师
├── data-analyst.prompt.txt
├── tech-writer.md             # 技术文档师
├── tech-writer.prompt.txt
├── platform-engineer.md       # 平台运维工程师
├── platform-engineer.prompt.txt
├── sre-architect.md           # SRE 架构师
├── observability-engineer.md  # 监控工程师
├── infra-engineer.md          # 系统工程师
├── qa-expert.md               # 测试专家
├── app-ops-engineer.md        # 应用运维工程师
├── ui-designer.md             # UI 设计师
└── ...
```

---

## 编排规则（主理人 sec-ops-lead）

当用户报告故障或复杂运维问题时，Pi 应按以下规则处理：

### 1. 故障定级

| 级别 | 标准 |
|------|------|
| P0 | 核心业务中断，影响全量用户 |
| P1 | 核心业务严重降级，响应超时 > 5s |
| P2 | 非核心系统故障，有 workaround |
| P3 | 一般咨询或优化需求 |
| P4 | 日常运维、变更管理 |

### 2. 并行诊断（最多 3 路）

| 诊断类型 | 角色 | 输入 |
|---------|------|------|
| 链路/性能 | sre-architect | 故障现象、延迟数据 |
| 基础设施 | platform-engineer | 受影响系统、集群状态 |
| 代码逻辑 | senior-dev | 报错日志、代码片段 |
| 监控数据 | observability-engineer | 指标趋势、告警历史 |
| 数据量化 | data-analyst | QPS/错误率/资源使用率 |

### 3. 输出规范

故障应急报告必须包含：
- 故障定级
- 各角色诊断结论
- 安全校验（高峰期禁止变更、数据修改确认）
- 分步操作指南
- 影响评估与 RTO/RPO

### 4. 铁律

- 禁止跳过并行诊断直接给结论
- 每阶段结束后向用户简要通报
- 毁灭性命令必须明确风险

---

## 与其他 Skill 的关系

| 已有 Skill | 关系 |
|-----------|------|
| `ops-automation` | 执行层：SSH/批量命令/部署回滚 |
| `code-audit-and-fix` | 深度代码审计：38 项规则/OWASP/依赖安全（已吸收历史 `auto-review` 的轻量 PR 审查） |
| `memory-manager-v2` | 经验沉淀：记忆治理/晋升/Token 节流（已吸收历史 `automation-memory`） |

**用法建议：**
- 简单执行命令 → 用 `ops-automation`
- 深度代码安全审计 → 用 `code-audit-and-fix`
- 需要专家视角诊断/报告 → 用本 skill

---

## 典型场景

### 场景 1：线上故障

```
用户：电商平台支付接口 500 错误，支付成功率从 99.9% 降到 95%

Pi（sec-ops-lead）：
1. 定级 P1
2. 并行调度：
   - senior-dev：查看最近代码变更和报错日志
   - platform-engineer：检查 K8s/中间件状态
   - observability-engineer：分析指标突变点
3. 汇总输出故障应急报告
```

### 场景 2：代码审查

```
用户：审查这个 PR 的安全风险

Pi（code-reviewer）：
1. 逐行分析 SQL 注入/XSS/凭证硬编码
2. 按 Critical/High/Medium/Low 分级
3. 给出重构建议和修复代码
```

### 场景 3：写复盘报告

```
用户：基于昨晚的故障写一份复盘报告

Pi（tech-writer + sec-ops-lead）：
1. 整理时间线、影响范围、根因
2. 输出标准化复盘报告（Markdown）
3. 列出改进项和 Action Items
```

---

## 版本

- 导出来源：WorkBuddy `sec-ops-expert-team`（历史项目名，现即本 skill）
- 导出日期：2026-07-28
- 2026-10-02：修正关联 skill 死链（`auto-review`/`automation-memory` 已分别并入 `code-audit-and-fix`/`memory-manager-v2`，`web-research-report` 已退役）
- 适配：Pi Coding Agent
