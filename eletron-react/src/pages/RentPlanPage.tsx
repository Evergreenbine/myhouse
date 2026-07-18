import React from 'react'
import { CopyOutlined, DeleteOutlined, DownloadOutlined, LeftOutlined, PlusOutlined, RightOutlined, UploadOutlined } from '@ant-design/icons'
import { rental } from '../api'
import { DayPicker, MonthPicker, showToast } from '../components/ui'
import { resolveBuildingId, useUIStore } from '../store'
import Zoom from 'react-medium-image-zoom'
import html2canvas from 'html2canvas'
import { formatChineseMoney } from '../utils/money'

interface Contract { id: number; tenant_name: string; tenant_id: number; room_number: string; room_id: number; monthly_rent: number; water_unit_price: number; electric_unit_price: number; water_meter_id: number | null; electric_meter_id: number | null; building_id: number; building_name: string; status?: string; other_fee_details?: string }
interface Bill { id: number; contract_id: number; total_amount: number; status: string; water_fee: number; electric_fee: number; other_fee: number; other_fee_details?: string; remark?: string; water_current_reading: number; water_last_reading: number; electric_current_reading: number; electric_last_reading: number; water_photo: string; electric_photo: string }
interface MeterReading { id: number; meter_no: string; room_number: string; reading: number | null; previous_reading: number; usage: number | null; photo: string; status: string }
interface Building { id: number; name: string; rent_day: number }
interface OtherFeeItem { id: string; name: string; amount: string }
interface OtherFeeDetail { name: string; amount: number }

interface State {
  buildings: Building[]
  contracts: Contract[]
  bills: Bill[]
  curBid: number | null
  planYear: number
  planMonth: number
  loading: boolean
  firstLoad: boolean
  // drawer
  drawerOpen: boolean
  drawerStep: number
  drawerContract: Contract | null
  drawerBill: Bill | null
  waterMeter: MeterReading | null
  electricMeter: MeterReading | null
  wLast: string
  wCurr: string
  eLast: string
  eCurr: string
  wPhoto: string
  ePhoto: string
  otherFees: OtherFeeItem[]
  paidAmount: string
  paidDate: string
  waterPreviewOpen: boolean
  electricPreviewOpen: boolean
}

export class RentPlanPage extends React.Component<{}, State> {
  private planLoadSeq = 0
  private otherFeeItemSeq = 0
  private initialUiState = useUIStore.getState()

  state: State = {
    buildings: [],
    contracts: [],
    bills: [],
    curBid: null,
    planYear: this.initialUiState.planYear,
    planMonth: this.initialUiState.planMonth,
    loading: true,
    firstLoad: true,
    drawerOpen: false,
    drawerStep: 1,
    drawerContract: null,
    drawerBill: null,
    waterMeter: null,
    electricMeter: null,
    wLast: '', wCurr: '', eLast: '', eCurr: '',
    wPhoto: '', ePhoto: '',
    otherFees: [{ id: 'fee-initial', name: '', amount: '' }],
    paidAmount: '', paidDate: new Date().toISOString().split('T')[0],
    waterPreviewOpen: false, electricPreviewOpen: false,
  }

  componentDidMount() { this.loadBuildings() }

  formatBillingMonth = (year: number, month: number) => year + '-' + String(month).padStart(2, '0')

  get billingMonth() { return this.formatBillingMonth(this.state.planYear, this.state.planMonth) }

  loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = resolveBuildingId(data)
    useUIStore.getState().setSelectedBuildingId(bid)
    this.setState({ buildings: data, curBid: bid, firstLoad: false, loading: false }, () => {
      if (bid) this.loadPlan(bid)
    })
  }

  loadPlan = async (bid: number, month = this.billingMonth) => {
    const seq = ++this.planLoadSeq
    const timer = setTimeout(() => {
      if (seq === this.planLoadSeq) this.setState({ loading: true })
    }, 200)
    const [allContracts, bs] = await Promise.all([
      rental('contracts', 'list', { active_only: false, building_id: bid }),
      rental('bills', 'list', { month }),
    ])
    clearTimeout(timer)
    if (seq !== this.planLoadSeq || this.state.curBid !== bid || this.billingMonth !== month) return
    const billContractIds = new Set((bs || []).map((b: Bill) => Number(b.contract_id)))
    const visibleContracts = (allContracts || []).filter((c: Contract) =>
      c.status === 'active' || billContractIds.has(Number(c.id))
    )
    this.setState({ contracts: visibleContracts, bills: bs || [], loading: false })
  }

  switchBuilding = (id: number) => {
    useUIStore.getState().setSelectedBuildingId(id)
    this.setState({ curBid: id }, () => this.loadPlan(id))
  }

  changeMonth = (delta: number) => {
    const { planYear: currentYear, planMonth: currentMonth, curBid } = this.state
    let planYear = currentYear
    let planMonth = currentMonth + delta
    if (planMonth < 1) { planMonth = 12; planYear-- }
    if (planMonth > 12) { planMonth = 1; planYear++ }
    const month = this.formatBillingMonth(planYear, planMonth)
    useUIStore.getState().setPlanYearMonth(planYear, planMonth)
    this.setState({ planYear, planMonth }, () => {
      if (curBid) this.loadPlan(curBid, month)
    })
  }

  selectMonth = (value: string) => {
    const [yearText, monthText] = value.split('-')
    const planYear = Number(yearText)
    const planMonth = Number(monthText)
    if (!planYear || planMonth < 1 || planMonth > 12) return
    const month = this.formatBillingMonth(planYear, planMonth)
    useUIStore.getState().setPlanYearMonth(planYear, planMonth)
    this.setState({ planYear, planMonth }, () => {
      if (this.state.curBid) this.loadPlan(this.state.curBid, month)
    })
  }

  getBillStep = (bill?: Bill | null) => {
    if (!bill?.id) return 1
    if (bill.status === 'draft') return 1
    if (bill.status === 'paid') return 3
    if (bill.status === 'pending_payment') return 3
    return 2
  }

  getStepDotClass = (step: number) => {
    if (step === 1) return 'step-entry'
    if (step === 2) return 'step-preview'
    return 'step-payment'
  }

  getStepLabel = (step: number) => {
    if (step === 1) return '录入账单'
    if (step === 2) return '预览账单'
    return '收款'
  }

  setDrawerStep = async (step: number) => {
    const nextStep = Math.max(1, Math.min(3, step))
    if (nextStep > 1 && !this.state.drawerBill?.id) {
      showToast('请先保存账单')
      return
    }
    if (nextStep === 1 && this.state.drawerBill?.id && this.state.drawerBill.status !== 'paid') {
      await rental('bills', 'update_status', { id: this.state.drawerBill.id, status: 'draft' })
      this.setState((s: State) => ({
        drawerStep: 1,
        drawerBill: s.drawerBill ? { ...s.drawerBill, status: 'draft' } : s.drawerBill,
      }))
      if (this.state.curBid) this.loadPlan(this.state.curBid)
      return
    }
    this.setState({ drawerStep: nextStep })
  }

  createOtherFeeItem = (name = '', amount = ''): OtherFeeItem => ({
    id: `fee-${Date.now()}-${++this.otherFeeItemSeq}`,
    name,
    amount,
  })

  parseOtherFeeItems = (source?: { other_fee_details?: string; other_fee?: number | string }): OtherFeeItem[] => {
    try {
      const parsed = JSON.parse(source?.other_fee_details || '[]')
      if (Array.isArray(parsed) && parsed.length > 0) {
        const items = parsed
          .map((item: any) => ({
            name: String(item?.name || item?.project_name || '').trim(),
            amount: Number(item?.amount),
          }))
          .filter(item => item.name && Number.isFinite(item.amount) && item.amount > 0)
          .map(item => this.createOtherFeeItem(item.name, String(item.amount)))
        if (items.length > 0) return items
      }
    } catch {
      // 兼容尚未保存明细的旧账单，继续使用汇总金额回填。
    }
    const legacyAmount = Number(source?.other_fee || 0)
    if (legacyAmount > 0) return [this.createOtherFeeItem('其他费用', String(legacyAmount))]
    return [this.createOtherFeeItem()]
  }

  addOtherFeeItem = () => {
    this.setState(state => ({ otherFees: [...state.otherFees, this.createOtherFeeItem()] }))
  }

  updateOtherFeeItem = (id: string, field: 'name' | 'amount', value: string) => {
    this.setState(state => ({
      otherFees: state.otherFees.map(item => item.id === id ? { ...item, [field]: value } : item),
    }))
  }

  removeOtherFeeItem = (id: string) => {
    this.setState(state => {
      const remaining = state.otherFees.filter(item => item.id !== id)
      return { otherFees: remaining.length > 0 ? remaining : [this.createOtherFeeItem()] }
    })
  }

  getOtherFeeAmount = () => this.state.otherFees.reduce((total, item) => {
    const amount = Number(item.amount)
    return total + (Number.isFinite(amount) && amount > 0 ? amount : 0)
  }, 0)

  getOtherFeeDetails = (): OtherFeeDetail[] => this.state.otherFees
    .map(item => ({ name: item.name.trim(), amount: Number(item.amount) }))
    .filter(item => item.name && Number.isFinite(item.amount) && item.amount > 0)

  openDrawer = async (contract: Contract) => {
    const billSummary = this.state.bills.find(b => Number(b.contract_id) === Number(contract.id))

    const [billDetail, waterRows, electricRows] = await Promise.all([
      billSummary?.id ? rental('bills', 'get', { id: billSummary.id }) : Promise.resolve(billSummary),
      contract.water_meter_id ? rental('readings', 'monthly', { type: 'water', month: this.billingMonth, meter_id: contract.water_meter_id }) : Promise.resolve([]),
      contract.electric_meter_id ? rental('readings', 'monthly', { type: 'electric', month: this.billingMonth, meter_id: contract.electric_meter_id }) : Promise.resolve([]),
    ])
    const bill = billDetail || billSummary
    var wm = (waterRows || [])[0] || null
    var em = (electricRows || [])[0] || null

    const step = this.getBillStep(bill)


    this.setState({
      drawerOpen: true, drawerStep: step,
      drawerContract: contract, drawerBill: bill || null,
      waterMeter: wm, electricMeter: em,
      wLast: String(wm?.previous_reading || 0),
      wCurr: wm?.reading != null ? String(wm.reading) : '',
      eLast: String(em?.previous_reading || 0),
      eCurr: em?.reading != null ? String(em.reading) : '',
      wPhoto: wm?.photo || bill?.water_photo || '',
      ePhoto: em?.photo || bill?.electric_photo || '',
      otherFees: this.parseOtherFeeItems(bill || contract),
    })
  }

  calcWaterFee = () => {
    const { drawerContract, wLast, wCurr } = this.state
    return Math.max(0, (parseFloat(wCurr) || 0) - parseFloat(wLast) || 0) * Number(drawerContract?.water_unit_price || 0)
  }
  calcElectricFee = () => {
    const { drawerContract, eLast, eCurr } = this.state
    return Math.max(0, (parseFloat(eCurr) || 0) - parseFloat(eLast) || 0) * Number(drawerContract?.electric_unit_price || 0)
  }

  hasReading = (value: string) => value.trim() !== ''

  parseOptionalReading = (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) return null
    const num = Number(trimmed)
    return Number.isFinite(num) ? num : null
  }

  formatReceiptReading = (value: string) => value.trim() === '' ? '' : value

  formatReceiptUsage = (current: string, last: string, fractionDigits: number) => {
    if (!this.hasReading(current)) return ''
    const usage = Math.max(0, (parseFloat(current) || 0) - (parseFloat(last) || 0))
    return usage.toFixed(fractionDigits)
  }

  waitForReceiptImages = async (el: HTMLElement) => {
    const images = Array.from(el.querySelectorAll('img'))
    await Promise.all(images.map(img => {
      if (img.complete && img.naturalWidth > 0) return Promise.resolve()
      return new Promise<void>(resolve => {
        const done = () => resolve()
        img.addEventListener('load', done, { once: true })
        img.addEventListener('error', done, { once: true })
        window.setTimeout(done, 3000)
      })
    }))
  }

  handlePhoto = (type: 'water' | 'electric', e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async () => {
      const dataUrl = reader.result as string
      if (type === 'water') this.setState({ wPhoto: dataUrl })
      else this.setState({ ePhoto: dataUrl })
      // AI识别读数
      try {
        const meterType = type === 'water' ? '水表' : '电表'
        const res = await rental('_ocr', 'read', { image: dataUrl, meter_type: meterType })
        if (res && res.numbers && res.numbers.length > 0) {
          const num = res.numbers[0]
          if (type === 'water') this.setState({ wCurr: String(num) })
          else this.setState({ eCurr: String(num) })
          showToast('AI识别读数：' + num)
        } else {
          showToast('未识别到数字，请手动输入')
        }
      } catch(err) {
        showToast('识别失败，请手动输入')
      }
    }
    reader.readAsDataURL(file)
  }

  removePhoto = (type: 'water' | 'electric') => {
    const isWater = type === 'water'
    const input = document.getElementById(isWater ? 'file_water' : 'file_electric') as HTMLInputElement | null
    if (input) input.value = ''
    if (isWater) this.setState({ wPhoto: '', waterPreviewOpen: false })
    else this.setState({ ePhoto: '', electricPreviewOpen: false })
    showToast(`${isWater ? '水表' : '电表'}照片已移除，请保存数据`)
  }

  saveDrawer = async () => {
    const { drawerContract, drawerBill, waterMeter, electricMeter, wLast, wCurr, eLast, eCurr, wPhoto, ePhoto, otherFees } = this.state
    const contract = drawerContract!
    const waterFee = this.calcWaterFee()
    const elecFee = this.calcElectricFee()
    const rentAmount = Number(contract.monthly_rent || 0)
    const enteredOtherFees = otherFees.filter(item => item.name.trim() || item.amount.trim())
    for (const item of enteredOtherFees) {
      if (!item.name.trim()) {
        showToast('请填写其他费用的项目名称')
        return
      }
      const amount = Number(item.amount)
      if (!item.amount.trim() || !Number.isFinite(amount) || amount <= 0) {
        showToast(`请输入“${item.name.trim()}”的有效费用`)
        return
      }
    }
    const otherFeeDetails: OtherFeeDetail[] = enteredOtherFees.map(item => ({
      name: item.name.trim(),
      amount: Number(item.amount),
    }))
    const otherFeeAmount = otherFeeDetails.reduce((total, item) => total + item.amount, 0)

    const waterCurrReading = this.parseOptionalReading(wCurr)
    const electricCurrReading = this.parseOptionalReading(eCurr)

    if (waterMeter && waterCurrReading !== null) {
      await rental('readings', 'save_monthly', { meter_id: waterMeter.id, month: this.billingMonth, reading: waterCurrReading, photo: wPhoto })
    }
    if (electricMeter && electricCurrReading !== null) {
      await rental('readings', 'save_monthly', { meter_id: electricMeter.id, month: this.billingMonth, reading: electricCurrReading, photo: ePhoto })
    }

    const data = {
      contract_id: contract.id, billing_month: this.billingMonth,
      rent_amount: rentAmount, water_fee: waterFee, electric_fee: elecFee,
      other_fee: otherFeeAmount, other_fee_details: JSON.stringify(otherFeeDetails), remark: drawerBill?.remark || '',
      water_last: parseFloat(wLast) || 0, water_curr: waterCurrReading,
      electric_last: parseFloat(eLast) || 0, electric_curr: electricCurrReading,
      water_photo: wPhoto, electric_photo: ePhoto,
    }

    const res = drawerBill?.id
      ? await rental('bills', 'update', { ...data, id: drawerBill.id })
      : await rental('bills', 'add', data)

    if (res && !res.error) {
      const bid = drawerBill?.id || res.id
      await rental('bills', 'update_status', { id: bid, status: 'pending' })
      showToast('保存成功')
      this.setState({ drawerStep: 2, drawerBill: { ...data, id: bid, total_amount: rentAmount + waterFee + elecFee + otherFeeAmount, status: 'pending' } as any })
      if (this.state.curBid) this.loadPlan(this.state.curBid)
    } else { showToast('保存失败') }
  }

  
  goToPaymentStep = async () => {
    if (this.state.drawerBill?.id) {
      await rental('bills', 'update_status', { id: this.state.drawerBill.id, status: 'pending_payment' })
    }
    this.setState((s: State) => ({
      drawerStep: 3,
      drawerBill: s.drawerBill ? { ...s.drawerBill, status: 'pending_payment' } : s.drawerBill,
    }))
    if (this.state.curBid) this.loadPlan(this.state.curBid)
  }

  confirmPayment = async () => {
    if (!this.state.drawerBill?.id) return
    const amountText = this.state.paidAmount.trim()
    const fallbackAmount = Number(this.state.drawerBill.total_amount || 0)
    const amount = amountText ? Number(amountText) : fallbackAmount
    if (!Number.isFinite(amount) || amount <= 0) {
      showToast('请输入有效收款金额')
      return
    }
    await rental('payments', 'add', {
      bill_id: this.state.drawerBill.id,
      amount,
      pay_date: this.state.paidDate,
      pay_method: '收租计划',
      remark: '收租计划确认收款',
    })
    const nextStatus = amount >= fallbackAmount ? 'paid' : 'partial'
    showToast('收款确认')
    this.setState((s: any) => ({
      drawerStep: 3,
      paidAmount: String(amount),
      drawerBill: { ...s.drawerBill, status: nextStatus }
    }))
    if (this.state.curBid) this.loadPlan(this.state.curBid)
  }

  receiptToCanvas = async (): Promise<HTMLCanvasElement | null> => {
    const el = document.querySelector('.receipt-capture') as HTMLElement | null
    if (!el) return null
    // 只截取收据正文，避免把复制/保存按钮和抽屉操作区带进图片。
    try {
      await this.waitForReceiptImages(el)
      const rect = el.getBoundingClientRect()
      const wrapper = document.createElement('div')
      wrapper.style.position = 'fixed'
      wrapper.style.left = '-10000px'
      wrapper.style.top = '0'
      wrapper.style.zIndex = '-1'
      wrapper.style.pointerEvents = 'none'
      wrapper.style.overflow = 'visible'
      wrapper.style.background = '#FFF4E1'
      wrapper.style.width = Math.ceil(rect.width) + 'px'
      wrapper.style.minWidth = Math.ceil(rect.width) + 'px'

      const clone = el.cloneNode(true) as HTMLElement
      clone.style.maxHeight = 'none'
      clone.style.overflow = 'visible'
      clone.style.width = '100%'

      wrapper.appendChild(clone)
      document.body.appendChild(wrapper)
      try {
        return await html2canvas(clone, {
          backgroundColor: '#FFF4E1',
          scale: 2,
          useCORS: true,
          width: clone.scrollWidth,
          height: clone.scrollHeight,
        })
      } finally {
        document.body.removeChild(wrapper)
      }
    } catch { return null }
  }

  copyReceipt = async () => {
    var canvas = await this.receiptToCanvas()
    if (!canvas) { showToast('复制失败，请手动截图'); return }
    canvas.toBlob(async (blob: Blob | null) => {
      if (!blob) { showToast('复制失败'); return }
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      showToast('已复制到剪贴板')
    }, 'image/png')
  }

  saveReceipt = async () => {
    var canvas = await this.receiptToCanvas()
    if (!canvas) { showToast('保存失败'); return }
    var dataUrl = canvas.toDataURL('image/png')
    var a = document.createElement('a')
    a.href = dataUrl
    a.download = 'receipt_' + new Date().toISOString().split('T')[0] + '.png'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    showToast('已保存图片')
  }

  closeDrawer = () => this.setState({ drawerOpen: false })

  renderOtherFeeReceiptRows = () => this.getOtherFeeDetails().map((item, index) => (
    <tr key={`other-fee-receipt-${index}`}>
      <td style={{padding:6,border:'1px solid #ddd'}}>{item.name}</td>
      <td style={{padding:6,border:'1px solid #ddd'}} colSpan={4} />
      <td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{item.amount.toFixed(2)}</td>
    </tr>
  ))

  render() {
    const { buildings, contracts, bills, curBid, planYear, planMonth, loading } = this.state
    if (this.state.firstLoad) return <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div>

    if (buildings.length === 0) return (
      <div className="empty-state"><div className="icon">📊</div><div>请先添加楼栋和合同</div></div>
    )

    // 汇总统计
    var totalRent = 0, paidAmount = 0, paidCount = 0, unpaidCount = 0
    contracts.forEach(c => {
      const bill = bills.find(b => Number(b.contract_id) === Number(c.id))
      const ta = bill ? Number(bill.total_amount || 0) : Number(c.monthly_rent || 0)
      totalRent += ta
      if (bill && bill.status === 'paid') { paidCount++; paidAmount += ta }
      if (!bill || bill.status !== 'paid') unpaidCount++
    })

    return (
      <div>
        {/* 月份筛选 */}
        <div className="month-filter">
          <button className="month-nav" onClick={() => this.changeMonth(-1)} aria-label="上一个月"><LeftOutlined /></button>
          <MonthPicker value={this.billingMonth} onChange={this.selectMonth} ariaLabel="选择账单月份" />
          <button className="month-nav" onClick={() => this.changeMonth(1)} aria-label="下一个月"><RightOutlined /></button>
        </div>

        {/* 楼栋 tabs */}
        <div className="tab-action-row">
          <div className="building-tabs">
            {buildings.map(b => (
              <button key={b.id}
                className={'building-tab' + (Number(b.id) === Number(curBid) ? ' active' : '')}
                onClick={() => this.switchBuilding(b.id)}>{b.name}</button>
            ))}
          </div>
        </div>

        {loading ? <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div> : (
          <>
            {/* 汇总 */}
            <div className="summary-row">
              <div className="stat-card"><div>当月应收</div><div className="stat-val" style={{color:'var(--blue)'}}>¥{totalRent.toFixed(2)}</div></div>
              <div className="stat-card"><div>当月已收</div><div className="stat-val" style={{color:'var(--green)'}}>¥{paidAmount.toFixed(2)}</div></div>
              <div className="stat-card"><div>已收户数</div><div className="stat-val" style={{color:'var(--text-sec)'}}>{paidCount}户</div></div>
              <div className="stat-card"><div>未收户数</div><div className="stat-val" style={{color:'var(--red)'}}>{unpaidCount}户</div></div>
            </div>

            {contracts.length === 0 ? (
              <div className="empty-state"><div className="icon">📋</div><div>当前筛选条件下没有合同</div></div>
            ) : (
              <div className="plan-cards">
                {contracts.map(c => {
                  const bill = bills.find(b => Number(b.contract_id) === Number(c.id))
                  const status = bill ? (bill.status || 'unpaid') : 'empty'
                  const isDrawerContract = this.state.drawerOpen && this.state.drawerContract && Number(this.state.drawerContract.id) === Number(c.id)
                  const dotClass = isDrawerContract ? this.getStepDotClass(this.state.drawerStep) : status === 'paid' ? 'paid' : status === 'pending_payment' ? 'step-payment' : status === 'draft' ? 'step-entry' : status === 'empty' ? 'empty' : 'unpaid'
                  const statusLabel = status === 'paid' ? '已收' : status === 'pending_payment' ? '待收款' : status === 'draft' ? '录入中' : status === 'pending' ? '待发送' : status === 'empty' ? '未录入' : '未收'
                  const dotLabel = isDrawerContract ? this.getStepLabel(this.state.drawerStep) : statusLabel
                  const statusCls = status === 'paid' ? 'tag-green' : status === 'pending_payment' ? 'tag-green' : status === 'draft' ? 'tag-blue' : status === 'empty' ? 'tag-red' : 'tag-orange'
                  const waterFee = bill ? Number(bill.water_fee || 0) : 0
                  const electricFee = bill ? Number(bill.electric_fee || 0) : 0
                  const otherFee = bill ? Number(bill.other_fee || 0) : 0
                  const totalAmount = bill ? Number(bill.total_amount || 0) : Number(c.monthly_rent || 0)
                  return (
                    <div key={c.id} className="plan-card" onClick={() => this.openDrawer(c)}>
                      <div className={'card-dot ' + dotClass} title={dotLabel} onClick={e => e.stopPropagation()} />
                      <div className="card-header">
                        <span className="card-room">{c.room_number || ''}</span>
                        <span className="card-tenant">{c.tenant_name || ''}</span>
                      </div>
                      <div className="card-items">
                        <div className="card-item">月租 <span>¥{Number(c.monthly_rent || 0).toFixed(2)}</span></div>
                        {waterFee > 0 && <div className="card-item">水费 <span>¥{waterFee.toFixed(2)}</span></div>}
                        {electricFee > 0 && <div className="card-item">电费 <span>¥{electricFee.toFixed(2)}</span></div>}
                        {otherFee > 0 && <div className="card-item">其他费用 <span>¥{otherFee.toFixed(2)}</span></div>}
                      </div>
                      <div className="card-total">
                        <span className={'tag ' + statusCls}>{statusLabel}</span>
                        <span className="amount">¥{totalAmount.toFixed(2)}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}

        {this.renderDrawer()}
      </div>
    )
  }

  renderDrawer() {
    const { drawerOpen, drawerStep, drawerContract, drawerBill, waterMeter, electricMeter, wLast, wCurr, eLast, eCurr, wPhoto, ePhoto, otherFees } = this.state
    if (!drawerOpen || !drawerContract) return null
    const waterFee = this.calcWaterFee()
    const elecFee = this.calcElectricFee()
    const rentAmount = Number(drawerContract.monthly_rent || 0)
    const otherFeeAmount = this.getOtherFeeAmount()
    const calculatedTotal = rentAmount + waterFee + elecFee + otherFeeAmount
    const totalAmount = Number(drawerStep === 1 ? calculatedTotal : (drawerBill?.total_amount ?? calculatedTotal)).toFixed(2)

    return (
      <>
        <div className="drawer-overlay open" onClick={this.closeDrawer} />
        <div className="drawer open">
          <div className="drawer-header">
            <span className="drawer-title">{drawerContract.tenant_name} · {drawerContract.room_number}</span>
            <button className="drawer-close" onClick={this.closeDrawer}>✕</button>
          </div>

          <div className="drawer-steps" style={{display:'flex',padding:14,justifyContent:'center',gap:0,alignItems:'center',borderBottom:'1px solid var(--border-light)',background:'var(--bg)'}}>
              <button className={'step step-1' + (drawerStep === 1 ? ' active' : '') + (drawerStep > 1 ? ' done' : '')}
                onClick={() => this.setDrawerStep(1)}><span className="step-num">1</span>录入</button>
              <div className="step-line" />
              <button className={'step step-2' + (drawerStep === 2 ? ' active' : '') + (drawerStep > 2 ? ' done' : '')}
                onClick={() => this.setDrawerStep(2)}><span className="step-num">2</span>预览</button>
              <div className="step-line" />
              <button className={'step step-3' + (drawerStep === 3 ? ' active' : '')}
                onClick={() => this.setDrawerStep(3)}><span className="step-num">3</span>收款</button>
            </div>

          <div className="drawer-body">
            {drawerStep === 1 && (
              <div>
                <div className="drawer-section">
                  <div className="section-label">📋 月租</div>
                  <div className="locked-field">¥{rentAmount.toFixed(2)} / 月</div>
                </div>

                <div className="drawer-section">
                  <div className="section-label">💧 水费（单价：¥{Number(drawerContract.water_unit_price||0).toFixed(2)}/m³）{waterMeter?.meter_no ? <span className="ms-tag" style={{marginLeft:8}}>{waterMeter.meter_no}</span> : ''}</div>
                  <div style={{display:'flex',gap:8,marginBottom:8}}>
                    <div style={{flex:1}}><label style={{fontSize:11,color:'var(--text-sec)'}}>上月读数（m³）</label>
                      <input className="soft-input" type="number" value={wLast} onChange={e => this.setState({ wLast: e.target.value })} step="0.1" placeholder="0" style={{height:32}} /></div>
                    <div style={{flex:1}}><label style={{fontSize:11,color:'var(--text-sec)'}}>当月结算读数（m³）</label>
                      <input className="soft-input" type="number" value={wCurr} onChange={e => this.setState({ wCurr: e.target.value })} step="0.1" placeholder="请输入读数" style={{height:32}} /></div>
                    <div style={{flex:1}}><label style={{fontSize:11,color:'var(--text-sec)'}}>水费（元）</label>
                      <div className="locked-field" style={{height:32}}>¥{waterFee.toFixed(2)}</div></div>
                  </div>
                  <div className={'upload-area' + (wPhoto ? ' has-image' : '')}>
                    <input type="file" accept="image/*" onChange={e => this.handlePhoto('water', e)} id="file_water" style={{display:'none'}} />
                    <div className="upload-preview" style={{flexDirection:'column',gap:6}}>
                      {wPhoto ? (
                        <div className="meter-photo-preview">
                          <Zoom><img src={wPhoto} className="meter-preview-img" title="点击放大预览" /></Zoom>
                          <div className="meter-photo-actions">
                            <button type="button" className="meter-photo-action" onClick={() => document.getElementById('file_water')?.click()}>
                              <UploadOutlined /> 更换
                            </button>
                            <button type="button" className="meter-photo-action delete" onClick={() => this.removePhoto('water')}>
                              <DeleteOutlined /> 删除
                            </button>
                          </div>
                        </div>
                      ) : (
                        <span style={{cursor:'pointer'}} onClick={() => document.getElementById('file_water')?.click()}>📷 点击或拖拽上传水表照片</span>
                      )}
                    </div>
                    
                  </div>
                </div>

                <div className="drawer-section">
                  <div className="section-label">⚡ 电费（单价：¥{Number(drawerContract.electric_unit_price||0).toFixed(2)}/度）{electricMeter?.meter_no ? <span className="ms-tag" style={{marginLeft:8}}>{electricMeter.meter_no}</span> : ''}</div>
                  <div style={{display:'flex',gap:8,marginBottom:8}}>
                    <div style={{flex:1}}><label style={{fontSize:11,color:'var(--text-sec)'}}>上月读数（度）</label>
                      <input className="soft-input" type="number" value={eLast} onChange={e => this.setState({ eLast: e.target.value })} step="0.1" placeholder="0" style={{height:32}} /></div>
                    <div style={{flex:1}}><label style={{fontSize:11,color:'var(--text-sec)'}}>当月结算读数（度）</label>
                      <input className="soft-input" type="number" value={eCurr} onChange={e => this.setState({ eCurr: e.target.value })} step="0.1" placeholder="请输入读数" style={{height:32}} /></div>
                    <div style={{flex:1}}><label style={{fontSize:11,color:'var(--text-sec)'}}>电费（元）</label>
                      <div className="locked-field" style={{height:32}}>¥{elecFee.toFixed(2)}</div></div>
                  </div>
                  <div className={'upload-area' + (ePhoto ? ' has-image' : '')}>
                    <input type="file" accept="image/*" onChange={e => this.handlePhoto('electric', e)} id="file_electric" style={{display:'none'}} />
                    <div className="upload-preview" style={{flexDirection:'column',gap:6}}>
                      {ePhoto ? (
                        <div className="meter-photo-preview">
                          <Zoom><img src={ePhoto} className="meter-preview-img" title="点击放大预览" /></Zoom>
                          <div className="meter-photo-actions">
                            <button type="button" className="meter-photo-action" onClick={() => document.getElementById('file_electric')?.click()}>
                              <UploadOutlined /> 更换
                            </button>
                            <button type="button" className="meter-photo-action delete" onClick={() => this.removePhoto('electric')}>
                              <DeleteOutlined /> 删除
                            </button>
                          </div>
                        </div>
                      ) : (
                        <span style={{cursor:'pointer'}} onClick={() => document.getElementById('file_electric')?.click()}>📷 点击或拖拽上传电表照片</span>
                      )}
                    </div>
                    
                  </div>
                </div>

                <div className="drawer-section">
                  <div className="section-label">其他费用</div>
                  <div className="other-fee-editor">
                    <div className="other-fee-editor-head">
                      <span>项目名称</span>
                      <span>费用（元）</span>
                      <span>操作</span>
                    </div>
                    {otherFees.map(item => (
                      <div className="other-fee-editor-row" key={item.id}>
                        <input type="text" value={item.name} placeholder="如：网费、卫生费"
                          onChange={e => this.updateOtherFeeItem(item.id, 'name', e.target.value)} />
                        <input type="number" min="0" step="0.01" value={item.amount} placeholder="0.00"
                          onChange={e => this.updateOtherFeeItem(item.id, 'amount', e.target.value)} />
                        <button type="button" className="other-fee-delete" title="删除项目" aria-label="删除费用项目"
                          onClick={() => this.removeOtherFeeItem(item.id)}><DeleteOutlined /></button>
                      </div>
                    ))}
                    <div className="other-fee-editor-footer">
                      <span>小计：<strong>¥{otherFeeAmount.toFixed(2)}</strong></span>
                      <button type="button" className="btn btn-sm btn-outline other-fee-add" onClick={this.addOtherFeeItem}>
                        <PlusOutlined /> 添加项目
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {drawerStep === 2 && drawerBill && (
              <>
                <div className="drawer-section">
                  <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:10}}>
                    <span className="section-label" style={{marginBottom:0}}>📋 账单预览</span>
                    <div style={{display:'flex',gap:6}}>
                      <button className="btn btn-sm btn-outline" onClick={() => this.setDrawerStep(1)} style={{padding:'3px 10px',fontSize:11,borderRadius:6}}>返回录入</button>
                      <button className="btn btn-sm btn-primary" onClick={this.goToPaymentStep} style={{padding:'3px 12px',fontSize:11,borderRadius:6}}>完成发送</button>
                    </div>
                  </div>
                  <div className="receipt-image-toolbar">
                    <div className="ai-bill-image-tools">
                      <button type="button" onClick={this.copyReceipt} title="复制账单图片" aria-label="复制账单图片">
                        <CopyOutlined />
                      </button>
                      <button type="button" onClick={this.saveReceipt} title="保存账单图片" aria-label="保存账单图片">
                        <DownloadOutlined />
                      </button>
                    </div>
                  </div>
                  <div className="receipt-capture" style={{border:'1px solid var(--border-light)',borderRadius:8,padding:16,background:'var(--receipt-bg)',fontSize:13}}>
                    <div style={{textAlign:'center',fontWeight:600,fontSize:15,marginBottom:2}}>房租及费用收据</div>
                    <div style={{fontSize:11,color:'var(--text-third)',marginBottom:8}}>No.{(this.state.planYear + '-' + String(this.state.planMonth).padStart(2,'0')).replace('-','') + drawerContract.room_number}</div>
                    <div style={{marginBottom:6}}>房间：<b>{drawerContract.room_number}</b></div>
                    <table style={{width:'100%',borderCollapse:'collapse',fontSize:12,margin:'8px 0'}}>
                    <thead><tr style={{background:'var(--receipt-bg)'}}><th style={{padding:6,border:'1px solid #ddd'}}>项目</th><th style={{padding:6,border:'1px solid #ddd'}}>本月读数</th><th style={{padding:6,border:'1px solid #ddd'}}>上月读数</th><th style={{padding:6,border:'1px solid #ddd'}}>实用量</th><th style={{padding:6,border:'1px solid #ddd'}}>单价</th><th style={{padding:6,border:'1px solid #ddd'}}>金额</th></tr></thead>
                    <tbody>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>水费（吨）</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{this.formatReceiptReading(wCurr)}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{wLast || '—'}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.water_unit_price) > 0 ? this.formatReceiptUsage(wCurr, wLast, 1) : ''}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.water_unit_price).toFixed(2)}</td>
                        <td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{waterFee.toFixed(2)}</td></tr>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>电费（度）</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{this.formatReceiptReading(eCurr)}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{eLast || '—'}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.electric_unit_price) > 0 ? this.formatReceiptUsage(eCurr, eLast, 0) : ''}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.electric_unit_price).toFixed(2)}</td>
                        <td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{elecFee.toFixed(2)}</td></tr>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>房租</td><td style={{padding:6,border:'1px solid #ddd'}} colSpan={4} /><td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{rentAmount.toFixed(2)}</td></tr>
                      {this.renderOtherFeeReceiptRows()}
                    </tbody>
                  </table>
                  <div style={{textAlign:'right',fontWeight:700,fontSize:15}}>合计：<span style={{color:'var(--red)',fontSize:18}}>¥{totalAmount}</span></div>
                  <div className="receipt-total-cn">大写：{formatChineseMoney(totalAmount)}</div>
                  <div style={{textAlign:'right',fontSize:12,color:'var(--text-sec)',marginTop:4,lineHeight:1.8}}>
                    <div>交款人：{drawerContract.tenant_name}</div>
                    <div>收款人：吴钦腾</div>
                    <div>发单日期：{new Date().toISOString().split('T')[0]}</div>
                  </div>
                  {(wPhoto || ePhoto) && (
                    <>
                      <hr style={{margin:'10px 0',border:'none',borderTop:'1px dashed #ddd'}} />
                      <div style={{display:'flex',flexDirection:'column',alignItems:'center',gap:10}}>
                        {wPhoto && (
                          <Zoom><img src={wPhoto} className="meter-preview-img" style={{maxWidth:'100%',maxHeight:260,borderRadius:6,border:'1px solid #ddd'}} /></Zoom>
                        )}
                        {ePhoto && (
                          <>
                            <hr style={{width:'80%',margin:'4px 0',border:'none',borderTop:'1px dashed #DDE3EA'}} />
                            <Zoom><img src={ePhoto} className="meter-preview-img" style={{width:'100%',maxWidth:320,aspectRatio:'1',objectFit:'cover',borderRadius:6,border:'1px solid #ddd'}} /></Zoom>
                          </>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
              </>
            )}

            {drawerStep === 3 && drawerBill && drawerBill.status !== 'paid' && (
              <>
                <div className="drawer-section">
                  <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:10}}>
                    <span className="section-label" style={{marginBottom:0}}>📋 账单预览</span>
                  </div>
                  <div className="receipt-capture" style={{border:'1px solid var(--border-light)',borderRadius:8,padding:16,background:'var(--receipt-bg)',fontSize:13}}>
                    <div style={{textAlign:'center',fontWeight:600,fontSize:15,marginBottom:2}}>房租及费用收据</div>
                    <div style={{fontSize:11,color:'var(--text-third)',marginBottom:8}}>No.{(this.state.planYear + '-' + String(this.state.planMonth).padStart(2,'0')).replace('-','') + drawerContract.room_number}</div>
                    <div style={{marginBottom:6}}>房间：<b>{drawerContract.room_number}</b></div>
                    <table style={{width:'100%',borderCollapse:'collapse',fontSize:12,margin:'8px 0'}}>
                    <thead><tr style={{background:'var(--receipt-bg)'}}><th style={{padding:6,border:'1px solid #ddd'}}>项目</th><th style={{padding:6,border:'1px solid #ddd'}}>本月读数</th><th style={{padding:6,border:'1px solid #ddd'}}>上月读数</th><th style={{padding:6,border:'1px solid #ddd'}}>实用量</th><th style={{padding:6,border:'1px solid #ddd'}}>单价</th><th style={{padding:6,border:'1px solid #ddd'}}>金额</th></tr></thead>
                    <tbody>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>水费（吨）</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{this.formatReceiptReading(wCurr)}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{wLast || '—'}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.water_unit_price) > 0 ? this.formatReceiptUsage(wCurr, wLast, 1) : ''}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.water_unit_price).toFixed(2)}</td>
                        <td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{waterFee.toFixed(2)}</td></tr>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>电费（度）</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{this.formatReceiptReading(eCurr)}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{eLast || '—'}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.electric_unit_price) > 0 ? this.formatReceiptUsage(eCurr, eLast, 0) : ''}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.electric_unit_price).toFixed(2)}</td>
                        <td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{elecFee.toFixed(2)}</td></tr>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>房租</td><td style={{padding:6,border:'1px solid #ddd'}} colSpan={4} /><td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{rentAmount.toFixed(2)}</td></tr>
                      {this.renderOtherFeeReceiptRows()}
                    </tbody>
                  </table>
                  <div style={{textAlign:'right',fontWeight:700,fontSize:15}}>合计：<span style={{color:'var(--red)',fontSize:18}}>¥{totalAmount}</span></div>
                  <div className="receipt-total-cn">大写：{formatChineseMoney(totalAmount)}</div>
                  <div style={{textAlign:'right',fontSize:12,color:'var(--text-sec)',marginTop:4,lineHeight:1.8}}>
                    <div>付款人：{drawerContract.tenant_name}</div>
                    <div>收款人：吴钦腾</div>
                    <div>发单日期：{new Date().toISOString().split('T')[0]}</div>
                  </div>
                  {(wPhoto || ePhoto) && (
                    <>
                      <hr style={{margin:'10px 0',border:'none',borderTop:'1px dashed #ddd'}} />
                      <div style={{display:'flex',flexDirection:'column',alignItems:'center',gap:10}}>
                        {wPhoto && (
                          <Zoom><img src={wPhoto} className="meter-preview-img" style={{maxWidth:'100%',maxHeight:260,borderRadius:6,border:'1px solid #ddd'}} /></Zoom>
                        )}
                        {ePhoto && (
                          <>
                            <hr style={{width:'80%',margin:'4px 0',border:'none',borderTop:'1px dashed #DDE3EA'}} />
                            <Zoom><img src={ePhoto} className="meter-preview-img" style={{maxWidth:'100%',maxHeight:260,borderRadius:6,border:'1px solid #ddd'}} /></Zoom>
                          </>
                        )}
                      </div>
                    </>
                  )}
                </div>
                </div>

                <div className="drawer-section">
                  <div className="section-label">💳 确认收款</div>
                  <div style={{display:'flex',gap:12,alignItems:'flex-end'}}>
                    <div className="form-group" style={{marginBottom:0,flex:1}}>
                      <label style={{fontSize:12}}>实收金额（元）</label>
                      <input className="soft-input" type="number" value={this.state.paidAmount} onChange={e => this.setState({ paidAmount: e.target.value })} step="0.01" style={{height:36}} />
                    </div>
                    <div className="form-group" style={{marginBottom:0,flex:1}}>
                      <label style={{fontSize:12}}>收款日期</label>
                      <DayPicker value={this.state.paidDate} onChange={paidDate => this.setState({ paidDate })} ariaLabel="选择收款日期" />
                    </div>
                    <button className="btn btn-primary btn-sm" onClick={this.confirmPayment} style={{height:36,padding:'0 16px',whiteSpace:'nowrap'}}>确认收款</button>
                  </div>
                </div>
              </>
            )}

{drawerStep === 3 && drawerBill && drawerBill.status === 'paid' && (
              <>
                <div className="drawer-section">
                  <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:10}}>
                    <span className="section-label" style={{marginBottom:0}}>📋 账单</span>
                  </div>
                  <div className="receipt-image-toolbar">
                    <div className="ai-bill-image-tools">
                      <button type="button" onClick={this.copyReceipt} title="复制账单图片" aria-label="复制账单图片">
                        <CopyOutlined />
                      </button>
                      <button type="button" onClick={this.saveReceipt} title="保存账单图片" aria-label="保存账单图片">
                        <DownloadOutlined />
                      </button>
                    </div>
                  </div>
                  <div className="receipt-capture" style={{border:'1px solid var(--border-light)',borderRadius:8,padding:16,background:'var(--receipt-bg)',fontSize:13}}>
                    <div style={{textAlign:'center',fontWeight:600,fontSize:15,marginBottom:2}}>房租及费用收据</div>
                    <div style={{fontSize:11,color:'var(--text-third)',marginBottom:8}}>No.{(this.state.planYear + '-' + String(this.state.planMonth).padStart(2,'0')).replace('-','') + drawerContract.room_number}</div>
                    <div style={{marginBottom:6}}>房间：<b>{drawerContract.room_number}</b></div>
                    <table style={{width:'100%',borderCollapse:'collapse',fontSize:12,margin:'8px 0'}}>
                    <thead><tr style={{background:'var(--receipt-bg)'}}><th style={{padding:6,border:'1px solid #ddd'}}>项目</th><th style={{padding:6,border:'1px solid #ddd'}}>本月读数</th><th style={{padding:6,border:'1px solid #ddd'}}>上月读数</th><th style={{padding:6,border:'1px solid #ddd'}}>实用量</th><th style={{padding:6,border:'1px solid #ddd'}}>单价</th><th style={{padding:6,border:'1px solid #ddd'}}>金额</th></tr></thead>
                    <tbody>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>水费（吨）</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{this.formatReceiptReading(wCurr)}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{wLast || '—'}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.water_unit_price) > 0 ? this.formatReceiptUsage(wCurr, wLast, 1) : ''}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.water_unit_price).toFixed(2)}</td>
                        <td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{waterFee.toFixed(2)}</td></tr>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>电费（度）</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{this.formatReceiptReading(eCurr)}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{eLast || '—'}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.electric_unit_price) > 0 ? this.formatReceiptUsage(eCurr, eLast, 0) : ''}</td>
                        <td style={{padding:6,border:'1px solid #ddd'}}>{Number(drawerContract.electric_unit_price).toFixed(2)}</td>
                        <td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{elecFee.toFixed(2)}</td></tr>
                      <tr><td style={{padding:6,border:'1px solid #ddd'}}>房租</td><td style={{padding:6,border:'1px solid #ddd'}} colSpan={4} /><td style={{padding:6,border:'1px solid #ddd',fontWeight:'bold'}}>¥{rentAmount.toFixed(2)}</td></tr>
                      {this.renderOtherFeeReceiptRows()}
                    </tbody>
                  </table>
                  <div style={{textAlign:'right',fontWeight:700,fontSize:15}}>合计：<span style={{color:'var(--red)',fontSize:18}}>¥{totalAmount}</span></div>
                  <div className="receipt-total-cn">大写：{formatChineseMoney(totalAmount)}</div>
                  <div style={{textAlign:'right',fontSize:12,color:'var(--text-sec)',marginTop:4,lineHeight:1.8}}>
                    <div>付款人：{drawerContract.tenant_name}</div>
                    <div>收款人：吴钦腾</div>
                    <div>发单日期：{new Date().toISOString().split('T')[0]}</div>
                  </div>

                  {(wPhoto || ePhoto) && (
                    <>
                      <hr style={{margin:'10px 0',border:'none',borderTop:'1px dashed #ddd'}} />
                      <div style={{display:'flex',flexDirection:'column',alignItems:'center',gap:10}}>
                        {wPhoto && (
                          <Zoom><img src={wPhoto} className="meter-preview-img" style={{maxWidth:'100%',maxHeight:260,borderRadius:6,border:'1px solid #ddd'}} /></Zoom>
                        )}
                        {ePhoto && (
                          <>
                            <hr style={{width:'80%',margin:'4px 0',border:'none',borderTop:'1px dashed #DDE3EA'}} />
                            <Zoom><img src={ePhoto} className="meter-preview-img" style={{maxWidth:'100%',maxHeight:260,borderRadius:6,border:'1px solid #ddd'}} /></Zoom>
                          </>
                        )}
                      </div>
                    </>
                  )}
                </div>
                </div>

                <div className="drawer-section">
                  <div className="section-label" style={{color:'var(--green)'}}>✅ 已收款</div>
                  <div style={{display:'flex',gap:12}}>
                    <div style={{flex:1,background:'var(--bg)',borderRadius:8,padding:'10px 14px'}}>
                      <div style={{fontSize:11,color:'var(--text-third)'}}>实收金额</div>
                      <div style={{fontSize:16,fontWeight:600,color:'var(--text)'}}>¥{this.state.paidAmount || totalAmount}</div>
                    </div>
                    <div style={{flex:1,background:'var(--bg)',borderRadius:8,padding:'10px 14px'}}>
                      <div style={{fontSize:11,color:'var(--text-third)'}}>收款日期</div>
                      <div style={{fontSize:16,fontWeight:600,color:'var(--text)'}}>{this.state.paidDate}</div>
                    </div>
                  </div>
                </div>
              </>
            )}

{drawerStep === 1 && <button className="btn btn-primary" onClick={this.saveDrawer}>保存数据</button>}
            {drawerStep === 2 && <div />}
            {drawerStep === 3 && <div />}
          </div>
        </div>
      </>
    )
  }
}
