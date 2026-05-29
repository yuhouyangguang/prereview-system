import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'

const INDUSTRIES = ['科技', '医疗', '教育', '绿色能源', '农业', '服务业', '制造业', '批发零售', '建筑', '采矿', '房地产', '化工', '煤炭', '钢铁', '电解铝', '地方政府融资平台', '其他']
const LOAN_TYPES = ['流动资金贷款', '固定资产贷款', '贸易融资', '银行承兑汇票', '保函']
const GUARANTEE_TYPES = ['抵押', '质押', '保证', '信用', '组合担保']
const CREDIT_RATINGS = ['AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', '未评级']

export default function ProjectCreate() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    client_name: '', client_industry: '', client_credit_rating: '', client_description: '',
    loan_amount: '', loan_purpose: '', loan_type: '', loan_term: '', guarantee_type: '',
    interest_rate: '', fee_rate: '', deposit_return: '', competitor_rate: '', competitor_bank: '',
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSubmit = async e => {
    e.preventDefault()
    if (!form.client_name || !form.loan_amount || !form.loan_type) {
      setError('请填写客户名称、贷款金额和贷款类型')
      return
    }
    setLoading(true); setError('')
    try {
      const payload = {
        ...form,
        loan_amount: form.loan_amount ? parseFloat(form.loan_amount) : null,
        loan_term: form.loan_term ? parseInt(form.loan_term) : null,
        interest_rate: form.interest_rate ? parseFloat(form.interest_rate) : null,
        fee_rate: form.fee_rate ? parseFloat(form.fee_rate) : null,
        deposit_return: form.deposit_return ? parseFloat(form.deposit_return) : null,
        competitor_rate: form.competitor_rate ? parseFloat(form.competitor_rate) : null,
      }
      const r = await api.post('/projects', payload)
      navigate(`/projects/${r.data.id}`)
    } catch (err) {
      setError(err.response?.data?.error || '创建失败')
    } finally { setLoading(false) }
  }

  return (
    <div>
      <div className="page-header">
        <h1>新建预审项目</h1>
        <p>填写项目基本信息，提交后系统将进行AI预审分析</p>
      </div>

      <form onSubmit={handleSubmit}>
        {error && <div className="alert alert-danger">{error}</div>}

        <div className="card" style={{ marginBottom: 20 }}>
          <div className="section-title">客户基本信息</div>
          <div className="grid-2">
            <div className="form-group">
              <label>客户名称 <span className="required">*</span></label>
              <input className="form-control" value={form.client_name} onChange={e => set('client_name', e.target.value)} placeholder="企业全称" />
            </div>
            <div className="form-group">
              <label>所属行业 <span className="required">*</span></label>
              <select className="form-control" value={form.client_industry} onChange={e => set('client_industry', e.target.value)}>
                <option value="">请选择行业</option>
                {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>客户信用评级</label>
              <select className="form-control" value={form.client_credit_rating} onChange={e => set('client_credit_rating', e.target.value)}>
                <option value="">请选择</option>
                {CREDIT_RATINGS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <div className="form-group">
            <label>客户简介</label>
            <textarea className="form-control" value={form.client_description} onChange={e => set('client_description', e.target.value)} placeholder="客户背景、主营业务、经营状况等（可选）" rows={3} />
          </div>
        </div>

        <div className="card" style={{ marginBottom: 20 }}>
          <div className="section-title">融资方案信息</div>
          <div className="grid-3">
            <div className="form-group">
              <label>融资金额（万元）<span className="required">*</span></label>
              <input type="number" className="form-control" value={form.loan_amount} onChange={e => set('loan_amount', e.target.value)} placeholder="如：5000" />
            </div>
            <div className="form-group">
              <label>贷款类型 <span className="required">*</span></label>
              <select className="form-control" value={form.loan_type} onChange={e => set('loan_type', e.target.value)}>
                <option value="">请选择</option>
                {LOAN_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>贷款期限（月）</label>
              <input type="number" className="form-control" value={form.loan_term} onChange={e => set('loan_term', e.target.value)} placeholder="如：12" />
            </div>
          </div>
          <div className="form-group">
            <label>融资用途</label>
            <input className="form-control" value={form.loan_purpose} onChange={e => set('loan_purpose', e.target.value)} placeholder="资金具体用途" />
          </div>
          <div className="form-group">
            <label>担保方式</label>
            <select className="form-control" value={form.guarantee_type} onChange={e => set('guarantee_type', e.target.value)}>
              <option value="">请选择</option>
              {GUARANTEE_TYPES.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
        </div>

        <div className="card" style={{ marginBottom: 20 }}>
          <div className="section-title">初步报价方案</div>
          <div className="alert alert-info">综合收益将用于AI预审效益评估和EVA/RWA/RAROC自动测算</div>
          <div className="grid-3">
            <div className="form-group">
              <label>拟报贷款利率（%）</label>
              <input type="number" step="0.01" className="form-control" value={form.interest_rate} onChange={e => set('interest_rate', e.target.value)} placeholder="如：4.25" />
            </div>
            <div className="form-group">
              <label>综合手续费率（%）</label>
              <input type="number" step="0.01" className="form-control" value={form.fee_rate} onChange={e => set('fee_rate', e.target.value)} placeholder="如：0.5" />
            </div>
            <div className="form-group">
              <label>存款回报率（%）</label>
              <input type="number" step="0.01" className="form-control" value={form.deposit_return} onChange={e => set('deposit_return', e.target.value)} placeholder="如：1.0" />
            </div>
          </div>
          <div className="grid-2">
            <div className="form-group">
              <label>同业参考利率（%）</label>
              <input type="number" step="0.01" className="form-control" value={form.competitor_rate} onChange={e => set('competitor_rate', e.target.value)} placeholder="客户声称他行报价" />
            </div>
            <div className="form-group">
              <label>参考银行名称</label>
              <input className="form-control" value={form.competitor_bank} onChange={e => set('competitor_bank', e.target.value)} placeholder="如：建设银行" />
            </div>
          </div>
        </div>

        <div className="flex-end gap-3">
          <button type="button" onClick={() => navigate(-1)} className="btn btn-ghost">取消</button>
          <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
            {loading ? <><span className="spinner" style={{ width: 16, height: 16 }} /> 创建中...</> : '💾 保存并查看'}
          </button>
        </div>
      </form>
    </div>
  )
}
