import React, { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import api from '../services/api'

const ROLE_LABELS = {
  R01: '客户经理', R02: '支行行长', R03: '支行审批员',
  R04: '分行审批员', R05: '分行行长', R06: '总行审批员', R07: '总行行长',
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return isMobile
}

export default function Layout({ children }) {
  const { user, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const isMobile = useIsMobile()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [showNotif, setShowNotif] = useState(false)
  const [notifications, setNotifications] = useState([])

  // 路由跳转时自动关闭移动端侧边栏
  useEffect(() => {
    if (isMobile) setSidebarOpen(false)
  }, [location.pathname])

  useEffect(() => {
    // 初始加载未读数
    api.get('/auth/me').then(r => setUnread(r.data.unread_count || 0)).catch(() => {})

    // SSE 实时通知（失败自动降级轮询）
    const token = localStorage.getItem('token')
    if (!token) return
    let es = null
    let fallback = null
    let lastId = 0

    const connectSSE = () => {
      es = new EventSource(`/api/notifications/stream?token=${encodeURIComponent(token)}&last_id=${lastId}`)
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'notification') {
            lastId = data.id
            if (!data.is_read) setUnread(prev => prev + 1)
            setNotifications(prev => [data, ...prev].slice(0, 50))
          }
        } catch (_) {}
      }
      es.onerror = () => {
        es.close()
        // 降级到 15s 轮询
        fallback = setInterval(() => {
          api.get('/auth/me').then(r => setUnread(r.data.unread_count || 0)).catch(() => {})
        }, 15000)
      }
    }

    connectSSE()
    return () => {
      if (es) es.close()
      if (fallback) clearInterval(fallback)
    }
  }, [])

  const loadNotifications = async () => {
    const r = await api.get('/notifications')
    setNotifications(r.data)
    setShowNotif(true)
  }

  const markAllRead = async () => {
    await api.put('/notifications/read-all')
    setUnread(0)
    setNotifications(ns => ns.map(n => ({ ...n, is_read: true })))
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navLinks = () => {
    const role = user?.role
    const links = [{ to: '/dashboard', label: '工作台', icon: '🏠' }]
    if (role === 'R01') {
      links.push({ to: '/projects', label: '我的项目', icon: '📁' })
      links.push({ to: '/projects/create', label: '新建项目', icon: '➕' })
    }
    if (['R03', 'R04', 'R06'].includes(role)) {
      links.push({ to: '/approval-queue', label: '审批待办', icon: '📋' })
    }
    if (['R02', 'R05', 'R07'].includes(role)) {
      links.push({ to: '/leader-queue', label: '待我终审', icon: '✍️' })
      links.push({ to: '/leader-stats', label: '绩效统计', icon: '📈' })
    }
    if (role === 'R02') {
      links.push({ to: '/branch-params', label: '经营参数', icon: '⚙️' })
    }
    if (['R03', 'R04', 'R06'].includes(role)) {
      links.push({ to: '/knowledge-base', label: '信贷知识库', icon: '📚' })
    }
    links.push({ to: '/all-projects', label: '项目总览', icon: '🗂️' })
    return links
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* 移动端遮罩 */}
      {isMobile && sidebarOpen && (
        <div onClick={() => setSidebarOpen(false)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 99,
        }} />
      )}

      {/* Sidebar */}
      <aside style={{
        width: 220, background: 'var(--primary-dark)', color: '#fff',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: 'fixed', top: 0, left: 0, bottom: 0, zIndex: 100,
        transform: isMobile && !sidebarOpen ? 'translateX(-100%)' : 'translateX(0)',
        transition: 'transform .25s ease',
      }}>
        <div style={{ padding: '20px 16px 16px', borderBottom: '1px solid rgba(255,255,255,.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 13, opacity: .7, marginBottom: 4 }}>北京银行</div>
            <div style={{ fontWeight: 700, fontSize: 15, lineHeight: 1.3 }}>公司业务预审系统</div>
          </div>
          {isMobile && (
            <button onClick={() => setSidebarOpen(false)} style={{
              background: 'none', border: 'none', color: 'rgba(255,255,255,.7)',
              fontSize: 22, cursor: 'pointer', lineHeight: 1, padding: '0 4px',
            }}>×</button>
          )}
        </div>
        <nav style={{ flex: 1, padding: '12px 0', overflowY: 'auto' }}>
          {navLinks().map(l => (
            <Link key={l.to} to={l.to} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '11px 20px', fontSize: 14, fontWeight: 500,
              color: location.pathname === l.to ? '#fff' : 'rgba(255,255,255,.7)',
              background: location.pathname === l.to ? 'rgba(255,255,255,.15)' : 'transparent',
              borderLeft: location.pathname === l.to ? '3px solid #fff' : '3px solid transparent',
              textDecoration: 'none', transition: 'all .15s',
            }}>
              <span>{l.icon}</span>
              <span>{l.label}</span>
            </Link>
          ))}
        </nav>
        <div style={{ padding: '16px', borderTop: '1px solid rgba(255,255,255,.1)' }}>
          <div style={{ fontSize: 12, opacity: .6, marginBottom: 4 }}>{user?.branch_name}</div>
          <div style={{ fontWeight: 600, marginBottom: 2 }}>{user?.name}</div>
          <div style={{ fontSize: 12, opacity: .7, marginBottom: 12 }}>{ROLE_LABELS[user?.role]}</div>
          <button onClick={handleLogout} style={{
            width: '100%', padding: '10px', background: 'rgba(255,255,255,.1)',
            border: '1px solid rgba(255,255,255,.2)', color: '#fff', borderRadius: 6,
            fontSize: 13, cursor: 'pointer',
          }}>退出登录</button>
        </div>
      </aside>

      {/* Main */}
      <div style={{ marginLeft: isMobile ? 0 : 220, flex: 1, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        {/* Top bar */}
        <header style={{
          background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.08)',
          padding: isMobile ? '0 16px' : '0 24px', height: 56,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          position: 'sticky', top: 0, zIndex: 50,
        }}>
          {/* 移动端汉堡按钮 */}
          {isMobile ? (
            <button onClick={() => setSidebarOpen(true)} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 22, color: 'var(--gray-700)', padding: '4px 6px',
              display: 'flex', alignItems: 'center',
            }}>☰</button>
          ) : <div />}

          <div style={{ position: 'relative' }}>
            <button onClick={loadNotifications} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 20, position: 'relative', padding: '4px 8px',
            }}>
              🔔
              {unread > 0 && (
                <span style={{
                  position: 'absolute', top: 0, right: 0,
                  background: 'var(--danger)', color: '#fff',
                  borderRadius: '99px', fontSize: 10, fontWeight: 700,
                  padding: '1px 5px', minWidth: 16, textAlign: 'center',
                }}>{unread > 99 ? '99+' : unread}</span>
              )}
            </button>
            {showNotif && (
              <div style={{
                position: 'fixed',
                right: isMobile ? 8 : 16,
                left: isMobile ? 8 : 'auto',
                top: 64,
                width: isMobile ? 'auto' : 360,
                background: '#fff', borderRadius: 12,
                boxShadow: '0 10px 40px rgba(0,0,0,.15)',
                border: '1px solid var(--gray-200)', zIndex: 200,
              }}>
                <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--gray-200)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 700 }}>消息通知</span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={markAllRead} style={{ fontSize: 12, color: 'var(--primary-light)', background: 'none', border: 'none', cursor: 'pointer' }}>全部已读</button>
                    <button onClick={() => setShowNotif(false)} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', lineHeight: 1 }}>×</button>
                  </div>
                </div>
                <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                  {notifications.length === 0 ? (
                    <div style={{ padding: 32, textAlign: 'center', color: 'var(--gray-400)' }}>暂无消息</div>
                  ) : notifications.map(n => (
                    <div key={n.id} onClick={async () => {
                      await api.put(`/notifications/${n.id}/read`)
                      if (n.project_id) navigate(`/projects/${n.project_id}`)
                      setShowNotif(false)
                    }} style={{
                      padding: '12px 16px', cursor: 'pointer',
                      background: n.is_read ? '#fff' : '#f0f7ff',
                      borderBottom: '1px solid var(--gray-100)',
                    }}>
                      <div style={{ fontWeight: n.is_read ? 400 : 600, fontSize: 13, marginBottom: 3 }}>{n.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--gray-500)' }}>{n.message}</div>
                      <div style={{ fontSize: 11, color: 'var(--gray-400)', marginTop: 4 }}>{new Date(n.created_at).toLocaleString('zh-CN')}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </header>

        {/* Content */}
        <main style={{ flex: 1, padding: isMobile ? '16px' : '24px', maxWidth: 1200, width: '100%', margin: '0 auto' }}>
          {children}
        </main>
      </div>
    </div>
  )
}
