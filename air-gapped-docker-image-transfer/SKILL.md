---
name: air-gapped-docker-image-transfer
display_name: "气隙主机 Docker 镜像中转部署"
display_name_en: "Air-Gapped Docker Image Transfer"
description: "目标 Linux 主机完全气隙（无法访问 Docker Hub / GHCR / 公网镜像源）却要部署容器时，通过中间节点中转镜像。覆盖三端连通性侦察、pull→save→SFTP→load 中转链、sha256 端到端完整性校验，以及加速器探测、pkill 自杀、nginx http2 版本等已知坑。当用户说「镜像拉不下来」「气隙/内网部署容器」「跨机传镜像」「测试机没外网要装 Docker 服务」时使用。"
description_zh: "目标主机完全气隙时，通过中间节点中转 Docker 镜像：连通性侦察、pull→save→SFTP→load 链路、sha256 端到端完整性校验。"
description_en: "Relay Docker images to a fully air-gapped host through an intermediate node: connectivity recon, a pull/save/SFTP/load chain and end-to-end sha256 integrity verification."
version: 1.0.0
author: "马欣/码心AI"
metadata:
  workbuddy:
    agent_created: "true"
---

# air-gapped-docker-image-transfer — 气隙主机 Docker 镜像中转部署

## 何时用

目标主机**无公网出口**（连公共 DNS 都不通），无法 `docker pull`，但需要在上面跑容器。
典型：企业内网测试机 / 生产隔离区。

**核心判断**：「DNS 能解析」≠「能出网」。必须做 TCP 握手测试，不能只看 `curl` 的域名结果。

## 第一步：三端连通性侦察（必做，决定方案可行性）

```bash
# 在每一端执行，建立连通性矩阵
for hp in "registry-1.docker.io:443" "ghcr.io:443" "github.com:443" "8.8.8.8:53" "1.1.1.1:53"; do
  h=${hp%:*}; p=${hp#*:}
  printf '%-28s ' "$hp"
  timeout 5 bash -c "echo > /dev/tcp/$h/$p" 2>/dev/null && echo OPEN || echo BLOCKED
done
```

判读要点：

| 现象 | 结论 |
|------|------|
| 域名能解析，但所有公网 `:443` BLOCKED | **上游 ACL 阻断**，本机 iptables 无关，需网络团队开白名单 |
| 连 `8.8.8.8:53` 都 BLOCKED | 确认是上游 ACL，不是 DNS 问题 |
| 只有某个内网源（如 yum 源）OPEN | 白名单模式，出网希望只在内网源侧 |

**同时确认内网镜像仓库是否可用**（别假设存在）：
```bash
for p in 80 443 5000 8443; do timeout 3 bash -c "echo > /dev/tcp/<registry-ip>/$p" && echo "$p OPEN"; done
```

**不要浪费时间扫描未知内网代理**——常见代理域名 + 端口扫一遍没有就收手，这属于网络组职责。

## 第二步：加速器探测（**先否后取**）

**血的教训：GHCR/DockerHub 的公共加速器大面积失效，先探测再依赖。**

```bash
# 用 manifest inspect 快速探测（不下载镜像层）
for r in \
  "docker.m.daocloud.io/<owner>/<image>:<tag>" \
  "ghcr.nju.edu.cn/<owner>/<image>:<tag>" \
  "ghcr.dockerproxy.com/<owner>/<image>:<tag>" \
  "<original-registry>/<owner>/<image>:<tag>"; do
  printf '%-70s ' "$r"
  timeout 20 docker manifest inspect "$r" >/dev/null 2>&1 && echo OK || echo FAIL
done
```

实测（2026-09）：`docker.m.daocloud.io` / `ghcr.nju.edu.cn` / `ghcr.dockerproxy.com` **全部 FAIL**，
只有 `ghcr.io` 原站直连可达。**直连即使慢也要用，配重试。**

## 第三步：中转链（核心）

```
有出网的中间机(跳板机)           本机(Windows/工作站)         目标气隙机
  docker pull  ──┐
  docker save    │  SFTP            SFTP
  gzip ──────────┴──→ 临时文件 ──────→ /tmp/xxx.tar.gz ──→ docker load
  sha256 记录                     sha256 校验 ×3
```

**关键：中间机与目标机通常网络不通**，必须经本机中转（本机需同时能 SSH 到两端）。

### 拉取脚本要点（中间机，带重试）

```bash
IMG="<registry>/<owner>/<image>:<tag>"
ok=0
for i in $(seq 1 12); do
  echo "--- attempt $i $(date '+%H:%M:%S') ---"
  if docker pull "$IMG" --quiet; then ok=1; echo "PULL_OK on $i"; break; fi
  echo "failed, waiting 10s..."; sleep 10
done
[ "$ok" = "1" ] || { echo "PULL_FAILED_ALL"; exit 1; }

mkdir -p /tmp/imgx
docker save "$IMG" -o /tmp/imgx/img.tar
pigz -1 -f /tmp/imgx/img.tar 2>/dev/null || gzip -1 -f /tmp/imgx/img.tar
du -h /tmp/imgx/img.tar.gz
sha256sum /tmp/imgx/img.tar.gz      # ← 记录，后续校验
```

> `docker pull` 幂等且复用已完成层，循环重试可**逐层累积**，这是对付不稳定链路的关键。

### 中转脚本要点（本机，paramiko）

```python
# 三段 sha256 必须一致，任一段不符立即中止
src_sha = remote_sha(jump, "/tmp/imgx/img.tar.gz")
sftp.get(REMOTE_SRC, str(LOCAL))                 # 跳板机 → 本机
assert src_sha == sha256_file(LOCAL)             # 校验 1

sftp2.put(str(LOCAL), "/tmp/img.tar.gz")         # 本机 → 目标机
assert sha256_file(LOCAL) == remote_sha(test, "/tmp/img.tar.gz")   # 校验 2
```

目标机：`docker load -i /tmp/img.tar.gz`

### 规模参考（用于估算时间）

| 阶段 | 大小 |
|------|------|
| 压缩层（registry 内） | 38.4 MB |
| `docker save` 后 | 108 MB |
| gzip -1 后 | 42 MB |
| `docker load` 后（解压） | 222 MB |
| 跳板机→本机 SFTP | ~47 s |
| 本机→目标机 SFTP | ~6 s |

## 踩坑速查

| 坑 | 现象 | 解法 |
|----|------|------|
| **`pkill -f` 自杀** | 脚本静默无输出、被自己杀掉 | `pkill -f 'xxx'` 会匹配**执行它的 bash 自身命令行**。改用 `pgrep -a -x -f` 精确匹配，或先 `pgrep` 确认 PID 再 `kill` |
| **nginx 1.24 不支持 `http2 on;`** | `nginx -t` 报 `unknown directive "http2"`（需 1.25.1+） | 用兼容写法 `listen 443 ssl http2;` |
| **`nginx -t` 失败但进程仍 active** | reload 被拒，误判为已生效 | `systemctl reload` 失败时**旧配置仍在跑**，必须查 `nginx -t` 结果再下结论 |
| 加速器集体失效 | pull 卡在 `unexpected EOF` | 见第二步：先探测，直连 + 重试 |
| 容器内无 `wget`/`du` | 容器内探测命令 not found | 用 `sh -c` 前先探；或从宿主机侧验证 |
| 跳板机→目标机不通 | 直连 SSH 超时 | 必须经本机中转，别试图建立直连隧道 |

## 验证清单（DoD）

- [ ] 三段 sha256 完全一致
- [ ] `docker images | grep <image>` 在目标机可见
- [ ] 容器 `healthy`（不是 just `running`）
- [ ] 端口绑定符合预期（**内部服务绑 `127.0.0.1`，不对外暴露**）
- [ ] 反代链路端到端：域名 → nginx → 后端，逐跳取状态码
- [ ] 从**外部节点**（非目标机本机）经域名验证，避免只测 localhost 自欺
- [ ] 清理所有中转临时文件（`/tmp`、本机 `_xfer/`、中间机镜像）

## 现场清理原则

**清过程产物，留交付成果**：

| 类别 | 处置 |
|------|------|
| 侦察/执行/验证脚本（本机工作区） | 删 |
| 中间机中转镜像 + `/tmp` 残留 | 删（它非运行服务） |
| **目标机运行中的镜像 + 容器 + 部署目录** | **留**（服务在线） |
| 交付报告、运维脚本、nginx 配置 | 留 |

## 相关

- 跨机 SSH：Python paramiko + `~/.ssh/id_workbuddy`（禁 Windows `ssh.exe`）
- 远端路径：显式正斜杠字面量，禁 `os.path.join`（会注入反斜杠）
