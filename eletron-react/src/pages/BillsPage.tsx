import { useState, useEffect } from 'react'
import { rental } from '../api'
import { useUIStore } from '../store'

interface Bill { id: number; tenant_name: string; room_number: string; billing_month: string; total_amount: number; status: string; building_name: string; building_id: number }
interface Building { id: number; name: string }

export function BillsPage() {
  const { planYear, planMonth } = useUIStore()
  const [bills, setBills] = useState<Bill[]>([])
  const [buildings, setBuildings] = useState<Building[]>([])
  const [curBid, setCurBid] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const billingMonth = `${planYear}-${String(planMonth).padStart(2, '0')}`

  const load = async () => {
    const [bs, blds] = await Promise.all([
      rental('bills', 'list', { month: billingMonth }),
      rental('buildings', 'list'),
    ])
    setBuildings(blds || [])
    if (blds?.length && !curBid) setCurBid(blds[0].id)
    const filtered = (bs || []).filter((b: Bill) => !curBid || Number(b.building_id) === Number(curBid))
    setBills(filtered)
    setLoading(false)
  }

  useEffect(() => { setLoading(true); load() }, [curBid, planYear, planMonth])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">账单管理</h2>
          <div className="flex gap-2">
            {buildings.map(b => (
              <button key={b.id} className={`px-3 py-1 rounded text-xs font-medium transition-colors ${curBid === b.id ? 'bg-[var(--primary-light)] text-[var(--primary)]' : 'text-[var(--text-secondary)] hover:bg-gray-100'}`}
                onClick={() => setCurBid(b.id)}>{b.name}</button>
            ))}
          </div>
        </div>
      </div>

      {loading ? <div className="text-sm text-[var(--text-third)] p-8">加载中...</div> :
        bills.length === 0 ? <div className="text-center py-20 text-[var(--text-third)]">暂无账单</div> :
          <div className="bg-white rounded-lg border border-[var(--border-light)] overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="bg-gray-50"><th className="text-left px-4 py-2.5 font-medium">租客</th><th className="text-left px-4 py-2.5 font-medium">房间</th><th className="text-left px-4 py-2.5 font-medium">账期</th><th className="text-left px-4 py-2.5 font-medium">合计</th><th className="text-left px-4 py-2.5 font-medium">状态</th></tr></thead>
              <tbody>
                {bills.map(b => (
                  <tr key={b.id} className="border-t border-[var(--border-light)] hover:bg-gray-50">
                    <td className="px-4 py-2.5">{b.tenant_name}</td>
                    <td className="px-4 py-2.5">{b.room_number}</td>
                    <td className="px-4 py-2.5">{b.billing_month}</td>
                    <td className="px-4 py-2.5">¥{Number(b.total_amount).toFixed(2)}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${b.status === 'paid' ? 'bg-[var(--green)]' : 'bg-[var(--text-third)]'}`} />
                      {b.status === 'paid' ? '已付' : '未付'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      }
    </div>
  )
}
