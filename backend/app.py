import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta

from flask import Flask, Response, request, jsonify, stream_with_context
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    db, User, Project, PreReviewResult, Material, AIApprovalResult,
    ApprovalRecord, BranchParams, ParamsChangeLog, Signature, Notification,
    AuditLog, ProjectVersion, UserKeyPair,
)
from ai_engine import (
    ai_pre_review, generate_material_checklist, ai_auto_approval, verify_materials,
    determine_approval_level, calculate_eva, calculate_rwa, calculate_raroc,
)

try:
    from crypto_sign import get_or_create_keypair, sign_payload, verify_payload
    _RSA_ENABLED = True
except ImportError:
    _RSA_ENABLED = False

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URI', 'sqlite:///prereview.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# 生产环境必须通过环境变量提供密钥，避免硬编码泄露
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
if not app.config['JWT_SECRET_KEY']:
    if os.environ.get('FLASK_ENV') == 'production':
        raise RuntimeError('生产环境必须设置 JWT_SECRET_KEY 环境变量')
    app.config['JWT_SECRET_KEY'] = os.urandom(32).hex()
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
# 允许 JWT 从 query string 读取（供 EventSource SSE 使用）
app.config['JWT_TOKEN_LOCATION'] = ['headers', 'query_string']
app.config['JWT_QUERY_STRING_NAME'] = 'token'

db.init_app(app)
JWTManager(app)
CORS(app, origins=['http://localhost:3000', 'http://localhost:5173'])


def log_action(user_id, project_id, action, details=None):
    details_json = json.dumps(details or {}, ensure_ascii=False)
    # 哈希链：链接到全局最后一条日志，形成防篡改链条
    last = AuditLog.query.order_by(AuditLog.id.desc()).first()
    prev_hash = last.entry_hash if last and last.entry_hash else '0' * 64
    ts = datetime.utcnow().isoformat()
    payload = f'{prev_hash}|{user_id}|{project_id}|{action}|{details_json}|{ts}'
    entry_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    log = AuditLog(user_id=user_id, project_id=project_id, action=action,
                   details=details_json, prev_hash=prev_hash, entry_hash=entry_hash)
    db.session.add(log)


def can_access_project(user, p):
    """对象级访问授权（FR-12）。

    - 客户经理(R01)：仅本人创建的项目；
    - 审批员(R03/R04/R06)：仅其所属层级、且当前流转到该层级的项目；
    - 行长(R02/R05/R07)：仅其所属层级、待终审或已处理的项目。
    """
    if user.role == 'R01':
        return p.creator_id == user.id

    approver_level = {'R03': '支行', 'R04': '分行', 'R06': '总行'}
    leader_level = {'R02': '支行', 'R05': '分行', 'R07': '总行'}

    if user.role in approver_level:
        my_level = approver_level[user.role]
        # 当前正流转到本层级，或本人正/曾处理该项目
        if p.current_approval_level == my_level:
            return True
        if p.current_approver_id == user.id:
            return True
        return ApprovalRecord.query.filter_by(project_id=p.id, approver_id=user.id).first() is not None

    if user.role in leader_level:
        my_level = leader_level[user.role]
        if p.current_approval_level == my_level and p.status in ['待行长终审', '已终审', '行长退回']:
            return True
        # 本人已签字/处理过的项目可查看
        if Signature.query.filter_by(project_id=p.id, signer_id=user.id).first():
            return True
        return ApprovalRecord.query.filter_by(project_id=p.id, approver_id=user.id).first() is not None

    return False


def notify(user_id, project_id, title, message):
    n = Notification(user_id=user_id, project_id=project_id, title=title, message=message)
    db.session.add(n)


def get_branch_params(branch_id, business_type='通用'):
    params = BranchParams.query.filter_by(branch_id=branch_id, business_type=business_type).first()
    if not params:
        params = BranchParams.query.filter_by(branch_id=branch_id, business_type='通用').first()
    return params


def project_to_dict(p, include_details=False):
    creator = p.creator
    d = {
        'id': p.id,
        'project_no': p.project_no,
        'creator_id': p.creator_id,
        'current_approver_id': p.current_approver_id,
        'client_name': p.client_name,
        'client_industry': p.client_industry,
        'loan_amount': p.loan_amount,
        'loan_type': p.loan_type,
        'loan_term': p.loan_term,
        'guarantee_type': p.guarantee_type,
        'interest_rate': p.interest_rate,
        'status': p.status,
        'version': p.version,
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'updated_at': p.updated_at.isoformat() if p.updated_at else None,
        'creator_name': creator.name if creator else '',
        'creator_branch': creator.branch_name if creator else '',
        'current_approval_level': p.current_approval_level,
    }
    if p.current_approver:
        d['current_approver_name'] = p.current_approver.name
    if include_details:
        d.update({
            'client_credit_rating': p.client_credit_rating,
            'client_description': p.client_description,
            'loan_purpose': p.loan_purpose,
            'fee_rate': p.fee_rate,
            'deposit_return': p.deposit_return,
            'competitor_rate': p.competitor_rate,
            'competitor_bank': p.competitor_bank,
        })
        if p.pre_review:
            pr = p.pre_review
            d['pre_review'] = {
                'policy_compliance': pr.policy_compliance,
                'policy_notes': pr.policy_notes,
                'benefit_assessment': pr.benefit_assessment,
                'benefit_notes': pr.benefit_notes,
                'traffic_light': pr.traffic_light,
                'recommendations': pr.recommendations,
                'eva_result': pr.eva_result,
                'rwa_result': pr.rwa_result,
                'raroc_result': pr.raroc_result,
                'valid_until': pr.valid_until.isoformat() if pr.valid_until else None,
                'created_at': pr.created_at.isoformat() if pr.created_at else None,
            }
        if p.ai_approval:
            ai = p.ai_approval
            d['ai_approval'] = {
                'result': ai.result,
                'suggested_level': ai.suggested_level,
                'policy_opinion': ai.policy_opinion,
                'risk_opinion': ai.risk_opinion,
                'pricing_opinion': ai.pricing_opinion,
                'material_opinion': ai.material_opinion,
                'modification_suggestions': json.loads(ai.modification_suggestions) if ai.modification_suggestions else [],
                'created_at': ai.created_at.isoformat() if ai.created_at else None,
            }
        d['materials'] = [{
            'id': m.id, 'material_name': m.material_name, 'material_type': m.material_type,
            'filename': m.filename, 'verification_status': m.verification_status,
            'verification_notes': m.verification_notes,
            'uploaded_at': m.uploaded_at.isoformat() if m.uploaded_at else None,
        } for m in p.materials]
        d['approval_records'] = [{
            'id': r.id, 'action': r.action, 'opinion': r.opinion,
            'from_level': r.from_level, 'to_level': r.to_level,
            'approver_name': r.approver.name if r.approver else '',
            'approver_role': r.approver.role if r.approver else '',
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in p.approval_records]
        sigs = Signature.query.filter_by(project_id=p.id).all()
        d['signatures'] = [{
            'signer_name': s.signer.name if s.signer else '',
            'signature_level': s.signature_level,
            'certificate_no': s.certificate_no,
            'signed_hash': s.signed_hash,
            'created_at': s.created_at.isoformat() if s.created_at else None,
        } for s in sigs]
        versions = ProjectVersion.query.filter_by(project_id=p.id)\
            .order_by(ProjectVersion.version.desc()).all()
        d['versions'] = [{
            'version': v.version,
            'note': v.note,
            'changed_fields': json.loads(v.changed_fields) if v.changed_fields else {},
            'created_by_name': v.created_by_user.name if v.created_by_user else '',
            'created_at': v.created_at.isoformat() if v.created_at else None,
        } for v in versions]
    return d


# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data.get('username')).first()
    if not user or not check_password_hash(user.password_hash, data.get('password', '')):
        return jsonify({'error': '用户名或密码错误'}), 401
    token = create_access_token(identity=str(user.id))
    return jsonify({
        'token': token,
        'user': {
            'id': user.id, 'name': user.name, 'role': user.role,
            'branch_level': user.branch_level, 'branch_id': user.branch_id,
            'branch_name': user.branch_name, 'username': user.username,
        }
    })


@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def me():
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    unread = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify({
        'id': user.id, 'name': user.name, 'role': user.role,
        'branch_level': user.branch_level, 'branch_id': user.branch_id,
        'branch_name': user.branch_name, 'username': user.username,
        'unread_count': unread,
    })


# ── PROJECTS ─────────────────────────────────────────────────────────────────

@app.route('/api/projects', methods=['GET'])
@jwt_required()
def list_projects():
    user = User.query.get(int(get_jwt_identity()))
    q = Project.query
    if user.role == 'R01':
        q = q.filter_by(creator_id=user.id)
    elif user.role in ['R03']:  # 支行审批员
        q = q.filter(Project.status.in_(['待人工审批', '待补充材料', '人工审批退回']),
                     Project.current_approval_level == '支行')
    elif user.role in ['R02']:  # 支行行长
        q = q.filter(Project.status == '待行长终审',
                     Project.current_approval_level == '支行')
    elif user.role in ['R04']:  # 分行审批员
        q = q.filter(Project.status.in_(['待人工审批', '待补充材料', '人工审批退回']),
                     Project.current_approval_level == '分行')
    elif user.role in ['R05']:  # 分行行长
        q = q.filter(Project.status == '待行长终审',
                     Project.current_approval_level == '分行')
    elif user.role in ['R06']:  # 总行审批员
        q = q.filter(Project.status.in_(['待人工审批', '待补充材料', '人工审批退回']),
                     Project.current_approval_level == '总行')
    elif user.role in ['R07']:  # 总行行长
        q = q.filter(Project.status == '待行长终审',
                     Project.current_approval_level == '总行')

    status_filter = request.args.get('status')
    if status_filter:
        q = q.filter_by(status=status_filter)

    projects = q.order_by(Project.updated_at.desc()).all()
    return jsonify([project_to_dict(p) for p in projects])


@app.route('/api/projects', methods=['POST'])
@jwt_required()
def create_project():
    user = User.query.get(int(get_jwt_identity()))
    if user.role != 'R01':
        return jsonify({'error': '仅客户经理可创建项目'}), 403
    data = request.get_json()
    no = f'PRJ-{datetime.utcnow().strftime("%Y%m%d")}-{uuid.uuid4().hex[:6].upper()}'
    p = Project(
        project_no=no, creator_id=user.id, status='draft',
        client_name=data.get('client_name'), client_industry=data.get('client_industry'),
        client_credit_rating=data.get('client_credit_rating'),
        client_description=data.get('client_description'),
        loan_amount=data.get('loan_amount'), loan_purpose=data.get('loan_purpose'),
        loan_type=data.get('loan_type'), loan_term=data.get('loan_term'),
        guarantee_type=data.get('guarantee_type'), interest_rate=data.get('interest_rate'),
        fee_rate=data.get('fee_rate'), deposit_return=data.get('deposit_return'),
        competitor_rate=data.get('competitor_rate'), competitor_bank=data.get('competitor_bank'),
        updated_at=datetime.utcnow(),
    )
    db.session.add(p)
    db.session.flush()
    log_action(user.id, p.id, '创建项目')
    db.session.commit()
    return jsonify(project_to_dict(p)), 201


@app.route('/api/projects/<int:pid>', methods=['GET'])
@jwt_required()
def get_project(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if not can_access_project(user, p):
        return jsonify({'error': '无权访问此项目'}), 403
    return jsonify(project_to_dict(p, include_details=True))


@app.route('/api/projects/<int:pid>', methods=['PUT'])
@jwt_required()
def update_project(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权修改此项目'}), 403
    if p.status not in ['draft', 'AI已退回', '人工审批退回', '行长退回', '修改中', '红灯']:
        return jsonify({'error': f'当前状态({p.status})不允许修改'}), 400
    data = request.get_json()
    fields = ['client_name', 'client_industry', 'client_credit_rating', 'client_description',
              'loan_amount', 'loan_purpose', 'loan_type', 'loan_term', 'guarantee_type',
              'interest_rate', 'fee_rate', 'deposit_return', 'competitor_rate', 'competitor_bank']
    for f in fields:
        if f in data:
            setattr(p, f, data[f])
    p.updated_at = datetime.utcnow()
    log_action(user.id, p.id, '修改项目信息')
    db.session.commit()
    return jsonify(project_to_dict(p, include_details=True))


@app.route('/api/projects/<int:pid>', methods=['DELETE'])
@jwt_required()
def delete_project(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权删除此项目'}), 403
    if p.status not in ['draft', '红灯']:
        return jsonify({'error': '只能删除草稿或红灯项目'}), 400
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': '删除成功'})


# ── PRE-REVIEW ────────────────────────────────────────────────────────────────

@app.route('/api/projects/<int:pid>/submit-prereview', methods=['POST'])
@jwt_required()
def submit_prereview(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权操作'}), 403
    if p.status not in ['draft', '红灯']:
        return jsonify({'error': f'当前状态({p.status})不可提交预审'}), 400

    p.status = '预审中'
    p.updated_at = datetime.utcnow()
    db.session.flush()

    # Execute AI pre-review immediately
    params = get_branch_params(user.branch_id, p.loan_type or '通用')
    result = ai_pre_review(p, params)

    if p.pre_review:
        db.session.delete(p.pre_review)
        db.session.flush()

    pr = PreReviewResult(
        project_id=p.id,
        policy_compliance=result['policy_compliance'],
        policy_notes=result['policy_notes'],
        benefit_assessment=result['benefit_assessment'],
        benefit_notes=result['benefit_notes'],
        traffic_light=result['traffic_light'],
        recommendations=result['recommendations'],
        eva_result=result['eva_result'],
        rwa_result=result['rwa_result'],
        raroc_result=result['raroc_result'],
        valid_until=result['valid_until'],
    )
    db.session.add(pr)

    tl = result['traffic_light']
    status_map = {'绿灯': '绿灯', '黄灯': '黄灯', '红灯': '红灯'}
    p.status = status_map[tl]
    p.updated_at = datetime.utcnow()

    log_action(user.id, p.id, 'AI预审', {'traffic_light': tl})
    notify(user.id, p.id, f'预审结果：{tl}', result['recommendations'][:100])
    db.session.commit()
    return jsonify(project_to_dict(p, include_details=True))


# ── MATERIALS ─────────────────────────────────────────────────────────────────

@app.route('/api/projects/<int:pid>/material-checklist', methods=['GET'])
@jwt_required()
def get_material_checklist(pid):
    p = Project.query.get_or_404(pid)
    checklist = generate_material_checklist(p)
    existing = {m.material_name: m for m in p.materials}
    result = []
    for item in checklist:
        existing_mat = existing.get(item['name'])
        result.append({
            'id': existing_mat.id if existing_mat else None,
            'material_name': item['name'],
            'material_type': item['type'],
            'filename': existing_mat.filename if existing_mat else None,
            'verification_status': existing_mat.verification_status if existing_mat else 'pending',
            'verification_notes': existing_mat.verification_notes if existing_mat else None,
        })
    return jsonify(result)


@app.route('/api/projects/<int:pid>/upload-material', methods=['POST'])
@jwt_required()
def upload_material(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权操作'}), 403
    data = request.get_json()
    mat_name = data.get('material_name')
    filename = data.get('filename')
    mat_type = data.get('material_type', '必需')

    if p.status not in ['绿灯', '黄灯', '材料提交中', 'AI已退回', '待补充材料']:
        return jsonify({'error': f'当前状态({p.status})不允许上传材料'}), 400

    existing = Material.query.filter_by(project_id=p.id, material_name=mat_name).first()
    if existing:
        existing.filename = filename
        existing.uploaded_at = datetime.utcnow()
        existing.verification_status = 'pending'
        mat = existing
    else:
        mat = Material(
            project_id=p.id, material_name=mat_name, material_type=mat_type,
            filename=filename, uploaded_at=datetime.utcnow()
        )
        db.session.add(mat)

    if p.status in ['绿灯', '黄灯']:
        p.status = '材料提交中'
    p.updated_at = datetime.utcnow()
    log_action(user.id, p.id, '上传材料', {'material': mat_name})
    db.session.commit()
    return jsonify({'id': mat.id, 'material_name': mat.material_name, 'filename': mat.filename})


@app.route('/api/projects/<int:pid>/ai-verify-materials', methods=['POST'])
@jwt_required()
def ai_verify_materials(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权操作'}), 403

    checklist = generate_material_checklist(p)
    mat_map = {m.material_name: m for m in p.materials}

    # 确保完整清单落库（缺失项以 pending 记录，便于完整性核验）
    for item in checklist:
        mat = mat_map.get(item['name'])
        if not mat:
            mat = Material(
                project_id=p.id, material_name=item['name'],
                material_type=item['type']
            )
            db.session.add(mat)
            mat_map[item['name']] = mat
        elif not mat.filename:
            mat.verification_status = 'pending'

    db.session.flush()

    # 对已上传材料调用 zai 进行三性核验（不可用时回退规则引擎）
    verdicts = verify_materials(p, list(mat_map.values()))
    for mat in mat_map.values():
        if mat.filename:
            v = verdicts.get(mat.material_name)
            if v:
                mat.verification_status = v['status']
                mat.verification_notes = v['notes']

    log_action(user.id, p.id, 'AI材料核验')
    db.session.commit()
    return jsonify({'message': 'AI核验完成', 'materials': [{
        'id': m.id, 'material_name': m.material_name, 'material_type': m.material_type,
        'filename': m.filename, 'verification_status': m.verification_status,
        'verification_notes': m.verification_notes,
    } for m in p.materials]})


# ── AI APPROVAL ───────────────────────────────────────────────────────────────

@app.route('/api/projects/<int:pid>/ai-approval', methods=['POST'])
@jwt_required()
def trigger_ai_approval(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权操作'}), 403
    if p.status not in ['材料提交中', 'AI已退回', '修改中']:
        return jsonify({'error': f'当前状态({p.status})不可提交AI审批'}), 400
    if not p.pre_review:
        return jsonify({'error': '请先完成预审'}), 400

    p.status = 'AI审批中'
    p.updated_at = datetime.utcnow()
    db.session.flush()

    # 服务端重新生成完整材料清单，不依赖前端流程顺序（FR-06/FR-07）
    checklist = generate_material_checklist(p)

    # 对已上传材料做服务端三性核验，刷新核验状态，供审批完整性判断使用
    verdicts = verify_materials(p, p.materials)
    for m in p.materials:
        v = verdicts.get(m.material_name)
        if v:
            m.verification_status = v['status']
            m.verification_notes = v['notes']
    db.session.flush()

    result = ai_auto_approval(p, p.pre_review, p.materials, checklist=checklist)

    if p.ai_approval:
        db.session.delete(p.ai_approval)
        db.session.flush()

    ai_res = AIApprovalResult(
        project_id=p.id,
        result=result['result'],
        suggested_level=result['suggested_level'],
        policy_opinion=result['policy_opinion'],
        risk_opinion=result['risk_opinion'],
        pricing_opinion=result['pricing_opinion'],
        material_opinion=result['material_opinion'],
        modification_suggestions=result['modification_suggestions'],
    )
    db.session.add(ai_res)

    if result['result'] == '不通过':
        p.status = 'AI已退回'
        notify(user.id, p.id, 'AI审批未通过', f'请查看修改建议并重新提交')
    else:
        p.status = '待人工审批'
        p.current_approval_level = result['suggested_level']
        # Route to approver
        level_role_map = {'支行': 'R03', '分行': 'R04', '总行': 'R06'}
        role = level_role_map[result['suggested_level']]
        approver = User.query.filter_by(role=role).first()
        if approver:
            p.current_approver_id = approver.id
            notify(approver.id, p.id, f'新项目待审批', f'{p.client_name} - {p.loan_type} {p.loan_amount}万元')
        notify(user.id, p.id, 'AI审批通过', f'项目已路由至{result["suggested_level"]}级审批员')

    p.updated_at = datetime.utcnow()
    log_action(user.id, p.id, 'AI审批', {'result': result['result']})
    db.session.commit()
    return jsonify(project_to_dict(p, include_details=True))


# ── HUMAN APPROVAL ────────────────────────────────────────────────────────────

@app.route('/api/projects/<int:pid>/approve', methods=['POST'])
@jwt_required()
def human_approve(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    data = request.get_json()
    action = data.get('action')  # 通过/补充材料/退回修改/上转/下转
    opinion = data.get('opinion', '')
    to_level = data.get('to_level')

    approver_roles = ['R03', 'R04', 'R06']
    if user.role not in approver_roles:
        return jsonify({'error': '无审批权限'}), 403

    level_role_map = {'支行': 'R03', '分行': 'R04', '总行': 'R06'}
    leader_role_map = {'支行': 'R02', '分行': 'R05', '总行': 'R07'}
    approver_level_map = {'R03': '支行', 'R04': '分行', 'R06': '总行'}

    # 状态机校验：必须处于待人工审批
    if p.status != '待人工审批':
        return jsonify({'error': f'当前状态({p.status})不可进行人工审批'}), 400
    # 必须是当前处理人
    if p.current_approver_id != user.id:
        return jsonify({'error': '该项目当前不在您的待办中，无权审批'}), 403
    # 角色层级必须匹配项目当前审批层级
    if approver_level_map.get(user.role) != p.current_approval_level:
        return jsonify({'error': '审批层级与您的权限不匹配'}), 403

    record = ApprovalRecord(
        project_id=p.id, approver_id=user.id, action=action,
        opinion=opinion, from_level=p.current_approval_level
    )

    if action == '通过':
        lv = p.current_approval_level
        p.status = '待行长终审'
        record.to_level = lv
        leader = User.query.filter_by(role=leader_role_map[lv]).first()
        if leader:
            p.current_approver_id = leader.id
            notify(leader.id, p.id, f'项目待终审', f'{p.client_name} 等待您的签字确认')
        creator = User.query.get(p.creator_id)
        if creator:
            notify(creator.id, p.id, '审批进展', f'您的项目已通过{lv}审批员审核，等待{lv}行长终审')
    elif action == '补充材料':
        p.status = '待补充材料'
        record.to_level = p.current_approval_level
        creator = User.query.get(p.creator_id)
        if creator:
            notify(creator.id, p.id, '需补充材料', opinion[:100] if opinion else '请补充相关材料')
    elif action == '退回修改':
        p.status = '人工审批退回'
        record.to_level = p.current_approval_level
        creator = User.query.get(p.creator_id)
        if creator:
            notify(creator.id, p.id, '项目被退回', opinion[:100] if opinion else '审批员要求修改项目信息')
    elif action in ['上转', '下转']:
        if not to_level or to_level not in level_role_map:
            return jsonify({'error': '请指定合法的流转目标层级'}), 400
        order = {'支行': 0, '分行': 1, '总行': 2}
        cur = order.get(p.current_approval_level, 0)
        tgt = order[to_level]
        if action == '上转' and tgt <= cur:
            return jsonify({'error': '上转目标层级必须高于当前层级'}), 400
        if action == '下转' and tgt >= cur:
            return jsonify({'error': '下转目标层级必须低于当前层级'}), 400
        if not opinion:
            return jsonify({'error': '流转必须填写流转原因'}), 400
        new_role = level_role_map[to_level]
        new_approver = User.query.filter_by(role=new_role).first()
        if not new_approver:
            return jsonify({'error': f'未找到{to_level}级审批员'}), 400
        record.to_level = to_level
        p.current_approval_level = to_level
        p.current_approver_id = new_approver.id
        notify(new_approver.id, p.id, f'项目{action}至您处', f'来自{user.name}的流转：{opinion[:80]}')
    else:
        return jsonify({'error': '无效操作'}), 400

    db.session.add(record)
    p.updated_at = datetime.utcnow()
    log_action(user.id, p.id, f'人工审批-{action}', {'opinion': opinion})
    db.session.commit()
    return jsonify(project_to_dict(p, include_details=True))


@app.route('/api/projects/<int:pid>/resubmit-after-return', methods=['POST'])
@jwt_required()
def resubmit_after_return(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权操作'}), 403
    if p.status not in ['人工审批退回', '待补充材料']:
        return jsonify({'error': f'当前状态({p.status})不支持此操作'}), 400
    # Return directly to the approver (no re-AI approval)
    p.status = '待人工审批'
    p.updated_at = datetime.utcnow()
    approver = p.current_approver
    if approver:
        notify(approver.id, p.id, '项目重新提交', f'{p.client_name} 客户经理已补充材料，请重新审核')
    log_action(user.id, p.id, '重新提交至审批员')
    db.session.commit()
    return jsonify(project_to_dict(p, include_details=True))


# ── LEADER SIGN ───────────────────────────────────────────────────────────────

@app.route('/api/projects/<int:pid>/leader-approve', methods=['POST'])
@jwt_required()
def leader_approve(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    data = request.get_json()
    action = data.get('action')  # 通过/不通过
    opinion = data.get('opinion', '')
    signature_data = data.get('signature_data', '')

    leader_roles = ['R02', 'R05', 'R07']
    leader_level_map = {'R02': '支行', 'R05': '分行', 'R07': '总行'}
    if user.role not in leader_roles:
        return jsonify({'error': '无行长权限'}), 403
    if p.status != '待行长终审':
        return jsonify({'error': f'当前状态({p.status})不支持行长审批'}), 400
    # 必须是当前流转到的行长本人
    if p.current_approver_id != user.id:
        return jsonify({'error': '该项目当前不在您的待终审列表中'}), 403
    # 行长层级必须与项目审批层级一致
    if leader_level_map.get(user.role) != p.current_approval_level:
        return jsonify({'error': '审批层级与您的权限不匹配'}), 403

    record = ApprovalRecord(
        project_id=p.id, approver_id=user.id,
        from_level=p.current_approval_level,
        to_level=p.current_approval_level,
    )

    if action == '通过':
        cert_no = f'CERT-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:8].upper()}'
        signed_at = datetime.utcnow().isoformat()
        sig_payload_str = f'{p.id}|{user.id}|{p.current_approval_level}|{cert_no}|{signature_data}|{signed_at}'
        signed_hash = hashlib.sha256(sig_payload_str.encode('utf-8')).hexdigest()

        # RSA-SHA256 数字签名：确保公钥落库，再签名
        rsa_sig = ''
        if _RSA_ENABLED:
            try:
                _, pub_pem = get_or_create_keypair(user.id)
                kp = UserKeyPair.query.filter_by(user_id=user.id).first()
                if not kp:
                    kp = UserKeyPair(user_id=user.id, public_key_pem=pub_pem)
                    db.session.add(kp)
                    db.session.flush()
                elif kp.public_key_pem != pub_pem:
                    kp.public_key_pem = pub_pem
                rsa_sig = sign_payload(user.id, sig_payload_str)
            except Exception as _e:
                app.logger.warning('RSA 签名失败（非致命）: %s', _e)

        sig = Signature(
            project_id=p.id, signer_id=user.id,
            signature_data=signature_data,
            signature_level=p.current_approval_level,
            certificate_no=cert_no,
            signed_hash=signed_hash,
            rsa_signature=rsa_sig or None,
        )
        db.session.add(sig)
        p.status = '已终审'
        record.action = f'{p.current_approval_level}行长签字通过'
        record.opinion = opinion
        creator = User.query.get(p.creator_id)
        if creator:
            notify(creator.id, p.id, f'{p.current_approval_level}行长审批完成',
                   f'恭喜！您的项目已通过{p.current_approval_level}行长审批并完成电子签字')
        log_action(user.id, p.id, '行长终审通过', {'cert_no': cert_no})
    else:
        p.status = '行长退回'
        record.action = '行长审批不通过'
        record.opinion = opinion
        creator = User.query.get(p.creator_id)
        if creator:
            notify(creator.id, p.id, '行长审批未通过', opinion[:100] if opinion else '行长退回，请修改后重新提交')
        log_action(user.id, p.id, '行长退回', {'opinion': opinion})

    db.session.add(record)
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(project_to_dict(p, include_details=True))


# ── MODIFY APPROVED PROJECT ───────────────────────────────────────────────────

SNAPSHOT_FIELDS = ['client_name', 'client_industry', 'client_credit_rating', 'client_description',
                   'loan_amount', 'loan_purpose', 'loan_type', 'loan_term', 'guarantee_type',
                   'interest_rate', 'fee_rate', 'deposit_return', 'competitor_rate', 'competitor_bank']


def build_project_snapshot(p):
    """构造项目完整快照：项目字段 + 材料 + AI审批 + 人工审批 + 签字状态。"""
    snap = {'fields': {f: getattr(p, f) for f in SNAPSHOT_FIELDS}, 'status': p.status}
    if p.pre_review:
        pr = p.pre_review
        snap['pre_review'] = {
            'policy_compliance': pr.policy_compliance, 'traffic_light': pr.traffic_light,
            'benefit_assessment': pr.benefit_assessment,
            'eva_result': pr.eva_result, 'rwa_result': pr.rwa_result, 'raroc_result': pr.raroc_result,
        }
    if p.ai_approval:
        snap['ai_approval'] = {'result': p.ai_approval.result, 'suggested_level': p.ai_approval.suggested_level}
    snap['materials'] = [{'material_name': m.material_name, 'material_type': m.material_type,
                          'filename': m.filename, 'verification_status': m.verification_status}
                         for m in p.materials]
    snap['approval_records'] = [{'approver_id': r.approver_id, 'action': r.action,
                                 'opinion': r.opinion, 'created_at': r.created_at.isoformat() if r.created_at else None}
                                for r in p.approval_records]
    snap['signatures'] = [{'signer_id': s.signer_id, 'signature_level': s.signature_level,
                           'certificate_no': s.certificate_no, 'signed_hash': s.signed_hash}
                          for s in Signature.query.filter_by(project_id=p.id).all()]
    return snap


@app.route('/api/projects/<int:pid>/request-modification', methods=['POST'])
@jwt_required()
def request_modification(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if p.creator_id != user.id:
        return jsonify({'error': '无权操作'}), 403
    if p.status not in ['已终审', '行长退回']:
        return jsonify({'error': '只有已终审或行长退回的项目可发起修改'}), 400

    # 冻结当前版本快照，保留修改历史（FR-08）
    snapshot = build_project_snapshot(p)
    # 与上一次快照的字段差异
    prev = ProjectVersion.query.filter_by(project_id=p.id)\
        .order_by(ProjectVersion.version.desc()).first()
    changed = {}
    base_fields = prev and json.loads(prev.snapshot).get('fields', {}) or {}
    if prev:
        for f in SNAPSHOT_FIELDS:
            if base_fields.get(f) != snapshot['fields'].get(f):
                changed[f] = {'from': base_fields.get(f), 'to': snapshot['fields'].get(f)}
    pv = ProjectVersion(
        project_id=p.id, version=p.version, snapshot=json.dumps(snapshot, ensure_ascii=False),
        changed_fields=json.dumps(changed, ensure_ascii=False),
        note=f'v{p.version} 终审版本快照（发起修改重提前冻结）', created_by=user.id,
    )
    db.session.add(pv)

    # 原审批结果失效：清空当前审批人，进入修改中并递增版本
    p.status = '修改中'
    p.version += 1
    p.current_approver_id = None
    p.current_approval_level = None
    p.updated_at = datetime.utcnow()
    notify(user.id, p.id, '项目进入修改状态',
           f'原终审结果(v{p.version - 1})已失效，请修改后重新提交AI审批')
    log_action(user.id, p.id, '发起修改重提', {'new_version': p.version, 'frozen_version': p.version - 1})
    db.session.commit()
    return jsonify(project_to_dict(p, include_details=True))


# ── BRANCH PARAMS ─────────────────────────────────────────────────────────────

@app.route('/api/branch-params', methods=['GET'])
@jwt_required()
def get_params():
    user = User.query.get(int(get_jwt_identity()))
    params = BranchParams.query.filter_by(branch_id=user.branch_id).all()
    return jsonify([{
        'id': p.id, 'business_type': p.business_type,
        'capital_cost_rate': p.capital_cost_rate,
        'operating_cost_rate': p.operating_cost_rate,
        'risk_weight_coeff': p.risk_weight_coeff,
        'deposit_ftp_rate': p.deposit_ftp_rate,
        'loan_ftp_rate': p.loan_ftp_rate,
        'tax_rate': p.tax_rate,
        'expected_loss_rate': p.expected_loss_rate,
        'updated_at': p.updated_at.isoformat() if p.updated_at else None,
        'updated_by_name': p.updated_by_user.name if p.updated_by_user else '',
    } for p in params])


@app.route('/api/branch-params', methods=['POST'])
@jwt_required()
def save_params():
    user = User.query.get(int(get_jwt_identity()))
    if user.role != 'R02':
        return jsonify({'error': '仅支行行长可管理参数'}), 403
    data = request.get_json()
    business_type = data.get('business_type', '通用')
    existing = BranchParams.query.filter_by(
        branch_id=user.branch_id, business_type=business_type).first()

    fields = ['capital_cost_rate', 'operating_cost_rate', 'risk_weight_coeff',
              'deposit_ftp_rate', 'loan_ftp_rate', 'tax_rate', 'expected_loss_rate']
    old_values = {}
    if existing:
        old_values = {f: getattr(existing, f) for f in fields}
        for f in fields:
            if f in data:
                setattr(existing, f, data[f])
        existing.updated_by = user.id
        existing.updated_at = datetime.utcnow()
        params = existing
    else:
        params = BranchParams(branch_id=user.branch_id, business_type=business_type,
                               updated_by=user.id, updated_at=datetime.utcnow())
        for f in fields:
            if f in data:
                setattr(params, f, data[f])
        db.session.add(params)

    new_values = {f: getattr(params, f) for f in fields}
    log = ParamsChangeLog(branch_id=user.branch_id, business_type=business_type,
                          changed_by=user.id,
                          old_values=json.dumps(old_values),
                          new_values=json.dumps(new_values))
    db.session.add(log)
    db.session.flush()

    # FR-05 ③：参数变更后，本支行所有未归档项目的测算结果实时更新为最新参数
    recomputed = recompute_branch_projects(user.branch_id)

    db.session.commit()
    return jsonify({'message': '参数保存成功', 'recomputed_projects': recomputed})


def recompute_branch_projects(branch_id):
    """对指定支行下、未归档（非已终审）且已有预审结果的项目，按最新参数重算 EVA/RWA/RAROC。

    已终审项目作为审批时点快照保留，不再重算。
    """
    creator_ids = [u.id for u in User.query.filter_by(branch_id=branch_id).all()]
    if not creator_ids:
        return 0
    projects = Project.query.filter(
        Project.creator_id.in_(creator_ids),
        Project.status != '已终审',
    ).all()
    count = 0
    for proj in projects:
        if not proj.pre_review:
            continue
        params = get_branch_params(branch_id, proj.loan_type or '通用')
        proj.pre_review.eva_result = calculate_eva(proj, params)
        proj.pre_review.rwa_result = calculate_rwa(proj, params)
        proj.pre_review.raroc_result = calculate_raroc(proj, params)
        count += 1
    return count


@app.route('/api/branch-params/logs', methods=['GET'])
@jwt_required()
def get_params_logs():
    user = User.query.get(int(get_jwt_identity()))
    logs = ParamsChangeLog.query.filter_by(branch_id=user.branch_id)\
        .order_by(ParamsChangeLog.created_at.desc()).limit(20).all()
    return jsonify([{
        'id': l.id, 'business_type': l.business_type,
        'changed_by_name': l.changed_by_user.name if l.changed_by_user else '',
        'old_values': json.loads(l.old_values) if l.old_values else {},
        'new_values': json.loads(l.new_values) if l.new_values else {},
        'created_at': l.created_at.isoformat(),
    } for l in logs])


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    user = User.query.get(int(get_jwt_identity()))
    ns = Notification.query.filter_by(user_id=user.id)\
        .order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([{
        'id': n.id, 'title': n.title, 'message': n.message,
        'is_read': n.is_read, 'project_id': n.project_id,
        'created_at': n.created_at.isoformat(),
    } for n in ns])


@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
@jwt_required()
def mark_read(nid):
    user = User.query.get(int(get_jwt_identity()))
    n = Notification.query.get_or_404(nid)
    if n.user_id != user.id:
        return jsonify({'error': '无权操作'}), 403
    n.is_read = True
    db.session.commit()
    return jsonify({'message': 'ok'})


@app.route('/api/notifications/read-all', methods=['PUT'])
@jwt_required()
def mark_all_read():
    user = User.query.get(int(get_jwt_identity()))
    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'message': 'ok'})


# ── AUDIT LOGS ────────────────────────────────────────────────────────────────

@app.route('/api/projects/<int:pid>/audit-logs', methods=['GET'])
@jwt_required()
def get_audit_logs(pid):
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if not can_access_project(user, p):
        return jsonify({'error': '无权访问此项目'}), 403
    logs = AuditLog.query.filter_by(project_id=pid)\
        .order_by(AuditLog.created_at.desc()).all()
    return jsonify([{
        'id': l.id, 'action': l.action,
        'user_name': l.user.name if l.user else '',
        'details': json.loads(l.details) if l.details else {},
        'entry_hash': l.entry_hash, 'prev_hash': l.prev_hash,
        'created_at': l.created_at.isoformat(),
    } for l in logs])


# ── STATS ─────────────────────────────────────────────────────────────────────

@app.route('/api/stats', methods=['GET'])
@jwt_required()
def get_stats():
    user = User.query.get(int(get_jwt_identity()))
    if user.role == 'R01':
        total = Project.query.filter_by(creator_id=user.id).count()
        green = Project.query.filter_by(creator_id=user.id, status='绿灯').count()
        approved = Project.query.filter_by(creator_id=user.id, status='已终审').count()
        pending = Project.query.filter_by(creator_id=user.id).filter(
            Project.status.in_(['待人工审批', '待行长终审', 'AI审批中'])).count()
    else:
        total = Project.query.count()
        green = Project.query.filter_by(status='已终审').count()
        approved = green
        pending = Project.query.filter(
            Project.status.in_(['待人工审批', '待行长终审'])).count()
    return jsonify({
        'total': total, 'green': green, 'approved': approved, 'pending': pending
    })


# ── USERS (admin-like) ────────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@jwt_required()
def list_users():
    user = User.query.get(int(get_jwt_identity()))
    # 仅审批员/行长出于流转选人需要可查看用户列表，客户经理无权
    if user.role not in ['R02', 'R03', 'R04', 'R05', 'R06', 'R07']:
        return jsonify({'error': '无权访问'}), 403
    users = User.query.all()
    return jsonify([{
        'id': u.id, 'name': u.name, 'role': u.role,
        'branch_level': u.branch_level, 'branch_name': u.branch_name,
    } for u in users])


# ── SEED DATA ─────────────────────────────────────────────────────────────────

def seed_data():
    if User.query.first():
        return

    users = [
        ('zhangwei', '张伟', 'R01', '支行', 'branch_001', '朝阳支行'),
        ('lihua', '李华', 'R02', '支行', 'branch_001', '朝阳支行'),
        ('wangfang', '王芳', 'R03', '支行', 'branch_001', '朝阳支行'),
        ('zhaoming', '赵明', 'R04', '分行', 'sub_branch_001', '北京分行'),
        ('chenli', '陈丽', 'R05', '分行', 'sub_branch_001', '北京分行'),
        ('liuyang', '刘阳', 'R06', '总行', 'hq_001', '总行公司业务部'),
        ('zhoujing', '周静', 'R07', '总行', 'hq_001', '总行公司业务部'),
    ]

    role_names = {
        'R01': '客户经理', 'R02': '支行行长', 'R03': '支行审批员',
        'R04': '分行审批员', 'R05': '分行行长', 'R06': '总行审批员', 'R07': '总行行长',
    }

    seed_password = os.environ.get('SEED_PASSWORD', 'password123')
    created_users = []
    for username, name, role, level, bid, bname in users:
        u = User(
            username=username,
            password_hash=generate_password_hash(seed_password),
            name=name, role=role, branch_level=level,
            branch_id=bid, branch_name=bname,
        )
        db.session.add(u)
        created_users.append(u)

    db.session.flush()

    # Default branch params
    for bid in ['branch_001', 'sub_branch_001', 'hq_001']:
        for btype in ['通用', '流动资金贷款', '固定资产贷款', '贸易融资']:
            p = BranchParams(branch_id=bid, business_type=btype,
                             capital_cost_rate=10.5, operating_cost_rate=1.5,
                             risk_weight_coeff=1.0, deposit_ftp_rate=1.5,
                             loan_ftp_rate=3.0, tax_rate=25.0, expected_loss_rate=0.5,
                             updated_by=created_users[1].id)
            db.session.add(p)

    db.session.commit()
    print("✅ 种子数据初始化完成")
    print("测试账号：")
    for username, name, role, *_ in users:
        print(f"  {username} / {seed_password}  ({role_names[role]})")


def ensure_schema():
    """对已存在的 SQLite 库做轻量级补列迁移（新增字段时不丢数据）。

    db.create_all() 只新建缺失的表，不会为已存在的表补列；这里用 ALTER TABLE 幂等补齐。
    """
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    pending = {
        'audit_logs': [('prev_hash', 'VARCHAR(64)'), ('entry_hash', 'VARCHAR(64)')],
        'signatures': [('signed_hash', 'VARCHAR(64)'), ('rsa_signature', 'TEXT')],
    }
    for table, cols in pending.items():
        if not inspector.has_table(table):
            continue
        existing = {c['name'] for c in inspector.get_columns(table)}
        for name, ddl in cols:
            if name not in existing:
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
    db.session.commit()


# ── REALTIME NOTIFICATIONS (SSE) ──────────────────────────────────────────────

@app.route('/api/notifications/stream')
@jwt_required()
def notification_stream():
    """Server-Sent Events 实时通知推送。
    前端用 EventSource('/api/notifications/stream?token=JWT') 订阅。
    每 5 秒轮询一次新通知，客户端断开时生成器自动退出。
    """
    user_id = int(get_jwt_identity())
    last_id = request.args.get('last_id', 0, type=int)

    def generate():
        nonlocal last_id
        yield 'data: {"type":"connected"}\n\n'
        while True:
            try:
                db.session.expire_all()
                new_notifs = (
                    Notification.query
                    .filter(Notification.user_id == user_id, Notification.id > last_id)
                    .order_by(Notification.id.asc())
                    .limit(20).all()
                )
                for n in new_notifs:
                    data = json.dumps({
                        'type': 'notification',
                        'id': n.id, 'title': n.title, 'message': n.message,
                        'project_id': n.project_id, 'is_read': n.is_read,
                        'created_at': n.created_at.isoformat(),
                    }, ensure_ascii=False)
                    yield f'data: {data}\n\n'
                    last_id = n.id
                yield ': ping\n\n'
            except GeneratorExit:
                return
            except Exception:
                yield ': error\n\n'
            time.sleep(5)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'X-Accel-Buffering': 'no',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    )


# ── SIGNATURE VERIFICATION ────────────────────────────────────────────────────

@app.route('/api/projects/<int:pid>/verify-signatures', methods=['GET'])
@jwt_required()
def verify_signatures(pid):
    """验证项目所有电子签章的 SHA-256 哈希和 RSA 数字签名。"""
    user = User.query.get(int(get_jwt_identity()))
    p = Project.query.get_or_404(pid)
    if not can_access_project(user, p):
        return jsonify({'error': '无权访问此项目'}), 403

    results = []
    for s in Signature.query.filter_by(project_id=pid).all():
        signed_at = s.created_at.isoformat() if s.created_at else ''
        payload = (f'{s.project_id}|{s.signer_id}|{s.signature_level}|'
                   f'{s.certificate_no}|{s.signature_data or ""}|{signed_at}')
        expected_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        hash_ok = s.signed_hash == expected_hash

        rsa_ok = None
        if _RSA_ENABLED and s.rsa_signature:
            kp = UserKeyPair.query.filter_by(user_id=s.signer_id).first()
            if kp:
                rsa_ok = verify_payload(kp.public_key_pem, payload, s.rsa_signature)

        results.append({
            'signer_name': s.signer.name if s.signer else '',
            'certificate_no': s.certificate_no,
            'signature_level': s.signature_level,
            'signed_at': signed_at,
            'hash_verified': hash_ok,
            'rsa_verified': rsa_ok,
            'algorithm': 'RSA-2048/SHA-256' if rsa_ok is not None else 'SHA-256',
        })

    return jsonify({'project_no': p.project_no, 'signatures': results})


# ── SYSTEM / AI CONFIG ────────────────────────────────────────────────────────

@app.route('/api/system/ai-status', methods=['GET'])
@jwt_required()
def ai_status():
    """返回 AI 配置状态和连通性（不暴露 API Key）。"""
    import zai_client
    enabled = zai_client.is_enabled()
    model = os.environ.get('ZAI_MODEL', 'glm-4-plus')
    base_url = os.environ.get('ZAI_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4/')
    connected = False
    latency_ms = None
    if enabled:
        t0 = time.time()
        result = zai_client.analyze_json(
            '请只返回JSON：{"ok":true}',
            '{"ok":true}',
            temperature=0,
        )
        latency_ms = round((time.time() - t0) * 1000)
        connected = bool(result and result.get('ok'))
    return jsonify({
        'enabled': enabled,
        'connected': connected,
        'model': model,
        'base_url': base_url,
        'latency_ms': latency_ms,
        'rsa_signing': _RSA_ENABLED,
    })


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_data()
    from scheduler import init_scheduler
    init_scheduler(app)
    # 生产环境务必设置 FLASK_DEBUG=0；默认仅开发环境开启 debug
    debug = os.environ.get('FLASK_DEBUG', '1') == '1' and os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=5000, debug=debug, use_reloader=False)
