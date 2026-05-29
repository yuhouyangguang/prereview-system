import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import StatusBadge from '../components/StatusBadge'
import { useAuth } from '../contexts/AuthContext'

export default function ProjectList({ showAll = false }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    api.get('/projects' + (statusFilter ? `?status=${statusFilter}` : ''))
      .then(r => setProjects(r.data))
      .finally(() => setLoading(false))
  }, [statusFilter])

  const filtered = projects.filter(p =>
    !search ||
    p.client_name?.includes(search) ||
    p.project_no?.includes(search) ||
    p.client_industry?.includes(search)
  )

  return (
    <div>
      <div className="page-header">
        <div className="flex-between">
          <div>
            <h1>{showAll ? '项目总览' : '我的项目'}</h1>
            <p>共 {filtered.length} 个项目</p>
          </div>
          {user?.role === 'R01' && (
            <Link to="/projects/create" className="btn btn-primary">➕ 新建项目</Link>
          )}
        </div>
      </div>

      <div className="card">
        <div className="flex gap-3" style={{ marginBottom: 16 }}>
          <input className="form-control" style={{ maxWidth: 300 }} placeholder="搜索客户名称、项目编号..."
            value={search} onChange={e => setSearch(e.target.value)} />
          <select className="form-control" style={{ maxWidth: 180 }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">全部状态</option>
            <option value="draft">草稿</option>
            <option value="绿灯">绿灯</option>
            <option value="黄灯">黄灯</option>
            <option value="红灯">红灯</option>
            <option value="材料提交中">材料提交中</option>
            <option value="AI已退回">AI已退回</option>
            <option value="待人工审批">待人工审批</option>
            <option value="待行长终审">待行长终审</option>
            <option value="已终审">已终审</option>
          </select>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} /></div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="icon">📁</div>
            <p>暂无项目</p>
            {user?.role === 'R01' && <Link to="/projects/create" className="btn btn-primary" style={{ marginTop: 16 }}>创建项目</Link>}
          </div>
        ) : (
          <table>
            <thead><tr>
              <th>项目编号</th>
              <th>客户名称</th>
              <th>行业</th>
              <th>贷款类型</th>
              <th>金额(万)</th>
              <th>利率(%)</th>
              {showAll && <th>创建人</th>}
              <th>状态</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr></thead>
            <tbody>
              {filtered.map(p => (
                <tr key={p.id}>
                  <td><code style={{ fontSize: 12, color: 'var(--primary)' }}>{p.project_no}</code></td>
                  <td style={{ fontWeight: 500 }}>{p.client_name || '-'}</td>
                  <td style={{ color: 'var(--gray-600)' }}>{p.client_industry || '-'}</td>
                  <td style={{ color: 'var(--gray-600)' }}>{p.loan_type || '-'}</td>
                  <td style={{ fontWeight: 600 }}>{p.loan_amount?.toLocaleString() || '-'}</td>
                  <td>{p.interest_rate ? `${p.interest_rate}%` : '-'}</td>
                  {showAll && <td style={{ fontSize: 12, color: 'var(--gray-500)' }}>{p.creator_name}<br/>{p.creator_branch}</td>}
                  <td><StatusBadge status={p.status} /></td>
                  <td style={{ color: 'var(--gray-400)', fontSize: 12 }}>{new Date(p.updated_at).toLocaleDateString('zh-CN')}</td>
                  <td>
                    <button onClick={() => navigate(`/projects/${p.id}`)} className="btn btn-outline btn-sm">查看</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
