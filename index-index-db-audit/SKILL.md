---
name: index-index-db-audit
display_name: "索引库与自动化编排一致性审计"
display_name_en: "Index DB and Orchestration Audit"
description: "审计 E:\\index 索引层与自动化编排（index.db + 服务器脚本一致性）"
description_zh: "审计本地索引层与自动化编排的一致性，核对索引库内容与服务器脚本、自动化任务定义是否对齐。"
description_en: "Audit the local index layer against automation orchestration, checking whether index contents match the server-side scripts and automation task definitions."
version: 1.0.0
author: "马欣/码心AI"
---

# index-index-db-audit

## 何时用
审计 E:\index\index.db 自动化任务的逻辑正确性：路径断裂、任务失败、prompt 质量。

## 标准流程
1. 导出 automations：`sqlite3 /e/index/index.db "SELECT id,name,status,rrule,model,timeout,prompt FROM automations ORDER BY id;"`（JSON 导出更稳：python3 + sqlite3 模块）
2. `automation_runs` 统计失败率/最近退出码分布
3. 对比 prompt 引用路径 vs 服务器实际路径（SSH 实测 `ls`，不轻信文档）
4. prompt 截断检查：index.db 的 prompt 字段只存前 500 字符，完整版在服务器侧脚本里
5. 输出 P0/P1/P2 分级 + 证据（命令+实测输出）

## 常见坑
- index.db ~162MB，别整库 dump；按表查询
- `5_engine/` 与 `.workflow_state/` 下有同名空 DB 诱饵，真执行历史在运行中服务锚定的 DB（lsof 查进程打开的文件）
- Git Bash 下 E 盘挂载为 /e/；sqlite3 CLI 可能没装，用 python3 -c "import sqlite3..."

## 关联 skill
脚本级审计走 `code-audit-and-fix`（§八运维脚本审计模式）；巡检修复与自动化健康验证走 `automation-health-validator`。
