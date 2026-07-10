import { useState, useEffect } from 'react'
import { rental } from '../api'

interface Payment { id: number; bill_id: number; amount: number; pay_date: string; pay_method: string; tenant_name: string; room_number: string; billing_month: string }

export function PaymentsPage() {
  const [payments, setPayments] = useState<Payment[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    const data = await rental('payments', 'list') || []
    setPayments(data)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">收款记录</h2>
      {loading ? <div className="text-sm text-[var(--text-third)] p-8">加载中...</div> :
        payments.length === 0 ? <div className="text-center py-20 text-[var(--text-third)]">暂无收款记录</div> :
          <div className="bg-white rounded-lg border border-[var(--border-light)] overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="bg-gray-50"><th className="text-left px-4 py-2.5 font-medium">租客</th><th className="text-left px-4 py-2.5 font-medium">房间</th><th className="text-left px-4 py-2.5 font-medium">账期</th><th className="text-left px-4 py-2.5 font-medium">金额</th><th className="text-left px-4 py-2.5 font-medium">收款日期</th><th className="text-left px-4 py-2.5 font-medium">方式</th></tr></thead>
              <tbody>
                {payments.map(p => (
                  <tr key={p.id} className="border-t border-[var(--border-light)] hover:bg-gray-50">
                    <td className="px-4 py-2.5">{p.tenant_name || '-'}</td>
                    <td className="px-4 py-2.5">{p.room_number || '-'}</td>
                    <td className="px-4 py-2.5">{p.billing_month || '-'}</td>
                    <td className="px-4 py-2.5 font-semibold">¥{Number(p.amount).toFixed(2)}</td>
                    <td className="px-4 py-2.5">{p.pay_date || '-'}</td>
                    <td className="px-4 py-2.5">{p.pay_method || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      }
    </div>
  )
}
