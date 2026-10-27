---
name: monorepo-split
display_name: "Monorepo 拆分为多独立仓"
display_name_en: "Split Monorepo into Independent Repos"
description: "把 monorepo 里的一个子项目拆成独立仓库，并**接回该子项目自己的提交历史**。当用户说\"每个工具单独一个仓库\"\"monorepo 拆开\"\"拆分成多个仓\"\"一个项目一个仓\"\"subtree 历史接回\"\"拆仓保留 git 历史\"\"split monorepo\"时使用。覆盖：subtree merge 结构探测、路径映射→重建merge→提取子目录三步接回法、治理文件按项目裁剪、内网信息脱敏、拆分后推送与回验。不适用：单仓建仓推送→github-repo-push；推送前只读风险尽调→git-push-risk-gate；代码库架构分析→architecture-optimizer；仓目录清理→devops-repo-cleanup。"
description_zh: "把 monorepo 子项目拆成独立仓库并接回其提交历史：subtree 结构探测、三步接回法、治理文件裁剪与脱敏、推送回验。"
description_en: "Split a monorepo subproject into an independent repo while reconnecting its own commit history: subtree detection, three-step reattach, governance-file pruning, sanitization and push verification."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
    date: "2026-10-27"
    verified: "2026-10-27 真实仓库实测（xmtool/RemoteDesktopPlus 19 源提交全部接回、blob 零损坏）+ 自测 24 项全绿"
---

# monorepo-split — Monorepo 拆分为多独立仓

**调用类型：Model-invoked（纪律型）** —— 教「怎么把 monorepo 拆开而不丢历史」这一门手艺。
拆分完成后**推送建仓**走 `github-repo-push`，本 skill 不重复实现推送链路。

## 何时用

- 用户说「每个工具单独一个项目仓库」「monorepo 拆开」「拆分成多个仓」「一个项目一个仓」
- 用户说「拆仓但要保留 git 历史」「subtree 历史接回」
- monorepo 用 `git subtree add` 接入了子项目，要把某个子目录抽出成独立仓
- 拆仓后需要做脱敏（内网域名/本机路径/账号）再开源

## 不适用（边界）

| 场景 | 用哪个 skill | 边界理由 |
|---|---|---|
| 单个仓库建仓并推到 GitHub | `github-repo-push` | 本 skill 只做拆分，不做建仓推送 |
| 推送前只读风险尽调（密钥泄漏/分叉） | `git-push-risk-gate` | 本 skill 是历史重写链路，风险闸门独立 |
| 代码库架构与热点分析 | `architecture-optimizer` | 本 skill 不分析架构，只做历史切分 |
| 仓目录清理、垃圾文件清扫 | `devops-repo-cleanup` | 本 skill 不做清理 |
| Gitea 平台建仓推送 | `gitea-push` / `gitea-ops` | 平台不同 |

**顺序**：`monorepo-split`（拆分+脱敏）→ `git-push-risk-gate`（可选只读尽调）→ `github-repo-push`（建仓推送）。

## 核心事实（踩坑表，全部实测得出）

| 坑 | 事实 | 后果 |
|---|---|---|
| `git filter-repo --subdirectory-filter <prefix>` 会丢源历史 | **实测**：xmtool 的 19 个源提交被压成 **1 个** | 子项目独立仓只剩一个 squash 提交，作者与演进史全丢 |
| 根因不是 filter-repo 的能力边界 | 实测对照：源提交**改动路径全部落在前缀路径内**时才会被保留；源仓文件在根目录时，改的是根路径，与前缀不重合 → 全被丢弃 | 只看「filter-repo 不支持 merge」会误判方向 |
| 解法不是换工具，是**先做路径映射** | 把源历史全部路径加前缀 → 重建 merge（父2 换成映射后 tip）→ 再提取子目录 | 三步后源历史完整保留（实测 19/19） |
| `--refs` 传裸 sha 看不到映射结果 | filter-repo 只更新它能对应到的 ref；裸 sha 传进去**不更新该 sha** | 会误判「映射没生效」而反复重试 |
| `--refs` 传**分支名**才生效 | 实测 `git branch mapped-src-tmp <sha>` + `--refs mapped-src-tmp` → 映射生效 | 本 skill 脚本用分支引用 |
| `filename-callback` 返回 str 会变成 `b'...'` | 回调的 `filename` 是 **bytes**，拼 str 会得到字面量 `b'xxx'` | 路径全变 `b'xmtool/src/...'`，提取时匹配不上 |
| 正确写法 | `return b'<prefix>/' + filename` | — |
| `filter-branch --index-filter` 在 Windows 下失败 | 实测报错退出 | 改用 filter-repo 的 `--filename-callback` |
| blob 校验不能逐行 diff 树路径 | `git ls-tree` 对非 ASCII 路径会**加引号**，文本级 sed/diff 产生假阳性 | 改用 blob sha 多重集比对 |
| 校验必须在**提取前**采集源侧 blob | 提取用的 filter-repo 会清理未被 ref 引用的对象，临时分支届时已不存在 | 事后再查得到空集 → 假阴性误报 |
| `git ls-tree` 对中文路径加引号 | 同上 | 用 `awk '{print $3}'` 取 blob sha 做多重集 |
| 直接 `copytree` 整个仓库当产物 | filter-repo 只重写**历史**，不清理**工作区** | 产物里残留 `pmvault/` `team-planner/` 等其他子项目目录，推送时被当成未跟踪文件混进去。**只复制 `.git`，再 checkout 重建工作区** |
| 只复制 `.git` 后忘了重建工作区 | 工作区是空的 | 后续裁剪治理文件、脱敏都无从下手。提取后必须 `git checkout -f HEAD` + `git reset --hard HEAD` |

## 一键执行（首选）

```bash
python ~/.workbuddy/skills/monorepo-split/scripts/mono_split.py <monorepo路径> \
    --prefix <子树路径> [--name <新仓名>] [--source-tip <sha>] [--out <输出目录>] [--dry-run]
```

| 选项 | 说明 |
|---|---|
| `--prefix <路径>` | 子树在 monorepo 内的路径，如 `xmtool/src/RemoteDesktopPlus`（必填） |
| `--source-tip <sha>` | 源历史 tip；默认自动从 merge 提交的第二父推导 |
| `--out <目录>` | 输出目录；默认 `<monorepo父目录>/<prefix末段>-split` |
| `--name <名称>` | 新仓名（仅日志用） |
| `--dry-run` | 只探测 + 打印计划，**不做任何写操作** |

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 参数/预检失败（含输出目录已存在） |
| 3 | 未找到 subtree merge 结构 |
| 4 | 历史接回后校验失败 |

## 标准流程（每步带可验证退出条件）

### 步骤 0 — 前置门四问

1. 这件事是否重复发生（≥2 次）？ → 一次性任务可直接手工做，不必用本 skill
2. 输入/输出是否相对稳定？ → monorepo 路径 + 子树路径 → 独立仓目录，稳定
3. 是否存在固定步骤？ → 有，即下方步骤 1–5
4. 换一个 AI 是否还要重新解释一遍？ → 是，本 skill 即答案

四问全过 → 继续。任一不过 → 手工做，**不要为此硬造 skill**。

### 步骤 1 — 探测 subtree merge 结构（只读）

**退出条件**：日志出现 `命中 merge 提交: <sha>` + `父2(源): <sha>` + `源历史提交数（接回前）: N`。

探测走两条线索，先按 subject 匹配（`Add '<prefix>/' from commit '<sha>'`），
不中则按树结构兜底（树里有 `<prefix>/` 且提交有两个父）。

**必须先确认历史形态**：若日志报 `未找到 subtree merge 提交`（退出码 3），
说明该子树不是用 `git subtree add` 接入的 → **停下来问用户**，改用 cherry-pick / format-patch 手工迁移。

### 步骤 2 — 干跑确认计划

```bash
python mono_split.py <monorepo> --prefix <prefix> --dry-run
```

**退出条件**：退出码 0；输出含 5 步计划；**输出目录未被创建**；原仓库 HEAD 未变。

### 步骤 3 — 执行拆分（脚本自动完成三步）

脚本内部即「路径映射 → 重建 merge → 提取子目录」，逐步日志可见。

**退出条件**：退出码 0，且日志出现：
`路径映射完成: N 个提交 → N 个提交` → `重建 merge: ... → ...` →
`工作区已重建: M 个文件` → `最终提交数: N（源历史 N）` → `最终 blob 数: M（源侧 M）` →
`✅ 历史接回成功`。

**产物工作区必须干净**：`git status --porcelain` 无输出。
若有残留，说明复制时带上了 monorepo 的其他子项目目录 —— 不可直接推送。

### 步骤 4 — 外部回验（不依赖脚本自身输出）

```bash
cd <输出目录>
git rev-list --count HEAD          # 应 == 源历史提交数
git ls-tree --name-only HEAD       # 应无 <prefix>/ 前缀残留
git ls-tree -r HEAD | awk '{print $3}' | sort | md5sum
# 对照原 monorepo：
cd <monorepo> && git ls-tree -r <merge-sha> -- <prefix> | awk '{print $3}' | sort | md5sum
```

**退出条件**：两个 md5 **完全一致**（内容零损坏）；提交数相等；提交信息保留中文原文。

### 步骤 5 — 治理文件裁剪（按项目逐个判断）

monorepo 根目录的治理文件**不自动带到**独立仓。逐个判断：

| 文件 | 独立仓要不要 | 判据 |
|---|---|---|
| `LICENSE` | **要** | 项目自己的许可；与 monorepo 根 LICENSE 冲突时以源项目原本的为准 |
| `README.md` | **要** | 但要重写：删掉 monorepo 的全局导航段，保留项目自己的说明 |
| `CHANGELOG.md` | 看情况 | 源项目有自己的历史就带自己的；只有 monorepo 汇总版则按项目裁剪 |
| `CONTRIBUTING.md` | **要** | 独立仓需要自己的贡献指南 |
| `CODE_OF_CONDUCT.md` | **要** | 社区化必备，与项目语言无关 |
| `SECURITY.md` | **要** | 漏洞报告渠道需要指向本仓 |
| `ROADMAP.md` | 看情况 | monorepo 全局路线图与单项目无关 → 不带 |
| `THIRD-PARTY-NOTICES.md` | 看情况 | 依赖在项目内才带；根目录的全局清单不带 |
| Issue/PR Template | **要** | 独立仓必须有自己的模板 |
| `.github/workflows/*` | **要** | 但需改：monorepo 里的路径引用要改成单仓布局 |

**退出条件**：每个文件都有明确取舍结论；README 里没有指向 monorepo 其他子项目的死链
（`grep -rn "xmtool/\(pmvault\|team-planner\)" README.md docs/` 无命中）。

### 步骤 6 — 脱敏（开源前必做）

对**工作区**和**全历史**分别处理：

```bash
# 1) 全历史脱敏（内网域名 / 本机路径 / 账号）
git filter-repo --replace-text <(printf 'example.com==>example.com\n')
git filter-repo --replace-text <(printf 'C:\\Users\\<用户名>==>C:\\Users\\user\n')

# 2) 工作区二次确认
grep -rniE 'gf\.com\.cn|192\.168\.|10\.\d+\.\d+\.\d+|C:\\\\Users\\\\' . --exclude-dir=.git
```

**退出条件**：两条命令均**零命中**（`git grep` 与 `grep -r` 同时检查）；
`git log -p` 中不再出现内网标识。

> 注意：脱敏会重写全部提交 sha。若源历史刚接回，**先脱敏再推送**，
> 否则推送后还要再 force 一次。

### 步骤 7 — 推送与回验

交给 `github-repo-push` skill：

```bash
python ~/.workbuddy/skills/github-repo-push/scripts/github_repo_push.py <输出目录> \
    --name <新仓名> --description "<描述>" --push-timeout 600
```

**退出条件**：日志出现 `回验通过: <owner>/<name>@<branch> = <sha12>`。

### 步骤 8 — 清理与归档

拆完不删原 monorepo（它是历史归档）。若要归档：

```bash
git remote rename origin monorepo-archived-origin   # 避免误 push 到旧仓
```

**退出条件**：`git remote -v` 中旧远端已改名，push 目标不会误指向单项目仓。

## 防合理化表

| 借口 | 事实 |
|---|---|
| "直接 `filter-repo --subdirectory-filter` 不就行了" | 实测会丢源历史：19 个源提交被压成 1 个。丢的是作者与演进史，不可逆 |
| "丢历史无所谓，反正是新仓" | 历史是新仓最有价值的资产。接回成本是三步命令，不接的成本是永久丢失 |
| "手动 cherry-pick 更可控" | cherry-pick 会改写 commit sha 且丢失原提交结构。三步法保留原提交原信息（实测中文提交信息完整保留） |
| "映射后提交数不变就说明对了" | 提交数不变只证明没丢提交，**不证明路径对**。必须再比 blob sha 多重集 md5 |
| "脚本自己会校验，不用再验一遍" | 脚本的校验与实现同源，错了会一起错。外部命令交叉验证才有意义 |
| "把整个 monorepo 复制过去改改就行" | filter-repo 只重写历史不清工作区，复制会残留其他子项目目录。必须只复制 `.git` 再重建工作区 |
| "治理文件全带过去省事" | monorepo 的全局 ROADMAP/导航段对单项目是噪声，甚至是死链 |
| "先推送再脱敏，反正能改" | 脱敏重写全部 sha，推送后再改要 force push 到公网仓库，密钥曾外泄 |
| "输出目录已存在，覆盖掉就行" | 那可能是另一个项目的工作副本。脚本已设为拒绝（退出码 2），需人工确认后手工处理 |
| "拆完把 monorepo 删了吧" | monorepo 是历史归档。删它是不可逆操作，除非用户明确要求 |
| "这次先手工做，不用 skill" | 手工做也要按同样的三步接回法。手写命令更容易漏掉路径映射这一步 |

## 自检清单（执行后逐项核对）

- [ ] 日志出现 `命中 merge 提交:` 且父2 非空
- [ ] `源历史提交数（接回前）: N` 已记录
- [ ] 最终 `git rev-list --count HEAD` == N
- [ ] blob sha 多重集 md5 两侧一致
- [ ] `git ls-tree --name-only HEAD` 无 `<prefix>/` 前缀残留
- [ ] 源提交信息（含中文）完整保留
- [ ] 产物工作区 `git status --porcelain` **无输出**
- [ ] 产物工作区只有该子项目的文件，无其他子项目目录残留
- [ ] 治理文件逐个有取舍结论，无死链
- [ ] 内网域名/本机路径在工作区与全历史均零命中
- [ ] 推送后 `回验通过:` 出现
- [ ] 原 monorepo 远端已改名，不会误推

## 脚本自测

```bash
python ~/.workbuddy/skills/monorepo-split/scripts/test_mono_split.py
# 检查项共 24 项，失败 0 项
python ~/.workbuddy/skills/monorepo-split/scripts/test_skill_routing.py
# 三案例实测，失败 0 项
```

分层：外部检查（`py_compile`、真实 git 仓库跑完整拆分、非 subtree 历史明确失败、
输出目录保护）+ 项目检查（CLI 契约、dry-run 无副作用、凭据扫描）。

---

_2026-10-27 创建。核心机理（路径映射 → 重建 merge → 提取子目录）由本机实测得出：
对照实验确认「源提交改动路径是否落在前缀内」决定其能否在提取后存活。
真实案例：xmtool 的 `xmtool/src/RemoteDesktopPlus`，19 个源提交全部接回，blob 零损坏。_
