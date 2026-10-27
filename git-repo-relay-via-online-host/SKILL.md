---
name: git-repo-relay-via-online-host
display_name: "无出网主机 Git 仓库中继"
display_name_en: "Git Repo Relay via Online Host"
description: "无出网主机（气隙/内网隔离）的 git 仓库内容要进远端 Git 服务器时，改由「有网主机中继」——A 机无网 → B 机 SSH 直读 A 的仓库 → 裸克隆到 B → 由 B 推到远端。覆盖：出网能力判定（TCP 探测而非看 git 报错）、「remote 是占位地址」识别（FETCH_HEAD 指向本地 bundle / reflog 零 fetch / 文档写「需先建仓」）、404 vs SPA 兜底 200 陷阱、中继后完整性校验；以及「把 A 机独有内容并入 B 机仓库」前的四档分档（运行态数据/生产专属/对机有正本/可并），含同名内容冲突、明文凭据、.gitignore 连锁陷阱三项专项扫描。当用户说「跳板机同步不了」「无网机器要推 git」「从本机同步到服务器」「内网仓库进不了远端」「把服务器内容并进本机仓库」时使用。不适用：主机本身有网、推前风险尽调→git-push-risk-gate。"
description_zh: "无出网主机的 git 仓库经有网主机中继推到远端：出网能力判定、占位 remote 识别、中继后完整性校验与内容分档。"
description_en: "Push an air-gapped host's git repository to a remote through an online relay host: egress capability probing, placeholder remote detection, post-relay integrity verification and content triage."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
---

# git-repo-relay-via-online-host — 无出网主机 Git 仓库中继

## 何时用

- A 机**无公网/无出网**（气隙、内网隔离区），但它的 git 仓库需要进远端 Git 服务器 → 由**有网的 B 机中继**
- 用户说「跳板机同步不了，必须从本机」「无网机器推不了 git」「内网仓库进不了远端」
- 与 `git-push-risk-gate` 配合使用：本 skill 负责**中继链路**，那个 skill 负责**推送前闸门**

## 铁律

> **推送是唯一写操作，其余全部只读。**
> **无网主机的内容，别只想着「让无网机推」——先判断它是不是真没网，再看目标仓库是否存在。**

## 第一步：判定出网能力（不要看 git 报错）

**关键：`git push` 失败 ≠ 网络不通。** 必须先做 TCP 探测，把「网络层」与「仓库不存在」分开。

```bash
# 两个端口都要测（HTTPS 与 SSH 可能分别管控）
for port in 443 30004; do
  timeout 10 bash -c "cat < /dev/null > /dev/tcp/<git-host>/$port" \
    && echo "$port OPEN" || echo "$port FAIL"
done
```

- A 机 `FAIL` + B 机 `OPEN` → **只有 B 能推，必须中继**
- 两台都 `OPEN` → 先别中继，查是不是**目标仓库不存在**（见第三步）

> 用 `git ls-remote` 做端到端验证时，**不要加管道**——`... | head; echo $?` 取的是 `head` 的退出码，
> 会把超时（exit=124）误读为 exit=0「空仓库」。详见 `git-push-risk-gate` 闸门 4。

## 第二步：判定「remote 是不是从未建仓的占位符」

一个仓库配了 remote ≠ 远端存在。**三者具其一，就该先怀疑占位符，而不是反复调网络**：

| 判据 | 命令 | 占位符特征 |
|---|---|---|
| FETCH_HEAD 来源 | `cat .git/FETCH_HEAD` | 指向本地 `*.bundle`（而非远端 URL）→ 从 bundle 初始化，从未 clone |
| 使用记录 | `git reflog --all \| grep -iE "fetch\|push"` | **零记录** → 该 remote 从未成功用过 |
| 项目文档 | 仓库内 grep「404 / 需先建仓」 | 出现「推送 404：需先在 Web 端创建仓库」→ 预留地址惯例 |

本类「预留地址」常见于：**企业 Gitee/GitLab 需先在 Web 端建仓，再 `git push -u origin master`**。

## 第三步：验证目标仓库是否真的存在（404 vs SPA 陷阱）

**企业版 Git 前端是 SPA：任意不存在页面都返回 200 的 HTML 兜底页。只测带 `.git` 的 info/refs。**

```bash
# ✅ 正确：401/200 = 存在，404 = 不存在
curl -sS -o /dev/null -w "%{http_code}\n" \
  "https://<host>/<path>.git/info/refs?service=git-upload-pack"

# ❌ 错误：裸路径会被 SPA 兜底成 200 → 误判"存在"
curl -s -o /dev/null -w "%{http_code}" "https://<host>/<path>"
```

**必须用已知存在的仓库做阳性对照**，否则无法区分「不存在」与「凭证无效」：

```bash
# 已知存在的仓库应为 401（需认证）；不存在的应为 404
curl ... ".../gf/gzmaxin/aiops.git/info/refs?service=git-upload-pack"  # 401 = 存在
```

同时区分 `git-upload-pack`（读）与 `git-receive-pack`（写）—— 有些仓库只读不写。

## 第四步：中继（B 机 SSH 直读 A 仓 → 裸克隆 → 推）

前提：**B 机能 SSH 到 A**（`ssh user@A_HOST` 通）。

```bash
# 1) 先只读验证 B 能看到 A 的仓库
git ls-remote ssh://user@A_HOST/path/to/repo

# 2) 全量裸克隆到 B（含全部分支与 tag）
git clone --bare ssh://user@A_HOST/path/to/repo arepo.git

# 3) 在 B 上配远端并推（走 git-push-risk-gate 闸门后）
cd arepo.git
git remote add target <正确远端 URL>
git push target master        # 快进，绝不 --force
```

**SSH 到 A 的常见坑**：

- `ControlMaster` socket 缓存失效报 `Connection refused` / `cannot bind to path` →
  加 `-o ControlMaster=no -o ControlPath=none`，并确保 `~/.ssh/cm` 目录存在
- A 机上仓库属主非当前用户 → `git -c safe.directory='*' ls-remote ...`

## 第五步：完整性校验（中继必须回验）

```bash
# B 上裸克隆的目标仓库，回验 sha256
git --git-dir=arepo.git cat-file -e "HEAD:<关键文件>"     # 文件在不在
git --git-dir=arepo.git rev-parse HEAD                    # HEAD 对不对
git --git-dir=arepo.git rev-list --count master            # 提交数对不对
```

若目标是「推出去」，再**裸克隆远端**做端到端回验（最强证据）：

```bash
git clone --depth 1 <target-url> /tmp/verify
sha256sum <关键文件>            # 与本地版本比对，应逐字节一致
```

## 输出规范

给用户一张表：`源 / 目标 / 出网结果 / 仓库存在性 / 中继动作 / 回验结果`，
并**明确区分**三种失败原因：
1. **网络层**（TCP FAIL）→ 该机确实推不了，需中继
2. **仓库不存在**（404）→ 需先建仓或要正确 URL
3. **认证失败**（401 且报 publickey/denied）→ 需配凭证

## 第六步（变体）：把 A 机独有内容「并入」B 机仓库前，先做四档分档

当用户倾向「把 A 机独有内容并入 B 机仓库一起推」（而非独立建仓）时，
**不要直接 `cp -r` 或 `git merge`**。先做**只读分档**，因为跨机仓库通常是
「同项目的两份独立历史」（无共同祖先 → 并入 = **文件级叠加**，不是 merge）。

### 6.1 三个必查的量化指标

```bash
# 1) 独有 / 共有文件（用 comm 而非 diff）
git -C A ls-tree -r --name-only HEAD | sort > /tmp/a_all.txt
git -C B ls-tree -r --name-only HEAD | sort > /tmp/b_all.txt
comm -23 /tmp/a_all.txt /tmp/b_all.txt > /tmp/a_only.txt   # A 独有
comm -12 /tmp/a_all.txt /tmp/b_all.txt | wc -l             # 共有路径数

# 2) 🔴 同名但内容冲突（并入时必然要逐个拍板）—— 最关键的一步
git -C A ls-tree -r HEAD | awk '{print $3" "$4}' | sort -k2 > /tmp/a_hash.txt
git -C B ls-tree -r HEAD | awk '{print $3" "$4}' | sort -k2 > /tmp/b_hash.txt
join -1 2 -2 2 /tmp/a_hash.txt /tmp/b_hash.txt | awk '$2!=$3 {print $1}'

# 3) 是否同源
git -C A log --oneline --reverse | head -1      # 首个提交
git -C B log --oneline --reverse | head -1
```

### 6.2 独有文件四档分类（决定「并什么」）

| 档 | 判据 | 处置 |
|---|---|---|
| **A 运行态数据** | `data/history/`、`data/reports/`、`*sweep-manifest*`、`*sessions*/*.jsonl` | 🔴 **禁并**（且 B 机 `.gitignore` 往往已屏蔽同类 → 并入=自打脸） |
| **B 生产专属** | 部署组件目录（`alert-core/`、`backend/`、`git-mirrors/`、`ansible/`、`log-cleaner/`）、`*.backup-*` | 🟠 不宜并；含运维配置的须先查凭据 |
| **C 对机有正本** | A 侧是部署副本、B 侧（或其兄弟仓）才是开发正本 | 🟡 **方向相反**：应从 B 机下发到 A 机，不是并入 |
| **D 其他** | 纯文档 / 测试 / 无冲突新增 | ✅ B′ 候选 |

### 6.3 并入前必做的两项专项扫描

```bash
# ① 明文凭据（并入 = 主动把凭据写进远端历史，删文件也删不掉）
git -C A grep -I -l -E '(password|passwd|secret|token|api_key|Gf@|sk-[A-Za-z0-9]{20,})' HEAD

# ② 冲突文件里的 .gitignore —— 最危险的连锁陷阱
#    误取 A 机版会回退 B 机刚建立的运行态屏蔽规则，导致 A 档数据一次性涌入
git -C A diff HEAD:^ .. 2>/dev/null | head
```

### 6.4 结论模板

给用户三档建议而非二选一：

- **整体并入（原方案）**：列出「会带进多少非源码文件 + 多少明文口令 + 多少待拍板冲突」→ 通常**不可取**
- **B′ 裁剪并入**：给出**精确文件清单**（目录 + 数量 + 是否新增/覆盖）
- **独立建仓**：生产专属子系统（如 `alert-core/`）建议单开仓库承载

## 已知坑汇总

| # | 坑 | 正解 |
|---|---|---|
| 1 | `ls-remote \| head; echo $?` 取到 head 退出码 | 不加管道，直接 `echo $?` |
| 2 | 裸路径 200 被误判「仓库存在」 | 只测 `.git/info/refs`，并用已知仓库做对照 |
| 3 | `git push` 报错就断言是网络问题 | 先 TCP 探测，再查仓库存在性 |
| 4 | remote 是占位符却反复调网络 | 查 FETCH_HEAD 来源 + reflog + 文档 |
| 5 | ControlMaster socket 失效 | `-o ControlMaster=no -o ControlPath=none` |
| 6 | 中继后未回验，不知内容是否完整 | 裸克隆目标仓库 + sha256 比对 |
| 7 | **只比文件名就判断「修复未进远端」** | 必须 `git rev-parse HEAD:<path>` **逐文件哈希对撞**；哈希不同再验语义等价 |
| 8 | 哈希不同即断言「未修复」（假阳性） | 行序/注释/空行微差会造成哈希差异但**语义等价** → 抓关键定义行二次核验 |
| 9 | 用 `ls-tree` 名称直接 `comm` 比对，中文名被引号包裹 | 先 `sed 's/^"//'` 去掉 git 的引号包裹，否则分档计数偏差 |
| 10 | 把「A 机独有的同名文件」默认当新增 | 先算**同名内容冲突**（§6.2）；冲突数可能高达数十个 |
| 11 | 并入前不查 `.gitignore` 是否也在冲突集 | 目标仓的 `.gitignore` 常配置更严 → 误覆盖会放进运行态数据 |
| 12 | 并入时目标仓正被其他会话写 | 先 `git status -sb` 看 `ahead N`；未推提交属他会话 → **隔离**，或改独立分支 `import/<src>-<date>` |
| 13 | **`git ls-tree` 默认 `core.quotepath=true`**，中文名转义 `\347\233\221` 且被双引号包裹 | 一律 `git -c core.quotepath=false ls-tree -r --name-only`。否则 `comm` 分档**计数偏差**、`git archive` 直接失败 |
| 14 | `git archive --pathspec-from-file=<f>` | ❌ 不支持（报 `unknown option`）→ 用 `git archive HEAD $(cat list \| tr '\n' ' ')` |
| 15 | 只用「文件名在不在 + 哈希同不同」两层判「修复是否落地」 | 必须**三层**：①路径在不在 ②哈希是否相同 ③**哈希不同时验语义等价**（抓关键定义行）。缺第③层会把「已修但排版不同」误判为「未修」 |
| 16 | 断言「修复未进远端」却没查**承载仓库本身有无 remote** | 先 `git remote -v`；若承载仓**零 remote**，真因是「无处可推」而非「没修」，对应动作从「打补丁」变成「建远端」 |
| 17 | 首次推送（仓库从来没有远端）时只扫 HEAD | **必须扫全历史**：`git log --all -p \| grep '^+' \| grep -E '<高危模式>'`。首次推送会把全部历史一起带上，HEAD 干净 ≠ 历史干净 |
| 18 | 企业版 Gitee/GitLab 的 API 建仓端点（`/api/v5/user/repos` 等）返 404 | **404 ≠ 需认证**，是端点根本不存在 → 自动化建仓不可行，须转 Web 端手动建仓 |
| 19 | 远端不存在就以为「等它出现」，无法推进 | 先做**存在性判据**（`curl -o /dev/null -w "%{http_code}" <repo>.git/info/refs?service=git-upload-pack` → 404=不存在 / 401=存在），并用已知仓库做**阳性对照**，判定可信后再决定「建仓 or 复用」 |

## 附录：B′ 并入的标准执行序列（已验证）

```bash
# ① 校验工作区干净 + 看他会话是否在写
git -C $DST status --porcelain | wc -l      # 必须 0
git -C $DST status -sb | head -1            # 有 ahead N → 走独立分支

# ② 独立分支隔离（绝不直接在 master 上并）
git -C $DST checkout -b import/<src>-<YYYYMMDD>

# ③ 精确导出（必须关 quotepath，否则中文名失败）
cd $SRC
git -c core.quotepath=false ls-tree -r --name-only HEAD | sort > /tmp/src.txt
git -C $DST -c core.quotepath=false ls-tree -r --name-only HEAD | sort > /tmp/dst.txt
comm -23 /tmp/src.txt /tmp/dst.txt > /tmp/only.txt        # 独有
# ...分档筛选出 B′ 清单 → /tmp/bprime.txt
git archive HEAD $(cat /tmp/bprime.txt | tr '\n' ' ') > /tmp/bp.tar
mkdir -p /tmp/bp_x && tar -xf /tmp/bp.tar -C /tmp/bp_x

# ④ 落盘前：覆盖校验（B′ 的核心承诺 = 零覆盖）
while IFS= read -r f; do [ -e "$DST/$f" ] && echo "OVERWRITE $f"; done < /tmp/bprime.txt

# ⑤ 落盘 + 双校验（凭据 / sha256 回验）
cd /tmp/bp_x && find . -type f | sed 's|^\./||' | while IFS= read -r f; do
  mkdir -p "$DST/$(dirname "$f")"; cp "$f" "$DST/$f"; done
while IFS= read -r f; do   # sha256 与源对撞
  a=$(cd $SRC && git show "HEAD:$f" | sha256sum | cut -d' ' -f1)
  b=$(sha256sum "$DST/$f" | cut -d' ' -f1)
  [ "$a" = "$b" ] || echo "MISMATCH $f"
done < /tmp/bprime.txt

# ⑥ 提交前确认变更类型全为 A（零 M / 零 D）
git -C $DST add <各组路径>
git -C $DST diff --cached --name-status | awk '{print $1}' | sort | uniq -c

# ⑦ 提交后切回 master 验证未被污染
git -C $DST commit -F - <<'MSG'
... 说明来源 / 分组 / 已排除档位 / 安全校验 / 隔离原因
MSG
git -C $DST checkout master && git -C $DST status --porcelain | wc -l   # 必须 0
```
