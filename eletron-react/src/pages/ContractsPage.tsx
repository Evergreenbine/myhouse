import React from 'react'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { rental } from '../api'
import { showToast, DatePicker } from '../components/ui'
import { resolveBuildingId, useUIStore } from '../store'

interface Contract { id: number; tenant_name: string; tenant_id: number; room_number: string; room_type?: string; room_id: number; monthly_rent: number; start_date: string; end_date: string; deposit: number; status: string; water_unit_price: number; electric_unit_price: number; water_meter_id: number | null; electric_meter_id: number | null; other_fee_details?: string }
interface Building { id: number; name: string; rent_day: number }
interface Room { id: number; room_number: string; room_type?: string; floor: number; status?: string }
interface Tenant { id: number; name: string; phone?: string; id_card?: string; room_id: string }
interface Meter { id: number; meter_no: string; room_number: string }
interface OtherFeeItem { id: string; name: string; amount: string }
interface OtherFeeDetail { name: string; amount: number }

interface State {
  contracts: Record<string, Contract[]>
  buildings: Building[]
  curBid: number | null
  showArchived: boolean
  loading: boolean
  firstLoad: boolean
  modal: boolean
  editId: number | null
  roomId: string
  tenantId: string
  tenantMode: 'existing' | 'new'
  newTenantName: string
  newTenantPhone: string
  newTenantIdCard: string
  monthlyRent: string
  startDate: string
  endDate: string
  rentDay: string
  waterInit: string
  waterMeterId: string
  waterPrice: string
  elecInit: string
  electricMeterId: string
  electricPrice: string
  deposit: string
  otherFees: OtherFeeItem[]
  status: string
  // modal data
  modalRooms: Room[]
  modalTenants: Tenant[]
  modalWaterMeters: Meter[]
  modalElectricMeters: Meter[]
  roomMenuOpen: boolean
  tenantMenuOpen: boolean
  waterMeterMenuOpen: boolean
  electricMeterMenuOpen: boolean
  checkoutConfirm: Contract | null
  checkoutDate: string
}

export class ContractsPage extends React.Component<{}, State> {
  private otherFeeItemSeq = 0

  state: State = {
    contracts: {},
    buildings: [],
    curBid: null,
    showArchived: false,
    loading: true,
    firstLoad: true,
    modal: false,
    editId: null,
    roomId: '', tenantId: '', tenantMode: 'existing', newTenantName: '', newTenantPhone: '', newTenantIdCard: '',
    monthlyRent: '', startDate: '', endDate: '', rentDay: '1',
    waterInit: '', waterMeterId: '', waterPrice: '',
    elecInit: '', electricMeterId: '', electricPrice: '',
    deposit: '', otherFees: [{ id: 'contract-fee-initial', name: '', amount: '' }], status: 'active',
    modalRooms: [], modalTenants: [], modalWaterMeters: [], modalElectricMeters: [],
    roomMenuOpen: false, tenantMenuOpen: false, waterMeterMenuOpen: false, electricMeterMenuOpen: false,
    checkoutConfirm: null,
    checkoutDate: new Date().toISOString().split('T')[0],
  }

  createOtherFeeItem = (name = '', amount = ''): OtherFeeItem => ({
    id: `contract-fee-${Date.now()}-${++this.otherFeeItemSeq}`,
    name,
    amount,
  })

  parseOtherFeeDetails = (value?: string): OtherFeeDetail[] => {
    try {
      const parsed = JSON.parse(value || '[]')
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed
          .map((item: any) => ({
            name: String(item?.name || item?.project_name || '').trim(),
            amount: Number(item?.amount),
          }))
          .filter(item => item.name && Number.isFinite(item.amount) && item.amount > 0)
      }
    } catch {}
    return []
  }

  parseOtherFeeItems = (value?: string): OtherFeeItem[] => {
    const details = this.parseOtherFeeDetails(value)
    if (details.length > 0) {
      return details.map(item => this.createOtherFeeItem(item.name, String(item.amount)))
    }
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

  getOtherFeeDetails = (): OtherFeeDetail[] => this.state.otherFees
    .map(item => ({ name: item.name.trim(), amount: Number(item.amount) }))
    .filter(item => item.name && Number.isFinite(item.amount) && item.amount > 0)

  getOtherFeeAmount = (items = this.state.otherFees) => items.reduce((total, item) => {
    const amount = Number(item.amount)
    return total + (Number.isFinite(amount) && amount > 0 ? amount : 0)
  }, 0)

  formatOtherFeeSummary = (value?: string) => {
    const items = this.parseOtherFeeDetails(value)
    if (!items.length) return '-'
    const total = items.reduce((sum, item) => sum + item.amount, 0)
    return `${items.length} 项 / ¥${total.toFixed(2)}`
  }

  formatRoomLabel = (room?: Room | null) => {
    if (!room) return ''
    return room.room_type ? `${room.room_number} · ${room.room_type}` : room.room_number
  }

  componentDidMount() { this.loadBuildings() }

  contractCacheKey = (bid: number, archived = this.state.showArchived) => bid + ':' + (archived ? 'archived' : 'active')

  loadContracts = async (bid: number, archived = this.state.showArchived) => {
    const data = await rental('contracts', 'list', { active_only: !archived, building_id: bid }) || []
    const cs = archived ? data.filter((c: Contract) => c.status !== 'active') : data
    this.setState(s => ({ contracts: { ...s.contracts, [this.contractCacheKey(bid, archived)]: cs } }))
    return cs
  }

  loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = resolveBuildingId(data)
    useUIStore.getState().setSelectedBuildingId(bid)
    if (bid) {
      const cs = await rental('contracts', 'list', { active_only: true, building_id: bid }) || []
      this.setState({ buildings: data, curBid: bid, contracts: { [this.contractCacheKey(bid, false)]: cs }, loading: false, firstLoad: false })
    } else {
      this.setState({ buildings: data, loading: false, firstLoad: false })
    }
  }

  switchBuilding = async (id: number) => {
    useUIStore.getState().setSelectedBuildingId(id)
    const key = this.contractCacheKey(id)
    if (this.state.contracts[key]) { this.setState({ curBid: id }); return }
    this.setState({ curBid: id, loading: true })
    await this.loadContracts(id)
    this.setState({ loading: false })
  }

  switchArchiveView = async (archived: boolean) => {
    const bid = this.state.curBid
    this.setState({ showArchived: archived })
    if (!bid) return
    const key = this.contractCacheKey(bid, archived)
    if (this.state.contracts[key]) return
    this.setState({ loading: true })
    await this.loadContracts(bid, archived)
    this.setState({ loading: false })
  }

  refreshCurrentContracts = async () => {
    const bid = this.state.curBid
    if (!bid) return
    const archived = this.state.showArchived
    const cs = await rental('contracts', 'list', { active_only: !archived, building_id: bid }) || []
    this.setState(s => ({
      contracts: { ...s.contracts, [this.contractCacheKey(bid, archived)]: archived ? cs.filter((c: Contract) => c.status !== 'active') : cs },
    }))
  }

  openCheckout = (contract: Contract) => {
    this.setState({ checkoutConfirm: contract, checkoutDate: new Date().toISOString().split('T')[0] })
  }

  confirmCheckout = async () => {
    const contract = this.state.checkoutConfirm
    if (!contract) return
    await rental('contracts', 'end', { id: contract.id, end_date: this.state.checkoutDate })
    this.setState({ checkoutConfirm: null })
    showToast('退租完成，房间已设为闲置')
    this.refreshCurrentContracts()
  }

  restoreContract = async (contract: Contract) => {
    await rental('contracts', 'update', { id: contract.id, status: 'active' })
    showToast('合同已恢复')
    this.refreshCurrentContracts()
  }

  openAdd = async () => {
    const bid = this.state.curBid!
    const bld = await rental('buildings', 'get', { id: bid }) || {}
    const [rooms, tenants, waterMeters, electricMeters] = await Promise.all([
      rental('rooms', 'list', { building_id: bid }),
      rental('tenants', 'list', { active_only: true, building_id: bid }),
      rental('meters', 'list', { building_id: bid, type: 'water' }),
      rental('meters', 'list', { building_id: bid, type: 'electric' }),
    ])
    if (!rooms || rooms.length === 0) { showToast('该楼栋没有房间，请先添加房间'); return }
    const initialTenant = tenants?.[0]
    const initialRoom = rooms.find((room: Room) => room.status !== 'rented') || rooms[0]
    this.setState({
      editId: null, modal: true,
      roomId: initialRoom?.id ? String(initialRoom.id) : '', tenantId: initialTenant?.id ? String(initialTenant.id) : '',
      tenantMode: initialTenant ? 'existing' : 'new',
      newTenantName: '', newTenantPhone: '', newTenantIdCard: '',
      monthlyRent: '', startDate: '', endDate: '', rentDay: String(bld.rent_day || 1),
      waterInit: '', waterMeterId: '', waterPrice: '',
      elecInit: '', electricMeterId: '', electricPrice: '',
      deposit: '', otherFees: [this.createOtherFeeItem()], status: 'active',
      modalRooms: rooms || [], modalTenants: tenants || [],
      modalWaterMeters: waterMeters || [], modalElectricMeters: electricMeters || [],
      roomMenuOpen: false, tenantMenuOpen: false, waterMeterMenuOpen: false, electricMeterMenuOpen: false,
    })
  }

  openEdit = async (id: number) => {
    const c = await rental('contracts', 'get', { id })
    if (!c || c.error) { showToast('未找到合同'); return }
    const bid = this.state.curBid!
    const bld = await rental('buildings', 'get', { id: bid }) || {}
    const [rooms, tenants, allTenants, waterMeters, electricMeters] = await Promise.all([
      rental('rooms', 'list', { building_id: bid }),
      rental('tenants', 'list', { active_only: true, building_id: bid }),
      rental('tenants', 'list', { active_only: false, building_id: bid }),
      rental('meters', 'list', { building_id: bid, type: 'water' }),
      rental('meters', 'list', { building_id: bid, type: 'electric' }),
    ])
    // merge in non-active tenant if they're the contract's tenant
    const allT: Tenant[] = tenants || []
    ;(allTenants || []).forEach((t: Tenant) => { if (!allT.some(x => Number(x.id) === Number(t.id))) allT.push(t) })
    this.setState({
      editId: id, modal: true,
      roomId: String(c.room_id || ''), tenantId: String(c.tenant_id || ''),
      tenantMode: 'existing', newTenantName: '', newTenantPhone: '', newTenantIdCard: '',
      monthlyRent: String(c.monthly_rent || ''), startDate: c.start_date || '', endDate: c.end_date || '',
      rentDay: String(bld.rent_day || 1),
      waterInit: '', waterMeterId: String(c.water_meter_id || ''), waterPrice: String(c.water_unit_price || ''),
      elecInit: '', electricMeterId: String(c.electric_meter_id || ''), electricPrice: String(c.electric_unit_price || ''),
      deposit: String(c.deposit || ''), otherFees: this.parseOtherFeeItems(c.other_fee_details), status: c.status || 'active',
      modalRooms: rooms || [], modalTenants: allT,
      modalWaterMeters: waterMeters || [], modalElectricMeters: electricMeters || [],
      roomMenuOpen: false, tenantMenuOpen: false, waterMeterMenuOpen: false, electricMeterMenuOpen: false,
    })
  }

  save = async () => {
    const { startDate, roomId, tenantId, tenantMode, newTenantName, newTenantPhone, newTenantIdCard, monthlyRent, rentDay, deposit, waterMeterId, waterPrice, electricMeterId, electricPrice, editId, curBid, otherFees } = this.state
    if (!startDate) { showToast('请选择合同开始日期'); return }
    if (!roomId) { showToast('请选择房间'); return }
    const resolvedTenantId = parseInt(tenantId)
    if (!editId && tenantMode === 'existing' && !resolvedTenantId) {
      showToast('请选择租客')
      return
    }
    if (!editId && tenantMode === 'new' && !newTenantName.trim()) {
      showToast('请填写新租客姓名')
      return
    }
    const enteredOtherFees = otherFees.filter(item => item.name.trim() || item.amount.trim())
    for (const item of enteredOtherFees) {
      if (!item.name.trim()) { showToast('请填写其它费用的项目名称'); return }
      const amount = Number(item.amount)
      if (!item.amount.trim() || !Number.isFinite(amount) || amount <= 0) {
        showToast(`请输入“${item.name.trim()}”的有效费用`)
        return
      }
    }
    const otherFeeDetails = this.getOtherFeeDetails()
    const data: any = {
      tenant_id: resolvedTenantId || null, tenant_name: tenantMode === 'new' ? newTenantName.trim() : undefined,
      tenant_phone: tenantMode === 'new' ? newTenantPhone.trim() : undefined,
      tenant_id_card: tenantMode === 'new' ? newTenantIdCard.trim() : undefined,
      room_id: parseInt(roomId),
      start_date: startDate, end_date: this.state.endDate,
      monthly_rent: parseFloat(monthlyRent) || 0, deposit: parseFloat(deposit) || 0,
      water_unit_price: parseFloat(waterPrice) || 0, electric_unit_price: parseFloat(electricPrice) || 0,
      water_meter_id: waterMeterId || null, electric_meter_id: electricMeterId || null,
      other_fee_details: JSON.stringify(otherFeeDetails),
      rent_day: parseInt(rentDay) || 1,
    }
    if (editId) data.status = this.state.status
    const res = editId
      ? await rental('contracts', 'update', { ...data, id: editId })
      : await rental('contracts', 'add', data)
    if (res && !res.error) {
      this.setState({ modal: false })
      if (curBid) {
        const cs = await rental('contracts', 'list', { active_only: !this.state.showArchived, building_id: curBid }) || []
        this.setState(s => ({ contracts: { ...s.contracts, [this.contractCacheKey(curBid)]: this.state.showArchived ? cs.filter((c: Contract) => c.status !== 'active') : cs } }))
      }
      showToast(editId ? '保存成功' : '新签成功')
    } else { showToast('保存失败') }
  }

  render() {
    const { buildings, curBid, loading } = this.state
    if (this.state.firstLoad) return <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div>

    if (buildings.length === 0) return (
      <div>
        <div className="toolbar"><button className="btn btn-primary btn-sm">+ 先添加楼栋</button></div>
        <div className="toolbar-divider" />
        <div className="empty-state"><div className="icon">📄</div><div>请先添加楼栋，再录入合同</div></div>
      </div>
    )

    const curContracts: Contract[] = curBid ? (this.state.contracts[this.contractCacheKey(curBid)] || []) : []

    return (
      <div>
        <div className="tab-action-row">
          <div className="building-tabs">
            {buildings.map(b => (
              <button key={b.id}
                className={'building-tab' + (Number(b.id) === Number(curBid) ? ' active' : '')}
                onClick={() => this.switchBuilding(b.id)}>{b.name}</button>
            ))}
          </div>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <div className="contract-status-tabs">
              <button className={!this.state.showArchived ? 'active' : ''} onClick={() => this.switchArchiveView(false)}>在租</button>
              <button className={this.state.showArchived ? 'active' : ''} onClick={() => this.switchArchiveView(true)}>已退租</button>
            </div>
            <button className="btn btn-primary btn-sm contract-new-btn" onClick={this.openAdd}>+ 新签合同</button>
          </div>
        </div>

        {loading ? <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div> :
          curContracts.length === 0 ? (
            <div className="empty-state"><div className="icon">📄</div><div>{this.state.showArchived ? '当前楼栋暂无已退租合同' : '当前楼栋暂无合同，点击上方按钮新签'}</div></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>租客</th><th>房间</th><th>户型</th><th>月租</th><th>合同期</th><th>保证金</th><th>其它费用</th><th className="status-cell">状态</th><th>操作</th></tr></thead>
                <tbody>
                  {curContracts.map(c => (
                    <tr key={c.id}>
                      <td><span className="name-link" onClick={() => this.openEdit(c.id)}>{c.tenant_name || ''}</span></td>
                      <td>{c.room_number || ''}</td>
                      <td>{c.room_type || '单间'}</td>
                      <td>¥{Number(c.monthly_rent || 0).toFixed(2)}</td>
                      <td>{(c.start_date || '') + ' ~ ' + (c.end_date || '')}</td>
                      <td>¥{Number(c.deposit || 0).toFixed(2)}</td>
                      <td>{this.formatOtherFeeSummary(c.other_fee_details)}</td>
                      <td className="status-cell">
                        <span className={'status-dot ' + (c.status === 'active' ? 'rented' : 'idle')}
                          title={c.status === 'active' ? '生效中' : '已退租'} />
                      </td>
                      <td>
                        {c.status === 'active' ? (
                          <button className="contract-action-btn end" onClick={() => this.openCheckout(c)}>退租</button>
                        ) : (
                          <button className="contract-action-btn restore" onClick={() => this.restoreContract(c)}>恢复</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
        <div className="list-meta">共 {curContracts.length} 份合同</div>

        {this.renderModal()}
        {this.renderCheckoutConfirm()}
      </div>
    )
  }

  renderCheckoutConfirm() {
    const contract = this.state.checkoutConfirm
    if (!contract) return null
    return (
      <div className="modal-overlay" onClick={() => this.setState({ checkoutConfirm: null })}>
        <div className="modal contract-checkout-modal" onClick={e => e.stopPropagation()}>
          <div className="modal-title">办理退租</div>
          <div className="checkout-summary">
            <div><span>租客</span><b>{contract.tenant_name}</b></div>
            <div><span>房间</span><b>{contract.room_number}</b></div>
            <div><span>户型</span><b>{contract.room_type || '单间'}</b></div>
            <div><span>月租</span><b>¥{Number(contract.monthly_rent || 0).toFixed(2)}</b></div>
          </div>
          <div className="form-group">
            <label>退租日期</label>
            <DatePicker value={this.state.checkoutDate} onChange={v => this.setState({ checkoutDate: v })} placeholder="选择退租日期" />
          </div>
          <div className="checkout-note">确认后合同会归档，房间状态会同步改为闲置。</div>
          <div className="modal-actions">
            <button className="btn btn-outline" onClick={() => this.setState({ checkoutConfirm: null })}>取消</button>
            <button className="btn btn-danger" onClick={this.confirmCheckout}>确认退租</button>
          </div>
        </div>
      </div>
    )
  }

  renderModal() {
    const { modal, editId, roomId, tenantId, tenantMode, newTenantName, newTenantPhone, newTenantIdCard, monthlyRent, startDate, endDate, rentDay, waterInit, waterMeterId, waterPrice, elecInit, electricMeterId, electricPrice, deposit, otherFees, status, modalRooms, modalTenants, modalWaterMeters, modalElectricMeters } = this.state
    if (!modal) return null

    const roomMap: Record<string,string> = {}
    modalRooms.forEach(r => { roomMap[String(r.id)] = r.room_number })

    const selTenant = modalTenants.find(t => String(t.id) === tenantId)
    const selRoom = modalRooms.find(r => String(r.id) === roomId)
    const selWaterMeter = modalWaterMeters.find(m => String(m.id) === waterMeterId)
    const selElecMeter = modalElectricMeters.find(m => String(m.id) === electricMeterId)
    const otherFeeAmount = this.getOtherFeeAmount(otherFees)

    return (
      <div className="modal-overlay" onClick={() => this.setState({ modal: false })}>
        <div className="modal" onClick={e => e.stopPropagation()} style={{minWidth:600}}>
          <div className="modal-title">{editId ? '编辑合同' : '新签合同'}</div>
          <div className="soft-form">
            <div className="grid3">
              {/* Row 1: 房间 租客 月租 */}
              <div className="form-group">
                <label>房间</label>
                <div className="custom-select" style={{position:'relative'}}>
                  <div className="select-trigger" onClick={() => this.setState({ roomMenuOpen: !this.state.roomMenuOpen })}>
                    <span>{this.formatRoomLabel(selRoom) || '请选择'}</span>
                  </div>
                  {this.state.roomMenuOpen && (
                    <div className="select-menu" style={{display:'block',position:'absolute',left:0,right:0,top:'100%',marginTop:4,zIndex:10}}>
                      {modalRooms.map(r => (
                        <div key={r.id} className={'select-option' + (String(r.id) === roomId ? ' active' : '')}
                          onClick={() => this.setState({ roomId: String(r.id), roomMenuOpen: false })}>{this.formatRoomLabel(r)}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="form-group">
                <label>租客</label>
                {!editId && (
                  <div className="tenant-source-segment">
                    <button type="button" className={tenantMode === 'existing' ? 'active' : ''} onClick={() => this.setState({ tenantMode: 'existing' })}>选择</button>
                    <button type="button" className={tenantMode === 'new' ? 'active' : ''} onClick={() => this.setState({ tenantMode: 'new' })}>新建</button>
                  </div>
                )}
                {tenantMode === 'existing' || editId ? (
                  <div className="custom-select" style={{position:'relative'}}>
                    <div className="select-trigger" onClick={() => this.setState({ tenantMenuOpen: !this.state.tenantMenuOpen })}>
                      <span id="contract_tenant_label">
                        {selTenant ? (
                          <>
                            {selTenant.room_id && String(selTenant.room_id).split(',').map(rid => (
                              <span key={rid} className="ms-tag" style={{marginRight:2}}>{roomMap[rid] || rid}</span>
                            ))}
                            {selTenant.name}
                          </>
                        ) : '请选择'}
                      </span>
                    </div>
                    {this.state.tenantMenuOpen && (
                      <div className="select-menu cs-tenant-menu" style={{display:'block',position:'absolute',left:0,right:0,top:'100%',marginTop:4,zIndex:10}}>
                        {modalTenants.map(t => (
                          <div key={t.id} className={'select-option' + (String(t.id) === tenantId ? ' active' : '')}
                            onClick={() => this.setState({ tenantId: String(t.id), tenantMenuOpen: false })}>
                            <span className="ct-tags">
                              {t.room_id && String(t.room_id).split(',').map(rid => (
                                <span key={rid} className="ms-tag">{roomMap[rid] || rid}</span>
                              ))}
                            </span>
                            <span className="ct-name">{t.name}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <input className="soft-input" value={newTenantName} onChange={e => this.setState({ newTenantName: e.target.value })} placeholder="如：张三" />
                )}
              </div>

              <div className="form-group">
                <label>月租（元）</label>
                <input className="soft-input" type="number" value={monthlyRent} onChange={e => this.setState({ monthlyRent: e.target.value })} placeholder="0.00" />
              </div>

              {!editId && tenantMode === 'new' && (
                <>
                  <div className="form-group">
                    <label>手机号</label>
                    <input className="soft-input" value={newTenantPhone} onChange={e => this.setState({ newTenantPhone: e.target.value })} placeholder="如：13800000000" />
                  </div>
                  <div className="form-group">
                    <label>证件号</label>
                    <input className="soft-input" value={newTenantIdCard} onChange={e => this.setState({ newTenantIdCard: e.target.value })} placeholder="身份证或其他证件" />
                  </div>
                </>
              )}

              {/* Row 2: 合同开始 合同结束 收租日 */}
              <div className="form-group">
                <label>合同开始</label>
                <DatePicker value={startDate} onChange={v => this.setState({ startDate: v })} placeholder="合同开始日期" />
              </div>
              <div className="form-group">
                <label>合同结束</label>
                <DatePicker value={endDate} onChange={v => this.setState({ endDate: v })} placeholder="合同结束日期" />
              </div>
              <div className="form-group">
                <label>收租日（每月几号）</label>
                <input className="soft-input" type="number" value={rentDay} onChange={e => this.setState({ rentDay: e.target.value })} min="1" max="28" />
              </div>

              {/* Row 3: 水表起始读数 水表 水费单价 */}
              <div className="form-group">
                <label>水表起始读数</label>
                <input className="soft-input" type="number" value={waterInit} onChange={e => this.setState({ waterInit: e.target.value })} placeholder="0" step="0.1" />
              </div>
              <div className="form-group">
                <label>水表</label>
                <div className="custom-select" style={{position:'relative'}}>
                  <div className="select-trigger" onClick={() => this.setState({ waterMeterMenuOpen: !this.state.waterMeterMenuOpen })}>
                    <span>{selWaterMeter ? (selWaterMeter.room_number + ' - ' + selWaterMeter.meter_no) : '请选择'}</span>
                  </div>
                  {this.state.waterMeterMenuOpen && (
                    <div className="select-menu" style={{display:'block',position:'absolute',left:0,right:0,top:'100%',marginTop:4,zIndex:10}}>
                      {modalWaterMeters.map(m => (
                        <div key={m.id} className={'select-option' + (String(m.id) === waterMeterId ? ' active' : '')}
                          onClick={() => this.setState({ waterMeterId: String(m.id), waterMeterMenuOpen: false })}>{m.room_number} - {m.meter_no}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div className="form-group">
                <label>水费单价（元/吨）</label>
                <input className="soft-input" type="number" value={waterPrice} onChange={e => this.setState({ waterPrice: e.target.value })} placeholder="0.00" />
              </div>

              {/* Row 4: 电表起始读数 电表 电费单价 */}
              <div className="form-group">
                <label>电表起始读数</label>
                <input className="soft-input" type="number" value={elecInit} onChange={e => this.setState({ elecInit: e.target.value })} placeholder="0" step="0.1" />
              </div>
              <div className="form-group">
                <label>电表</label>
                <div className="custom-select" style={{position:'relative'}}>
                  <div className="select-trigger" onClick={() => this.setState({ electricMeterMenuOpen: !this.state.electricMeterMenuOpen })}>
                    <span>{selElecMeter ? (selElecMeter.room_number + ' - ' + selElecMeter.meter_no) : '请选择'}</span>
                  </div>
                  {this.state.electricMeterMenuOpen && (
                    <div className="select-menu" style={{display:'block',position:'absolute',left:0,right:0,top:'100%',marginTop:4,zIndex:10}}>
                      {modalElectricMeters.map(m => (
                        <div key={m.id} className={'select-option' + (String(m.id) === electricMeterId ? ' active' : '')}
                          onClick={() => this.setState({ electricMeterId: String(m.id), electricMeterMenuOpen: false })}>{m.room_number} - {m.meter_no}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div className="form-group">
                <label>电费单价（元/度）</label>
                <input className="soft-input" type="number" value={electricPrice} onChange={e => this.setState({ electricPrice: e.target.value })} placeholder="0.00" />
              </div>

              {/* Row 5: 保证金 + 状态(仅编辑时) */}
              <div className="form-group">
                <label>保证金（元）</label>
                <input className="soft-input" type="number" value={deposit} onChange={e => this.setState({ deposit: e.target.value })} placeholder="0.00" />
              </div>
              {editId && (
                <div className="form-group">
                  <label>合同状态</label>
                  <div className="status-switch-row">
                    <button
                      className={'status-switch' + (status === 'active' ? ' rented' : '')}
                      onClick={() => this.setState({ status: status === 'active' ? 'ended' : 'active' })}
                      type="button"
                    />
                    <span className="status-switch-label">{status === 'active' ? '生效中' : '已解除'}</span>
                  </div>
                </div>
              )}
              <div className="form-group" style={{gridColumn:'1 / -1'}}>
                <label>其它费用约定</label>
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
            <div className="modal-actions">
              <button className="btn btn-outline" onClick={() => this.setState({ modal: false })}>取消</button>
              <button className="btn btn-primary" onClick={this.save}>保存</button>
            </div>
          </div>
        </div>
      </div>
    )
  }
}
