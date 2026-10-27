---
name: ansible-batch-discipline
display_name: "Ansible 批量执行纪律"
display_name_en: "Ansible Batch Execution Discipline"
description: "Ansible 批量执行纪律。批量 playbook 上线（多台主机纳管、灰度发布、批量变更）时使用。含分阶段上线节奏与幂等性量化判据。"
description_zh: "Ansible 批量执行纪律：多台主机纳管、灰度发布、批量变更上线时的分阶段节奏与幂等性量化判据。"
description_en: "Discipline for running Ansible at scale: staged rollout pacing and quantified idempotency criteria when enrolling many hosts, canarying releases or running bulk changes."
version: 1.0.0
author: "马欣/码心AI"
---

# Ansible 批量执行纪律

> 来源：公众号「云境运维实录」Ansible 批量部署文（2026-10-19 评估，采纳 2/8 条，其余已被现有规则覆盖或场景不符）。
> 适用场景：剩余主机纳管、批量配置变更、灰度发布等影响面大的 playbook。

## 分阶段上线节奏

批量 playbook 执行前四步，**不得跳步**：

1. `--check --diff` 全量预演
2. `--limit <1台>` 试点
3. 灰度一个组
4. 全量

批量影响面大，正属「验证与风险相称」的扩大验证场景（见 `rules/architecture.md §执行纪律`）。

## 幂等性量化判据

playbook 幂等与否看**第二次**执行的 `PLAY RECAP`：

- changed 应趋近 0（几乎全 ok）
- 「执行成功」≠「幂等」——每轮重做的 task 是隐藏的**重复变更源**

## 已知假绿陷阱

`--syntax-check` 通过 ≠ 可运行：它不加载 stdout callback，曾导致 10-15 ansible 假绿。
验证命令必须与真实执行等价（详见 `rules/ops.md §踩坑速查` 末行）。

---

_2026-10-20 从 `rules/ops.md` 迁出（A 层常驻瘦身），规则未改动。_
