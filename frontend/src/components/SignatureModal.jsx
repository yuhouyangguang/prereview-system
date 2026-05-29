import React, { useRef, useState, useEffect } from 'react'

export default function SignatureModal({ onConfirm, onCancel }) {
  const canvasRef = useRef(null)
  const [drawing, setDrawing] = useState(false)
  const [hasSignature, setHasSignature] = useState(false)
  const [opinion, setOpinion] = useState('')

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    ctx.strokeStyle = '#003087'
    ctx.lineWidth = 2.5
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
  }, [])

  const getPos = (e, canvas) => {
    const rect = canvas.getBoundingClientRect()
    if (e.touches) {
      return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top }
    }
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const start = e => {
    e.preventDefault()
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const pos = getPos(e, canvas)
    ctx.beginPath()
    ctx.moveTo(pos.x, pos.y)
    setDrawing(true)
    setHasSignature(true)
  }

  const draw = e => {
    if (!drawing) return
    e.preventDefault()
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const pos = getPos(e, canvas)
    ctx.lineTo(pos.x, pos.y)
    ctx.stroke()
  }

  const end = e => {
    e.preventDefault()
    setDrawing(false)
  }

  const clear = () => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setHasSignature(false)
  }

  const confirm = () => {
    const canvas = canvasRef.current
    const sigData = canvas.toDataURL('image/png')
    onConfirm(sigData, opinion)
  }

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ maxWidth: 520 }}>
        <div className="modal-header">
          <h3>✍️ 电子签字确认</h3>
          <button onClick={onCancel} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--gray-400)' }}>×</button>
        </div>
        <div className="modal-body">
          <div className="alert alert-info" style={{ marginBottom: 16 }}>
            请在下方签字区域手写签名，签名具有法律效力，依据《电子签名法》生效。
          </div>
          <div className="form-group">
            <label>审批意见</label>
            <textarea className="form-control" rows={2} value={opinion} onChange={e => setOpinion(e.target.value)} placeholder="请填写审批意见（可选）..." />
          </div>
          <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--gray-700)' }}>手写签名区 <span style={{ color: 'var(--danger)' }}>*</span></label>
            <button onClick={clear} className="btn btn-ghost btn-sm">清除重写</button>
          </div>
          <canvas
            ref={canvasRef}
            width={468} height={160}
            style={{
              border: '2px dashed var(--gray-300)', borderRadius: 8,
              cursor: 'crosshair', touchAction: 'none', display: 'block',
              background: '#fafbff',
            }}
            onMouseDown={start} onMouseMove={draw} onMouseUp={end} onMouseLeave={end}
            onTouchStart={start} onTouchMove={draw} onTouchEnd={end}
          />
          {!hasSignature && (
            <div style={{ textAlign: 'center', color: 'var(--gray-400)', fontSize: 12, marginTop: 8 }}>请在上方区域进行手写签名</div>
          )}
        </div>
        <div className="modal-footer">
          <button onClick={onCancel} className="btn btn-ghost">取消</button>
          <button onClick={confirm} className="btn btn-primary" disabled={!hasSignature}>
            确认签字并提交
          </button>
        </div>
      </div>
    </div>
  )
}
