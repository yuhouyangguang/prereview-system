"""一次性迁移：将旧版开发库升级到含哈希链审计、签字哈希与版本快照的新模型。

幂等：可重复执行。对已有库执行 ADD COLUMN / CREATE TABLE（缺失才加），
并按 app.log_action / leader_approve 相同的算法回填历史记录的哈希，使审计哈希链可验证。

用法：python3 migrate_add_hashchain.py
"""
import hashlib

from app import app, db
from models import AuditLog, Signature
from sqlalchemy import text, inspect


def _columns(insp, table):
    return {c['name'] for c in insp.get_columns(table)}


def migrate():
    with app.app_context():
        insp = inspect(db.engine)

        # 1) 缺失的表（project_versions 等）由 create_all 补齐，不影响既有表
        db.create_all()

        # 2) 既有表补列（SQLite 支持 ADD COLUMN）
        alters = []
        sig_cols = _columns(insp, 'signatures')
        if 'signed_hash' not in sig_cols:
            alters.append('ALTER TABLE signatures ADD COLUMN signed_hash VARCHAR(64)')
        audit_cols = _columns(insp, 'audit_logs')
        if 'prev_hash' not in audit_cols:
            alters.append('ALTER TABLE audit_logs ADD COLUMN prev_hash VARCHAR(64)')
        if 'entry_hash' not in audit_cols:
            alters.append('ALTER TABLE audit_logs ADD COLUMN entry_hash VARCHAR(64)')
        for stmt in alters:
            db.session.execute(text(stmt))
            print(f'  + {stmt}')
        db.session.commit()

        # 3) 回填审计哈希链（按 id 顺序，与 log_action 算法一致；ts 用 created_at）
        backfilled = 0
        prev_hash = '0' * 64
        for log in AuditLog.query.order_by(AuditLog.id.asc()).all():
            ts = log.created_at.isoformat() if log.created_at else ''
            details_json = log.details or '{}'
            payload = f'{prev_hash}|{log.user_id}|{log.project_id}|{log.action}|{details_json}|{ts}'
            entry_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            if log.entry_hash != entry_hash or log.prev_hash != prev_hash:
                log.prev_hash = prev_hash
                log.entry_hash = entry_hash
                backfilled += 1
            prev_hash = entry_hash

        # 4) 回填签字哈希（与 leader_approve 算法一致；signed_at 用 created_at）
        sig_filled = 0
        for s in Signature.query.all():
            if s.signed_hash:
                continue
            signed_at = s.created_at.isoformat() if s.created_at else ''
            payload = f'{s.project_id}|{s.signer_id}|{s.signature_level}|{s.certificate_no}|{s.signature_data or ""}|{signed_at}'
            s.signed_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            sig_filled += 1

        db.session.commit()
        print(f'审计哈希回填 {backfilled} 条，签字哈希回填 {sig_filled} 条')
        print('迁移完成 ✅')


if __name__ == '__main__':
    migrate()
