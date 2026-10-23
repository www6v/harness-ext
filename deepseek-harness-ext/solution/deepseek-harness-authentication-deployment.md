# DeepSeek Harness 认证与部署方案

## 概述

本文档说明 DeepSeek Harness 与 meta-harness 之间的认证机制，以及在不同部署场景下的配置方案。

**认证流程：**
1. meta-harness 的 `deepseek_client.go` 从 `$DSH_HOME/.credentials.yaml` 读取认证密钥
2. 通过 WebSocket 连接 deepseek-harness 网关时，在 HTTP Header 中携带认证 cookie
3. deepseek-harness 验证认证密钥后建立连接

---

## 认证配置文件

### 文件位置

| 系统 | 路径 |
|------|------|
| Windows | `C:\Users\<用户名>\.dsh\.credentials.yaml` |
| Linux/Mac | `~/.dsh/.credentials.yaml` |
| Docker 容器内 | `/root/.dsh/.credentials.yaml` |

### 文件格式

```yaml
version: 1
records:
  client-connection/browser-session:
    kind: grant
    payload:
      version: 1
      secret: <认证密钥>
refs:
  DEEPSEEK_API_KEY: <DeepSeek API 密钥>
  BUYTOKEN_API_KEY: <BuyToken API 密钥>
```

### 关键字段说明

| 字段 | 用途 |
|------|------|
| `client-connection/browser-session.payload.secret` | WebSocket 连接认证密钥，客户端和服务端必须一致 |
| `refs.DEEPSEEK_API_KEY` | DeepSeek LLM API 密钥 |
| `refs.BUYTOKEN_API_KEY` | BuyToken 代理 API 密钥 |

---

## 部署方案

### 方案 1：本地开发环境（单机）

**场景：** meta-harness 和 deepseek-harness 运行在同一台宿主机上

#### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      宿主机（本地开发）                       │
│                                                             │
│  ┌─────────────────────┐      ┌─────────────────────────┐  │
│  │   meta-harness      │      │    deepseek-harness     │  │
│  │   (oma-server)      │─────▶│    (dsh gateway)        │  │
│  │   Port: 8787        │      │    Port: 3080           │  │
│  │                     │      │                         │  │
│  │   读取本地 ~/.dsh/  │      │   读取本地 ~/.dsh/      │  │
│  │   .credentials.yaml │      │   .credentials.yaml     │  │
│  └─────────────────────┘      └─────────────────────────┘  │
│                                                             │
│                    共享 ~/.dsh/ 配置目录                      │
└─────────────────────────────────────────────────────────────┘
```

#### 配置步骤

1. **创建认证配置：**
```bash
mkdir -p ~/.dsh
cat > ~/.dsh/.credentials.yaml << 'EOF'
version: 1
records:
  client-connection/browser-session:
    kind: grant
    payload:
      version: 1
      secret: BWfO8bVG4AFqD61xF2vA0-g-lukRmiJnz__gvvqXSb0
refs:
  DEEPSEEK_API_KEY: sk-your-deepseek-api-key
  BUYTOKEN_API_KEY: sk-your-buytoken-key
EOF
```

2. **启动 deepseek-harness：**
```bash
cd deepseek-harness
export DEEPSEEK_API_KEY=sk-your-deepseek-api-key
export BUYTOKEN_API_KEY=sk-your-buytoken-key
node --import tsx/esm apps/cli/src/bin.ts --profile headless gateway
```

3. **启动 meta-harness：**
```bash
cd meta-harness
export AUTH_DISABLED=1
export OMA_DEEPSEEK_GATEWAY_URL=http://127.0.0.1:3080
./bin/oma-server.exe
```

4. **测试连接：**
```bash
curl http://127.0.0.1:8787/health
```

#### Docker Compose（本地单机）

```yaml
# docker-compose.yml
version: '3.8'

services:
  deepseek-harness:
    image: deepseek-harness:latest
    ports:
      - "3080:3080"
    volumes:
      - ~/.dsh/.credentials.yaml:/root/.dsh/.credentials.yaml:ro
      - ~/.dsh/settings.yaml:/root/.dsh/settings.yaml:ro
      - dsh-profiles:/root/.dsh/profiles
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - BUYTOKEN_API_KEY=${BUYTOKEN_API_KEY}
    command: ["--profile", "headless", "gateway"]

  oma-server:
    image: meta-harness:latest
    ports:
      - "8787:8787"
    volumes:
      - ~/.dsh/.credentials.yaml:/root/.dsh/.credentials.yaml:ro
      - oma-data:/root/.local/share/oma
    environment:
      - AUTH_DISABLED=1
      - OMA_DEEPSEEK_GATEWAY_URL=http://deepseek-harness:3080
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - BUYTOKEN_API_KEY=${BUYTOKEN_API_KEY}
    depends_on:
      - deepseek-harness

volumes:
  dsh-profiles:
  oma-data:
```

**启动命令：**
```bash
docker-compose up -d
```

---

### 方案 2：远程容器部署（多宿主机）

**场景：** meta-harness 和 deepseek-harness 运行在不同宿主机上

#### 架构图

```
┌──────────────────────────┐         ┌──────────────────────────┐
│     宿主机 A             │         │     宿主机 B             │
│   (deepseek-harness)     │         │   (meta-harness)         │
│                          │         │                          │
│  ┌────────────────────┐  │         │  ┌────────────────────┐  │
│  │  dsh gateway       │  │         │  │   oma-server       │  │
│  │  Port: 3080        │  │         │  │   Port: 8787       │  │
│  │                    │  │         │  │                    │  │
│  │  ~/.dsh/           │  │         │  │  ~/.dsh/           │  │
│  │  .credentials.yaml │  │         │  │  .credentials.yaml │  │
│  └────────────────────┘  │         │  └────────────────────┘  │
│                          │         │                          │
│  防火墙：开放 3080 端口    │         │  出站：允许访问宿主机 A:3080│
└──────────────────────────┘         └──────────────────────────┘
              │                                   │
              │                                   │
              └───────────────┬───────────────────┘
                              │
                    HTTP/WebSocket (认证通信)
                              │
                    宿主机 A:3080 ←─ 宿主机 B:8787
```

#### 配置步骤

**步骤 1：在宿主机 A 生成认证配置**

```bash
# 宿主机 A
mkdir -p ~/.dsh
cat > ~/.dsh/.credentials.yaml << 'EOF'
version: 1
records:
  client-connection/browser-session:
    kind: grant
    payload:
      version: 1
      secret: $(openssl rand -base64 32)
refs:
  DEEPSEEK_API_KEY: sk-your-deepseek-api-key
  BUYTOKEN_API_KEY: sk-your-buytoken-key
EOF

# 查看生成的密钥
cat ~/.dsh/.credentials.yaml
```

**步骤 2：同步认证配置到宿主机 B**

```bash
# 方式 1: 使用 scp 复制
scp ~/.dsh/.credentials.yaml user@宿主机B-IP:~/.dsh/.credentials.yaml

# 方式 2: 手动复制（复制上面 cat 输出的内容）
# 在宿主机 B 上执行：
mkdir -p ~/.dsh
cat > ~/.dsh/.credentials.yaml << 'EOF'
version: 1
records:
  client-connection/browser-session:
    kind: grant
    payload:
      version: 1
      secret: <从宿主机 A 复制的密钥>
refs:
  DEEPSEEK_API_KEY: sk-your-deepseek-api-key
  BUYTOKEN_API_KEY: sk-your-buytoken-key
EOF
```

**步骤 3：配置防火墙（宿主机 A）**

```bash
# Ubuntu/Debian
ufw allow 3080/tcp
ufw allow from 宿主机B-IP to any port 3080

# CentOS/RHEL
firewall-cmd --permanent --add-port=3080/tcp
firewall-cmd --permanent --add-source=宿主机 B-IP --port=3080/tcp
firewall-cmd --reload

# 云服务器安全组（阿里云/腾讯云/AWS）
# 添加入站规则：
#   源 IP: 宿主机 B 的公网 IP
#   端口：3080
#   协议：TCP
```

**步骤 4：部署 Docker 容器**

```yaml
# 宿主机 A - docker-compose.yml (deepseek-harness)
version: '3.8'

services:
  deepseek-harness:
    image: deepseek-harness:latest
    ports:
      - "3080:3080"
    volumes:
      - ~/.dsh/.credentials.yaml:/root/.dsh/.credentials.yaml:ro
      - ~/.dsh/settings.yaml:/root/.dsh/settings.yaml:ro
      - dsh-profiles:/root/.dsh/profiles
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - BUYTOKEN_API_KEY=${BUYTOKEN_API_KEY}
    command: ["--profile", "headless", "gateway"]
    restart: unless-stopped

volumes:
  dsh-profiles:
```

```yaml
# 宿主机 B - docker-compose.yml (meta-harness)
version: '3.8'

services:
  oma-server:
    image: meta-harness:latest
    ports:
      - "8787:8787"
    volumes:
      - ~/.dsh/.credentials.yaml:/root/.dsh/.credentials.yaml:ro
      - oma-data:/root/.local/share/oma
    environment:
      - AUTH_DISABLED=0
      - PUBLIC_BASE_URL=http://宿主机B-IP:8787
      - OMA_DEEPSEEK_GATEWAY_URL=http://宿主机A-内网IP:3080
      - OMA_API_KEY=dev-key
      - BETTER_AUTH_SECRET=your-better-auth-secret
    restart: unless-stopped

volumes:
  oma-data:
```

**步骤 5：启动服务**

```bash
# 宿主机 A
cd /path/to/deepseek-harness
export DEEPSEEK_API_KEY=sk-xxx
export BUYTOKEN_API_KEY=sk-xxx
docker-compose up -d

# 宿主机 B
cd /path/to/meta-harness
docker-compose up -d
```

**步骤 6：验证连接**

```bash
# 在宿主机 B 测试到宿主机 A 的连接
curl http://宿主机A-内网IP:3080/health

# 检查 meta-harness 日志
docker logs oma-server | grep -i "DSH CLIENT"
```

---

### 方案 3：使用环境变量传递认证（推荐用于自动化）

**场景：** CI/CD 自动化部署，避免文件同步

#### 架构说明

不依赖 `.credentials.yaml` 文件，而是通过环境变量传递认证密钥：

```
┌──────────────────────┐              ┌──────────────────────┐
│   宿主机 A           │              │   宿主机 B           │
│   deepseek-harness   │              │   meta-harness       │
│                      │              │                      │
│  DSH_AUTH_SECRET=xxx │              │  DSH_AUTH_SECRET=xxx │
│  DEEPSEEK_API_KEY=xx │              │  (相同密钥)          │
│                      │              │                      │
└──────────────────────┘              └──────────────────────┘
```

#### Docker Compose 配置

```yaml
# 宿主机 A - docker-compose.yml
services:
  deepseek-harness:
    image: deepseek-harness:latest
    ports:
      - "3080:3080"
    environment:
      - DSH_AUTH_SECRET=${DSH_AUTH_SECRET}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - BUYTOKEN_API_KEY=${BUYTOKEN_API_KEY}
    command: ["--profile", "headless", "gateway", "--auth-secret", "${DSH_AUTH_SECRET}"]
```

```yaml
# 宿主机 B - docker-compose.yml
services:
  oma-server:
    image: meta-harness:latest
    ports:
      - "8787:8787"
    volumes:
      - oma-data:/root/.local/share/oma
    environment:
      - DSH_AUTH_SECRET=${DSH_AUTH_SECRET}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - BUYTOKEN_API_KEY=${BUYTOKEN_API_KEY}
      - OMA_DEEPSEEK_GATEWAY_URL=http://宿主机A-IP:3080
```

#### .env 文件示例

```bash
# .env (两台宿主机使用相同的值)
DSH_AUTH_SECRET=BWfO8bVG4AFqD61xF2vA0-g-lukRmiJnz__gvvqXSb0
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
BUYTOKEN_API_KEY=sk-your-buytoken-key
```

---

### 方案 4：使用密钥管理服务（生产环境推荐）

**场景：** 多节点生产环境，需要密钥轮换和审计

#### 使用 HashiCorp Vault

```bash
# 初始化 Vault（首次）
vault server -dev -dev-root-token-id=root

# 写入密钥
vault kv put secret/deepseek-harness/auth \
  auth_secret="BWfO8bVG4AFqD61xF2vA0-g-lukRmiJnz__gvvqXSb0" \
  deepseek_api_key="sk-xxx" \
  buytoken_api_key="sk-xxx"
```

**Vault 读取脚本：**

```bash
#!/bin/bash
# get-dsh-credentials.sh

VAULT_ADDR="http://vault-server:8200"
VAULT_TOKEN="your-vault-token"

# 读取密钥
AUTH_SECRET=$(vault kv get -field=auth_secret -address=$VAULT_ADDR -token=$VAULT_TOKEN secret/deepseek-harness/auth)
DEEPSEEK_KEY=$(vault kv get -field=deepseek_api_key -address=$VAULT_ADDR -token=$VAULT_TOKEN secret/deepseek-harness/auth)
BUYTOKEN_KEY=$(vault kv get -field=buytoken_api_key -address=$VAULT_ADDR -token=$VAULT_TOKEN secret/deepseek-harness/auth)

export DSH_AUTH_SECRET=$AUTH_SECRET
export DEEPSEEK_API_KEY=$DEEPSEEK_KEY
export BUYTOKEN_API_KEY=$BUYTOKEN_KEY
```

**Docker Compose + Vault：**

```yaml
services:
  deepseek-harness:
    image: deepseek-harness:latest
    ports:
      - "3080:3080"
    environment:
      - VAULT_ADDR=http://vault:8200
      - VAULT_TOKEN=${VAULT_TOKEN}
    command: |
      sh -c '
        export DSH_AUTH_SECRET=$(vault kv get -field=auth_secret secret/deepseek-harness/auth)
        export DEEPSEEK_API_KEY=$(vault kv get -field=deepseek_api_key secret/deepseek-harness/auth)
        exec dsh --profile headless gateway
      '
```

---

## 故障排查

### 问题 1: 401 Unauthorized

**症状：**
```
[DSH RPC ERROR] method=session/create status=401 body=unauthorized
```

**排查步骤：**

1. 检查两台宿主机的认证密钥是否一致：
```bash
# 宿主机 A
grep secret ~/.dsh/.credentials.yaml

# 宿主机 B
grep secret ~/.dsh/.credentials.yaml
```

2. 检查 Docker 容器内配置是否正确挂载：
```bash
docker exec <container-id> cat /root/.dsh/.credentials.yaml
```

3. 检查环境变量是否覆盖了文件配置：
```bash
docker exec <container-id> env | grep DSH_AUTH
```

### 问题 2: 连接超时

**症状：**
```
context deadline exceeded
dial tcp <IP>:3080: connect: connection timed out
```

**排查步骤：**

1. 测试网络连通性：
```bash
# 从宿主机 B ping 宿主机 A
ping 宿主机 A-IP

# 测试端口连通性
telnet 宿主机 A-IP 3080
# 或
nc -zv 宿主机 A-IP 3080
```

2. 检查防火墙规则：
```bash
# 宿主机 A
ufw status
iptables -L -n | grep 3080
```

3. 检查 deepseek-harness 是否监听正确地址：
```bash
netstat -tlnp | grep 3080
# 应该监听 0.0.0.0:3080 而不是 127.0.0.1:3080
```

### 问题 3: WebSocket 连接失败

**症状：**
```
websocket: bad handshake
```

**排查步骤：**

1. 检查认证密钥格式：
```yaml
# 确保 YAML 格式正确
records:
  client-connection/browser-session:
    kind: grant
    payload:
      version: 1
      secret: 正确的密钥
```

2. 检查代理/负载均衡器配置：
- 确保支持 WebSocket 升级
- 检查 `Upgrade` 和 `Connection` Header 是否正确转发

---

## 安全建议

1. **密钥生成：** 使用强随机密钥
```bash
openssl rand -base64 32
```

2. **文件权限：** 限制配置文件访问
```bash
chmod 600 ~/.dsh/.credentials.yaml
```

3. **网络隔离：** 使用内网通信
- 宿主机间通过内网 IP 通信
- 防火墙只允许特定 IP 访问 3080 端口

4. **密钥轮换：** 定期更新认证密钥
```bash
# 生成新密钥
NEW_SECRET=$(openssl rand -base64 32)

# 更新所有宿主机的配置
# 重启服务使新密钥生效
```

5. **审计日志：** 启用访问日志
```yaml
# deepseek-harness 配置
logging:
  level: info
  format: json
```

---

## 快速参考

| 部署场景 | 推荐方案 | 配置复杂度 | 安全性 |
|---------|---------|-----------|--------|
| 本地开发 | 方案 1（共享文件） | 低 | 中 |
| 测试环境 | 方案 2（文件同步） | 中 | 中 |
| 生产环境 | 方案 4（Vault） | 高 | 高 |
| CI/CD 自动化 | 方案 3（环境变量） | 低 | 中 |

---

## 参考资料

- `internal/harness/deepseek_client.go` - meta-harness DeepSeek 客户端实现
- `~/.dsh/.credentials.yaml` - 认证配置文件
- `scripts/e2e/test-deepseek-whoami.mjs` - E2E 验证测试
