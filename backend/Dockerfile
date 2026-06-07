# ── 后端镜像：Flask + gunicorn ──────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖以利用缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端源码（.dockerignore 已排除 instance/keystores/__pycache__）
COPY . .

# 持久化目录：SQLite 数据库 与 RSA 私钥库（compose 挂载卷）
RUN mkdir -p instance keystores && chmod 700 keystores

EXPOSE 5000

# 单 worker：APScheduler 定时任务 + SQLite 要求单实例；
# gthread + 多线程支撑 SSE 长连接；timeout 0 不中断 SSE。
CMD ["gunicorn", "--workers", "1", "--worker-class", "gthread", \
     "--threads", "16", "--timeout", "0", \
     "--bind", "0.0.0.0:5000", "--access-logfile", "-", "wsgi:app"]
