# ops-skills-collection

面向 AI 助手（WorkBuddy / Claude Code 等 Agent Skills 生态）的运维实战技能集。
全部来自生产环境实战沉淀，每个目录即一个独立技能。

## 安装

把所需技能目录整体复制到本地技能目录即可：

```bash
cp -r <skill-name>/ ~/.workbuddy/skills/   # WorkBuddy
# 或 Claude Code: cp -r <skill-name>/ ~/.claude/skills/
```

## 技能清单

| 技能 | 说明 |
|---|---|
| [`systemd-credential-leak-audit`](systemd-credential-leak-audit/) | systemd 凭据泄漏进日志的排查与修复（EnvironmentFile 失效、命令行参数泄漏、journald 取证） |
| [`linux-perf-tuning`](linux-perf-tuning/) | Linux 性能调优端到端流程：load 高 CPU 空闲、%sys 异常、iostat 百分位采集等，附可直接跑的脚本 |
| [`air-gapped-docker-image-transfer`](air-gapped-docker-image-transfer/) | 气隙环境 Docker 镜像中转：pull→save→SFTP→load + sha256 端到端校验 |
| [`git-repo-relay-via-online-host`](git-repo-relay-via-online-host/) | 无出网主机的 git 仓库中继：A 机无网 → 有网主机中转 → 远端 Git 服务器 |
| [`automation-silent-failure-triage`](automation-silent-failure-triage/) | 自动化任务静默失败分诊：心跳告警 / 未按计划推送 / 该出结果却没出 |
| [`script-status-exit`](script-status-exit/) | 给运维脚本补 STATUS= 机器可读自证信号，根治状态误判 |
| [`docker-compose-name-drift-fix`](docker-compose-name-drift-fix/) | Docker Compose 容器名漂移与「容器未运行」误报的诊断修复 |
| [`python-gradual-refactor`](python-gradual-refactor/) | Python 单文件模块 → 多文件包的 4 阶段渐进重构流程 |
| [`grilling`](grilling/) | 拷问式访谈：对计划/设计/决策做无情追问，直到设计树每个分支都有答案 |
| [`daily-reflection`](daily-reflection/) | AI 会话反思沉淀：把当天工作蒸馏为跨会话记忆候选 |
| [`workspace-stage-consolidation`](workspace-stage-consolidation/) | 任务封板时的现场收敛：散落脚本、临时文件、明文凭据残留的清理规范 |
| [`ponytail`](ponytail/) | 最懒老手模式：以最小改动完整交付（lite/full/ultra 三档）<br>📝 ported from https://github.com/DietrichGebert/ponytail (MIT) |
| [`ansible-batch-discipline`](ansible-batch-discipline/) | Ansible 批量执行纪律：--check 预演 → 单台试点 → 灰度 → 全量，幂等量化判据 |
| [`ansible-generator`](ansible-generator/) | Ansible role/playbook 脚手架生成器，含模板与参考库 |
| [`ansible-validator`](ansible-validator/) | Ansible 产物静态校验器：语法、最佳实践与常见反模式 |
| [`promql-generator`](promql-generator/) | PromQL 查询生成器：从需求描述到可运行查询，附函数速查 |
| [`promql-validator`](promql-validator/) | PromQL 查询校验器：语法与语义检查、反模式识别 |
| [`sre-engineer`](sre-engineer/) | SRE 工程方法集：SLO/告警/容量/故障演练的实践框架 |
| [`it-ops-expert-team`](it-ops-expert-team/) | IT 运维专家团队协作框架：多角色（代码审查/数据分析/运维）提示词集 |
| [`code-audit-and-fix`](code-audit-and-fix/) | 代码审计与修复 SOP：债务清单 → 依赖架构 → 运维审计闭环 |
| [`ops-automation`](ops-automation/) | 远程服务器批量巡检/日志收集/服务重启/部署回滚的通用流程 |
| [`index-index-db-audit`](index-index-db-audit/) | 索引与索引库审计方法 |
| [`github-accelerator`](github-accelerator/) | GitHub 操作加速器：常用 API/CLI 组合与网络优化 |
| [`monorepo-split`](monorepo-split/) | Monorepo 拆分流程：历史保留与仓库迁移<br>📝 agent-built |
| [`answer-me-with-html`](answer-me-with-html/) | 把复杂答案渲染成单文件离线 HTML（流程/时序/对比/架构/diff/决策） |
| [`sketch-infographic`](sketch-infographic/) | 无 npm 依赖的 Node 脚本生成手绘风 SVG 信息图，可复现可进 Git |

## 关于占位符

文中出现的 `<LAN_IP>`、`<JUMP_HOST_IP>`、`<TEST_HOST_IP>`、`<WEBHOOK_KEY>`、`<公司名>` 等占位符，
是发布前统一脱敏的结果（原文出自某券商内网运维环境）。使用时替换为你自己的环境值。

## License

MIT，见 LICENSE。第三方移植内容以上游标注为准。