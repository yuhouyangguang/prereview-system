import React, { useState, useEffect, useRef } from 'react'
import api from '../services/api'

const STATUS_LABELS = { processing: '解读中', active: '已生效', failed: '解读失败' }
const STATUS_COLORS = { processing: '#d97706', active: '#059669', failed: '#dc2626' }
const LEVEL_COLORS = { 总行: '#dc2626', 分行: '#d97706', 支行: '#2563eb' }
const LEVEL_PRIORITY = { 总行: 3, 分行: 2, 支行: 1 }

function DocCard({ doc, onDelete, readonly }) {
  const [expanded, setExpanded] = useState(false)
  const policies = Array.isArray(doc.key_policies) ? doc.key_policies : []

  return (
    <div style={{
      background: '#fff', borderRadius: 10, padding: '16px 20px',
      boxShadow: '0 1px 4px rgba(0,0,0,.07)',
      borderLeft: `4px solid ${LEVEL_COLORS[doc.branch_level] || '#6b7280'}`,
      marginBottom: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
            <span style={{
              background: LEVEL_COLORS[doc.branch_level] + '18',
              color: LEVEL_COLORS[doc.branch_level],
              borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 600,
            }}>
              {doc.branch_level}
            </span>
            <span style={{
              background: STATUS_COLORS[doc.status] + '18',
              color: STATUS_COLORS[doc.status],
              borderRadius: 4, padding: '2px 8px', fontSize: 11,
            }}>
              {STATUS_LABELS[doc.status] || doc.status}
            </span>
            <span style={{ fontSize: 11, color: 'var(--gray-400)' }}>
              {doc.doc_type?.toUpperCase()} · {doc.uploader_name}
            </span>
            <span style={{ fontSize: 11, color: 'var(--gray-400)' }}>
              {doc.created_at ? new Date(doc.created_at).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) : ''}
            </span>
          </div>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4, wordBreak: 'break-all' }}>
            {doc.original_filename}
          </div>
          {doc.ai_summary && (
            <div style={{ fontSize: 13, color: 'var(--gray-600)', lineHeight: 1.5 }}>
              {doc.ai_summary}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          {policies.length > 0 && (
            <button onClick={() => setExpanded(e => !e)} style={{
              padding: '5px 12px', fontSize: 12,
              background: expanded ? '#eff6ff' : '#f9fafb',
              color: expanded ? '#2563eb' : 'var(--gray-600)',
              border: `1px solid ${expanded ? '#bfdbfe' : 'var(--gray-200)'}`,
              borderRadius: 6, cursor: 'pointer',
            }}>
              {expanded ? '收起' : `查看 ${policies.length} 条条款`}
            </button>
          )}
          {!readonly && (
            <button onClick={() => onDelete(doc)} style={{
              padding: '5px 12px', fontSize: 12,
              background: '#fef2f2', color: '#dc2626',
              border: '1px solid #fecaca', borderRadius: 6, cursor: 'pointer',
            }}>
              删除
            </button>
          )}
        </div>
      </div>

      {expanded && policies.length > 0 && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--gray-100)' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 8 }}>核心政策条款</div>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {policies.map((p, i) => (
              <li key={i} style={{ fontSize: 13, color: 'var(--gray-700)', marginBottom: 4, lineHeight: 1.5 }}>{p}</li>
            ))}
          </ul>
          {doc.applicable_scope && (
            <div style={{ marginTop: 10 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--gray-500)' }}>适用范围：</span>
              <span style={{ fontSize: 13, color: 'var(--gray-600)' }}>{doc.applicable_scope}</span>
            </div>
          )}
          {doc.prohibitions && (
            <div style={{ marginTop: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: '#dc2626' }}>禁止事项：</span>
              <span style={{ fontSize: 13, color: 'var(--gray-600)' }}>{doc.prohibitions}</span>
            </div>
          )}
          {doc.exceptions && (
            <div style={{ marginTop: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: '#d97706' }}>例外情形：</span>
              <span style={{ fontSize: 13, color: 'var(--gray-600)' }}>{doc.exceptions}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function KnowledgeBase() {
  const [tab, setTab] = useState('own')      // own | upper
  const [ownDocs, setOwnDocs] = useState([])
  const [upperDocs, setUpperDocs] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [uploadMsg, setUploadMsg] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [confirmDoc, setConfirmDoc] = useState(null)
  const fileRef = useRef()

  const fetchDocs = async () => {
    setLoading(true)
    setError('')
    try {
      const [ownRes, upperRes] = await Promise.all([
        api.get('/knowledge?scope=own'),
        api.get('/knowledge?scope=upper'),
      ])
      setOwnDocs(ownRes.data)
      setUpperDocs(upperRes.data)
    } catch (e) {
      setError(e.response?.data?.error || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchDocs() }, [])

  const handleUpload = async (file) => {
    if (!file) return
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['pdf', 'docx', 'doc', 'txt'].includes(ext)) {
      setUploadMsg('仅支持 PDF、Word(.docx/.doc)、TXT 格式')
      return
    }
    if (file.size > 50 * 1024 * 1024) {
      setUploadMsg('文件大小不能超过 50MB')
      return
    }
    setUploading(true)
    setUploadMsg('')
    const form = new FormData()
    form.append('file', file)
    try {
      await api.post('/knowledge/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadMsg('上传并解读成功，文档已写入知识库')
      await fetchDocs()
    } catch (e) {
      setUploadMsg(e.response?.data?.error || '上传失败，请重试')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleDelete = async () => {
    if (!confirmDoc) return
    try {
      await api.delete(`/knowledge/${confirmDoc.id}`)
      setConfirmDoc(null)
      await fetchDocs()
    } catch (e) {
      alert(e.response?.data?.error || '删除失败')
    }
  }

  // Group upper docs by level (高→低)
  const upperByLevel = upperDocs.reduce((acc, doc) => {
    if (!acc[doc.branch_level]) acc[doc.branch_level] = []
    acc[doc.branch_level].push(doc)
    return acc
  }, {})
  const upperLevels = Object.keys(upperByLevel).sort((a, b) => LEVEL_PRIORITY[b] - LEVEL_PRIORITY[a])

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>信贷政策知识库</h2>
        <p style={{ margin: '4px 0 0', color: 'var(--gray-500)', fontSize: 13 }}>
          上传信贷政策文件，AI自动解读并写入知识库，AI预审批和审批时将参考本级及上级内容
        </p>
      </div>

      {error && (
        <div style={{ background: '#fef2f2', color: 'var(--danger)', borderRadius: 8, padding: '12px 16px', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Tab 切换 */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid var(--gray-200)' }}>
        {[['own', '本级知识库'], ['upper', '上级知识库（只读）']].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} style={{
            padding: '10px 20px', fontSize: 14, fontWeight: tab === key ? 600 : 400,
            color: tab === key ? 'var(--primary)' : 'var(--gray-500)',
            background: 'none', border: 'none', borderBottom: tab === key ? '2px solid var(--primary)' : '2px solid transparent',
            cursor: 'pointer', marginBottom: -1,
          }}>
            {label}
            {key === 'own' && ownDocs.length > 0 && (
              <span style={{ marginLeft: 6, background: 'var(--primary)', color: '#fff', borderRadius: 99, fontSize: 11, padding: '1px 6px' }}>
                {ownDocs.length}
              </span>
            )}
            {key === 'upper' && upperDocs.length > 0 && (
              <span style={{ marginLeft: 6, background: 'var(--gray-400)', color: '#fff', borderRadius: 99, fontSize: 11, padding: '1px 6px' }}>
                {upperDocs.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 本级知识库 */}
      {tab === 'own' && (
        <>
          {/* 上传区 */}
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); handleUpload(e.dataTransfer.files[0]) }}
            style={{
              border: `2px dashed ${dragOver ? 'var(--primary)' : 'var(--gray-300)'}`,
              borderRadius: 10, padding: '28px 20px', textAlign: 'center',
              background: dragOver ? '#eff6ff' : '#fafafa',
              marginBottom: 20, transition: 'all .15s',
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
            <div style={{ fontSize: 14, color: 'var(--gray-600)', marginBottom: 12 }}>
              拖拽文件至此处，或
              <button onClick={() => fileRef.current?.click()}
                style={{ marginLeft: 6, color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
                点击上传
              </button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>支持 PDF、Word(.docx/.doc)、TXT，单文件 ≤ 50MB</div>
            <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt" style={{ display: 'none' }}
              onChange={e => handleUpload(e.target.files[0])} />
          </div>

          {uploading && (
            <div style={{ background: '#eff6ff', borderRadius: 8, padding: '12px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
              <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              <span style={{ fontSize: 13, color: '#2563eb' }}>正在上传并AI解读中，请稍候…</span>
            </div>
          )}
          {uploadMsg && !uploading && (
            <div style={{
              background: uploadMsg.includes('成功') ? '#f0fdf4' : '#fef2f2',
              color: uploadMsg.includes('成功') ? '#059669' : '#dc2626',
              borderRadius: 8, padding: '10px 16px', marginBottom: 16, fontSize: 13,
            }}>
              {uploadMsg}
            </div>
          )}

          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--gray-400)' }}>
              <div className="spinner" style={{ margin: '0 auto 12px' }} />加载中…
            </div>
          ) : ownDocs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--gray-400)', background: '#fff', borderRadius: 10 }}>
              本级知识库暂无文档，请上传信贷政策文件
            </div>
          ) : (
            ownDocs.map(doc => (
              <DocCard key={doc.id} doc={doc} readonly={false} onDelete={d => setConfirmDoc(d)} />
            ))
          )}
        </>
      )}

      {/* 上级知识库（只读） */}
      {tab === 'upper' && (
        <>
          <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, padding: '10px 16px', marginBottom: 16, fontSize: 13, color: '#92400e' }}>
            上级知识库为只读，AI审批时优先采用高级别内容（总行 &gt; 分行）
          </div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--gray-400)' }}>
              <div className="spinner" style={{ margin: '0 auto 12px' }} />加载中…
            </div>
          ) : upperLevels.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--gray-400)', background: '#fff', borderRadius: 10 }}>
              上级审批人员暂未上传任何知识库文档
            </div>
          ) : (
            upperLevels.map(level => (
              <div key={level} style={{ marginBottom: 20 }}>
                <div style={{
                  fontSize: 13, fontWeight: 700, color: LEVEL_COLORS[level],
                  marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <span style={{ background: LEVEL_COLORS[level] + '18', borderRadius: 4, padding: '2px 10px' }}>
                    {level}知识库
                  </span>
                  <span style={{ fontWeight: 400, color: 'var(--gray-400)' }}>（{upperByLevel[level].length} 份文档）</span>
                </div>
                {upperByLevel[level].map(doc => (
                  <DocCard key={doc.id} doc={doc} readonly={true} onDelete={() => {}} />
                ))}
              </div>
            ))
          )}
        </>
      )}

      {/* 删除确认弹窗 */}
      {confirmDoc && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: 28, width: 360, boxShadow: '0 20px 60px rgba(0,0,0,.2)' }}>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 12 }}>确认删除文档？</div>
            <div style={{ fontSize: 13, color: 'var(--gray-600)', marginBottom: 6 }}>
              文档删除后，该文档相关的知识库条目将停用（历史审批引用快照保留）。
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 20 }}>《{confirmDoc.original_filename}》</div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setConfirmDoc(null)}
                style={{ padding: '8px 18px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>
                取消
              </button>
              <button onClick={handleDelete}
                style={{ padding: '8px 18px', background: '#dc2626', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
