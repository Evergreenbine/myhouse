import React from 'react'
import { rental } from '../api'
import { showToast } from '../components/ui'

interface Contract { id: number; tenant_name: string; tenant_id: number; room_number: string; room_id: number; monthly_rent: number; start_date: string; end_date: string; deposit: number; status: string; water_unit_price: number; electric_unit_price: number; water_meter_id: number | null; electric_meter_id: number | null }
interface Building { id: number; name: string; rent_day: number }
interface Room { id: number; room_number: string; floor: number }
interface Tenant { id: number; name: string; room_id: string }
interface Meter { id: number; meter_no: string; room_number: string }

interface State {
  contracts: Record<number, Contract[]>
  buildings: Building[]
  curBid: number | null
  loading: boolean
  firstLoad: boolean
  modal: boolean
  editId: number | null
  roomId: string
  tenantId: string
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
}

export class ContractsPage extends React.Component<{}, State> {
  state: State = {
    contracts: {},
    buildings: [],
    curBid: null,
    loading: true,
    firstLoad: true,
    modal: false,
    editId: null,
    roomId: '', tenantId: '', monthlyRent: '', startDate: '', endDate: '', rentDay: '1',
    waterInit: '', waterMeterId: '', waterPrice: '',
    elecInit: '', electricMeterId: '', electricPrice: '',
    deposit: '', status: 'active',
    modalRooms: [], modalTenants: [], modalWaterMeters: [], modalElectricMeters: [],
    roomMenuOpen: false, tenantMenuOpen: false, waterMeterMenuOpen: false, electricMeterMenuOpen: false,
  }

  componentDidMount() { this.loadBuildings() }

  loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = data.length > 0 ? data[0].id : null
    if (bid) {
      const cs = await rental('contracts', 'list', { building_id: bid }) || []
      this.setState({ buildings: data, curBid: bid, contracts: { [bid]: cs }, loading: false, firstLoad: false })
    } else {
      this.setState({ buildings: data, loading: false, firstLoad: false })
    }
  }

  switchBuilding = async (id: number) => {
    if (this.state.contracts[id]) { this.setState({ curBid: id }); return }
    this.setState({ curBid: id, loading: true })
    const cs = await rental('contracts', 'list', { building_id: id }) || []
    this.setState(s => ({ contracts: { ...s.contracts, [id]: cs }, loading: false }))
  }

  toggleStatus = async (id: number, status: string) => {
    const newStatus = status === 'active' ? 'ended' : 'active'
    await rental('contracts', 'update', { id, status: newStatus })
    if (this.state.curBid) this.switchBuilding(this.state.curBid)
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
    if (!tenants || tenants.length === 0) { showToast('该楼栋没有租客，请先添加租客'); return }
    if (!rooms || rooms.length === 0) { showToast('该楼栋没有房间，请先添加房间'); return }
    this.setState({
      editId: null, modal: true,
      roomId: rooms[0]?.id || '', tenantId: tenants[0]?.id || '',
      monthlyRent: '', startDate: '', endDate: '', rentDay: String(bld.rent_day || 1),
      waterInit: '', waterMeterId: '', waterPrice: '',
      elecInit: '', electricMeterId: '', electricPrice: '',
      deposit: '', status: 'active',
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
      monthlyRent: String(c.monthly_rent || ''), startDate: c.start_date || '', endDate: c.end_date || '',
      rentDay: String(bld.rent_day || 1),
      waterInit: '', waterMeterId: String(c.water_meter_id || ''), waterPrice: String(c.water_unit_price || ''),
      elecInit: '', electricMeterId: String(c.electric_meter_id || ''), electricPrice: String(c.electric_unit_price || ''),
      deposit: String(c.deposit || ''), status: c.status || 'active',
      modalRooms: rooms || [], modalTenants: allT,
      modalWaterMeters: waterMeters || [], modalElectricMeters: electricMeters || [],
      roomMenuOpen: false, tenantMenuOpen: false, waterMeterMenuOpen: false, electricMeterMenuOpen: false,
    })
  }

  save = async () => {
    const { startDate, roomId, tenantId, monthlyRent, rentDay, deposit, waterMeterId, waterPrice, electricMeterId, electricPrice, editId, curBid } = this.state
    if (!startDate) { showToast('请选择合同开始日期'); return }
    const data: any = {
      tenant_id: parseInt(tenantId), room_id: parseInt(roomId),
      start_date: startDate, end_date: this.state.endDate,
      monthly_rent: parseFloat(monthlyRent) || 0, deposit: parseFloat(deposit) || 0,
      water_unit_price: parseFloat(waterPrice) || 0, electric_unit_price: parseFloat(electricPrice) || 0,
      water_meter_id: waterMeterId || null, electric_meter_id: electricMeterId || null,
      rent_day: parseInt(rentDay) || 1,
    }
    if (editId) data.status = this.state.status
    const res = editId
      ? await rental('contracts', 'update', { ...data, id: editId })
      : await rental('contracts', 'add', data)
    if (res && !res.error) {
      this.setState({ modal: false })
      if (curBid) {
        const cs = await rental('contracts', 'list', { building_id: curBid }) || []
        this.setState(s => ({ contracts: { ...s.contracts, [curBid]: cs } }))
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

    const curContracts: Contract[] = curBid ? (this.state.contracts[curBid] || []) : []

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
          <button className="btn btn-primary btn-sm" onClick={this.openAdd}>+ 新签合同</button>
        </div>

        {loading ? <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div> :
          curContracts.length === 0 ? (
            <div className="empty-state"><div className="icon">📄</div><div>当前楼栋暂无合同，点击上方按钮新签</div></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>租客</th><th>房间</th><th>月租</th><th>合同期</th><th>保证金</th><th className="status-cell">状态</th></tr></thead>
                <tbody>
                  {curContracts.map(c => (
                    <tr key={c.id}>
                      <td><span className="name-link" onClick={() => this.openEdit(c.id)}>{c.tenant_name || ''}</span></td>
                      <td>{c.room_number || ''}</td>
                      <td>¥{Number(c.monthly_rent || 0).toFixed(2)}</td>
                      <td>{(c.start_date || '') + ' ~ ' + (c.end_date || '')}</td>
                      <td>¥{Number(c.deposit || 0).toFixed(2)}</td>
                      <td className="status-cell">
                        <span className={'status-dot ' + (c.status === 'active' ? 'rented' : 'idle')}
                          onClick={e => { e.stopPropagation(); this.toggleStatus(c.id, c.status) }}
                          title={c.status === 'active' ? '生效中，点击解除' : '已解除，点击生效'} />
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
      </div>
    )
  }

  renderModal() {
    const { modal, editId, roomId, tenantId, monthlyRent, startDate, endDate, rentDay, waterInit, waterMeterId, waterPrice, elecInit, electricMeterId, electricPrice, deposit, status, modalRooms, modalTenants, modalWaterMeters, modalElectricMeters } = this.state
    if (!modal) return null

    const roomMap: Record<string,string> = {}
    modalRooms.forEach(r => { roomMap[String(r.id)] = r.room_number })

    const selTenant = modalTenants.find(t => String(t.id) === tenantId)
    const selRoom = modalRooms.find(r => String(r.id) === roomId)
    const selWaterMeter = modalWaterMeters.find(m => String(m.id) === waterMeterId)
    const selElecMeter = modalElectricMeters.find(m => String(m.id) === electricMeterId)

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
                    <span>{selRoom?.room_number || '请选择'}</span>
                  </div>
                  {this.state.roomMenuOpen && (
                    <div className="select-menu" style={{display:'block',position:'absolute',left:0,right:0,top:'100%',marginTop:4,zIndex:10}}>
                      {modalRooms.map(r => (
                        <div key={r.id} className={'select-option' + (String(r.id) === roomId ? ' active' : '')}
                          onClick={() => this.setState({ roomId: String(r.id), roomMenuOpen: false })}>{r.room_number}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="form-group">
                <label>租客</label>
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
              </div>

              <div className="form-group">
                <label>月租（元）</label>
                <input className="soft-input" type="number" value={monthlyRent} onChange={e => this.setState({ monthlyRent: e.target.value })} placeholder="0.00" />
              </div>

              {/* Row 2: 合同开始 合同结束 收租日 */}
              <div className="form-group">
                <label>合同开始</label>
                <input className="soft-input" type="date" value={startDate} onChange={e => this.setState({ startDate: e.target.value })} />
              </div>
              <div className="form-group">
                <label>合同结束</label>
                <input className="soft-input" type="date" value={endDate} onChange={e => this.setState({ endDate: e.target.value })} />
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
