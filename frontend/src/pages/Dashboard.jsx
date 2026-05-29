import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import api from '../services/api'
import StatusBadge from '../components/StatusBadge'

const ROLE_LABELS = {
  R01: '客户经理', R02: '支行行长', R03: '支行审批员',
  R04: '分行审批员', R05: '分行行长', R06: '总行审批员', R07: '总行行长',
}

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState({ total: 0, green: 0, approved: 0, pending: 0 })
  const [recentProjects, setRecentProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get('/stats'),
      api.get('/projects'),
    ]).then(([s, p]) => {
      setStats(s.data)
      setRecentProjects(p.data.slice(0, 5))
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} /></div>

  const quickActions = () => {
    const r = user?.role
    if (r === 'R01') return [
      { label: '新建项目', icon: '➕', to: '/projects/create', color: 'var(--primary)' },
      { label: '我的项目', icon: '📁', to: '/projects', color: 'var(--info)' },
    ]
    if (['R03', 'R04', 'R06'].includes(r)) return [
      { label: '审批待办', icon: '📋', to: '/approval-queue', color: 'var(--warning)' },
      { label: '项目总览', icon: '🗂️', to: '/all-projects', color: 'var(--info)' },
    ]
    if (['R02', 'R05', 'R07'].includes(r)) return [
      { label: '待我终审', icon: '✍️', to: '/leader-queue', color: 'var(--danger)' },
      { label: '经营参数', icon: '⚙️', to: '/branch-params', color: 'var(--success)' },
      { label: '项目总览', icon: '🗂️', to: '/all-projects', color: 'var(--info)' },
    ]
    return []
  }

  return (
    <div>
      <div className="page-header">
        <h1>你好，{user?.name} 👋</h1>
        <p>{user?.branch_name} · {ROLE_LABELS[user?.role]} · {new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })}</p>
      </div>

      {/* Stats */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="value" style={{ color: 'var(--primary)' }}>{stats.total}</div>
          <div className="label">📁 项目总数</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: 'var(--warning)' }}>{stats.pending}</div>
          <div className="label">⏳ 待处理</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: 'var(--success)' }}>{stats.green}</div>
          <div className="label">🟢 {user?.role === 'R01' ? '预审绿灯' : '已终审'}</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: '#8b5cf6' }}>{stats.approved}</div>
          <div className="label">✅ 已完成</div>
        </div>
      </div>

      <div className="dashboard-main-grid">
        {/* Recent projects */}
        <div className="card">
          <div className="flex-between" style={{ marginBottom: 16 }}>
            <div className="section-title" style={{ marginBottom: 0 }}>
              {user?.role === 'R01' ? '我的最近项目' : '最新待处理'}
            </div>
            <Link to={['R03','R04','R06'].includes(user?.role) ? '/approval-queue' : ['R02','R05','R07'].includes(user?.role) ? '/leader-queue' : '/projects'} style={{ fontSize: 13, color: 'var(--primary-light)' }}>查看全部 →</Link>
          </div>
          {recentProjects.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📋</div>
              <p>暂无项目数据</p>
              {user?.role === 'R01' && <Link to="/projects/create" className="btn btn-primary" style={{ marginTop: 16 }}>创建第一个项目</Link>}
            </div>
          ) : (
            <table>
              <thead><tr>
                <th>项目编号</th>
                <th>客户名称</th>
                <th>贷款金额(万)</th>
                <th>状态</th>
                <th>更新时间</th>
              </tr></thead>
              <tbody>
                {recentProjects.map(p => (
                  <tr key={p.id} onClick={() => navigate(`/projects/${p.id}`)} style={{ cursor: 'pointer' }}>
                    <td><code style={{ fontSize: 12, color: 'var(--primary)' }}>{p.project_no}</code></td>
                    <td style={{ fontWeight: 500 }}>{p.client_name || '-'}</td>
                    <td>{p.loan_amount?.toLocaleString() || '-'}</td>
                    <td><StatusBadge status={p.status} /></td>
                    <td style={{ color: 'var(--gray-400)', fontSize: 12 }}>{new Date(p.updated_at).toLocaleDateString('zh-CN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Quick actions + guide */}
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">快捷操作</div>
            {quickActions().map(a => (
              <button key={a.to} onClick={() => navigate(a.to)} style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 12,
                padding: '12px 14px', marginBottom: 8, borderRadius: 8,
                border: '1.5px solid var(--gray-200)', background: '#fff',
                cursor: 'pointer', fontSize: 14, fontWeight: 500,
                transition: 'all .15s',
              }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = a.color; e.currentTarget.style.background = '#f8faff' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--gray-200)'; e.currentTarget.style.background = '#fff' }}
              >
                <span style={{ fontSize: 20 }}>{a.icon}</span>
                <span>{a.label}</span>
              </button>
            ))}
          </div>

          <div className="card">
            <div className="section-title">业务流程</div>
            {[
              { step: '1', text: '创建项目基本信息', role: 'R01' },
              { step: '2', text: 'AI预审 → 绿/黄/红灯', role: 'R01' },
              { step: '3', text: '上传材料 + AI核验', role: 'R01' },
              { step: '4', text: 'AI自动审批', role: 'R01' },
              { step: '5', text: '审批员人工审核', role: 'R03/R04/R06' },
              { step: '6', text: '行长终审签字', role: 'R02/R05/R07' },
              { step: '7', text: '项目已终审归档', role: 'ALL' },
            ].map(s => (
              <div key={s.step} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
                <div style={{
                  width: 22, height: 22, borderRadius: '50%', background: 'var(--primary)',
                  color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1,
                }}>{s.step}</div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{s.text}</div>
                  <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>{s.role}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
