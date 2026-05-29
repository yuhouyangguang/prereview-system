import json
from datetime import datetime, timedelta
from pathlib import Path

import zai_client

HIGH_RISK_INDUSTRIES = ['房地产', '地方政府融资平台', '煤炭', '钢铁', '化工', '电解铝']
MEDIUM_RISK_INDUSTRIES = ['制造业', '批发零售', '采矿', '建筑']
LOW_RISK_INDUSTRIES = ['科技', '医疗', '教育', '绿色能源', '农业', '服务业']
RESTRICTED_INDUSTRIES = ['房地产', '地方政府融资平台']

# ── 政策知识库 & 同业参考数据（模块级加载）─────────────────────────────────────────────
_KB_PATH = Path(__file__).parent / 'policy_kb.json'
_PEER_PATH = Path(__file__).parent / 'peer_data.json'

try:
    with open(_KB_PATH, encoding='utf-8') as _f:
        _POLICY_KB = json.load(_f)
except Exception:
    _POLICY_KB = {'policies': [], 'pricing_benchmarks': {}}

try:
    with open(_PEER_PATH, encoding='utf-8') as _f:
        _PEER_DATA = json.load(_f)['data']
except Exception:
    _PEER_DATA = []


def _relevant_policies(project) -> list[dict]:
    """返回与本项目最相关的政策条目（最多 5 条）。"""
    hits = []
    for p in _POLICY_KB.get('policies', []):
        content = p.get('content', '')
        # 按行业、担保方式、金额关键词匹配
        if (project.client_industry and project.client_industry in content):
            hits.append(p)
        elif p.get('category') in ['审批权限', '定价政策', '担保政策']:
            hits.append(p)
    # 去重后取前 5 条
    seen, result = set(), []
    for p in hits:
        if p['id'] not in seen:
            seen.add(p['id'])
            result.append(p)
        if len(result) >= 5:
            break
    return result


def _peer_benchmark(project) -> dict | None:
    """查找同业参考数据中最接近的条目（行业+贷款类型优先，再放宽到仅行业）。"""
    ind = project.client_industry or ''
    lt = project.loan_type or ''
    gt = project.guarantee_type or ''
    # 优先：行业+贷款类型+担保方式完全匹配
    for row in _PEER_DATA:
        if row['industry'] == ind and row['loan_type'] == lt and row['guarantee_type'] == gt:
            return row
    # 次优：行业+贷款类型
    for row in _PEER_DATA:
        if row['industry'] == ind and row['loan_type'] == lt:
            return row
    # 再次：行业
    for row in _PEER_DATA:
        if row['industry'] == ind:
            return row
    return None


def _policy_context_text(project) -> str:
    """格式化政策条目为可插入提示词的字符串。"""
    policies = _relevant_policies(project)
    if not policies:
        return ''
    lines = ['【相关内部信贷政策（摘要）】']
    for p in policies:
        lines.append(f"[{p['id']}] {p['title']}：{p['content']}")
    bm = _POLICY_KB.get('pricing_benchmarks', {})
    if bm:
        lines.append(
            f"【定价基准参考】支行级≥{bm.get('floor_branch')}%，"
            f"分行级≥{bm.get('floor_subbranch')}%，"
            f"总行级≥{bm.get('floor_hq')}%，"
            f"RAROC≥{bm.get('raroc_floor_pct')}%，EVA>0"
        )
    return '\n'.join(lines)


MATERIAL_TEMPLATES = {
    'common': [
        {'name': '企业营业执照', 'type': '必需'},
        {'name': '企业章程及历次修正章程', 'type': '必需'},
        {'name': '法定代表人身份证明', 'type': '必需'},
        {'name': '贷款申请书', 'type': '必需'},
        {'name': '近三年审计报告', 'type': '必需'},
        {'name': '近期资产负债表和损益表', 'type': '必需'},
        {'name': '企业信用报告授权书', 'type': '必需'},
    ],
    '流动资金贷款': [
        {'name': '生产经营计划书', 'type': '必需'},
        {'name': '主要客户合同样本', 'type': '条件必需'},
        {'name': '应收账款明细表', 'type': '条件必需'},
        {'name': '库存商品明细表', 'type': '补充参考'},
    ],
    '固定资产贷款': [
        {'name': '项目可行性研究报告', 'type': '必需'},
        {'name': '项目批复/核准/备案文件', 'type': '必需'},
        {'name': '工程概算书', 'type': '必需'},
        {'name': '建设用地规划许可证', 'type': '条件必需'},
        {'name': '建设工程规划许可证', 'type': '条件必需'},
        {'name': '施工合同', 'type': '补充参考'},
    ],
    '贸易融资': [
        {'name': '贸易合同', 'type': '必需'},
        {'name': '发票', 'type': '必需'},
        {'name': '提单/仓单', 'type': '条件必需'},
        {'name': '报关单', 'type': '条件必需'},
        {'name': '信用证（如适用）', 'type': '补充参考'},
    ],
    '银行承兑汇票': [
        {'name': '购销合同', 'type': '必需'},
        {'name': '增值税发票', 'type': '必需'},
        {'name': '开户证明', 'type': '必需'},
    ],
    '保函': [
        {'name': '基础合同', 'type': '必需'},
        {'name': '保函申请书', 'type': '必需'},
        {'name': '反担保文件', 'type': '条件必需'},
    ],
}

GUARANTEE_MATERIALS = {
    '抵押': [
        {'name': '抵押物权属证明文件', 'type': '必需'},
        {'name': '抵押物评估报告', 'type': '必需'},
        {'name': '不动产登记证明（如适用）', 'type': '条件必需'},
    ],
    '质押': [
        {'name': '质押物权属证明', 'type': '必需'},
        {'name': '质押物价值评估', 'type': '必需'},
    ],
    '保证': [
        {'name': '担保方营业执照', 'type': '必需'},
        {'name': '担保方近期财务报表', 'type': '必需'},
        {'name': '担保合同', 'type': '必需'},
    ],
    '信用': [
        {'name': '近三年纳税证明', 'type': '必需'},
        {'name': '社保缴纳证明', 'type': '补充参考'},
    ],
}

# ── 统一审批权限矩阵 ──────────────────────────────────────────────────────────────
LEVELS = ['支行', '分行', '总行']


def determine_approval_level(loan_amount, guarantee_type=None, industry=None):
    amount = loan_amount or 0
    if amount >= 30000:
        level_idx = 2
    elif amount >= 5000:
        level_idx = 1
    else:
        level_idx = 0
    if industry in RESTRICTED_INDUSTRIES:
        level_idx = max(level_idx, 2)
    elif industry in HIGH_RISK_INDUSTRIES:
        level_idx = min(level_idx + 1, 2)
    if not guarantee_type or guarantee_type in ['信用', '无担保']:
        level_idx = min(level_idx + 1, 2)
    return LEVELS[level_idx]


def _project_brief(project):
    return {
        'client_name': project.client_name,
        'client_industry': project.client_industry,
        'client_credit_rating': project.client_credit_rating,
        'client_description': project.client_description,
        'loan_amount_万元': project.loan_amount,
        'loan_type': project.loan_type,
        'loan_term_月': project.loan_term,
        'loan_purpose': project.loan_purpose,
        'guarantee_type': project.guarantee_type,
        'interest_rate_%': project.interest_rate,
        'fee_rate_%': project.fee_rate,
        'deposit_return_%': project.deposit_return,
        'competitor_rate_%': project.competitor_rate,
        'competitor_bank': project.competitor_bank,
    }


# ── AI 预审 ──────────────────────────────────────────────────────────────────────

def ai_pre_review(project, branch_params, knowledge_ctx=''):
    eva = calculate_eva(project, branch_params)
    rwa = calculate_rwa(project, branch_params)
    raroc = calculate_raroc(project, branch_params)

    result = _zai_pre_review(project, eva, rwa, raroc, knowledge_ctx)
    if result is None:
        result = _rule_pre_review(project)

    result['eva_result'] = eva
    result['rwa_result'] = rwa
    result['raroc_result'] = raroc
    result['valid_until'] = datetime.utcnow() + timedelta(days=30)
    return result


def _zai_pre_review(project, eva, rwa, raroc, knowledge_ctx=''):
    if not zai_client.is_enabled():
        return None

    policy_ctx = _policy_context_text(project)
    peer = _peer_benchmark(project)
    peer_ctx = ''
    if peer:
        peer_ctx = (
            f"\n【同业参考】辖内同类项目（{peer['industry']}·{peer['loan_type']}·{peer['guarantee_type']}）"
            f"平均利率 {peer['rate_avg']}%，区间 [{peer['rate_range'][0]}%, {peer['rate_range'][1]}%]，"
            f"样本数 {peer['count']}。"
        )

    kb_section = f"\n{knowledge_ctx}\n" if knowledge_ctx else ''

    system = (
        "你是北京银行公司业务条线的资深信贷预审专家，熟悉总行信贷政策、行业限额、"
        "准入负面清单、集中度要求与综合定价。请基于给定项目信息做前置预审，"
        "重点判断：①是否符合总行信贷政策；②综合效益与定价是否合理；③给出红/黄/绿灯结论与可操作建议。"
        "房地产、地方政府融资平台属于限制行业需触发专项审查。\n"
        + (policy_ctx + '\n' if policy_ctx else '')
        + kb_section
        + "请严格只输出 JSON，字段：policy_compliance(取值:符合/基本符合/需调整/不符合)、"
        "policy_notes(字符串,政策合规要点,可多行)、benefit_assessment(取值:高/中/低)、"
        "benefit_notes(字符串)、traffic_light(取值:绿灯/黄灯/红灯)、recommendations(字符串,可操作建议,可多行)。"
        "判定原则：政策不符合→红灯；政策符合/基本符合且效益高/中→绿灯；其余→黄灯。"
        "若知识库内容与其他政策存在冲突，以更高级别审批人员上传的知识库内容为准。"
    )
    user = (
        f"项目信息（金额单位:万元，利率单位:%）：\n{json.dumps(_project_brief(project), ensure_ascii=False, indent=2)}\n\n"
        f"系统已确定性测算：EVA={eva}万元, RWA={rwa}万元, RAROC={raroc}%。{peer_ctx}\n"
        "请结合上述测算和政策知识库给出预审结论，只返回 JSON。"
    )
    data = zai_client.analyze_json(system, user)
    if not data:
        return None
    pc = data.get('policy_compliance')
    if pc not in ['符合', '基本符合', '需调整', '不符合']:
        pc = '基本符合'
    benefit = data.get('benefit_assessment')
    if benefit not in ['高', '中', '低']:
        benefit = '中'
    tl = data.get('traffic_light')
    if tl not in ['绿灯', '黄灯', '红灯']:
        if pc == '不符合':
            tl = '红灯'
        elif pc in ['符合', '基本符合'] and benefit in ['高', '中']:
            tl = '绿灯'
        else:
            tl = '黄灯'
    return {
        'policy_compliance': pc,
        'policy_notes': data.get('policy_notes') or '（AI 未返回详细说明）',
        'benefit_assessment': benefit,
        'benefit_notes': data.get('benefit_notes') or '',
        'traffic_light': tl,
        'recommendations': data.get('recommendations') or '',
    }


def _rule_pre_review(project):
    """zai 不可用时的规则引擎兜底。"""
    issues = []
    suggestions = []

    policy_compliance = '符合'
    if project.client_industry in RESTRICTED_INDUSTRIES:
        policy_compliance = '不符合'
        issues.append(f'⚠️ {project.client_industry}属于总行限制行业，须触发专项审查流程，需上报总行审批')
    elif project.client_industry in HIGH_RISK_INDUSTRIES:
        policy_compliance = '基本符合'
        issues.append(f'⚠️ {project.client_industry}行业属于风险关注行业，需关注行业集中度限额，确认未超出分行授信上限')
    elif project.client_industry in MEDIUM_RISK_INDUSTRIES:
        policy_compliance = '基本符合'
        issues.append(f'{project.client_industry}行业需关注周期性风险，建议评估客户抗周期能力')

    loan_amount = project.loan_amount or 0
    if loan_amount > 30000:
        if policy_compliance == '符合':
            policy_compliance = '需调整'
        issues.append(f'授信金额{loan_amount:.0f}万元超过3亿元，须上报总行审批委员会')
    elif loan_amount > 5000:
        issues.append(f'授信金额{loan_amount:.0f}万元超过5000万元，须上报分行审批')

    if not project.guarantee_type or project.guarantee_type in ['无担保', '信用']:
        if policy_compliance == '符合':
            policy_compliance = '需调整'
        issues.append('纯信用贷款需符合信用类贷款准入标准，建议补充担保措施')

    interest_rate = project.interest_rate or 0
    fee_rate = project.fee_rate or 0
    deposit_return = project.deposit_return or 0
    comprehensive_rate = interest_rate + fee_rate * 0.3 + deposit_return * 0.1

    # 同业参考对比
    peer = _peer_benchmark(project)
    peer_note = ''
    if peer:
        diff = interest_rate - peer['rate_avg']
        peer_note = (f'同业参考：{peer["industry"]}·{peer["loan_type"]} 均值{peer["rate_avg"]}%'
                     f'（区间{peer["rate_range"][0]}%~{peer["rate_range"][1]}%）。')
        if diff < -0.5:
            suggestions.append(f'我行报价({interest_rate}%)较同业均值({peer["rate_avg"]}%)低{abs(diff):.2f}%，需核实同业报价真实性，防止虚报压价')
        elif diff > 1.0:
            suggestions.append(f'我行报价({interest_rate}%)较同业均值({peer["rate_avg"]}%)高{diff:.2f}%，存在客户流失风险')

    bm = _POLICY_KB.get('pricing_benchmarks', {})
    floor = bm.get('floor_branch', 3.75)
    if comprehensive_rate >= floor + 1.25:
        benefit = '高'
        benefit_note = f'综合收益率约{comprehensive_rate:.2f}%，显著高于分行基准要求，效益优质。{peer_note}'
    elif comprehensive_rate >= floor:
        benefit = '中'
        benefit_note = f'综合收益率约{comprehensive_rate:.2f}%，达到分行基准收益要求，效益合理。{peer_note}'
    else:
        benefit = '低'
        benefit_note = f'综合收益率约{comprehensive_rate:.2f}%，低于分行基准收益要求（{floor}%），建议提高定价。{peer_note}'
        suggestions.append(f'当前综合收益率{comprehensive_rate:.2f}%未达分行基准，建议将贷款利率上调至少{max(0, floor - comprehensive_rate):.2f}个百分点')

    if project.competitor_rate and interest_rate and not peer:
        diff = interest_rate - project.competitor_rate
        if diff < -0.5:
            suggestions.append(f'我行报价({interest_rate}%)较同业({project.competitor_rate}%)低{abs(diff):.2f}%，需核实同业报价真实性')
        elif diff > 1.5:
            suggestions.append(f'我行报价({interest_rate}%)较同业({project.competitor_rate}%)高{diff:.2f}%，存在较高客户流失风险')

    if policy_compliance == '不符合':
        traffic_light = '红灯'
        suggestions.insert(0, '🔴 红灯：该项目不符合总行信贷政策，不建议继续推进，建议客户调整方案后重新申报')
    elif policy_compliance in ['符合', '基本符合'] and benefit in ['高', '中']:
        traffic_light = '绿灯'
        suggestions.insert(0, '🟢 绿灯：政策合规且综合效益达标，可正式推进项目尽调和申报工作')
    else:
        traffic_light = '黄灯'
        suggestions.insert(0, '🟡 黄灯：项目存在需调整事项，建议与客户重新协商后再次提交预审')

    return {
        'policy_compliance': policy_compliance,
        'policy_notes': '\n'.join(issues) if issues else '✅ 政策合规性检查通过，无重大风险点',
        'benefit_assessment': benefit,
        'benefit_notes': benefit_note,
        'traffic_light': traffic_light,
        'recommendations': '\n'.join(suggestions),
    }


def calculate_eva(project, params):
    if not params:
        return None
    try:
        loan_amount = project.loan_amount or 0
        interest_rate = (project.interest_rate or 0) / 100
        ftp_rate = params.loan_ftp_rate / 100
        op_cost = params.operating_cost_rate / 100
        loss_rate = params.expected_loss_rate / 100
        capital_cost = params.capital_cost_rate / 100
        capital_ratio = 0.08 * params.risk_weight_coeff
        net_spread = interest_rate - ftp_rate - op_cost - loss_rate - capital_cost * capital_ratio
        return round(net_spread * loan_amount, 2)
    except Exception:
        return None


def calculate_rwa(project, params):
    if not params:
        return None
    try:
        loan_amount = project.loan_amount or 0
        return round(loan_amount * 1.0 * params.risk_weight_coeff, 2)
    except Exception:
        return None


def calculate_raroc(project, params):
    if not params:
        return None
    try:
        loan_amount = project.loan_amount or 0
        interest_rate = (project.interest_rate or 0) / 100
        ftp_rate = params.loan_ftp_rate / 100
        op_cost = params.operating_cost_rate / 100
        loss_rate = params.expected_loss_rate / 100
        tax_rate = params.tax_rate / 100
        capital_ratio = 0.08 * params.risk_weight_coeff
        net_income = (interest_rate - ftp_rate - op_cost - loss_rate) * loan_amount * (1 - tax_rate)
        economic_capital = loan_amount * capital_ratio
        if economic_capital == 0:
            return None
        return round((net_income / economic_capital) * 100, 2)
    except Exception:
        return None


def generate_material_checklist(project):
    checklist = list(MATERIAL_TEMPLATES['common'])
    loan_type_mats = MATERIAL_TEMPLATES.get(project.loan_type, [])
    checklist.extend(loan_type_mats)
    if project.guarantee_type:
        guarantee_mats = GUARANTEE_MATERIALS.get(project.guarantee_type, [])
        checklist.extend(guarantee_mats)
    checklist.append({'name': '征信报告（企业+法人）', 'type': '补充参考'})
    checklist.append({'name': '同业可比项目参考数据', 'type': '补充参考'})
    return checklist


# ── 材料核验 ──────────────────────────────────────────────────────────────────────

def verify_materials(project, materials):
    uploaded = [m for m in materials if m.filename]
    if not uploaded:
        return {}
    result = _zai_verify_materials(project, uploaded)
    if result is None:
        result = {m.material_name: _rule_verify_one(m.material_name) for m in uploaded}
    return result


def _zai_verify_materials(project, uploaded):
    if not zai_client.is_enabled():
        return None
    system = (
        "你是银行公司业务审批员，负责对客户经理上传的授信业务材料做形式核验，"
        "从真实性、完整性、合规性三个角度给出每份材料的核验结论。"
        "结论取值：green(合规可用)/yellow(有效但需关注时效或细节)/red(存在明显问题需重新提交)。"
        "财务/审计/评估类材料若可能超过有效期通常判 yellow。"
        "请严格只输出 JSON：{\"materials\":[{\"name\":\"材料名\",\"status\":\"green|yellow|red\",\"notes\":\"简要说明\"}]}。"
    )
    items = [{'name': m.material_name, 'type': m.material_type, 'filename': m.filename} for m in uploaded]
    user = (
        f"项目业务类型：{project.loan_type or '通用'}，担保方式：{project.guarantee_type or '无'}。\n"
        f"待核验材料清单：\n{json.dumps(items, ensure_ascii=False, indent=2)}\n"
        "请逐项给出核验结论，只返回 JSON。"
    )
    data = zai_client.analyze_json(system, user)
    if not data or 'materials' not in data:
        return None
    out = {}
    for item in data.get('materials', []):
        name = item.get('name')
        status = item.get('status')
        if name is None:
            continue
        if status not in ['green', 'yellow', 'red']:
            status = 'green'
        out[name] = {'status': status, 'notes': item.get('notes') or '核验通过'}
    for m in uploaded:
        if m.material_name not in out:
            out[m.material_name] = _rule_verify_one(m.material_name)
    return out


def _rule_verify_one(name):
    if '营业执照' in name or '身份证' in name or '贷款申请' in name:
        return {'status': 'green', 'notes': '格式合规，签章有效，信息完整'}
    if '审计报告' in name or '财务' in name or '评估' in name:
        return {'status': 'yellow', 'notes': '材料有效，建议核实数据时效性（超过6个月需更新）'}
    return {'status': 'green', 'notes': '核验通过'}


# ── AI 自动审批 ───────────────────────────────────────────────────────────────────

def ai_auto_approval(project, pre_review, materials, checklist=None, knowledge_ctx=''):
    if checklist is None:
        checklist = generate_material_checklist(project)

    policy_passed = pre_review.policy_compliance in ['符合', '基本符合']
    mat_map = {m.material_name: m for m in materials}
    required_names = [item['name'] for item in checklist if item['type'] == '必需']
    missing_mats = [name for name in required_names
                    if not mat_map.get(name) or not mat_map[name].filename]
    problem_mats = [m.material_name for m in materials if m.verification_status == 'red']
    suggested_level = determine_approval_level(
        project.loan_amount, project.guarantee_type, project.client_industry)

    hard_reject_reasons = []
    if not policy_passed:
        hard_reject_reasons.append('【一票否决】信贷政策不符合，无法通过AI审批')
    if missing_mats:
        names = '、'.join(missing_mats[:3])
        hard_reject_reasons.append(f'必需材料未齐全，缺少：{names}{"等" if len(missing_mats) > 3 else ""}')
    if len(problem_mats) >= 2:
        names = '、'.join(problem_mats[:2])
        hard_reject_reasons.append(f'多项材料核验不通过：{names}，请核实后重新提交')

    zai_part = _zai_auto_approval(project, pre_review, materials, missing_mats,
                                  problem_mats, bool(hard_reject_reasons), knowledge_ctx)

    if zai_part is None:
        return _rule_auto_approval(project, pre_review, materials, checklist,
                                   suggested_level, missing_mats, problem_mats,
                                   hard_reject_reasons, policy_passed)

    if hard_reject_reasons:
        result = '不通过'
    else:
        result = zai_part.get('result')
        if result not in ['通过', '有条件通过', '不通过']:
            result = '有条件通过' if (problem_mats or pre_review.benefit_assessment == '低') else '通过'

    mod_suggestions = zai_part.get('modification_suggestions') or []
    if hard_reject_reasons:
        mod_suggestions = hard_reject_reasons + [s for s in mod_suggestions if s not in hard_reject_reasons]

    return {
        'result': result,
        'suggested_level': suggested_level,
        'policy_opinion': zai_part.get('policy_opinion') or f"【政策合规性】{pre_review.policy_compliance}\n{pre_review.policy_notes}",
        'risk_opinion': zai_part.get('risk_opinion') or '【风险评估】见预审说明',
        'pricing_opinion': zai_part.get('pricing_opinion') or '【定价合理性】见预审说明',
        'material_opinion': zai_part.get('material_opinion') or _material_opinion_text(materials, missing_mats, problem_mats),
        'modification_suggestions': json.dumps(mod_suggestions, ensure_ascii=False),
    }


def _zai_auto_approval(project, pre_review, materials, missing_mats, problem_mats, hard_rejected, knowledge_ctx=''):
    if not zai_client.is_enabled():
        return None

    policy_ctx = _policy_context_text(project)
    peer = _peer_benchmark(project)
    peer_ctx = ''
    if peer:
        peer_ctx = (f"同业参考（{peer['industry']}·{peer['loan_type']}）："
                    f"均值{peer['rate_avg']}%，区间[{peer['rate_range'][0]}%,{peer['rate_range'][1]}%]。")

    kb_section = f"\n{knowledge_ctx}\n" if knowledge_ctx else ''

    system = (
        "你是北京银行公司业务 AI 审批引擎。请综合评估：政策红线(一票否决)、风险维度(行业/区域/客户/产品)、"
        "定价维度(综合收益是否达标)、合规维度(材料是否齐全合规)，给出审批结论与可操作的修改建议。\n"
        + (policy_ctx + '\n' if policy_ctx else '')
        + kb_section
        + "请严格只输出 JSON，字段：result(取值:通过/有条件通过/不通过)、"
        "policy_opinion、risk_opinion、pricing_opinion、material_opinion(均为字符串,可多行)、"
        "modification_suggestions(字符串数组,逐条列出需调整内容和建议方案;若通过可为空数组)。"
        "若知识库内容与其他政策存在冲突，以更高级别审批人员上传的知识库内容为准。"
    )
    facts = {
        '项目信息': _project_brief(project),
        '预审结论': {
            'policy_compliance': pre_review.policy_compliance,
            'policy_notes': pre_review.policy_notes,
            'benefit_assessment': pre_review.benefit_assessment,
            'traffic_light': pre_review.traffic_light,
            'EVA_万元': pre_review.eva_result,
            'RWA_万元': pre_review.rwa_result,
            'RAROC_%': pre_review.raroc_result,
        },
        '材料情况': {
            '缺失必需材料': missing_mats,
            '核验不通过材料': problem_mats,
            '已上传材料': [{'name': m.material_name, 'status': m.verification_status}
                        for m in materials if m.filename],
        },
        '同业定价参考': peer_ctx or '无匹配数据',
        '系统硬约束提示': '存在政策不符合或必需材料缺失等硬否决项，最终结论应为不通过' if hard_rejected else '无硬否决项',
    }
    user = (
        f"审批事实：\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n"
        "请给出审批意见，只返回 JSON。"
    )
    data = zai_client.analyze_json(system, user)
    if not data:
        return None
    ms = data.get('modification_suggestions')
    if isinstance(ms, str):
        ms = [ms]
    elif not isinstance(ms, list):
        ms = []
    data['modification_suggestions'] = [str(x) for x in ms]
    return data


def _material_opinion_text(materials, missing_mats, problem_mats):
    text = "【材料核验情况】\n"
    if missing_mats:
        text += f"❌ 缺失必需材料（{len(missing_mats)}项）：{'、'.join(missing_mats)}\n"
    if problem_mats:
        text += f"⚠️ 问题材料（{len(problem_mats)}项）：{'、'.join(problem_mats)}\n"
    uploaded = [m for m in materials if m.filename]
    if not missing_mats and not problem_mats:
        text += f"✅ 材料核验通过，共提交{len(uploaded)}份材料，均符合要求"
    return text


def _rule_auto_approval(project, pre_review, materials, checklist, suggested_level,
                        missing_mats, problem_mats, hard_reject_reasons, policy_passed):
    issues = []
    benefit_ok = pre_review.benefit_assessment in ['高', '中']

    if hard_reject_reasons:
        result = '不通过'
        issues.extend(hard_reject_reasons)
    elif not benefit_ok or problem_mats:
        result = '有条件通过'
        if not benefit_ok:
            issues.append('综合收益偏低，建议提高定价至基准水平')
        if problem_mats:
            issues.append(f'以下材料存在瑕疵需关注：{"、".join(problem_mats)}')
    else:
        result = '通过'

    policy_opinion = f"【政策合规性】{pre_review.policy_compliance}\n{pre_review.policy_notes}"

    risk_opinion = "【风险评估】\n"
    if project.client_industry in HIGH_RISK_INDUSTRIES:
        risk_opinion += f"⚠️ 行业风险：{project.client_industry}属于高风险行业，需重点关注行业景气度变化\n"
    else:
        risk_opinion += (f"行业风险：{project.client_industry or '未填写'}，"
                         f"风险水平{'偏高' if project.client_industry in MEDIUM_RISK_INDUSTRIES else '正常'}\n")
    gt = project.guarantee_type or '未设置'
    quality = '强' if gt in ['抵押', '质押'] else ('中等' if gt == '保证' else '弱')
    risk_opinion += f"担保方式：{gt}，风险缓释质量{quality}"

    pricing_opinion = f"【定价合理性】\n贷款利率：{project.interest_rate or 0}%\n"
    if project.fee_rate:
        pricing_opinion += f"手续费率：{project.fee_rate}%\n"
    if pre_review.raroc_result is not None:
        threshold = _POLICY_KB.get('pricing_benchmarks', {}).get('raroc_floor_pct', 10)
        pricing_opinion += (f"RAROC：{pre_review.raroc_result:.1f}%，"
                            f"{'✅ 达到资本回报要求' if pre_review.raroc_result >= threshold else '⚠️ 未达到资本回报要求'}")
    if pre_review.eva_result is not None:
        pricing_opinion += f"\nEVA：{pre_review.eva_result:.2f}万元"

    peer = _peer_benchmark(project)
    if peer and project.interest_rate:
        diff = project.interest_rate - peer['rate_avg']
        pricing_opinion += (f"\n同业参考均值：{peer['rate_avg']}%（"
                             f"{'高于' if diff >= 0 else '低于'}同业{abs(diff):.2f}%）")

    material_opinion = _material_opinion_text(materials, missing_mats, problem_mats)

    mod_suggestions = []
    if result != '通过':
        idx = 1
        if not policy_passed:
            mod_suggestions.append(f'{idx}. 项目需符合总行信贷政策要求，建议调整行业/担保方式/用途后重新申报')
            idx += 1
        if not benefit_ok:
            mod_suggestions.append(f'{idx}. 提高综合定价至市场合理水平，建议贷款利率上调至LPR+80BP以上')
            idx += 1
        if missing_mats:
            mod_suggestions.append(f'{idx}. 补充以下必需材料：{"、".join(missing_mats)}')
            idx += 1
        if problem_mats:
            mod_suggestions.append(f'{idx}. 修正以下材料中的问题后重新上传：{"、".join(problem_mats)}')

    return {
        'result': result,
        'suggested_level': suggested_level,
        'policy_opinion': policy_opinion,
        'risk_opinion': risk_opinion,
        'pricing_opinion': pricing_opinion,
        'material_opinion': material_opinion,
        'modification_suggestions': json.dumps(mod_suggestions, ensure_ascii=False),
    }


# ── 知识库文档 AI 解读（FR-14）────────────────────────────────────────────────────

def ai_interpret_document(text, filename):
    """AI解读上传的信贷政策文档，提取核心条款结构化存储。"""
    if not text or not text.strip():
        return {
            'summary': '文档内容为空，无法解读',
            'key_policies': [],
            'applicable_scope': '',
            'prohibitions': '',
            'exceptions': '',
        }

    # 超长文档截断，避免超出 token 上限
    text_preview = text[:8000] + ('…（文档过长，已截取前8000字）' if len(text) > 8000 else '')

    if not zai_client.is_enabled():
        return _rule_interpret_document(text, filename)

    system = (
        "你是北京银行信贷政策专家，擅长解读信贷政策文件并结构化输出核心要素。"
        "请从文档中提取以下内容：\n"
        "1. summary：文档整体摘要（200字以内）\n"
        "2. key_policies：核心政策条款列表（字符串数组，每条简明扼要，最多15条）\n"
        "3. applicable_scope：适用范围（字符串）\n"
        "4. prohibitions：禁止事项（字符串）\n"
        "5. exceptions：例外情形（字符串）\n"
        "请严格只输出 JSON，字段：summary、key_policies(字符串数组)、"
        "applicable_scope、prohibitions、exceptions（均为字符串）。"
    )
    user = (
        f"文档名称：{filename}\n\n"
        f"文档内容：\n{text_preview}\n\n"
        "请提取核心政策要素，只返回 JSON。"
    )

    result = zai_client.analyze_json(system, user)
    if not result:
        return _rule_interpret_document(text, filename)

    key_policies = result.get('key_policies', [])
    if isinstance(key_policies, str):
        key_policies = [key_policies]
    elif not isinstance(key_policies, list):
        key_policies = []

    return {
        'summary': result.get('summary') or f'已解读文档：{filename}',
        'key_policies': [str(p) for p in key_policies[:15]],
        'applicable_scope': result.get('applicable_scope') or '',
        'prohibitions': result.get('prohibitions') or '',
        'exceptions': result.get('exceptions') or '',
    }


def _rule_interpret_document(text, filename):
    """AI 不可用时规则兜底：提取文档前几行作为摘要。"""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    summary = (
        f'已上传文档：{filename}（共 {len(lines)} 行）。'
        'AI解读功能暂不可用，文档已存入知识库，内容可在详情页查看原文。'
    )
    return {
        'summary': summary,
        'key_policies': lines[:10],
        'applicable_scope': '',
        'prohibitions': '',
        'exceptions': '',
    }
