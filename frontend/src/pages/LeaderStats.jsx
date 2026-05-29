import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

// ── 内置 SVG 折线图组件 ────────────────────────────────────────────────────────

function LineChart({ data, valueKey, label, color, unit, height = 160 }) {
  if (!data || data.length === 0) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gray-400)', fontSize: 13 }}>
        暂无数据
      </div>
    )
  }

  const values = data.map(d => d[valueKey]).filter(v => v !== null && v !== undefined)
  if (values.length === 0) return (
    <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--gray-400)', fontSize: 13 }}>
      暂无数据
    </div>
  )

  const W = 600, H = height
  const padL = 60, padR = 20, padT = 16, padB = 36

  const minV = Math.min(...values)
  const maxV = Math.max(...values)
  const range = maxV - minV || 1

  const points = data.map((d, i) => {
    const x = padL + (i / Math.max(data.length - 1, 1)) * (W - padL - padR)
    const v = d[valueKey]
    const y = v === null || v === undefined
      ? null
      : padT + (1 - (v - minV) / range) * (H - padT - padB)
    return { x, y, v, date: d.date }
  })

  // Y-axis ticks
  const ticks = 4
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => {
    const v = minV + (range * i) / ticks
    const y = padT + (1 - (v - minV) / range) * (H - padT - padB)
    return { v, y }
  })

  // X-axis labels (show at most 6)
  const step = Math.max(1, Math.floor(data.length / 6))
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1)

  // Build polyline path (skip null points)
  let pathD = ''
  let inPath = false
  points.forEach(pt => {
    if (pt.y === null) { inPath = false; return }
    if (!inPath) { pathD += `M ${pt.x} ${pt.y} `; inPath = true }
    else pathD += `L ${pt.x} ${pt.y} `
  })

  const [tooltip, setTooltip] = useState(null)

  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height }} preserveAspectRatio="none">
        {/* Grid lines */}
        {yTicks.map((t, i) => (
          <line key={i} x1={padL} x2={W - padR} y1={t.y} y2={t.y}
            stroke="#e5e7eb" strokeWidth={1} />
        ))}
        {/* Y-axis labels */}
        {yTicks.map((t, i) => (
          <text key={i} x={padL - 6} y={t.y + 4} textAnchor="end"
            fontSize={10} fill="#9ca3af">
            {Math.abs(t.v) >= 10000 ? `${(t.v / 10000).toFixed(1)}万` : t.v.toFixed(1)}
          </text>
        ))}
        {/* X-axis labels */}
        {xLabels.map((d, i) => {
          const idx = data.indexOf(d)
          const x = padL + (idx / Math.max(data.length - 1, 1)) * (W - padL - padR)
          return (
            <text key={i} x={x} y={H - padB + 14} textAnchor="middle"
              fontSize={9} fill="#9ca3af">
              {d.date.length > 7 ? d.date.slice(5) : d.date}
            </text>
          )
        })}
        {/* Line */}
        {pathD && <path d={pathD} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />}
        {/* Dots + hover areas */}
        {points.map((pt, i) => pt.y !== null && (
          <g key={i}>
            <circle cx={pt.x} cy={pt.y} r={3} fill={color} />
            <circle cx={pt.x} cy={pt.y} r={12} fill="transparent"
              onMouseEnter={() => setTooltip({ x: pt.x, y: pt.y, v: pt.v, date: pt.date, count: data[i].count })}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: 'crosshair' }} />
          </g>
        ))}
      </svg>
      {tooltip && (
        <div style={{
          position: 'absolute',
          left: `calc(${(tooltip.x / W) * 100}% + 8px)`,
          top: `${(tooltip.y / H) * 100}%`,
          background: 'rgba(0,0,0,.75)', color: '#fff',
          borderRadius: 6, padding: '6px 10px', fontSize: 12,
          pointerEvents: 'none', whiteSpace: 'nowrap', zIndex: 10,
          transform: 'translateY(-50%)',
        }}>
          <div style={{ fontWeight: 600 }}>{tooltip.date}</div>
          <div>{label}: {tooltip.v?.toFixed(2)} {unit}</div>
          <div>业务 {tooltip.count} 笔</div>
        </div>
      )}
    </div>
  )
}

// ── 汇总卡片 ──────────────────────────────────────────────────────────────────

function SummaryCard({ label, value, unit, color }) {
  return (
    <div style={{
      flex: 1, background: '#fff', borderRadius: 10, padding: '16px 20px',
      boxShadow: '0 1px 4px rgba(0,0,0,.07)', borderLeft: `4px solid ${color}`,
    }}>
      <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>
        {value === null || value === undefined ? '—' : value}
        <span style={{ fontSize: 13, fontWeight: 400, marginLeft: 4 }}>{unit}</span>
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

const LOAN_TYPES = ['', '流动资金贷款', '固定资产贷款', '贸易融资', '银行承兑汇票', '保函']

export default function LeaderStats() {
  const today = new Date()
  const thirtyDaysAgo = new Date(today)
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30)
  const fmt = d => d.toISOString().slice(0, 10)

  const [start, setStart] = useState(fmt(thirtyDaysAgo))
  const [end, setEnd] = useState(fmt(today))
  const [loanType, setLoanType] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const fetchStats = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.get('/leader-stats', { params: { start, end, loan_type: loanType } })
      setData(res.data)
    } catch (e) {
      setError(e.response?.data?.error || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [start, end, loanType])

  useEffect(() => { fetchStats() }, [fetchStats])

  const handleExport = async () => {
    try {
      const res = await api.get('/leader-stats', {
        params: { start, end, loan_type: loanType, export: '1' },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `leader_stats_${start}_${end}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      alert('导出失败')
    }
  }

  const summary = data?.summary || {}
  const points = data?.data_points || []

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>业务绩效统计分析</h2>
        <p style={{ margin: '4px 0 0', color: 'var(--gray-500)', fontSize: 13 }}>
          查看本层级及以下已终审业务的 EVA / RWA / RAROC 统计曲线
        </p>
      </div>

      {/* 筛选栏 */}
      <div style={{
        background: '#fff', borderRadius: 10, padding: '16px 20px', marginBottom: 20,
        boxShadow: '0 1px 4px rgba(0,0,0,.07)',
        display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 13, color: 'var(--gray-600)' }}>开始日期</label>
          <input type="date" value={start} onChange={e => setStart(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid var(--gray-300)', fontSize: 13 }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 13, color: 'var(--gray-600)' }}>结束日期</label>
          <input type="date" value={end} onChange={e => setEnd(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid var(--gray-300)', fontSize: 13 }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 13, color: 'var(--gray-600)' }}>业务类型</label>
          <select value={loanType} onChange={e => setLoanType(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid var(--gray-300)', fontSize: 13 }}>
            {LOAN_TYPES.map(t => <option key={t} value={t}>{t || '全部类型'}</option>)}
          </select>
        </div>
        <button onClick={fetchStats} disabled={loading}
          style={{ padding: '7px 18px', background: 'var(--primary)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, cursor: loading ? 'not-allowed' : 'pointer' }}>
          {loading ? '查询中…' : '查询'}
        </button>
        <button onClick={handleExport}
          style={{ padding: '7px 14px', background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', borderRadius: 6, fontSize: 13, cursor: 'pointer', marginLeft: 'auto' }}>
          导出 Excel
        </button>
      </div>

      {error && (
        <div style={{ background: '#fef2f2', color: 'var(--danger)', borderRadius: 8, padding: '12px 16px', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* 汇总卡片 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <SummaryCard label="累计 EVA" value={summary.total_eva} unit="万元" color="#2563eb" />
        <SummaryCard label="累计 RWA" value={summary.total_rwa} unit="万元" color="#7c3aed" />
        <SummaryCard label="平均 RAROC" value={summary.avg_raroc} unit="%" color="#059669" />
        <SummaryCard label="已终审业务" value={summary.total_count} unit="笔" color="#d97706" />
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 48, color: 'var(--gray-400)' }}>
          <div className="spinner" style={{ margin: '0 auto 12px' }} />
          加载中…
        </div>
      )}

      {!loading && points.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--gray-400)', background: '#fff', borderRadius: 10 }}>
          所选时间段内暂无已终审业务数据
        </div>
      )}

      {!loading && points.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[
            { key: 'eva', label: 'EVA', unit: '万元', color: '#2563eb' },
            { key: 'rwa', label: 'RWA', unit: '万元', color: '#7c3aed' },
            { key: 'raroc', label: 'RAROC', unit: '%', color: '#059669' },
          ].map(({ key, label, unit, color }) => (
            <div key={key} style={{
              background: '#fff', borderRadius: 10, padding: '16px 20px',
              boxShadow: '0 1px 4px rgba(0,0,0,.07)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color }}>
                  {label} 趋势
                  <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--gray-400)', marginLeft: 8 }}>
                    ({unit}，{data?.granularity === 'day' ? '按日' : data?.granularity === 'week' ? '按周' : '按月'}汇总)
                  </span>
                </div>
              </div>
              <LineChart data={points} valueKey={key} label={label} color={color} unit={unit} height={180} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
