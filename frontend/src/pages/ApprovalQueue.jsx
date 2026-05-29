import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import StatusBadge from '../components/StatusBadge'
import { useAuth } from '../contexts/AuthContext'

const ROLE_LABELS = {
  R03: '支行审批员', R04: '分行审批员', R06: '总行审批员',
}

const ACTION_BADGE = {
  '通过': { cls: 'badge-green', text: '已通过' },
  '补充材料': { cls: 'badge-yellow', text: '要求补充' },
  '退回修改': { cls: 'badge-orange', text: '已退回' },
  '上转': { cls: 'badge-blue', text: '已上转' },
  '下转': { cls: 'badge-blue', text: '已下转' },
}

export default function ApprovalQueue() {
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
        <h1>审批工作列表</h1>
        <p>{ROLE_LABELS[user?.role]} · {user?.branch_name}</p>
      </div>

      {/* 标签页 */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--gray-200)', marginBottom: 16 }}>
        <button style={tabStyle('pending')} onClick={() => setTab('pending')}>
          待办审批
          {tab === 'pending' && projects.length > 0 && (
            <span style={{
              marginLeft: 6, background: 'var(--danger)', color: '#fff',
              borderRadius: '99px', fontSize: 11, padding: '1px 6px',
            }}>{projects.length}</span>
          )}
        </button>
        <button style={tabStyle('done')} onClick={() => setTab('done')}>
          已办记录
          {tab === 'done' && projects.length > 0 && (
            <span style={{
              marginLeft: 6, background: 'var(--gray-300)', color: 'var(--gray-700)',
              borderRadius: '99px', fontSize: 11, padding: '1px 6px',
            }}>{projects.length}</span>
          )}
        </button>
      </div>

      <div className="card">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
          </div>
        ) : projects.length === 0 ? (
          <div className="empty-state">
            <div className="icon">{tab === 'done' ? '📂' : '🎉'}</div>
            <p>{tab === 'done' ? '暂无已审批记录' : '暂无待审批项目'}</p>
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
              {tab === 'pending' ? (
                <th>AI审批结论</th>
              ) : (
                <>
                  <th>我的审批动作</th>
                  <th>审批意见</th>
                </>
              )}
              <th>{tab === 'done' ? '审批时间' : '提交时间'}</th>
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
                  {tab === 'pending' ? (
                    <td>
                      {p.status === '待人工审批' && <span className="badge badge-green">AI已通过</span>}
                      {p.status === '待补充材料' && <span className="badge badge-yellow">待补充材料</span>}
                      {p.status === '人工审批退回' && <span className="badge badge-orange">已退回修改</span>}
                    </td>
                  ) : (
                    <>
                      <td>
                        {p.my_last_action ? (
                          <span className={`badge ${(ACTION_BADGE[p.my_last_action] || {}).cls || 'badge-gray'}`}>
                            {(ACTION_BADGE[p.my_last_action] || {}).text || p.my_last_action}
                          </span>
                        ) : '-'}
                      </td>
                      <td style={{ maxWidth: 180, color: 'var(--gray-600)', fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {p.my_last_opinion || '-'}
                      </td>
                    </>
                  )}
                  <td style={{ color: 'var(--gray-400)', fontSize: 12 }}>
                    {new Date(tab === 'done' && p.my_acted_at ? p.my_acted_at : p.updated_at).toLocaleString('zh-CN')}
                  </td>
                  <td>
                    <button
                      onClick={() => navigate(`/projects/${p.id}`)}
                      className={`btn btn-sm ${tab === 'done' ? 'btn-ghost' : 'btn-primary'}`}
                    >
                      {tab === 'done' ? '查看' : '审批'}
                    </button>
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
