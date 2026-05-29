import React from 'react'

const STATUS_MAP = {
  'draft': { label: '草稿', cls: 'badge-gray' },
  '预审中': { label: '预审中', cls: 'badge-blue' },
  '绿灯': { label: '🟢 绿灯', cls: 'badge-green' },
  '黄灯': { label: '🟡 黄灯', cls: 'badge-yellow' },
  '红灯': { label: '🔴 红灯', cls: 'badge-red' },
  '材料提交中': { label: '材料提交中', cls: 'badge-blue' },
  'AI审批中': { label: 'AI审批中...', cls: 'badge-purple' },
  'AI已退回': { label: 'AI已退回', cls: 'badge-red' },
  '待人工审批': { label: '待人工审批', cls: 'badge-yellow' },
  '待补充材料': { label: '待补充材料', cls: 'badge-orange' },
  '人工审批退回': { label: '人工退回', cls: 'badge-red' },
  '待行长终审': { label: '待行长终审', cls: 'badge-orange' },
  '行长退回': { label: '行长退回', cls: 'badge-red' },
  '已终审': { label: '✅ 已终审', cls: 'badge-green' },
  '修改中': { label: '修改中', cls: 'badge-purple' },
}

export default function StatusBadge({ status }) {
  const cfg = STATUS_MAP[status] || { label: status, cls: 'badge-gray' }
  return <span className={`badge ${cfg.cls}`}>{cfg.label}</span>
}
