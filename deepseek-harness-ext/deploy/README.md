# DeepSeek Harness — Docker 部署

本目录包含 DeepSeek Harness 的 Docker 部署配置及运维脚本。

## 目录结构

```
deploy/
├── Dockerfile                  # 基础多阶段构建
├── Dockerfile.optimized        # 优化版构建（国内镜像源、healthcheck 修复）
├── docker-compose.yml          # 生产环境 Compose 配置
├── docker-compose.dev.yml      # 开发环境覆盖配置
├── .dockerignore               # Docker 构建排除文件
├── env.example                 # 环境变量示例
├── deploy.sh                   # Linux/macOS 部署脚本
├── deploy.bat                  # Windows 部署脚本
├── backup.sh                   # 数据备份脚本
├── restore.sh                  # 数据恢复脚本
├── healthcheck.sh              # 容器健康检查脚本
├── update.sh                   # 镜像更新脚本
├── REMOTE-DEPLOY.md            # 远程部署指南
├── README.md                   # 本文件
└── ssh-deploy/                 # SSH 远程部署辅助脚本（Python + paramiko）
```

## 前置条件

```
parent-directory/
├── deepseek-harness/           # 源代码（构建上下文）
└── deepseek-harness-ext/       # 扩展仓库
    └── deploy/                 # 本目录
```

构建上下文为 `deepseek-harness/`（sibling 目录），Dockerfile 位于 `deepseek-harness-ext/deploy/`。

## 快速启动

```bash
# 1. 设置 API Key
export DEEPSEEK_API_KEY="your-api-key-here"

# 2. 构建镜像（使用优化版 Dockerfile）
docker compose build --build-arg NPM_REGISTRY=https://registry.npmmirror.com

# 3. 启动服务
docker compose up -d

# 4. 查看状态
docker compose ps
```

服务启动后访问 **http://localhost:3080**。

## 服务说明

| 服务 | 端口 | 说明 |
|------|------|------|
| `dsh` | 3080 | DeepSeek Harness Web 主服务 |
| `dsh-web` | 3080 | Web UI（可选，依赖 dsh 健康） |

## Dockerfile 说明

### Dockerfile.optimized（推荐生产使用）

四阶段构建：**install → build → runtime-prep → runtime**

| 阶段 | 说明 |
|------|------|
| `install` | 解析 pnpm workspace 依赖，使用国内镜像源加速 |
| `build` | TypeScript 编译 + Vite Web 打包 |
| `runtime-prep` | 执行 postinstall 脚本，补全原生模块 |
| `runtime` | 最小运行时镜像，仅包含编译产出和 curl |

**构建参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `NPM_REGISTRY` | `https://registry.npmmirror.com` | npm/pnpm 镜像源 |
| `APT_MIRROR` | `mirrors.aliyun.com` | Debian apt 镜像源 |

**运行时环境变量：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NODE_ENV` | `production` | 运行模式 |
| `DSH_WEB_PORT` | `3080` | Web 服务端口 |
| `DSH_ALLOW_WILDCARD_HOST` | `1` | 允许容器内绑定 0.0.0.0 |
| `DSH_HOME` | `/app/.dsh` | 会话持久化目录 |

**Health Check：** 使用 `curl -so /dev/null http://127.0.0.1:3080/` 检测服务可用性。注意使用 `-s`（silent）而非 `-f`（fail），因为根路径 `/` 在未认证时返回 HTTP 303 重定向，`-f` 会将其视为错误（exit 22）。

### --trusted-host 信任围栏

容器默认启用 DNS 重绑定防护（trust fence），仅允许 loopback 地址的 API 请求。通过外部 IP 访问时需声明 `--trusted-host`：

```yaml
command: ["node", "apps/cli/lib/bin.js", "web", "--host", "0.0.0.0", "--port", "3080",
          "--no-open", "--trusted-host", "YOUR_PUBLIC_IP"]
```

`docker-compose.yml` 中已通过 `command` 字段覆盖默认 CMD，添加了 `--trusted-host`。

## 环境变量

复制 `env.example` 为 `.env` 并配置：

```bash
cp env.example .env
```

主要变量：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | API 基础地址（可选自定义 endpoint） |
| `DSH_WEB_PORT` | 宿主机映射端口（默认 3080） |
| `TZ` | 容器时区（默认 UTC） |

## 数据持久化

| Volume | 挂载路径 | 说明 |
|--------|----------|------|
| `deepseek-harness-config` | `/app/.dsh/config` | 配置文件 |
| `deepseek-harness-sessions` | `/app/.dsh/sessions` | 会话数据 |
| `deepseek-harness-logs` | `/app/.dsh/logs` | 应用日志 |

## 运维脚本

```bash
# 启动
./deploy.sh up

# 查看日志
./deploy.sh logs

# 停止
./deploy.sh down

# 查看状态
./deploy.sh status

# 备份数据
./backup.sh

# 恢复数据
./restore.sh

# 健康检查
./healthcheck.sh

# 更新镜像并重启
./update.sh
```

## 远程 SSH 部署

参见 `ssh-deploy/` 目录中的 Python 脚本，使用 paramiko 库通过 SSH 实现远程部署。

典型流程：
1. 本地上传 Dockerfile 和 docker-compose.yml
2. 远程构建镜像（后台运行 + 日志轮询，避免 SSH 流超时）
3. 健康检查确认容器状态
4. API 验证（settings、providers、presets）

详细说明见 `REMOTE-DEPLOY.md`。

## 资源限制

默认限制（`docker-compose.yml`）：

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
    reservations:
      cpus: '0.5'
      memory: 512M
```

## 故障排除

### 容器 unhealthy

```bash
# 查看健康检查日志
docker inspect deepseek-harness --format '{{range .State.Health.Log}}Exit={{.ExitCode}} Output={{.Output}}{{end}}'

# 查看容器日志
docker compose logs dsh --tail=50
```

常见原因：
- **exit code 22**：healthcheck 使用了 `curl -sf`，303 重定向被当作失败。已通过 `-so` 修复。
- **启动慢**：首次构建需编译 TypeScript，start_period 设为 30s 足够覆盖。

### 构建慢

```bash
# 使用国内镜像源
docker compose build --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
                     --build-arg APT_MIRROR=mirrors.aliyun.com

# 或使用 Docker BuildKit
export DOCKER_BUILDKIT=1
docker compose build --progress=plain
```

### API 返回 403

检查 `--trusted-host` 是否包含访问该容器所使用的 Host 头 IP。在 `docker-compose.yml` 的 `command` 字段中添加。

### 清理

```bash
# 停止并删除容器
docker compose down

# 清理所有数据（含 volumes）
docker compose down -v
```