"""Gunicorn 生产入口。

直接运行 `python app.py` 时初始化逻辑在 __main__ 块里，
gunicorn 加载模块不会执行该块，因此这里复刻初始化：
建表 / 补schema / 种子数据 / 启动定时任务，再暴露 app 供 gunicorn 使用。

注意：定时任务（APScheduler）与 SQLite 要求单 worker 运行，
        部署时务必使用 `gunicorn -w 1`（见 Dockerfile）。
"""
from app import app, ensure_schema, seed_data
from models import db
from scheduler import init_scheduler

with app.app_context():
    db.create_all()
    ensure_schema()
    seed_data()

init_scheduler(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
