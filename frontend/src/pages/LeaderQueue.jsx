import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../contexts/AuthContext'

const ROLE_LABELS = { R02: '支行行长', R05: '分行行长', R07: '总行行长' }

export default function LeaderQueue() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/projects').then(r => setProjects(r.data)).finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1>待终审项目</h1>
        <p>{ROLE_LABELS[user?.role]} · {user?.branch_name} · 共 {projects.length} 个待签字项目</p>
      </div>

      <div className="alert alert-info">
        以下项目均已通过AI审批和审批员人工审核，等待您的终审签字确认。
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}><div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} /></div>
      ) : projects.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="icon">✅</div>
            <p>暂无待终审项目</p>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {projects.map(p => (
            <div key={p.id} className="card" style={{ borderLeft: '4px solid var(--warning)' }}>
              <div className="flex-between">
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 17 }}>{p.client_name}</span>
                    <span className="badge badge-orange">待行长终审</span>
                    <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{p.project_no}</span>
                  </div>
                  <div className="grid-4">
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>贷款类型</div>
                      <div style={{ fontWeight: 500 }}>{p.loan_type}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>融资金额</div>
                      <div style={{ fontWeight: 700, color: 'var(--primary)', fontSize: 16 }}>{p.loan_amount?.toLocaleString()} 万元</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>贷款利率</div>
                      <div style={{ fontWeight: 500 }}>{p.interest_rate ? `${p.interest_rate}%` : '-'}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>审批层级</div>
                      <div style={{ fontWeight: 500 }}>{p.current_approval_level}级</div>
                    </div>
                  </div>
                  <div style={{ marginTop: 10, fontSize: 12, color: 'var(--gray-400)' }}>
                    创建人：{p.creator_name} ({p.creator_branch}) · 更新：{new Date(p.updated_at).toLocaleString('zh-CN')}
                  </div>
                </div>
                <div style={{ marginLeft: 24 }}>
                  <button onClick={() => navigate(`/projects/${p.id}`)} className="btn btn-primary">
                    ✍️ 查看并终审
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
