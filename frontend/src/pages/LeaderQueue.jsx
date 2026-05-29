import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import StatusBadge from '../components/StatusBadge'
import { useAuth } from '../contexts/AuthContext'

const ROLE_LABELS = { R02: '支行行长', R05: '分行行长', R07: '总行行长' }

export default function LeaderQueue() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState('pending')
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const url = tab === 'done' ? '/projects?done=1' : '/projects'
    api.get(url).then(r => setProjects(r.data)).finally(() => setLoading(false))
  }, [tab])

  const tabStyle = (t) => ({
    padding: '8px 20px', border: 'none', cursor: 'pointer',
    borderBottom: tab === t ? '2px solid var(--primary)' : '2px solid transparent',
    color: tab === t ? 'var(--primary)' : 'var(--gray-500)',
    fontWeight: tab === t ? 700 : 400,
    background: 'transparent', fontSize: 14,
  })

  return (
    <div>
      <div className="page-header">
        <h1>{tab === 'done' ? '已终审项目' : '待终审项目'}</h1>
        <p>{ROLE_LABELS[user?.role]} · {user?.branch_name} · 共 {projects.length} 个项目</p>
      </div>

      {/* 标签页 */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--gray-200)', marginBottom: 16 }}>
        <button style={tabStyle('pending')} onClick={() => setTab('pending')}>
          待终审
          {tab === 'pending' && projects.length > 0 && (
            <span style={{
              marginLeft: 6, background: 'var(--danger)', color: '#fff',
              borderRadius: '99px', fontSize: 11, padding: '1px 6px',
            }}>{projects.length}</span>
          )}
        </button>
        <button style={tabStyle('done')} onClick={() => setTab('done')}>
          已终审
          {tab === 'done' && projects.length > 0 && (
            <span style={{
              marginLeft: 6, background: 'var(--gray-300)', color: 'var(--gray-700)',
              borderRadius: '99px', fontSize: 11, padding: '1px 6px',
            }}>{projects.length}</span>
          )}
        </button>
      </div>

      {tab === 'pending' && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          以下项目均已通过AI审批和审批员人工审核，等待您的终审签字确认。
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
        </div>
      ) : projects.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="icon">{tab === 'done' ? '📂' : '✅'}</div>
            <p>{tab === 'done' ? '暂无已终审项目' : '暂无待终审项目'}</p>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {projects.map(p => {
            const isDone = tab === 'done'
            const borderColor = isDone
              ? (p.status === '已终审' ? 'var(--success)' : 'var(--danger)')
              : 'var(--warning)'
            return (
              <div key={p.id} className="card" style={{ borderLeft: `4px solid ${borderColor}` }}>
                <div className="flex-between">
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 700, fontSize: 17 }}>{p.client_name}</span>
                      <StatusBadge status={p.status} />
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
                    {isDone && p.my_last_opinion && (
                      <div style={{ marginTop: 10, padding: '8px 12px', background: 'var(--gray-50)', borderRadius: 6, fontSize: 12, color: 'var(--gray-600)' }}>
                        <span style={{ fontWeight: 600, marginRight: 6 }}>终审意见：</span>{p.my_last_opinion}
                      </div>
                    )}
                    <div style={{ marginTop: 10, fontSize: 12, color: 'var(--gray-400)' }}>
                      创建人：{p.creator_name} ({p.creator_branch}) · {isDone ? '终审时间' : '更新'}：{new Date(isDone && p.my_acted_at ? p.my_acted_at : p.updated_at).toLocaleString('zh-CN')}
                    </div>
                  </div>
                  <div style={{ marginLeft: 24, flexShrink: 0 }}>
                    <button
                      onClick={() => navigate(`/projects/${p.id}`)}
                      className={`btn ${isDone ? 'btn-ghost' : 'btn-primary'}`}
                    >
                      {isDone ? '📄 查看详情' : '✍️ 查看并终审'}
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
