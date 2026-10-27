# IT运维专家团 — 可移植交付包

> 专注IT系统高可用保障，覆盖故障应急响应、全链路性能优化、智能运维与自动化全栈能力。
> 擅长领域: IT系统运维与稳定性保障, SRE与性能优化, 自动化运维与可观测性
> 成员: 13 人 (主理人 + 12 名领域专家)
> 源: WorkBuddy 专家插件 `sec-ops-expert-team`

本包已将专家团从 WorkBuddy 导出为**平台无关**格式，可直接导入其他 AI 工具。

## 目录结构
```
it-ops-expert-team-export/
├── manifest.json              # 团队机器可读元数据(成员/角色/头像/提示词路径)
├── agents/<id>.md             # 每位成员的可移植系统提示词(去平台专用术语)
├── agents/<id>.prompt.txt     # 纯提示词文本, 直接复制粘贴用
├── avatars/<id>.png           # 成员头像(原样复制)
├── avatars/team.png           # 团队头像
├── imports/coze-bots.json     # Coze 机器人定义数组(seed for 开放API)
├── imports/chatgpt-gpts.json  # ChatGPT 自定义GPT定义数组
├── IT运维专家团-全集.md        # 全部人设单文件汇总
└── README.md                  # 本文件
```

## 各工具导入方式

### 1. 通用 / ChatGPT / Claude / 通义 / 文心 等(单智能体)
- 打开目标工具的「系统提示词 / 角色设定 / 自定义指令」输入框
- 复制 `agents/<对应id>.prompt.txt` 全文粘贴
- 头像: 在工具内上传 `avatars/<id>.png`
- 多专家协同: 为每个角色建一个独立助手, 人工充当"主理人"汇总

### 2. Coze(扣子)
- **方式A(网页)**: 逐个创建 Bot, 把 `agents/<id>.prompt.txt` 粘进「人设与回复逻辑」
- **方式B(API)**: `imports/coze-bots.json` 为机器人定义数组(name/description/prompt/icon_url), 可作为 Coze 开放平台创建 Bot 的请求体种子

### 3. Dify
- 创建一个「聊天助手」应用
- 将 `agents/<id>.prompt.txt` 粘贴进「预设提示词」
- 模型建议: 具备工具调用/SRE 知识的大模型
- 多专家: 用 Dify 的「工作流 / 多 Agent」将各角色串联, 主理人节点负责编排

### 4. WorkBuddy(原平台 / 重新导入)
- 本包即由原插件 `sec-ops-expert-team` 导出, 可直接放回 `plugins/marketplaces/my-experts/plugins/` 恢复使用

## 成员角色速查
- **🛠️ 应用运维工程师 周旭辉** (`app-ops-engineer`) — 应用运维工程师 ｜ 提示词: `agents/app-ops-engineer.prompt.txt`
- **🔍 代码审查师 冯欣** (`code-reviewer`) — 代码审查师 ｜ 提示词: `agents/code-reviewer.prompt.txt`
- **📊 数据分析报告师 李坚明** (`data-analyst`) — 数据分析报告师 ｜ 提示词: `agents/data-analyst.prompt.txt`
- **🤖 自动化与DevOps工程师 邓亚平** (`devops-engineer`) — 自动化与DevOps工程师 ｜ 提示词: `agents/devops-engineer.prompt.txt`
- **💾 系统/基础设施工程师 王威** (`infra-engineer`) — 系统/基础设施工程师 ｜ 提示词: `agents/infra-engineer.prompt.txt`
- **👁️ 监控与可观测性工程师 马欣** (`observability-engineer`) — 监控与可观测性工程师 ｜ 提示词: `agents/observability-engineer.prompt.txt`
- **🛡️ 平台运维工程师 周剑** (`platform-engineer`) — 平台运维工程师 ｜ 提示词: `agents/platform-engineer.prompt.txt`
- **🎯 测试专家** (`qa-expert`) — 测试专家 ｜ 提示词: `agents/qa-expert.prompt.txt`
- **👮 群组经理主管 王金刚** (`sec-ops-lead`) — 群组经理主管 ｜ 提示词: `agents/sec-ops-lead.prompt.txt`
- **💻 高级开发工程师 潘杰彬** (`senior-dev`) — 高级开发工程师 ｜ 提示词: `agents/senior-dev.prompt.txt`
- **⚡ SRE架构师 林华** (`sre-architect`) — SRE架构师 ｜ 提示词: `agents/sre-architect.prompt.txt`
- **📝 技术文档师** (`tech-writer`) — 技术文档师 ｜ 提示词: `agents/tech-writer.prompt.txt`
- **🎨 UI设计师** (`ui-designer`) — UI设计师 ｜ 提示词: `agents/ui-designer.prompt.txt`

## 注意事项
- 提示词已去除 WorkBuddy 专用协作指令(TeamCreate / SendMessage), 替换为中立的"返回结构化结论"
- 主理人(sec-ops-lead)原含多智能体编排铁律; 在单智能体工具中, 主理人自身应用 SOP 即可, 其余角色作为可选独立助手
- 头像为二进制资源, 跨工具使用时需按目标平台要求单独上传
