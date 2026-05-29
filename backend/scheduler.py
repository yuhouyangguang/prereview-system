"""后台定时任务：审批时限提醒 + 预审有效期提醒 + 企业微信通知。

与 app.py 的关系：由 app.py 调用 init_scheduler(app) 启动，
内部直接导入 models，不反向导入 app，避免循环引用。
"""
import datetime
import logging
import os

import requests as _req
from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger(__name__)
_scheduler = None


def _working_days_since(dt: datetime.datetime) -> int:
    now = datetime.datetime.utcnow()
    if now <= dt:
        return 0
    days, cur, end = 0, dt.date(), now.date()
    while cur < end:
        if cur.weekday() < 5:
            days += 1
        cur += datetime.timedelta(days=1)
    return days


def send_wechat(text: str):
    url = os.environ.get('WECHAT_WEBHOOK_URL', '').strip()
    if not url:
        return
    try:
        _req.post(url, json={'msgtype': 'text', 'text': {'content': text}}, timeout=5)
    except Exception as e:
        log.warning('企业微信推送失败: %s', e)


def _notify(db, Notification, user_id, project_id, title, message):
    db.session.add(Notification(user_id=user_id, project_id=project_id,
                                title=title, message=message))


def check_deadlines(app):
    """每小时执行：① 审批 ≥3 工作日超时提醒；② 预审有效期 ≤7 天提醒。"""
    from models import db, Project, PreReviewResult, Notification
    with app.app_context():
        try:
            today_start = datetime.datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0)

            # ── ① 审批超时 ─────────────────────────────────────
            pending = Project.query.filter(
                Project.status.in_(['待人工审批', '待行长终审'])
            ).all()
            for p in pending:
                elapsed = _working_days_since(p.updated_at)
                if elapsed < 3 or p.current_approver_id is None:
                    continue
                already = Notification.query.filter(
                    Notification.project_id == p.id,
                    Notification.user_id == p.current_approver_id,
                    Notification.title == '审批超时提醒',
                    Notification.created_at >= today_start,
                ).first()
                if already:
                    continue
                msg = (f'{p.client_name}（{p.project_no}）已在「{p.status}」'
                       f'状态超过 {elapsed} 个工作日，请及时处理')
                _notify(db, Notification, p.current_approver_id, p.id, '审批超时提醒', msg)
                send_wechat(f'【审批超时提醒】{msg}')
            db.session.commit()

            # ── ② 预审有效期 ───────────────────────────────────
            warn_threshold = datetime.datetime.utcnow() + datetime.timedelta(days=7)
            expiring = PreReviewResult.query.filter(
                PreReviewResult.valid_until != None,
                PreReviewResult.valid_until <= warn_threshold,
                PreReviewResult.valid_until >= datetime.datetime.utcnow(),
            ).all()
            for pr in expiring:
                p = pr.project
                if not p or p.status in ['已终审', 'draft', '红灯']:
                    continue
                already = Notification.query.filter(
                    Notification.project_id == p.id,
                    Notification.user_id == p.creator_id,
                    Notification.title == '预审有效期提醒',
                    Notification.created_at >= today_start,
                ).first()
                if already:
                    continue
                days_left = max(0, (pr.valid_until - datetime.datetime.utcnow()).days)
                msg = (f'{p.client_name}（{p.project_no}）预审结果将在 {days_left} 天后到期，'
                       '请尽快推进审批流程，逾期须重新申请预审')
                _notify(db, Notification, p.creator_id, p.id, '预审有效期提醒', msg)
                send_wechat(f'【预审到期提醒】{msg}')
            db.session.commit()
        except Exception as e:
            log.error('定时任务执行异常: %s', e)
            db.session.rollback()


def init_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
    _scheduler.add_job(
        check_deadlines, 'interval', hours=1, args=[app],
        id='deadline_check', replace_existing=True,
        # 启动后 1 分钟先跑一次，之后每小时
        next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=1),
    )
    _scheduler.start()
    import atexit
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    log.info('APScheduler 定时任务已启动（审批超时 + 预审有效期提醒，间隔 1h）')
