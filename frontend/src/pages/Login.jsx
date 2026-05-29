import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const DEMO_ACCOUNTS = [
  { username: 'zhangwei', name: '张伟', role: '客户经理' },
  { username: 'lihua', name: '李华', role: '支行行长' },
  { username: 'wangfang', name: '王芳', role: '支行审批员' },
  { username: 'zhaoming', name: '赵明', role: '分行审批员' },
  { username: 'chenli', name: '陈丽', role: '分行行长' },
  { username: 'liuyang', name: '刘阳', role: '总行审批员' },
  { username: 'zhoujing', name: '周静', role: '总行行长' },
]

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleLogin = async e => {
    e.preventDefault()
    if (!username || !password) { setError('请填写用户名和密码'); return }
    setLoading(true); setError('')
    try {
      await login(username, password)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.error || '登录失败，请检查用户名和密码')
    } finally { setLoading(false) }
  }

  const quickLogin = async (acc) => {
    setLoading(true); setError('')
    try {
      await login(acc.username, 'password123')
      navigate('/dashboard')
    } catch { setError('快速登录失败') } finally { setLoading(false) }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex',
      background: 'linear-gradient(135deg, #001f5b 0%, #003087 50%, #0057d9 100%)',
    }}>
      {/* Left panel */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center',
        padding: '60px 80px', color: '#fff',
      }}>
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, opacity: .7, marginBottom: 8, letterSpacing: '.1em' }}>BANK OF BEIJING</div>
          <h1 style={{ fontSize: 32, fontWeight: 800, lineHeight: 1.2, marginBottom: 12 }}>
            公司业务项目<br />AI智能预审系统
          </h1>
          <p style={{ opacity: .8, fontSize: 15, lineHeight: 1.8 }}>
            覆盖支行·分行·总行三级<br />
            AI预审 · 材料核验 · 智能审批 · 电子签字
          </p>
        </div>
        <div style={{ marginTop: 48 }}>
          {['🤖 AI智能预审，快速判断项目可行性', '📊 EVA/RWA/RAROC自动测算', '🔄 三级审批流转，全程可追溯', '✍️ 电子签字，符合《电子签名法》'].map((t, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, opacity: .85, fontSize: 14 }}>
              <span style={{ fontSize: 16 }}>{t.slice(0, 2)}</span>
              <span>{t.slice(3)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel */}
      <div style={{
        width: 480, background: '#fff', display: 'flex', flexDirection: 'column',
        justifyContent: 'center', padding: '48px 48px', overflowY: 'auto',
      }}>
        <div style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>欢迎登录</h2>
          <p style={{ color: 'var(--gray-500)', fontSize: 14 }}>请使用您的工号和密码登录</p>
        </div>

        <form onSubmit={handleLogin}>
          {error && <div className="alert alert-danger">{error}</div>}
          <div className="form-group">
            <label>用户名</label>
            <input className="form-control" value={username} onChange={e => setUsername(e.target.value)} placeholder="请输入用户名" autoFocus />
          </div>
          <div className="form-group">
            <label>密码</label>
            <input type="password" className="form-control" value={password} onChange={e => setPassword(e.target.value)} placeholder="请输入密码" />
          </div>
          <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%', marginTop: 8 }} disabled={loading}>
            {loading ? <><span className="spinner" style={{ width: 16, height: 16 }} /> 登录中...</> : '登 录'}
          </button>
        </form>

        <div className="divider" />
        <div>
          <p style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 12, fontWeight: 600 }}>演示账号（密码均为 password123）：</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {DEMO_ACCOUNTS.map(acc => (
              <button key={acc.username} onClick={() => quickLogin(acc)} style={{
                padding: '9px 12px', border: '1.5px solid var(--gray-200)',
                borderRadius: 8, background: '#fff', cursor: 'pointer', textAlign: 'left',
                transition: 'all .15s', fontSize: 13,
              }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--primary)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--gray-200)'}
              >
                <div style={{ fontWeight: 600, color: 'var(--gray-800)' }}>{acc.name}</div>
                <div style={{ color: 'var(--primary-light)', fontSize: 12 }}>{acc.role}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
