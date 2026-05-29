import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../services/api'

export default function MaterialVerification() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [checklist, setChecklist] = useState([])
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [uploadingId, setUploadingId] = useState(null)

  useEffect(() => {
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/projects/${id}/material-checklist`),
    ]).then(([p, c]) => {
      setProject(p.data)
      setChecklist(c.data)
    }).finally(() => setLoading(false))
  }, [id])

  const simulateUpload = async (item) => {
    setUploadingId(item.material_name); setError('')
    try {
      const fakeFilename = `${item.material_name.replace(/[\/\s]/g, '_')}_${Date.now()}.pdf`
      await api.post(`/projects/${id}/upload-material`, {
        material_name: item.material_name,
        material_type: item.material_type,
        filename: fakeFilename,
      })
      const c = await api.get(`/projects/${id}/material-checklist`)
      setChecklist(c.data)
    } catch (err) {
      setError(err.response?.data?.error || '上传失败')
    } finally { setUploadingId(null) }
  }

  const doVerify = async () => {
    setVerifying(true); setError('')
    try {
      await api.post(`/projects/${id}/ai-verify-materials`)
      const [p, c] = await Promise.all([
        api.get(`/projects/${id}`),
        api.get(`/projects/${id}/material-checklist`),
      ])
      setProject(p.data)
      setChecklist(c.data)
    } catch (err) {
      setError(err.response?.data?.error || '核验失败')
    } finally { setVerifying(false) }
  }

  const doAIApproval = async () => {
    setSubmitting(true); setError('')
    try {
      await api.post(`/projects/${id}/ai-approval`)
      navigate(`/projects/${id}`)
    } catch (err) {
      setError(err.response?.data?.error || '提交AI审批失败')
    } finally { setSubmitting(false) }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} /></div>

  const required = checklist.filter(m => m.material_type === '必需')
  const conditional = checklist.filter(m => m.material_type === '条件必需')
  const supplemental = checklist.filter(m => m.material_type === '补充参考')
  const uploadedRequired = required.filter(m => m.filename).length
  const allRequiredUploaded = uploadedRequired === required.length
  const hasVerified = checklist.some(m => m.verification_status !== 'pending')

  const getStatusIcon = (status) => {
    if (status === 'green') return <span style={{ color: 'var(--success)' }}>✅</span>
    if (status === 'yellow') return <span style={{ color: 'var(--warning)' }}>⚠️</span>
    if (status === 'red') return <span style={{ color: 'var(--danger)' }}>❌</span>
    return <span style={{ color: 'var(--gray-400)' }}>○</span>
  }

  return (
    <div>
      <div className="page-header">
        <div className="flex-between">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
              <button onClick={() => navigate(`/projects/${id}`)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', fontSize: 20 }}>←</button>
              <h1>业务材料AI核验</h1>
            </div>
            <p style={{ marginLeft: 36 }}>{project?.client_name} · {project?.loan_type}</p>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {/* Progress bar */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="flex-between" style={{ marginBottom: 10 }}>
          <div style={{ fontWeight: 600 }}>必需材料上传进度</div>
          <div style={{ fontSize: 13, color: 'var(--gray-500)' }}>{uploadedRequired} / {required.length} 已上传</div>
        </div>
        <div style={{ height: 8, background: 'var(--gray-200)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ height: '100%', background: allRequiredUploaded ? 'var(--success)' : 'var(--primary)', borderRadius: 4, width: `${required.length ? (uploadedRequired / required.length) * 100 : 0}%`, transition: 'width .3s' }} />
        </div>
        <div className="alert alert-info" style={{ marginTop: 12, marginBottom: 0 }}>
          材料按 <strong>必需 / 条件必需 / 补充参考</strong> 三级分类。点击「模拟上传」演示文件上传，完成后点击「AI核验」。
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
        {[
          { items: required, title: '🔴 必需材料', desc: '必须提交，缺失将导致AI审批不通过' },
          { items: conditional, title: '🟡 条件必需材料', desc: '根据业务类型和担保方式需要提交' },
          { items: supplemental, title: '⚪ 补充参考材料', desc: '有助于提升审批通过率' },
        ].map(({ items, title, desc }) => items.length > 0 && (
          <div key={title} className="card">
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>{title}</div>
              <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>{desc}</div>
            </div>
            <table>
              <thead><tr>
                <th>材料名称</th>
                <th>上传状态</th>
                <th>核验结果</th>
                <th>操作</th>
              </tr></thead>
              <tbody>
                {items.map(m => (
                  <tr key={m.material_name}>
                    <td style={{ fontWeight: 500 }}>{m.material_name}</td>
                    <td>
                      {m.filename
                        ? <span style={{ color: 'var(--success)', fontSize: 13 }}>✅ {m.filename}</span>
                        : <span style={{ color: 'var(--gray-400)', fontSize: 13 }}>未上传</span>
                      }
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {getStatusIcon(m.verification_status)}
                        <span style={{ fontSize: 12, color: 'var(--gray-600)' }}>
                          {m.verification_notes || (m.verification_status === 'pending' ? '待核验' : '')}
                        </span>
                      </div>
                    </td>
                    <td>
                      <button
                        onClick={() => simulateUpload(m)}
                        className="btn btn-outline btn-sm"
                        disabled={uploadingId === m.material_name}
                      >
                        {uploadingId === m.material_name ? <span className="spinner" style={{ width: 12, height: 12 }} /> : m.filename ? '重新上传' : '模拟上传'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--gray-200)' }}>
        <button onClick={() => navigate(`/projects/${id}`)} className="btn btn-ghost">返回详情</button>
        <button onClick={doVerify} className="btn btn-warning" disabled={verifying || !checklist.some(m => m.filename)}>
          {verifying ? <><span className="spinner" style={{ width: 14, height: 14 }} /> AI核验中...</> : '🔍 AI核验全部材料'}
        </button>
        <button
          onClick={doAIApproval}
          className="btn btn-primary btn-lg"
          disabled={submitting || !hasVerified}
        >
          {submitting ? <><span className="spinner" style={{ width: 14, height: 14 }} /> 提交中...</> : '🤖 提交AI审批'}
        </button>
      </div>
      {!hasVerified && <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--gray-400)', marginTop: 6 }}>请先完成AI核验后方可提交AI审批</div>}
    </div>
  )
}
