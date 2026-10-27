---
name: ops-automation
display_name: "运维自动化"
display_name_en: "Ops Automation"
description: "远程服务器批量巡检、日志收集、服务重启、部署回滚。用于 Linux 服务器运维、CI/CD 辅助、多机器批量操作。"
description_zh: "远程服务器批量巡检、日志收集、服务重启与部署回滚，用于 Linux 服务器运维、CI/CD 辅助与多机器批量操作。"
description_en: "Batch inspection, log collection, service restarts and deployment rollback on remote servers, for Linux operations, CI/CD assistance and multi-machine automation."
version: 1.0.0
author: "马欣/码心AI"
---

# ops-automation — Ops Automation

## 何时用
- 多服务器健康检查
- 日志 tail + 错误分析
- 服务重启（systemd/docker）
- 批量命令执行
- 部署与回滚

## 前置条件
- SSH 通道可用：本机 `~/.ssh/id_workbuddy` 密钥（paramiko），跳板机/测试机配置见全局运维规约
- 目标服务器支持 SSH 登录（Python paramiko 优先；Windows `ssh.exe` 不兼容密钥，禁用它）
- 上传/执行按「本地改 → paramiko 传 → 校验」流程，不做裸 shell 直连

## 执行方式

本 skill 是远程批量运维的能力入口，**不依赖自带的 shell 脚本文件**。实际操作按场景复用既有链路：

| 场景 | 落点 |
|------|------|
| 多机健康检查（CPU/MEM/磁盘/负载） | 服务器 Health Check v2.0 `healthcheck_monitor.py`（监控 ~39 台） |
| SSH 批量采集 | ops-platform zabbix-refactor（paramiko 采集 39 台指标） |
| 告警推送 | 统一企微推送（gf-shared/wecom-push 或 0_shared/push_wecom.py） |
| 批量命令执行 | Python paramiko 脚本，远端路径用显式正斜杠字面量 |

即：**优先对接已落地且通过健康巡检的监控/采集链路，不自造新的 shell 脚本**。避免与既有实现产生双源漂移。

## 参考入口
- 服务器布局、healthcheck、ops-platform 细节见全局运维规约（rules/ops.md、架构记录）
- 改动生产链路前遵守「改前 SSH 三查 + 改后验证」铁律
