import json as _json

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # R01-R07
    branch_level = db.Column(db.String(10))  # 支行/分行/总行
    branch_id = db.Column(db.String(50))
    branch_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    project_no = db.Column(db.String(50), unique=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Client info
    client_name = db.Column(db.String(100))
    client_industry = db.Column(db.String(50))
    client_credit_rating = db.Column(db.String(20))
    client_description = db.Column(db.Text)

    # Loan info
    loan_amount = db.Column(db.Float)  # 万元
    loan_purpose = db.Column(db.String(300))
    loan_type = db.Column(db.String(50))
    loan_term = db.Column(db.Integer)  # months
    guarantee_type = db.Column(db.String(50))

    # Pricing
    interest_rate = db.Column(db.Float)
    deposit_return = db.Column(db.Float)
    fee_rate = db.Column(db.Float)
    competitor_rate = db.Column(db.Float)
    competitor_bank = db.Column(db.String(100))

    # Status machine: S01-S14
    status = db.Column(db.String(20), default='draft')

    # Approval routing
    current_approver_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    current_approval_level = db.Column(db.String(10))

    version = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_projects')
    current_approver = db.relationship('User', foreign_keys=[current_approver_id])
    pre_review = db.relationship('PreReviewResult', backref='project', uselist=False)
    ai_approval = db.relationship('AIApprovalResult', backref='project', uselist=False)
    materials = db.relationship('Material', backref='project', lazy=True)
    approval_records = db.relationship('ApprovalRecord', backref='project', lazy=True, order_by='ApprovalRecord.created_at')
    notifications = db.relationship('Notification', backref='project', lazy=True)

class PreReviewResult(db.Model):
    __tablename__ = 'pre_review_results'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), unique=True)
    policy_compliance = db.Column(db.String(20))  # 符合/基本符合/不符合/需调整
    policy_notes = db.Column(db.Text)
    benefit_assessment = db.Column(db.String(10))  # 高/中/低
    benefit_notes = db.Column(db.Text)
    traffic_light = db.Column(db.String(10))  # 绿灯/黄灯/红灯
    recommendations = db.Column(db.Text)
    eva_result = db.Column(db.Float)
    rwa_result = db.Column(db.Float)
    raroc_result = db.Column(db.Float)
    valid_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    material_name = db.Column(db.String(100))
    material_type = db.Column(db.String(20))  # 必需/条件必需/补充参考
    filename = db.Column(db.String(255))
    verification_status = db.Column(db.String(10), default='pending')  # pending/red/yellow/green
    verification_notes = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AIApprovalResult(db.Model):
    __tablename__ = 'ai_approval_results'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), unique=True)
    result = db.Column(db.String(20))  # 通过/有条件通过/不通过
    suggested_level = db.Column(db.String(10))  # 支行/分行/总行
    policy_opinion = db.Column(db.Text)
    risk_opinion = db.Column(db.Text)
    pricing_opinion = db.Column(db.Text)
    material_opinion = db.Column(db.Text)
    modification_suggestions = db.Column(db.Text)  # JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ApprovalRecord(db.Model):
    __tablename__ = 'approval_records'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(30))
    opinion = db.Column(db.Text)
    from_level = db.Column(db.String(10))
    to_level = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approver = db.relationship('User', foreign_keys=[approver_id])

class BranchParams(db.Model):
    __tablename__ = 'branch_params'
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.String(50), nullable=False)
    business_type = db.Column(db.String(50), default='通用')
    capital_cost_rate = db.Column(db.Float, default=10.5)
    operating_cost_rate = db.Column(db.Float, default=1.5)
    risk_weight_coeff = db.Column(db.Float, default=1.0)
    deposit_ftp_rate = db.Column(db.Float, default=1.5)
    loan_ftp_rate = db.Column(db.Float, default=3.0)
    tax_rate = db.Column(db.Float, default=25.0)
    expected_loss_rate = db.Column(db.Float, default=0.5)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by_user = db.relationship('User', foreign_keys=[updated_by])

class ParamsChangeLog(db.Model):
    __tablename__ = 'params_change_logs'
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.String(50))
    business_type = db.Column(db.String(50))
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    old_values = db.Column(db.Text)
    new_values = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    changed_by_user = db.relationship('User', foreign_keys=[changed_by])

class ProjectVersion(db.Model):
    """已终审项目修改重提前的版本快照，用于 FR-08 的修改历史与前后差异对比。"""
    __tablename__ = 'project_versions'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    version = db.Column(db.Integer)
    snapshot = db.Column(db.Text)            # 项目字段 + 材料 + AI/人工审批 + 签字状态 的 JSON 快照
    changed_fields = db.Column(db.Text)      # 与上一版本的字段差异 JSON
    note = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user = db.relationship('User', foreign_keys=[created_by])


class UserKeyPair(db.Model):
    """用户 RSA-2048 公钥记录，配合 keystores/ 目录下的私钥文件实现电子签章验真。"""
    __tablename__ = 'user_key_pairs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    public_key_pem = db.Column(db.Text, nullable=False)
    algorithm = db.Column(db.String(20), default='RSA-2048')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', foreign_keys=[user_id])


class Signature(db.Model):
    __tablename__ = 'signatures'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    signer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    signature_data = db.Column(db.Text)
    signature_level = db.Column(db.String(10))
    certificate_no = db.Column(db.String(50), unique=True)
    # SHA-256 哈希链（不可篡改性证明）
    signed_hash = db.Column(db.String(64))
    # RSA-SHA256 数字签名（可独立验真，不依赖数据库完整性）
    rsa_signature = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    signer = db.relationship('User', foreign_keys=[signer_id])

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', foreign_keys=[user_id])

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    # 哈希链：entry_hash = sha256(prev_hash + 本条内容)，任何历史记录被篡改都会断链
    prev_hash = db.Column(db.String(64))
    entry_hash = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', foreign_keys=[user_id])


class KnowledgeDoc(db.Model):
    """FR-14：审批人员上传的信贷政策知识库文档。"""
    __tablename__ = 'knowledge_docs'
    id = db.Column(db.Integer, primary_key=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    branch_level = db.Column(db.String(20), nullable=False)   # 支行/分行/总行
    branch_id = db.Column(db.String(50), nullable=False)
    branch_name = db.Column(db.String(100))
    original_filename = db.Column(db.String(200), nullable=False)
    stored_filename = db.Column(db.String(200), nullable=False)
    doc_type = db.Column(db.String(10))   # pdf / word / txt
    ai_summary = db.Column(db.Text)
    key_policies = db.Column(db.Text)     # JSON 数组：核心政策条款列表
    applicable_scope = db.Column(db.Text)
    prohibitions = db.Column(db.Text)
    exceptions = db.Column(db.Text)
    status = db.Column(db.String(20), default='processing')   # processing/active/failed
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploader = db.relationship('User', foreign_keys=[uploader_id])

    def to_dict(self):
        return {
            'id': self.id,
            'uploader_id': self.uploader_id,
            'uploader_name': self.uploader.name if self.uploader else '',
            'branch_level': self.branch_level,
            'branch_id': self.branch_id,
            'branch_name': self.branch_name,
            'original_filename': self.original_filename,
            'doc_type': self.doc_type,
            'ai_summary': self.ai_summary,
            'key_policies': _json.loads(self.key_policies) if self.key_policies else [],
            'applicable_scope': self.applicable_scope,
            'prohibitions': self.prohibitions,
            'exceptions': self.exceptions,
            'status': self.status,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
