import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import StatusBadge from '../components/StatusBadge'
import SignatureModal from '../components/SignatureModal'

export default function ProjectDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showSignModal, setShowSignModal] = useState(false)
  const [approvalAction, setApprovalAction] = useState('')
  const [approvalOpinion, setApprovalOpinion] = useState('')
  const [showApprovalPanel, setShowApprovalPanel] = useState(false)
  const [transferLevel, setTransferLevel] = useState('')
  const [activeTab, setActiveTab] = useState('detail')
  const [auditLogs, setAuditLogs] = useState([])

  const load = async () => {
    try {
      const r = await api.get(`/projects/${id}`)
      setProject(r.data)
    } catch { navigate('/projects') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [id])

  const loadAuditLogs = async () => {
    const r = await api.get(`/projects/${id}/audit-logs`)
    setAuditLogs(r.data)
  }

  useEffect(() => {
    if (activeTab === 'audit') loadAuditLogs()
  }, [activeTab])

  const doAction = async (action, extra = {}) => {
    setActionLoading(action); setError(''); setSuccess('')
    try {
      let r
      switch (action) {
        case 'submit-prereview':
          r = await api.post(`/projects/${id}/submit-prereview`)
          setSuccess('AI预审已完成！')
          break
        case 'ai-verify':
          r = await api.post(`/projects/${id}/ai-verify-materials`)
          setSuccess('AI核验完成！')
          break
        case 'ai-approval':
          r = await api.post(`/projects/${id}/ai-approval`)
          setSuccess('AI审批完成！')
          break
        case 'resubmit':
          r = await api.post(`/projects/${id}/resubmit-after-return`)
          setSuccess('已重新提交至审批员')
          break
        case 'modify':
          r = await api.post(`/projects/${id}/request-modification`)
          setSuccess('项目已进入修改状态')
          break
        case 'human-approve':
          r = await api.post(`/projects/${id}/approve`, {
            action: extra.action, opinion: approvalOpinion,
            to_level: extra.toLevel || transferLevel,
          })
          setSuccess(`操作成功：${extra.action}`)
          setShowApprovalPanel(false)
          break
        case 'leader-approve':
          r = await api.post(`/projects/${id}/leader-approve`, extra)
          setSuccess(extra.action === '通过' ? '签字完成，项目已终审！' : '已退回客户经理')
          setShowSignModal(false)
          break
        default: return
      }
      setProject(r.data)
      window.scrollTo(0, 0)
    } catch (err) {
      setError(err.response?.data?.error || '操作失败')
    } finally { setActionLoading('') }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} /></div>
  if (!project) return null

  const p = project
  const isCreator = user?.id === p.creator_id
  const isApprover = ['R03', 'R04', 'R06'].includes(user?.role)
  const isLeader = ['R02', 'R05', 'R07'].includes(user?.role)
  const canEdit = isCreator && ['draft', 'AI已退回', '人工审批退回', '行长退回', '修改中', '红灯'].includes(p.status)

  const trafficColor = { '绿灯': '#10b981', '黄灯': '#f59e0b', '红灯': '#ef4444' }

  return (
    <div>
      <div className="page-header">
        <div className="flex-between">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
              <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', fontSize: 20 }}>←</button>
              <h1 style={{ margin: 0 }}>{p.client_name || '项目详情'}</h1>
              <StatusBadge status={p.status} />
            </div>
            <p style={{ marginLeft: 36 }}>{p.project_no} · v{p.version} · {p.creator_name} · {p.creator_branch}</p>
          </div>
          <div className="flex gap-2">
            {canEdit && <Link to={`/projects/${id}/edit`} className="btn btn-outline">✏️ 编辑</Link>}
            {isCreator && p.status === 'draft' && <button onClick={() => doAction('submit-prereview')} className="btn btn-primary" disabled={!!actionLoading}>{actionLoading === 'submit-prereview' ? <span className="spinner" style={{ width: 14, height: 14 }} /> : '🤖 提交AI预审'}</button>}
            {isCreator && p.status === '红灯' && <button onClick={() => doAction('submit-prereview')} className="btn btn-warning" disabled={!!actionLoading}>🔄 重新提交预审</button>}
            {isCreator && ['绿灯', '黄灯'].includes(p.status) && <button onClick={() => navigate(`/projects/${id}/materials`)} className="btn btn-primary">📎 业务材料AI核验</button>}
            {isCreator && ['材料提交中', 'AI已退回', '修改中'].includes(p.status) && <button onClick={() => navigate(`/projects/${id}/materials`)} className="btn btn-outline">📎 管理材料</button>}
            {isCreator && ['人工审批退回', '待补充材料'].includes(p.status) && <button onClick={() => doAction('resubmit')} className="btn btn-warning" disabled={!!actionLoading}>↩️ 重新提交审批</button>}
            {isCreator && ['已终审', '行长退回'].includes(p.status) && <button onClick={() => doAction('modify')} className="btn btn-outline" disabled={!!actionLoading}>✏️ 修改重提</button>}
            {isApprover && p.status === '待人工审批' && <button onClick={() => setShowApprovalPanel(true)} className="btn btn-primary">📝 审批操作</button>}
            {isLeader && p.status === '待行长终审' && (
              <>
                <button onClick={() => setShowSignModal(true)} className="btn btn-success">✍️ 审批通过并签字</button>
                <button onClick={() => { if (window.confirm('确认退回？')) doAction('leader-approve', { action: '不通过', opinion: '行长退回', signature_data: '' }) }} className="btn btn-danger">❌ 不通过</button>
              </>
            )}
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert alert-success">✅ {success}</div>}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '2px solid var(--gray-200)' }}>
        {['detail', 'prereview', 'materials', 'approval', 'audit'].map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '10px 20px', border: 'none', background: 'none', cursor: 'pointer',
            fontWeight: activeTab === tab ? 700 : 400,
            color: activeTab === tab ? 'var(--primary)' : 'var(--gray-500)',
            borderBottom: activeTab === tab ? '2px solid var(--primary)' : '2px solid transparent',
            marginBottom: -2, fontSize: 14,
          }}>
            {tab === 'detail' && '📋 项目信息'}
            {tab === 'prereview' && '🤖 预审结果'}
            {tab === 'materials' && '📎 材料清单'}
            {tab === 'approval' && '📝 审批轨迹'}
            {tab === 'audit' && '🔍 操作日志'}
          </button>
        ))}
      </div>

      {/* Tab: Detail */}
      {activeTab === 'detail' && (
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">客户基本信息</div>
            <div className="grid-3">
              <InfoItem label="客户名称" value={p.client_name} />
              <InfoItem label="所属行业" value={p.client_industry} />
              <InfoItem label="信用评级" value={p.client_credit_rating} />
            </div>
            {p.client_description && <InfoItem label="客户简介" value={p.client_description} />}
          </div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">融资方案</div>
            <div className="grid-3">
              <InfoItem label="贷款金额" value={p.loan_amount ? `${p.loan_amount.toLocaleString()} 万元` : '-'} highlight />
              <InfoItem label="贷款类型" value={p.loan_type} />
              <InfoItem label="贷款期限" value={p.loan_term ? `${p.loan_term} 个月` : '-'} />
              <InfoItem label="担保方式" value={p.guarantee_type} />
              <InfoItem label="融资用途" value={p.loan_purpose} />
            </div>
          </div>
          <div className="card">
            <div className="section-title">报价方案</div>
            <div className="grid-4">
              <InfoItem label="贷款利率" value={p.interest_rate ? `${p.interest_rate}%` : '-'} highlight />
              <InfoItem label="手续费率" value={p.fee_rate ? `${p.fee_rate}%` : '-'} />
              <InfoItem label="存款回报" value={p.deposit_return ? `${p.deposit_return}%` : '-'} />
              <InfoItem label="同业利率" value={p.competitor_rate ? `${p.competitor_rate}% (${p.competitor_bank || ''})` : '-'} />
            </div>
          </div>
        </div>
      )}

      {/* Tab: Pre-review */}
      {activeTab === 'prereview' && (
        <div>
          {!p.pre_review ? (
            <div className="card">
              <div className="empty-state">
                <div className="icon">🤖</div>
                <p>尚未进行AI预审</p>
                {isCreator && p.status === 'draft' && (
                  <button onClick={() => { doAction('submit-prereview'); setActiveTab('prereview') }} className="btn btn-primary" style={{ marginTop: 16 }} disabled={!!actionLoading}>
                    {actionLoading === 'submit-prereview' ? '分析中...' : '提交AI预审'}
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div>
              {/* Traffic light card */}
              <div className="card" style={{ marginBottom: 16, textAlign: 'center', background: `linear-gradient(135deg, ${trafficColor[p.pre_review.traffic_light]}15, white)`, border: `2px solid ${trafficColor[p.pre_review.traffic_light]}30` }}>
                <div style={{ fontSize: 64, marginBottom: 8 }}>
                  {p.pre_review.traffic_light === '绿灯' ? '🟢' : p.pre_review.traffic_light === '黄灯' ? '🟡' : '🔴'}
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: trafficColor[p.pre_review.traffic_light], marginBottom: 8 }}>
                  预审结论：{p.pre_review.traffic_light}
                </div>
                <div style={{ color: 'var(--gray-600)', maxWidth: 600, margin: '0 auto', fontSize: 15, lineHeight: 1.7 }}>
                  <pre>{p.pre_review.recommendations}</pre>
                </div>
                <div style={{ marginTop: 12, fontSize: 12, color: 'var(--gray-400)' }}>
                  有效期至：{p.pre_review.valid_until ? new Date(p.pre_review.valid_until).toLocaleDateString('zh-CN') : '-'}
                </div>
              </div>

              <div className="grid-2" style={{ marginBottom: 16 }}>
                <div className="card">
                  <div className="section-title">信贷政策符合性</div>
                  <div style={{ marginBottom: 10 }}>
                    <span className={`badge ${p.pre_review.policy_compliance === '符合' ? 'badge-green' : p.pre_review.policy_compliance === '不符合' ? 'badge-red' : 'badge-yellow'}`}>
                      {p.pre_review.policy_compliance}
                    </span>
                  </div>
                  <pre style={{ fontSize: 13, color: 'var(--gray-600)', lineHeight: 1.7 }}>{p.pre_review.policy_notes}</pre>
                </div>
                <div className="card">
                  <div className="section-title">综合效益评估</div>
                  <div style={{ marginBottom: 10 }}>
                    <span className={`badge ${p.pre_review.benefit_assessment === '高' ? 'badge-green' : p.pre_review.benefit_assessment === '低' ? 'badge-red' : 'badge-yellow'}`}>
                      综合效益：{p.pre_review.benefit_assessment}
                    </span>
                  </div>
                  <p style={{ fontSize: 13, color: 'var(--gray-600)' }}>{p.pre_review.benefit_notes}</p>
                </div>
              </div>

              {/* EVA/RWA/RAROC */}
              {(p.pre_review.eva_result !== null || p.pre_review.rwa_result !== null) && (
                <div className="card">
                  <div className="section-title">EVA / RWA / RAROC 测算结果</div>
                  <div className="alert alert-info" style={{ marginBottom: 12 }}>以下数据基于支行长设定的经营参数自动计算</div>
                  <div className="grid-3">
                    <div style={{ textAlign: 'center', padding: '16px', background: 'var(--gray-50)', borderRadius: 8 }}>
                      <div style={{ fontSize: 26, fontWeight: 700, color: p.pre_review.eva_result >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                        {p.pre_review.eva_result !== null ? `${p.pre_review.eva_result.toFixed(2)}` : 'N/A'}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>EVA（万元）</div>
                    </div>
                    <div style={{ textAlign: 'center', padding: '16px', background: 'var(--gray-50)', borderRadius: 8 }}>
                      <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--primary)' }}>
                        {p.pre_review.rwa_result !== null ? `${p.pre_review.rwa_result.toFixed(0)}` : 'N/A'}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>RWA（万元）</div>
                    </div>
                    <div style={{ textAlign: 'center', padding: '16px', background: 'var(--gray-50)', borderRadius: 8 }}>
                      <div style={{ fontSize: 26, fontWeight: 700, color: p.pre_review.raroc_result >= 10 ? 'var(--success)' : 'var(--warning)' }}>
                        {p.pre_review.raroc_result !== null ? `${p.pre_review.raroc_result.toFixed(1)}%` : 'N/A'}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>RAROC（资本回报率）</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Tab: Materials */}
      {activeTab === 'materials' && (
        <div className="card">
          <div className="flex-between" style={{ marginBottom: 16 }}>
            <div className="section-title" style={{ marginBottom: 0 }}>业务材料清单</div>
            {isCreator && ['绿灯', '黄灯', '材料提交中', 'AI已退回', '待补充材料'].includes(p.status) && (
              <button onClick={() => navigate(`/projects/${id}/materials`)} className="btn btn-primary">管理材料</button>
            )}
          </div>
          {p.materials.length === 0 ? (
            <div className="empty-state"><div className="icon">📎</div><p>尚未生成材料清单</p></div>
          ) : (
            <table>
              <thead><tr><th>材料名称</th><th>类别</th><th>上传状态</th><th>核验结果</th></tr></thead>
              <tbody>
                {p.materials.map(m => (
                  <tr key={m.id}>
                    <td style={{ fontWeight: 500 }}>{m.material_name}</td>
                    <td><span className={`badge ${m.material_type === '必需' ? 'badge-red' : m.material_type === '条件必需' ? 'badge-yellow' : 'badge-gray'}`}>{m.material_type}</span></td>
                    <td>{m.filename ? <span style={{ color: 'var(--success)' }}>✅ {m.filename}</span> : <span style={{ color: 'var(--gray-400)' }}>未上传</span>}</td>
                    <td>
                      {m.verification_status === 'green' && <span style={{ color: 'var(--success)' }}>✅ {m.verification_notes}</span>}
                      {m.verification_status === 'yellow' && <span style={{ color: 'var(--warning)' }}>⚠️ {m.verification_notes}</span>}
                      {m.verification_status === 'red' && <span style={{ color: 'var(--danger)' }}>❌ {m.verification_notes}</span>}
                      {m.verification_status === 'pending' && <span style={{ color: 'var(--gray-400)' }}>待核验</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Tab: Approval */}
      {activeTab === 'approval' && (
        <div>
          {p.ai_approval && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="section-title">AI审批结果</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <span style={{ fontSize: 36 }}>
                  {p.ai_approval.result === '通过' ? '✅' : p.ai_approval.result === '有条件通过' ? '⚠️' : '❌'}
                </span>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: p.ai_approval.result === '通过' ? 'var(--success)' : p.ai_approval.result === '有条件通过' ? 'var(--warning)' : 'var(--danger)' }}>
                    {p.ai_approval.result}
                  </div>
                  <div style={{ color: 'var(--gray-500)', fontSize: 13 }}>建议提交层级：{p.ai_approval.suggested_level}级审批</div>
                </div>
              </div>
              <div className="grid-2">
                {[
                  ['政策合规性', p.ai_approval.policy_opinion],
                  ['风险评估', p.ai_approval.risk_opinion],
                  ['定价合理性', p.ai_approval.pricing_opinion],
                  ['材料质量', p.ai_approval.material_opinion],
                ].map(([title, content]) => (
                  <div key={title} style={{ background: 'var(--gray-50)', borderRadius: 8, padding: 14 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: 'var(--gray-700)' }}>{title}</div>
                    <pre style={{ fontSize: 12, color: 'var(--gray-600)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{content}</pre>
                  </div>
                ))}
              </div>
              {p.ai_approval.modification_suggestions?.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>修改建议清单：</div>
                  {p.ai_approval.modification_suggestions.map((s, i) => (
                    <div key={i} style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 6, padding: '8px 12px', marginBottom: 6, fontSize: 13, color: '#9a3412' }}>{s}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Approval timeline */}
          <div className="card">
            <div className="section-title">审批流转记录</div>
            {p.approval_records.length === 0 ? (
              <div className="empty-state"><div className="icon">📝</div><p>暂无审批记录</p></div>
            ) : (
              <div className="timeline">
                {p.approval_records.map(r => (
                  <div key={r.id} className="timeline-item">
                    <div className="timeline-dot" />
                    <div className="timeline-content">
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>{r.approver_name}</span>
                        <span className={`badge ${r.action.includes('通过') || r.action.includes('签字') ? 'badge-green' : r.action.includes('退回') || r.action.includes('不通过') ? 'badge-red' : 'badge-yellow'}`}>{r.action}</span>
                      </div>
                      {r.opinion && <div style={{ fontSize: 13, color: 'var(--gray-600)', marginBottom: 4 }}>{r.opinion}</div>}
                      {(r.from_level || r.to_level) && (
                        <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>
                          {r.from_level && `来自：${r.from_level}级`}
                          {r.to_level && ` → 流转至：${r.to_level}级`}
                        </div>
                      )}
                    </div>
                    <div className="timeline-meta">{new Date(r.created_at).toLocaleString('zh-CN')}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Version history (FR-08 修改历史与前后差异) */}
          {p.versions?.length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="section-title">修改历史 / 版本差异</div>
              {p.versions.map((v, i) => (
                <div key={i} style={{ border: '1px solid var(--gray-200)', borderRadius: 8, padding: 14, marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>v{v.version} {v.note}</span>
                    <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{v.created_by_name} · {new Date(v.created_at).toLocaleString('zh-CN')}</span>
                  </div>
                  {Object.keys(v.changed_fields || {}).length > 0 ? (
                    <table style={{ fontSize: 12 }}>
                      <thead><tr><th>字段</th><th>修改前</th><th>修改后</th></tr></thead>
                      <tbody>
                        {Object.entries(v.changed_fields).map(([f, c]) => (
                          <tr key={f}><td>{f}</td><td style={{ color: 'var(--danger)' }}>{String(c.from ?? '-')}</td><td style={{ color: 'var(--success)' }}>{String(c.to ?? '-')}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  ) : <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>该版本为基线快照，无字段差异</div>}
                </div>
              ))}
            </div>
          )}

          {/* Signatures */}
          {p.signatures?.length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="section-title">电子签字记录</div>
              {p.signatures.map((s, i) => (
                <div key={i} style={{ background: 'linear-gradient(135deg, #f0fdf4, white)', border: '1.5px solid #86efac', borderRadius: 10, padding: 16, marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 15, color: '#166534' }}>
                        ✅ {s.signature_level}行长 {s.signer_name} 签字完成
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>
                        证书编号：{s.certificate_no} · {new Date(s.created_at).toLocaleString('zh-CN')}
                      </div>
                    </div>
                    <span className="badge badge-green">已终审</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab: Audit */}
      {activeTab === 'audit' && (
        <div className="card">
          <div className="section-title">操作日志（不可篡改）</div>
          {auditLogs.length === 0 ? (
            <div className="empty-state"><div className="icon">🔍</div><p>暂无日志</p></div>
          ) : (
            <table>
              <thead><tr><th>时间</th><th>操作人</th><th>操作</th><th>详情</th></tr></thead>
              <tbody>
                {auditLogs.map(l => (
                  <tr key={l.id}>
                    <td style={{ fontSize: 12, color: 'var(--gray-500)', whiteSpace: 'nowrap' }}>{new Date(l.created_at).toLocaleString('zh-CN')}</td>
                    <td style={{ fontWeight: 500 }}>{l.user_name}</td>
                    <td>{l.action}</td>
                    <td style={{ fontSize: 12, color: 'var(--gray-500)' }}>{Object.entries(l.details || {}).map(([k, v]) => `${k}:${v}`).join('  ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Approval Panel Modal */}
      {showApprovalPanel && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h3>审批操作</h3>
              <button onClick={() => setShowApprovalPanel(false)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--gray-400)' }}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>审批意见</label>
                <textarea className="form-control" rows={3} value={approvalOpinion} onChange={e => setApprovalOpinion(e.target.value)} placeholder="请填写审批意见..." />
              </div>
              {(approvalAction === '上转' || approvalAction === '下转') && (
                <div className="form-group">
                  <label>流转目标层级</label>
                  <select className="form-control" value={transferLevel} onChange={e => setTransferLevel(e.target.value)}>
                    <option value="">请选择</option>
                    <option value="支行">支行</option>
                    <option value="分行">分行</option>
                    <option value="总行">总行</option>
                  </select>
                </div>
              )}
            </div>
            <div className="modal-footer" style={{ flexWrap: 'wrap', gap: 8 }}>
              <button onClick={() => { setApprovalAction(''); doAction('human-approve', { action: '通过' }) }} className="btn btn-success">✅ 通过</button>
              <button onClick={() => { setApprovalAction(''); doAction('human-approve', { action: '补充材料' }) }} className="btn btn-warning">📎 要求补充材料</button>
              <button onClick={() => { setApprovalAction(''); doAction('human-approve', { action: '退回修改' }) }} className="btn btn-danger">↩️ 退回修改</button>
              <button onClick={() => setApprovalAction(prev => prev === '上转' ? '' : '上转')} className={`btn btn-outline ${approvalAction === '上转' ? 'btn-primary' : ''}`}>⬆️ 上转</button>
              <button onClick={() => setApprovalAction(prev => prev === '下转' ? '' : '下转')} className={`btn btn-outline ${approvalAction === '下转' ? 'btn-primary' : ''}`}>⬇️ 下转</button>
              {(approvalAction === '上转' || approvalAction === '下转') && (
                <button onClick={() => doAction('human-approve', { action: approvalAction })} className="btn btn-primary">确认{approvalAction}</button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Signature Modal */}
      {showSignModal && (
        <SignatureModal
          onConfirm={(sigData, opinion) => doAction('leader-approve', { action: '通过', opinion, signature_data: sigData })}
          onCancel={() => setShowSignModal(false)}
        />
      )}
    </div>
  )
}

function InfoItem({ label, value, highlight }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 12, color: 'var(--gray-400)', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: highlight ? 700 : 400, color: highlight ? 'var(--primary)' : 'var(--gray-800)' }}>{value || '-'}</div>
    </div>
  )
}
