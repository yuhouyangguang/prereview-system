# 公司业务预审系统 · Docker 部署指南

整套系统已容器化为两个服务：

| 服务 | 内容 | 端口 |
|------|------|------|
| `backend`  | Flask + gunicorn（单 worker，含 APScheduler 定时任务 / RSA 签章 / SSE） | 容器内 5000，不对外 |
| `frontend` | vite 构建产物 + nginx（静态托管 + 反代 `/api` 到 backend） | 对外 `8080` → 80 |

数据持久化在两个 named volume：
- `prereview-db`   → `/app/instance`（SQLite 数据库）
- `prereview-keys` → `/app/keystores`（RSA 签章私钥）

---

## 一、迁移到新服务器

1. 安装 Docker（含 compose 插件）：
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

2. 拷贝整个项目目录到新服务器（含 `.env`，**勿提交 git**）：
   ```bash
   scp -r prereview-system user@新服务器:/opt/
   ```
   或在新服务器 `git clone` 后，手动复制 `.env`（`.env` 不在版本库里）。

3. 检查 / 填写 `.env`（关键项）：
   ```ini
   ZAI_API_KEY=...            # 智谱 GLM 密钥（已填）
   JWT_SECRET_KEY=...         # 已生成 64 位随机串；换服务器可保留或重置
   SEED_PASSWORD=password123  # 首次建库的种子账号密码，生产请改
   WECHAT_WEBHOOK_URL=        # 可选：企业微信群机器人
   ```
   > `FLASK_ENV=production`、`FLASK_DEBUG=0`、`DATABASE_URI` 已在 compose 中固定，无需在 .env 改。

4. 构建并启动：
   ```bash
   cd /opt/prereview-system
   docker compose up -d --build
   ```

5. 访问：`http://<服务器IP>:8080`
   种子测试账号：`zhangwei / password123`（客户经理）等，详见后端启动日志。

---

## 二、常用运维命令

```bash
docker compose ps                 # 状态
docker compose logs -f backend    # 后端日志
docker compose logs -f frontend   # 前端/nginx 日志
docker compose restart            # 重启
docker compose down               # 停止（保留数据卷）
docker compose up -d --build      # 改代码后重新构建上线
```

## 三、数据备份 / 迁移

数据全在两个 volume 里。备份：
```bash
docker run --rm -v prereview-system_prereview-db:/db -v "$PWD":/bak \
  alpine tar czf /bak/db-backup.tgz -C /db .
docker run --rm -v prereview-system_prereview-keys:/keys -v "$PWD":/bak \
  alpine tar czf /bak/keys-backup.tgz -C /keys .
```
在新机恢复：先 `docker compose up -d` 创建卷，再把上面 tar 解回对应 volume。

> 若想直接沿用旧机已有数据库，把旧的 `backend/instance/prereview.db`
> 复制进 `prereview-db` 卷即可（注意旧库若缺哈希链字段，先跑
> `backend/migrate_add_hashchain.py` 迁移）。

## 四、端口 / 域名

- 改对外端口：编辑 `docker-compose.yml` 中 frontend 的 `ports`（如 `80:80`）。
- 上 HTTPS：建议在前面再加一层 nginx / Caddy 反代到 `8080`，或在 frontend 容器
  挂载证书并改 `nginx.conf`。
