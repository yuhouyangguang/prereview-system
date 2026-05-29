import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import StatusBadge from '../components/StatusBadge'
import { useAuth } from '../contexts/AuthContext'

const ROLE_LABELS = {
  R03: '支行审批员', R04: '分行审批员', R06: '总行审批员',
}

export default function ApprovalQueue() {
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
        <h1>审批待办列表</h1>
        <p>{ROLE_LABELS[user?.role]} · {user?.branch_name} · 共 {projects.length} 个待处理项目</p>
      </div>

      <div className="card">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} /></div>
        ) : projects.length === 0 ? (
          <div className="empty-state">
            <div className="icon">🎉</div>
            <p>暂无待审批项目</p>
          </div>
        ) : (
          <table>
            <thead><tr>
              <th>项目编号</th>
              <th>客户名称</th>
              <th>行业</th>
              <th>贷款类型</th>
              <th>金额(万)</th>
              <th>利率</th>
              <th>状态</th>
              <th>AI审批结论</th>
              <th>提交时间</th>
              <th>操作</th>
            </tr></thead>
            <tbody>
              {projects.map(p => (
                <tr key={p.id}>
                  <td><code style={{ fontSize: 12, color: 'var(--primary)' }}>{p.project_no}</code></td>
                  <td style={{ fontWeight: 600 }}>{p.client_name}</td>
                  <td style={{ color: 'var(--gray-600)' }}>{p.client_industry}</td>
                  <td>{p.loan_type}</td>
                  <td style={{ fontWeight: 600 }}>{p.loan_amount?.toLocaleString()}</td>
                  <td>{p.interest_rate ? `${p.interest_rate}%` : '-'}</td>
                  <td><StatusBadge status={p.status} /></td>
                  <td>
                    {p.status === '待人工审批' && (
                      <span className="badge badge-green">AI已通过</span>
                    )}
                    {p.status === '待补充材料' && (
                      <span className="badge badge-yellow">待补充材料</span>
                    )}
                    {p.status === '人工审批退回' && (
                      <span className="badge badge-orange">已退回修改</span>
                    )}
                  </td>
                  <td style={{ color: 'var(--gray-400)', fontSize: 12 }}>{new Date(p.updated_at).toLocaleString('zh-CN')}</td>
                  <td>
                    <button onClick={() => navigate(`/projects/${p.id}`)} className="btn btn-primary btn-sm">审批</button>
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
