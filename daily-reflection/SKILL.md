---
name: daily-reflection
display_name: "会话级反思沉淀"
display_name_en: "Session Reflection"
description: "会话级自我反思：把当天/本会话的工作沉淀为记忆候选。当用户说\"反思一下今天\"\"总结到记忆\"\"今天复盘\"\"沉淀经验\"\"吸收这篇文章/这次教训\"，或 substantive work（改代码/修故障/写报告/技术选型）刚完成时使用。产出：追加到当前工作区 daily log 的反思段 + 跨会话候选（进 self-improving 或 weekly-candidates）。不适用：只读问答/闲聊/简单查询（跳过反思）；决策级三类错误（假设/选型/顺序错）周度批量扫描 → automation「每周决策级反省」；记忆动刀 → memory-system-ops。"
description_zh: "会话级自我反思：把当天或本会话的工作沉淀为记忆候选，写入工作区 daily log 并产出跨会话候选。"
description_en: "Session-level self-reflection that distills the day's or session's work into memory candidates, appended to the workspace daily log as cross-session candidates."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
    date: "2026-10-19"
    type: "Model-invoked（纪律型）"
---

# daily-reflection — 会话级反思沉淀

**一句话**：干完活花 1 分钟问自己「这次有什么下次用得上」→ 追加到 daily log，够格的升候选。

## 为什么需要（证据）

- 反思的价值在**沉淀被消费**，不在产出报告（self-improving 10-15 自查：两轮 10 建议 0 落地）
- 会话级反思是 daily log 的直接来源——不反思 = daily log 只剩流水，周度反省无米下锅
- 对标：Hindsight `reflect`、Letta Reflection、openhanako rolling summary——**反思是记忆写入的闸门**，
  没有它记忆系统只有「存」没有「炼」

## 何时触发

| 场景 | 动作 |
|------|------|
| substantive work 完成（修故障/改架构/写报告/选型定案） | 收尾前 30 秒反思，追加 daily log |
| 用户明示「反思/总结/沉淀/吸收」 | 完整走本流程 |
| 纯问答/闲聊/单文件读取 | **跳过**（无信息增益不写） |
| 踩坑且修复过程 >2 轮 | 必写「坑 + 根因 + 判据」三段式 |

## 标准流程（3 步，≤2 分钟）

### 1. 三问过滤（先问该不该记）

- **可复用吗** —— 下次同类任务还会用到？（不复用 → 不记）
- **非显而易见吗** —— README/git log/常识已有的 → 不记（写进对应 rules/skill 更合适）
- **有证据吗** —— 实测过/有文件行号/有命令输出？没有 → 标 `[未验证]` 或干脆不记

三问全过 → 进入第 2 步；否则当场放弃，**禁止「聊胜于无」式写入**。

### 2. 追加到 daily log（B 层当日文件）

格式（追加到 `E:/WorkBuddy/<ws>/.workbuddy/memory/YYYY-MM-DD.md`，**append-only 不覆盖**）：

```markdown
## 反思 <HH:MM> — <一句话主题>

- **做了**：<结果一句话，非过程流水>
- **坑/结论**：<非显而易见的部分；无坑则写「顺利，无新增坑」>
- **判据**：<下次如何快速判断同类问题；命令/文件:行号/阈值>
- **去向**：⌂ 本项目复用（留 daily，30 天蒸馏）｜▲ 跨项目（升 self-improving 候选）｜
  ⚑ 决策级错误（标记待周五反省扫描）｜✘ 无沉淀价值
```

`去向` 标记是本 skill 的核心增量——**写入时就决定这条知识的生命周期**，
不靠 30 天后晋升引擎盲猜（其跨日重复信号已被运行态流水污染，见 MEMORY_POLICY §6 缺陷②）。

**蒸馏写法两条铁律**（2026-10-19 晋升段质量审查后立，治「过程叙事/待办快照」混入）：

1. **写「以后怎么做」，不写「这次做了什么」**——「交付了 ADR-001」✘ →
   「巡检任务输出必须进 EXEMPT_TASKS 豁免自身，防自指放大」✔
2. **禁待办/状态快照**——「任务 3 的 502 待核」✘（下周期就该消失）→
   要么当天闭环写结论，要么显式给消费者（⚑/▲）

### 3. 跨会话候选（仅 ▲/⚑ 类）

- **▲ 跨项目模式** → 追加到 `C:/Users/Administrator/self-improving/corrections.md`
  （格式照既有表），写完跑 `bash ~/self-improving/auto-commit.sh`
- **⚑ 决策级错误**（假设错/选型错/顺序错）→ 不立即写，留 daily log 原文 +
  在反思段标 `⚑`，周五反省自动化会扫描；若显然紧急（会再犯且代价大）→ 当场提醒用户是否立即蒸馏进 rules
- **候选必须带三要素**：日期来源 + 一句话事件 + 建议沉淀位置。缺一即丢弃（与周度反省同口径）

## 边界/安全

- **append-only**：daily log 禁覆盖/重排（Write 前先 Read 完整内容——2026-06-30 覆盖事故铁律）
- **禁直接改 rules/\*.md 与 A 层 MEMORY.md**：反思只产候选；rules 蒸馏走
  `MEMORY_POLICY.md §6.1` 闭环（用户裁决 → 主会话执行）
- **禁写凭据**：反思段同样过凭据扫描（`memory-system-ops §凭据扫描`）
- 静默时段（23:00–08:00）不因反思触发任何推送

## 防合理化表

| 借口 | 事实 |
|------|------|
| "这次很顺利，没什么好反思的" | 顺利的路径也要留「判据」行——下次不顺利时才知道哪里偏离了基线 |
| "先赶完任务，回头再补反思" | 回头补 = 永不补（实测 10-15 自查 0 落地的根源）；30 秒当场写 |
| "写详细点，把过程都记下来" | 过程流水是噪声（体检 ② 项专门检测它）；只写结论 + 判据 |
| "这条好像是常识，不记了" | 你刚踩过它就不是常识；三问里的判据是「非显而易见」，不是「听起来简单」 |

## 自检清单

- [ ] 三问过滤已过（可复用/非显而易见/有证据）
- [ ] daily log 用追加非覆盖，含「去向」标记
- [ ] ▲ 候选已进 corrections.md 且跑 auto-commit；⚑ 已标且带三要素
- [ ] 未触碰 rules/A 层/凭据
