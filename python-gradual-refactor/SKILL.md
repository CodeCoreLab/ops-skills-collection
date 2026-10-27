---
name: python-gradual-refactor
display_name: "Python 渐进式重构"
display_name_en: "Python Gradual Refactor"
description: "渐进式重构 Python 单文件模块为多文件包，采用 4 阶段流程（新包+兼容层 → 下游改造 → 删除兼容层 → 深入拆分）。本 skill 应在用户要求\"拆分 Python 单文件模块\"、\"渐进式重构\"、\"引入兼容层\"、\"删除兼容层\"、\"重构巨型模块\"、\"single-file to package\"、\"stage refactor\"、\"F8 stage refactor\" 时加载。适用于 500+ 行单文件、需保持下游零改造、需可回滚的运维/生产模块。"
description_zh: "渐进式重构 Python 单文件模块为多文件包，采用 4 阶段流程：新包加兼容层、下游改造、删除兼容层、深入拆分。"
description_en: "Progressively refactor a single-file Python module into a package through 4 stages: new package with a compatibility layer, downstream migration, compatibility layer removal, then deeper splitting."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
---

# python-gradual-refactor — Python 渐进式重构（4 阶段）

将 500+ 行单文件 Python 模块拆为多文件包，**下游零改造 + 可回滚 + 每阶段可验证**。

## 何时用

- 生产 Python 模块超过 500 行且已稳定运行
- 需要拆分但下游脚本/服务不能停机改造
- 需要每阶段独立可回滚（生产事故时能逐级退回）
- 需要保持对外符号（函数/类名）不变

## 4 阶段流程

| 阶段 | 目标 | 产出 | 退出准则 |
|---|---|---|---|
| 1 | 新包 + 兼容层 | `pkg/` 目录 + `old_module.py` 变薄兼容层 | 新旧 import 路径都可用；py_compile 通过 |
| 2 | 下游改造 | 下游 `import pkg.xxx` 替代 `import old_module` | 所有下游 grep 命中已改；行为等价 |
| 3 | 删除兼容层 | `old_module.py` 备份后删除 | 严格 grep 全 0 引用；生产冒烟通过 |
| 4 | 深入拆分 | 单函数拆为多子函数 + DRY 提取 | 一致性断言（聚合 == 独立调用）通过 |

**阶段 2 可跳过条件**：严格 grep 生产 + 本地全库 0 代码引用（仅文档/注释），兼容层可保留到阶段 3 再删。

## 关键铁律

### 1. 前置严格 grep（不可省略）

进阶段前**必须**在生产 + 本地全库 grep，覆盖：
- `.py` / `.sh` / `.yaml` / `.yml` / `.toml` / `.json`
- systemd unit（`/etc/systemd/system/`）
- crontab（`crontab -l` + `/etc/cron*`）
- workflow_tasks / ansible playbook
- workflow 定义（k8s operator / airflow DAG / etc.）

排除：`*.bak`、`*.md`（文档）、`backup_*` 目录、注释/docstring。

结果必须是 **0 代码引用** 才允许进入下一阶段。

### 2. 备份铁律

每阶段修改前：
```bash
STAMP=$(date +%Y%m%d_%H%M%S)
BK="/opt/workbuddy/backups/<module>_<stage>${STAMP}/"
mkdir -p "$BK"
cp -a /opt/workbuddy/<module> /opt/workbuddy/<module>.py "$BK"/
```
**备份路径必须记录到 MIGRATION.md**，支持逐级回滚。

### 3. 薄包装策略（阶段 4 保持向后兼容）

拆分大函数为子函数时，**保留原函数作为薄包装**：
```python
def calc_ops_summary(today_stats, today_ip_stats, hourly_ip_buckets,
                     yest_stats=None, ..., system="ITIS", measurement="info-restapi"):
    return {
        "trend_val": calc_trend(today_stats, yest_stats),
        "peak_servers_val": calc_peak_servers(...),
        ...
    }
```
- 原签名不变 → 下游零改造
- 子函数对外可独立调用 → 新能力可选
- 版本 minor bump（v2.0.0 → v2.1.0，非 breaking）

### 4. 一致性断言（阶段 4 验证必做）

拆分后必须断言：聚合输出 == 子函数独立调用。
```python
result = calc_ops_summary(...)
assert result["trend_val"] == calc_trend(...)
assert result["peak_servers_val"] == calc_peak_servers(...)
# ... 每个子函数一条 assert
```
断言失败 = 拆分改变了行为，禁止合并。

### 5. 生产验证 vs heredoc 陷阱

- 生产验证脚本走 **文件上传 + 执行**（`scp` + `python3 /tmp/x.py`）
- 禁止 heredoc 内嵌复杂 f-string + 反斜杠转义引号
  - 症状：`SyntaxError: unexpected character after line continuation character`
  - 根因：heredoc 内 `\"` 被 shell 二次转义
- heredoc 只跑简单 print / 无引号嵌套的 sanity check

### 6. 版本语义

- 阶段 1（新增包 + 兼容层）：**major bump** 或 **v1.0.0**（新起点）
- 阶段 3（删除兼容层）：**major bump**（旧 import 路径破坏）
- 阶段 4（新增子函数导出，薄包装保留）：**minor bump**（向后兼容增强）

## 验证矩阵

| 阶段 | 本地 | 生产 | 断言 |
|---|---|---|---|
| 1 | `py_compile` 全包 | 部署 + `py_compile` | 新旧 import 都通过 |
| 2 | grep 全下游改造完成 | grep 生产零残留 | import 行为等价 |
| 3 | 严格 grep 0 引用 | 备份 + 删除 | 新包正常 / 旧包报 `ModuleNotFoundError` |
| 4 | `py_compile` | 部署 + 一致性断言 | 5+ 项聚合 == 独立调用 |

## 交付物清单

- `MIGRATION.md`（阶段状态表、目录结构、备份路径、回滚方案、遗留事项）
- `.workbuddy/outputs/<module>_execution_result.md`（关键指标汇总）
- `.workbuddy/memory/YYYY-MM-DD.md`（当日工作日志追加）
- 每阶段备份目录 + 时间戳

## 常见坑

1. **只 grep 本地不 grep 生产** → 阶段 3 删了但生产服务还在 import，500 内报错
2. **兼容层直接删除无备份** → 生产事故无法回滚
3. **拆分函数改变返回类型** → 下游 `.get()` 或解包静默失败
4. **薄包装签名改动（即使参数顺序不变）** → 位置参数调用静默错位
5. **阶段 4 拆完没做一致性断言** → 逻辑漂移难以发现
6. **heredoc 内嵌复杂 f-string** → 转义陷阱，改用脚本文件
7. **不更新 `__init__.py` 版本号** → 下游判断依赖版本的能力失效
8. **只导出主函数不导出子函数** → 阶段 4 的"新能力可选"落空

## 参考案例

- F8-1 work_report 重构（2026-09-09）：1126 行单文件 → 20 文件 2057 行，v2.0.0 → v2.1.0，导出 36 → 42
  - 完整方案：`~/.workbuddy/.../F8-1_work_report_common_split.md`
  - 迁移指南：`F8-1-work_report_refactor/MIGRATION.md`
