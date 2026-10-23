# Remote Deployment Guide

## 方法 1: 使用 SSH 直接连接（推荐）

```bash
# 1. SSH 连接到服务器
ssh root@111.229.26.170
# 密码: 1qaZxsw@

# 2. 进入部署目录
cd /home/wei/deepseek-harness-ext/deploy

# 3. 启用 BuildKit 加速构建
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# 4. 构建镜像（使用优化配置）
docker compose build --progress=plain

# 5. 启动容器
docker compose up -d

# 6. 查看状态
docker compose ps

# 7. 查看日志
docker compose logs -f
```

## 方法 2: 使用自动化脚本

```bash
# 在本地运行
chmod +x remote-deploy.sh
./remote-deploy.sh
```

## 构建性能优化

### 已应用的优化：

1. **Docker BuildKit** - 并行构建和更好的缓存
2. **优化的 Dockerfile** - 减少层数，更好的缓存策略
3. **依赖预安装** - 使用 `--prefer-offline` 和 `--ignore-scripts`
4. **并行构建** - 分离构建步骤以利用多核 CPU
5. **最小化生产镜像** - 只包含必要的运行时文件

### 额外的性能优化建议：

#### 1. 使用 Docker 构建缓存挂载（需要 BuildKit）

在 Dockerfile 中添加：
```dockerfile
RUN --mount=type=cache,target=/root/.pnpm-store \
    pnpm install --frozen-lockfile
```

#### 2. 增加 Docker 资源限制

编辑 `docker-compose.yml`：
```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'  # 增加 CPU
      memory: 4G    # 增加内存
```

#### 3. 使用多阶段构建的并行化

已经在优化的 Dockerfile 中实现。

#### 4. 预拉取基础镜像

```bash
docker pull node:22-alpine
```

#### 5. 清理 Docker 缓存

```bash
docker system prune -a
```

## 故障排除

### 构建很慢？

1. 检查 Docker 资源：
   ```bash
   docker stats
   ```

2. 查看构建详情：
   ```bash
   docker compose build --progress=plain --no-cache
   ```

3. 使用构建缓存：
   ```bash
   docker compose build --pull
   ```

### 内存不足？

增加 Docker 内存限制：
```bash
# 在 docker-compose.yml 中调整
deploy:
  resources:
    limits:
      memory: 4G
```

### 构建失败？

查看详细日志：
```bash
docker compose build --progress=plain 2>&1 | tee build.log
```

## 监控构建进度

```bash
# 实时查看构建日志
docker compose build --progress=plain

# 查看容器资源使用
docker stats

# 查看磁盘使用
docker system df
```
