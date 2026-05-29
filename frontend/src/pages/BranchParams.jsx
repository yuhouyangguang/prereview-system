import React, { useState, useEffect } from 'react'
import api from '../services/api'
import { useAuth } from '../contexts/AuthContext'

const BUSINESS_TYPES = ['通用', '流动资金贷款', '固定资产贷款', '贸易融资', '银行承兑汇票', '保函']

const PARAM_FIELDS = [
  { key: 'capital_cost_rate', label: '经济资本成本率', unit: '%', desc: '资本占用的机会成本', min: 0, max: 30 },
  { key: 'operating_cost_rate', label: '经营费用率', unit: '%', desc: '运营管理成本', min: 0, max: 10 },
  { key: 'risk_weight_coeff', label: '风险权重调整系数', unit: '', desc: '风险加权资产计算系数', min: 0.1, max: 3 },
  { key: 'loan_ftp_rate', label: '贷款FTP基准利率', unit: '%', desc: '内部资金转移定价—贷款', min: 0, max: 10 },
  { key: 'deposit_ftp_rate', label: '存款FTP基准利率', unit: '%', desc: '内部资金转移定价—存款', min: 0, max: 5 },
  { key: 'tax_rate', label: '税收调整参数', unit: '%', desc: '所得税率（影响EVA税后计算）', min: 0, max: 50 },
  { key: 'expected_loss_rate', label: '预期损失率', unit: '%', desc: '预期信用损失率', min: 0, max: 10 },
]

const DEFAULT_PARAMS = { capital_cost_rate: 10.5, operating_cost_rate: 1.5, risk_weight_coeff: 1.0, loan_ftp_rate: 3.0, deposit_ftp_rate: 1.5, tax_rate: 25.0, expected_loss_rate: 0.5 }

export default function BranchParams() {
  const { user } = useAuth()
  const [activeType, setActiveType] = useState('通用')
  const [params, setParams] = useState({})
  const [editing, setEditing] = useState(false)
  const [editValues, setEditValues] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')
  const [logs, setLogs] = useState([])
  const [showLogs, setShowLogs] = useState(false)

  useEffect(() => {
    api.get('/branch-params').then(r => {
      const map = {}
      r.data.forEach(p => { map[p.business_type] = p })
      setParams(map)
    }).finally(() => setLoading(false))
  }, [])

  const current = params[activeType] || { ...DEFAULT_PARAMS, business_type: activeType }

  const startEdit = () => {
    setEditValues({ ...current })
    setEditing(true)
    setSuccess('')
    setError('')
  }

  const handleSave = async () => {
    if (!window.confirm(`保存后，所有未归档项目将采用新参数重新计算 EVA/RWA/RAROC。确认保存吗？`)) return
    setSaving(true); setError('')
    try {
      await api.post('/branch-params', { ...editValues, business_type: activeType })
      const r = await api.get('/branch-params')
      const map = {}
      r.data.forEach(p => { map[p.business_type] = p })
      setParams(map)
      setEditing(false)
      setSuccess(`${activeType} 参数已成功保存`)
    } catch (err) {
      setError(err.response?.data?.error || '保存失败')
    } finally { setSaving(false) }
  }

  const loadLogs = async () => {
    const r = await api.get('/branch-params/logs')
    setLogs(r.data)
    setShowLogs(true)
  }

  if (user?.role !== 'R02') {
    return <div className="card"><div className="empty-state"><div className="icon">🔒</div><p>仅支行行长可访问此页面</p></div></div>
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} /></div>

  return (
    <div>
      <div className="page-header">
        <div className="flex-between">
          <div>
            <h1>⚙️ 支行经营参数管理</h1>
            <p>{user?.branch_name} · 参数设置权限专属于支行行长</p>
          </div>
          <button onClick={loadLogs} className="btn btn-ghost">📋 查看变更历史</button>
        </div>
      </div>

      <div className="alert alert-info">
        EVA/RWA/RAROC 测算所需参数由支行行长统一设置。客户经理提交项目时自动引用，无需逐笔填写。支行长修改参数后，所有未归档项目将实时更新测算结果。
      </div>

      {success && <div className="alert alert-success">✅ {success}</div>}
      {error && <div className="alert alert-danger">{error}</div>}

      {/* Business type tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {BUSINESS_TYPES.map(t => (
          <button key={t} onClick={() => { setActiveType(t); setEditing(false) }} style={{
            padding: '8px 16px', borderRadius: 8, border: '1.5px solid',
            borderColor: activeType === t ? 'var(--primary)' : 'var(--gray-200)',
            background: activeType === t ? 'var(--primary)' : '#fff',
            color: activeType === t ? '#fff' : 'var(--gray-700)',
            fontWeight: activeType === t ? 600 : 400, fontSize: 13, cursor: 'pointer',
          }}>{t}</button>
        ))}
      </div>

      <div className="card">
        <div className="flex-between" style={{ marginBottom: 20 }}>
          <div className="section-title" style={{ marginBottom: 0 }}>
            {activeType} — 经营参数
          </div>
          <div className="flex gap-2">
            {!editing ? (
              <button onClick={startEdit} className="btn btn-primary">✏️ 编辑参数</button>
            ) : (
              <>
                <button onClick={() => setEditing(false)} className="btn btn-ghost">取消</button>
                <button onClick={handleSave} className="btn btn-success" disabled={saving}>
                  {saving ? <><span className="spinner" style={{ width: 14, height: 14 }} /> 保存中...</> : '💾 保存参数'}
                </button>
              </>
            )}
          </div>
        </div>

        {current.updated_by_name && (
          <div style={{ marginBottom: 16, padding: '8px 12px', background: 'var(--gray-50)', borderRadius: 6, fontSize: 12, color: 'var(--gray-500)' }}>
            最后更新：{current.updated_by_name} · {current.updated_at ? new Date(current.updated_at).toLocaleString('zh-CN') : '-'}
          </div>
        )}

        <table>
          <thead><tr>
            <th>参数项</th>
            <th>说明</th>
            <th>总行基准</th>
            <th>当前值</th>
            {editing && <th>修改</th>}
          </tr></thead>
          <tbody>
            {PARAM_FIELDS.map(f => (
              <tr key={f.key}>
                <td style={{ fontWeight: 600 }}>{f.label}</td>
                <td style={{ color: 'var(--gray-500)', fontSize: 12 }}>{f.desc}</td>
                <td style={{ color: 'var(--gray-400)' }}>{DEFAULT_PARAMS[f.key]}{f.unit}</td>
                <td style={{ fontWeight: 700, color: 'var(--primary)', fontSize: 15 }}>
                  {current[f.key]}{f.unit}
                </td>
                {editing && (
                  <td>
                    <input
                      type="number" step="0.01" min={f.min} max={f.max}
                      className="form-control" style={{ width: 120 }}
                      value={editValues[f.key] ?? ''}
                      onChange={e => setEditValues(v => ({ ...v, [f.key]: parseFloat(e.target.value) }))}
                    />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>

        {!editing && (
          <div style={{ marginTop: 20, padding: 16, background: 'linear-gradient(135deg, #f0f7ff, white)', borderRadius: 10, border: '1px solid #bfdbfe' }}>
            <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>📊 EVA/RWA/RAROC 公式说明</div>
            <div className="grid-3" style={{ fontSize: 12, color: 'var(--gray-600)', gap: 12 }}>
              <div style={{ background: '#fff', padding: 12, borderRadius: 8, border: '1px solid var(--gray-200)' }}>
                <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--gray-800)' }}>EVA（经济增加值）</div>
                <div style={{ lineHeight: 1.8 }}>
                  (贷款利率 - FTP利率 - 经营费用率<br />
                  - 预期损失率 - 资本成本率×8%×风险权重系数)<br />
                  × 贷款金额
                </div>
              </div>
              <div style={{ background: '#fff', padding: 12, borderRadius: 8, border: '1px solid var(--gray-200)' }}>
                <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--gray-800)' }}>RWA（风险加权资产）</div>
                <div style={{ lineHeight: 1.8 }}>
                  贷款金额 × 100%<br />
                  × 风险权重调整系数
                </div>
              </div>
              <div style={{ background: '#fff', padding: 12, borderRadius: 8, border: '1px solid var(--gray-200)' }}>
                <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--gray-800)' }}>RAROC（风险调整资本回报率）</div>
                <div style={{ lineHeight: 1.8 }}>
                  税后净收入 ÷ 经济资本<br />
                  = 净利差×贷款×(1-税率)<br />
                  ÷ (贷款×8%×风险权重)
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Change log modal */}
      {showLogs && (
        <div className="modal-overlay">
          <div className="modal" style={{ maxWidth: 700 }}>
            <div className="modal-header">
              <h3>📋 参数变更历史</h3>
              <button onClick={() => setShowLogs(false)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--gray-400)' }}>×</button>
            </div>
            <div className="modal-body">
              {logs.length === 0 ? (
                <div className="empty-state"><p>暂无变更记录</p></div>
              ) : logs.map(l => (
                <div key={l.id} style={{ padding: '12px 0', borderBottom: '1px solid var(--gray-100)' }}>
                  <div className="flex-between" style={{ marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>{l.business_type} 参数变更</span>
                    <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{l.changed_by_name} · {new Date(l.created_at).toLocaleString('zh-CN')}</span>
                  </div>
                  <div className="grid-2" style={{ fontSize: 12 }}>
                    <div>
                      <span style={{ color: 'var(--danger)' }}>变更前：</span>
                      {Object.entries(l.old_values || {}).map(([k, v]) => {
                        const field = PARAM_FIELDS.find(f => f.key === k)
                        return <div key={k} style={{ color: 'var(--gray-500)' }}>{field?.label}: {v}{field?.unit}</div>
                      })}
                    </div>
                    <div>
                      <span style={{ color: 'var(--success)' }}>变更后：</span>
                      {Object.entries(l.new_values || {}).map(([k, v]) => {
                        const field = PARAM_FIELDS.find(f => f.key === k)
                        const old = l.old_values?.[k]
                        const changed = old !== undefined && old !== v
                        return <div key={k} style={{ color: changed ? 'var(--primary)' : 'var(--gray-500)', fontWeight: changed ? 600 : 400 }}>{field?.label}: {v}{field?.unit}{changed ? ' ←' : ''}</div>
                      })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowLogs(false)} className="btn btn-ghost">关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
