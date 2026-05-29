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
    AuditLog, ProjectVersion, UserKeyPair, KnowledgeDoc,
)
from ai_engine import (
    ai_pre_review, generate_material_checklist, ai_auto_approval, verify_materials,
    determine_approval_level, calculate_eva, calculate_rwa, calculate_raroc,
    ai_interpret_document,
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


KNOWLEDGE_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_uploads')


def _build_knowledge_ctx(creator_branch_id):
    """构建分级知识库上下文字符串注入 AI 提示词。优先级：总行 > 分行 > 支行。"""
    hq_docs = KnowledgeDoc.query.filter_by(branch_level='总行', is_active=True, status='active').all()
    branch_docs = KnowledgeDoc.query.filter_by(branch_level='分行', is_active=True, status='active').all()
    sub_docs = KnowledgeDoc.query.filter_by(
        branch_level='支行', branch_id=creator_branch_id, is_active=True, status='active').all()

    all_docs = [('总行', hq_docs), ('分行', branch_docs), ('支行', sub_docs)]
    if not any(docs for _, docs in all_docs):
        return ''

    lines = ['【审批人员信贷政策知识库（冲突时高级别优先：总行>分行>支行）】']
    for level, docs in all_docs:
        for doc in docs:
            lines.append(f'[{level}·{doc.original_filename}] {doc.ai_summary or ""}')
            if doc.key_policies:
                try:
                    policies = json.loads(doc.key_policies)
                    for p in policies[:5]:
                        lines.append(f'  · {p}')
                except Exception:
                    pass
            if doc.prohibitions:
                lines.append(f'  禁止：{doc.prohibitions[:120]}')
    return '\n'.join(lines)


def _extract_text(file_path, doc_type):
    """从上传文件中提取文本，支持 PDF/Word/TXT，任一库缺失时优雅降级。"""
    try:
        if doc_type == 'txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif doc_type == 'pdf':
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    return '\n'.join(page.extract_text() or '' for page in reader.pages)
            except ImportError:
                return '（PDF解析库未安装，文档已保存，请联系管理员安装 PyPDF2）'
        elif doc_type == 'word':
            try:
                import docx
                doc = docx.Document(file_path)
                return '\n'.join(para.text for para in doc.paragraphs)
            except ImportError:
                return '（Word解析库未安装，文档已保存，请联系管理员安装 python-docx）'
    except Exception as e:
        return f'（文本提取失败：{e}）'
    return ''


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
    done = request.args.get('done') == '1'

    approver_level = {'R03': '支行', 'R04': '分行', 'R06': '总行'}
    leader_level   = {'R02': '支行', 'R05': '分行', 'R07': '总行'}
    PENDING_STATUSES = ['待人工审批', '待补充材料', '人工审批退回']
    DONE_STATUSES    = ['待行长终审', '已终审', '行长退回']

    q = Project.query
    if user.role == 'R01':
        q = q.filter_by(creator_id=user.id)
    elif user.role in approver_level:
        my_level = approver_level[user.role]
        if done:
            # 本人有审批记录且项目已流转至行长阶段或终审
            acted_ids = db.session.query(ApprovalRecord.project_id).filter_by(approver_id=user.id)
            q = q.filter(Project.id.in_(acted_ids),
                         Project.status.in_(DONE_STATUSES))
        else:
            q = q.filter(Project.status.in_(PENDING_STATUSES),
                         Project.current_approval_level == my_level)
    elif user.role in leader_level:
        my_level = leader_level[user.role]
        if done:
            q = q.filter(Project.status.in_(['已终审', '行长退回']),
                         Project.current_approval_level == my_level)
        else:
            q = q.filter(Project.status == '待行长终审',
                         Project.current_approval_level == my_level)

    status_filter = request.args.get('status')
    if status_filter:
        q = q.filter_by(status=status_filter)

    projects = q.order_by(Project.updated_at.desc()).all()
    result = [project_to_dict(p) for p in projects]

    # 已办列表附上本人最后一次审批动作
    if done and (user.role in approver_level or user.role in leader_level):
        for d, p in zip(result, projects):
            rec = ApprovalRecord.query.filter_by(
                project_id=p.id, approver_id=user.id
            ).order_by(ApprovalRecord.created_at.desc()).first()
            if rec:
                d['my_last_action'] = rec.action
                d['my_last_opinion'] = rec.opinion
                d['my_acted_at'] = rec.created_at.isoformat() if rec.created_at else None

    return jsonify(result)


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
    knowledge_ctx = _build_knowledge_ctx(user.branch_id)
    result = ai_pre_review(p, params, knowledge_ctx=knowledge_ctx)

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

    knowledge_ctx = _build_knowledge_ctx(p.creator.branch_id)
    result = ai_auto_approval(p, p.pre_review, p.materials, checklist=checklist, knowledge_ctx=knowledge_ctx)

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


# ── FR-13：行长业务绩效统计分析 ────────────────────────────────────────────────────

@app.route('/api/leader-stats', methods=['GET'])
@jwt_required()
def leader_stats():
    from collections import defaultdict
    user = User.query.get(int(get_jwt_identity()))
    if user.role not in ['R02', 'R05', 'R07']:
        return jsonify({'error': '仅行长可查看绩效统计'}), 403

    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=30)
    start_str = request.args.get('start', '')
    end_str = request.args.get('end', '')
    loan_type_filter = request.args.get('loan_type', '')
    do_export = request.args.get('export') == '1'

    if start_str:
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            pass
    if end_str:
        try:
            end_dt = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # 取日期范围内的签字记录，得到项目ID→签字时间映射
    sigs = Signature.query.filter(
        Signature.created_at >= start_dt,
        Signature.created_at <= end_dt,
    ).all()
    sig_map = {}
    for sig in sigs:
        if sig.project_id not in sig_map:
            sig_map[sig.project_id] = sig.created_at

    empty_summary = {'total_eva': 0, 'total_rwa': 0, 'avg_raroc': 0, 'total_count': 0}
    if not sig_map:
        return jsonify({'data_points': [], 'summary': empty_summary, 'granularity': 'day'})

    q = Project.query.filter(
        Project.id.in_(list(sig_map.keys())),
        Project.status == '已终审',
    )
    if loan_type_filter:
        q = q.filter(Project.loan_type == loan_type_filter)

    projects = q.all()

    entries = []
    for p in projects:
        if not p.pre_review:
            continue
        creator = User.query.get(p.creator_id)
        if not creator:
            continue
        if user.role == 'R02' and creator.branch_id != user.branch_id:
            continue
        if user.role == 'R05' and creator.branch_level not in ('支行', '分行'):
            continue
        entries.append((p, sig_map[p.id]))

    delta = (end_dt - start_dt).days
    if delta <= 30:
        granularity = 'day'
    elif delta <= 90:
        granularity = 'week'
    else:
        granularity = 'month'

    groups = defaultdict(lambda: {'eva': [], 'rwa': [], 'raroc': [], 'count': 0})
    for p, sig_date in entries:
        if granularity == 'week':
            week_start = sig_date.date() - timedelta(days=sig_date.weekday())
            date_key = str(week_start)
        elif granularity == 'month':
            date_key = sig_date.strftime('%Y-%m')
        else:
            date_key = sig_date.strftime('%Y-%m-%d')

        groups[date_key]['count'] += 1
        if p.pre_review.eva_result is not None:
            groups[date_key]['eva'].append(p.pre_review.eva_result)
        if p.pre_review.rwa_result is not None:
            groups[date_key]['rwa'].append(p.pre_review.rwa_result)
        if p.pre_review.raroc_result is not None:
            groups[date_key]['raroc'].append(p.pre_review.raroc_result)

    data_points = []
    for dk in sorted(groups.keys()):
        g = groups[dk]
        data_points.append({
            'date': dk,
            'eva': round(sum(g['eva']), 2) if g['eva'] else None,
            'rwa': round(sum(g['rwa']), 2) if g['rwa'] else None,
            'raroc': round(sum(g['raroc']) / len(g['raroc']), 2) if g['raroc'] else None,
            'count': g['count'],
        })

    all_eva = [dp['eva'] for dp in data_points if dp['eva'] is not None]
    all_rwa = [dp['rwa'] for dp in data_points if dp['rwa'] is not None]
    all_raroc = [dp['raroc'] for dp in data_points if dp['raroc'] is not None]
    total_count = sum(g['count'] for g in groups.values())
    summary = {
        'total_eva': round(sum(all_eva), 2) if all_eva else 0,
        'total_rwa': round(sum(all_rwa), 2) if all_rwa else 0,
        'avg_raroc': round(sum(all_raroc) / len(all_raroc), 2) if all_raroc else 0,
        'total_count': total_count,
    }

    if do_export:
        import csv, io
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(['日期', 'EVA(万元)', 'RWA(万元)', 'RAROC(%)', '业务笔数'])
        for dp in data_points:
            w.writerow([dp['date'], dp['eva'], dp['rwa'], dp['raroc'], dp['count']])
        w.writerow(['合计/均值', summary['total_eva'], summary['total_rwa'],
                    summary['avg_raroc'], summary['total_count']])
        fname = f'leader_stats_{start_str or "start"}_{end_str or "end"}.csv'
        return Response(
            '﻿' + out.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={fname}'},
        )

    return jsonify({'data_points': data_points, 'summary': summary, 'granularity': granularity})


# ── FR-14：审批人员信贷政策知识库 ────────────────────────────────────────────────────

@app.route('/api/knowledge', methods=['GET'])
@jwt_required()
def list_knowledge():
    user = User.query.get(int(get_jwt_identity()))
    if user.role not in ['R03', 'R04', 'R06']:
        return jsonify({'error': '仅审批员可访问知识库'}), 403

    scope = request.args.get('scope', 'own')
    if scope == 'own':
        docs = KnowledgeDoc.query.filter_by(
            branch_level=user.branch_level,
            branch_id=user.branch_id,
            is_active=True,
        ).order_by(KnowledgeDoc.created_at.desc()).all()
    else:
        upper_map = {'R03': ['分行', '总行'], 'R04': ['总行'], 'R06': []}
        upper_levels = upper_map.get(user.role, [])
        if not upper_levels:
            return jsonify([])
        docs = KnowledgeDoc.query.filter(
            KnowledgeDoc.branch_level.in_(upper_levels),
            KnowledgeDoc.is_active == True,
        ).order_by(KnowledgeDoc.branch_level.desc(), KnowledgeDoc.created_at.desc()).all()

    return jsonify([d.to_dict() for d in docs])


@app.route('/api/knowledge/upload', methods=['POST'])
@jwt_required()
def upload_knowledge():
    user = User.query.get(int(get_jwt_identity()))
    if user.role not in ['R03', 'R04', 'R06']:
        return jsonify({'error': '仅审批员可上传知识库文档'}), 403

    if 'file' not in request.files:
        return jsonify({'error': '请上传文件'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': '文件名不能为空'}), 400

    fname_lower = f.filename.lower()
    if fname_lower.endswith('.pdf'):
        doc_type = 'pdf'
    elif fname_lower.endswith('.docx') or fname_lower.endswith('.doc'):
        doc_type = 'word'
    elif fname_lower.endswith('.txt'):
        doc_type = 'txt'
    else:
        return jsonify({'error': '仅支持 PDF、Word(.docx/.doc)、TXT 格式'}), 400

    os.makedirs(KNOWLEDGE_UPLOAD_DIR, exist_ok=True)
    stored_name = f'{uuid.uuid4().hex}_{f.filename}'
    file_path = os.path.join(KNOWLEDGE_UPLOAD_DIR, stored_name)
    f.save(file_path)

    doc = KnowledgeDoc(
        uploader_id=user.id,
        branch_level=user.branch_level,
        branch_id=user.branch_id,
        branch_name=user.branch_name,
        original_filename=f.filename,
        stored_filename=stored_name,
        doc_type=doc_type,
        status='processing',
    )
    db.session.add(doc)
    db.session.commit()

    try:
        text = _extract_text(file_path, doc_type)
        interp = ai_interpret_document(text, f.filename)
        doc.ai_summary = interp.get('summary', '')
        doc.key_policies = json.dumps(interp.get('key_policies', []), ensure_ascii=False)
        doc.applicable_scope = interp.get('applicable_scope', '')
        doc.prohibitions = interp.get('prohibitions', '')
        doc.exceptions = interp.get('exceptions', '')
        doc.status = 'active'
    except Exception as e:
        doc.ai_summary = f'解读失败：{e}'
        doc.status = 'failed'

    db.session.commit()
    log_action(user.id, None, '上传知识库文档', {'filename': f.filename, 'doc_id': doc.id})
    return jsonify(doc.to_dict()), 201


@app.route('/api/knowledge/<int:doc_id>', methods=['DELETE'])
@jwt_required()
def delete_knowledge(doc_id):
    user = User.query.get(int(get_jwt_identity()))
    if user.role not in ['R03', 'R04', 'R06']:
        return jsonify({'error': '仅审批员可删除知识库文档'}), 403

    doc = KnowledgeDoc.query.get_or_404(doc_id)
    if doc.uploader_id != user.id:
        return jsonify({'error': '只能删除自己上传的文档'}), 403

    doc.is_active = False
    db.session.commit()
    log_action(user.id, None, '删除知识库文档', {'filename': doc.original_filename, 'doc_id': doc_id})
    return jsonify({'message': '文档已删除'})


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
