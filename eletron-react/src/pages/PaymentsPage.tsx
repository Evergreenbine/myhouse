import { useState, useEffect } from 'react'
import { CheckOutlined, CloseOutlined, DeleteOutlined, EditOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { rental } from '../api'
import { resolveBuildingId, useUIStore } from '../store'
import { DayPicker, Modal, MonthPicker, showToast } from '../components/ui'

interface Building { id: number; name: string; rent_day?: number }
interface Payment {
  id: number
  bill_id: number
  amount: number
  pay_date: string
  pay_method: string
  remark?: string
  tenant_name: string
  room_number: string
  billing_month: string
  total_amount?: number
  building_id?: number
}

interface PaymentEditForm {
  amount: string
  pay_date: string
  pay_method: string
  remark: string
}

const paymentSkeletonWidths = ['72%', '48%', '62%', '68%', '58%', '58%', '52%', '76%', '64%']

function PaymentsLoadingTable() {
  return (
    <div className="payment-loading-table" aria-busy="true" aria-label="正在加载收款记录">
      <div className="payment-loading-grid payment-loading-header">
        {paymentSkeletonWidths.map((width, index) => (
          <span key={index} className="payment-skeleton payment-skeleton-header" style={{ width }} />
        ))}
      </div>
      {Array.from({ length: 5 }, (_, rowIndex) => (
        <div className="payment-loading-grid payment-loading-row" key={rowIndex}>
          {paymentSkeletonWidths.map((width, columnIndex) => (
            <span
              key={columnIndex}
              className="payment-skeleton"
              style={{ width: `${Math.max(34, Number.parseInt(width) - (rowIndex % 3) * 6)}%` }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function PaymentsPage() {
  const { planYear, planMonth, selectedBuildingId, setSelectedBuildingId, setPlanYearMonth } = useUIStore()
  const [payments, setPayments] = useState<Payment[]>([])
  const [buildings, setBuildings] = useState<Building[]>([])
  const [curBid, setCurBid] = useState<number | null>(selectedBuildingId)
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<Payment | null>(null)
  const [editForm, setEditForm] = useState<PaymentEditForm>({ amount: '', pay_date: '', pay_method: '', remark: '' })
  const billingMonth = `${planYear}-${String(planMonth).padStart(2, '0')}`

  const changeMonth = (delta: number) => {
    let year = planYear
    let month = planMonth + delta
    if (month < 1) { month = 12; year-- }
    if (month > 12) { month = 1; year++ }
    setPlanYearMonth(year, month)
  }

  const load = async () => {
    setLoading(true)
    const data = await rental('payments', 'list', {
      month: billingMonth,
      building_id: curBid,
      keyword: keyword.trim(),
    }) || []
    setPayments(data)
    setLoading(false)
  }

  const loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = resolveBuildingId(data)
    setBuildings(data)
    setCurBid(bid)
    setSelectedBuildingId(bid)
  }

  const selectMonth = (value: string) => {
    const [yearText, monthText] = value.split('-')
    const year = Number(yearText)
    const month = Number(monthText)
    if (!year || month < 1 || month > 12) return
    setPlanYearMonth(year, month)
  }

  const switchBuilding = (id: number) => {
    const bid = Number(id)
    setCurBid(bid)
    setSelectedBuildingId(bid)
  }

  const startEdit = (payment: Payment) => {
    setEditingId(payment.id)
    setEditForm({
      amount: String(payment.amount || ''),
      pay_date: payment.pay_date || '',
      pay_method: payment.pay_method || '',
      remark: payment.remark || '',
    })
  }

  const cancelEdit = () => {
    setEditingId(0)
    setEditForm({ amount: '', pay_date: '', pay_method: '', remark: '' })
  }

  const saveEdit = async () => {
    const amount = Number(editForm.amount)
    if (!editingId || !Number.isFinite(amount) || amount <= 0) {
      showToast('请输入有效收款金额')
      return
    }
    const res = await rental('payments', 'update', {
      id: editingId,
      amount,
      pay_date: editForm.pay_date,
      pay_method: editForm.pay_method,
      remark: editForm.remark,
    })
    if (res && res.success !== false) {
      showToast('收款记录已更新')
      cancelEdit()
      load()
    } else {
      showToast('更新失败')
    }
  }

  const deletePayment = async (payment: Payment) => {
    setDeleteTarget(payment)
  }

  const confirmDeletePayment = async () => {
    if (!deleteTarget) return
    await rental('payments', 'delete', { id: deleteTarget.id })
    showToast('收款记录已删除')
    if (editingId === deleteTarget.id) cancelEdit()
    setDeleteTarget(null)
    load()
  }

  useEffect(() => { loadBuildings() }, [])
  useEffect(() => { load() }, [billingMonth, curBid, keyword])

  const totalAmount = payments.reduce((sum, p) => sum + Number(p.amount || 0), 0)
  const roomCount = new Set(payments.map(p => `${p.building_id || ''}-${p.room_number || ''}`).filter(Boolean)).size

  return (
    <div>
      <div className="month-filter">
        <button className="month-nav" onClick={() => changeMonth(-1)} aria-label="上一个月"><LeftOutlined /></button>
        <MonthPicker value={billingMonth} onChange={selectMonth} ariaLabel="选择收款账期" />
        <button className="month-nav" onClick={() => changeMonth(1)} aria-label="下一个月"><RightOutlined /></button>
      </div>

      <div className="tab-action-row">
        <div className="building-tabs">
          {buildings.map(b => (
            <button key={b.id}
              className={'building-tab' + (Number(b.id) === Number(curBid) ? ' active' : '')}
              onClick={() => switchBuilding(b.id)}>{b.name}</button>
          ))}
        </div>
        <input
          className="soft-input"
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          placeholder="搜索房间、租客、备注"
          style={{width:220,height:30,padding:'0 10px',fontSize:12}}
        />
      </div>

      <div className="summary-row">
        <div className="stat-card"><div>收款笔数</div><div className="stat-val" style={{color:'var(--blue)'}}>{payments.length}笔</div></div>
        <div className="stat-card"><div>实收合计</div><div className="stat-val" style={{color:'var(--green)'}}>{totalAmount.toFixed(2)}</div></div>
        <div className="stat-card"><div>涉及房间</div><div className="stat-val" style={{color:'var(--blue)'}}>{roomCount}间</div></div>
      </div>

      {loading ? <PaymentsLoadingTable /> :
        payments.length === 0 ? <div className="text-center py-20 text-[var(--text-third)]">暂无收款记录</div> :
          <div className="bg-white rounded-lg border border-[var(--border-light)] overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="bg-gray-50"><th className="text-left px-4 py-2.5 font-medium">收款日期</th><th className="text-left px-4 py-2.5 font-medium">房间</th><th className="text-left px-4 py-2.5 font-medium">租客</th><th className="text-left px-4 py-2.5 font-medium">账期</th><th className="text-left px-4 py-2.5 font-medium">应收</th><th className="text-left px-4 py-2.5 font-medium">实收</th><th className="text-left px-4 py-2.5 font-medium">方式</th><th className="text-left px-4 py-2.5 font-medium">备注</th><th className="text-left px-4 py-2.5 font-medium">操作</th></tr></thead>
              <tbody>
                {payments.map(p => {
                  const editing = editingId === p.id
                  return (
                    <tr key={p.id} className="border-t border-[var(--border-light)] hover:bg-gray-50">
                      <td className="px-4 py-2.5">
                        {editing ? <DayPicker value={editForm.pay_date} onChange={pay_date => setEditForm({ ...editForm, pay_date })} ariaLabel="选择收款日期" style={{height:28,width:138}} /> : (p.pay_date || '-')}
                      </td>
                      <td className="px-4 py-2.5"><span className="tag tag-blue">{p.room_number || '-'}</span></td>
                      <td className="px-4 py-2.5">{p.tenant_name || '-'}</td>
                      <td className="px-4 py-2.5">{p.billing_month || '-'}</td>
                      <td className="px-4 py-2.5" style={{color:'var(--orange)',fontWeight:600}}>{Number(p.total_amount || 0).toFixed(2)}</td>
                      <td className="px-4 py-2.5" style={{color:'var(--green)',fontWeight:700}}>
                        {editing ? <input className="soft-input" type="number" value={editForm.amount} onChange={e => setEditForm({ ...editForm, amount: e.target.value })} style={{height:28,width:96}} /> : Number(p.amount).toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5">
                        {editing ? <input className="soft-input" value={editForm.pay_method} onChange={e => setEditForm({ ...editForm, pay_method: e.target.value })} style={{height:28,width:96}} /> : (p.pay_method || '-')}
                      </td>
                      <td className="px-4 py-2.5">
                        {editing ? <input className="soft-input" value={editForm.remark} onChange={e => setEditForm({ ...editForm, remark: e.target.value })} style={{height:28,width:160}} /> : (p.remark || '-')}
                      </td>
                      <td className="px-4 py-2.5">
                        <div style={{display:'flex',gap:6}}>
                          {editing ? (
                            <>
                              <button className="btn btn-sm btn-primary" onClick={saveEdit} title="保存"><CheckOutlined /></button>
                              <button className="btn btn-sm btn-outline" onClick={cancelEdit} title="取消"><CloseOutlined /></button>
                            </>
                          ) : (
                            <>
                              <button className="btn btn-sm btn-outline" onClick={() => startEdit(p)} title="编辑"><EditOutlined /></button>
                              <button className="btn btn-sm btn-outline" onClick={() => deletePayment(p)} title="删除"><DeleteOutlined /></button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
      }
      <Modal open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title="删除收款记录">
        <div className="confirm-body">
          <div className="confirm-icon danger"><DeleteOutlined /></div>
          <div>
            <div className="confirm-main">确认删除这条收款记录？</div>
            <div className="confirm-sub">
              {deleteTarget?.room_number || '-'} · {deleteTarget?.tenant_name || '-'} · {deleteTarget?.pay_date || '-'}
            </div>
          </div>
        </div>
        <div className="modal-actions">
          <button className="btn btn-outline" onClick={() => setDeleteTarget(null)}>取消</button>
          <button className="btn btn-danger" onClick={confirmDeletePayment}>删除</button>
        </div>
      </Modal>
    </div>
  )
}
