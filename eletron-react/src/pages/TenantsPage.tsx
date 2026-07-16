import React from 'react'
import { rental } from '../api'
import { showToast } from '../components/ui'
import { resolveBuildingId, useUIStore } from '../store'

interface Tenant { id: number; name: string; phone: string; id_card: string; status: string; room_id: string }
interface Building { id: number; name: string; rent_day?: number }
interface Room { id: number; room_number: string; floor: number }

interface State {
  tenants: Record<string, Tenant[]>
  buildings: Building[]
  rooms: Record<number, Room[]>
  curBid: number | null
  activeOnly: boolean
  loading: boolean
  firstLoad: boolean
  modal: boolean
  editId: number | null
  name: string
  phone: string
  idCard: string
  status: 'active' | 'inactive'
  buildingId: string
  roomIds: string[]
  buildingMenuOpen: boolean
  roomMenuOpen: boolean
}

export class TenantsPage extends React.Component<{}, State> {
  state: State = {
    tenants: {},
    buildings: [],
    rooms: {},
    curBid: null,
    activeOnly: true,
    loading: true,
    firstLoad: true,
    modal: false,
    editId: null,
    name: '',
    phone: '',
    idCard: '',
    status: 'active',
    buildingId: '',
    roomIds: [],
    buildingMenuOpen: false,
    roomMenuOpen: false,
  }

  componentDidMount() { this.loadBuildings() }

  loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = resolveBuildingId(data)
    useUIStore.getState().setSelectedBuildingId(bid)
    if (bid) {
      const [tenants, rooms] = await Promise.all([
        rental('tenants', 'list', { active_only: true, building_id: bid }),
        rental('rooms', 'list', { building_id: bid }),
      ])
      this.setState({ buildings: data, curBid: bid, tenants: { ['a_' + bid]: tenants || [] }, rooms: { [bid]: rooms || [] }, loading: false, firstLoad: false })
    } else {
      this.setState({ buildings: data, loading: false, firstLoad: false })
    }
  }

  cacheKey(bid: number) { return (this.state.activeOnly ? 'a_' : 'all_') + bid }

  loadForBuilding = async (bid: number) => {
    const { activeOnly } = this.state
    const [tenants, rooms] = await Promise.all([
      rental('tenants', 'list', { active_only: activeOnly, building_id: bid }),
      rental('rooms', 'list', { building_id: bid }),
    ])
    this.setState(s => ({
      tenants: { ...s.tenants, [this.cacheKey(bid)]: tenants || [] },
      rooms: { ...s.rooms, [bid]: rooms || [] },
    }))
  }

  switchBuilding = async (id: number) => {
    useUIStore.getState().setSelectedBuildingId(id)
    const ck = this.cacheKey(id)
    if (this.state.tenants[ck]) {
      this.setState({ curBid: id })
      if (!this.state.rooms[id]) {
        const roomData = await rental('rooms', 'list', { building_id: id }) || []
        this.setState(s => ({ rooms: { ...s.rooms, [id]: roomData } }))
      }
      return
    }
    this.setState({ curBid: id, loading: true })
    await this.loadForBuilding(id)
    this.setState({ loading: false })
  }

  toggleActive = async () => {
    const { curBid, activeOnly } = this.state
    if (!curBid) return
    const newActive = !activeOnly
    this.setState({ activeOnly: newActive })
    const ck = (newActive ? 'a_' : 'all_') + curBid
    if (this.state.tenants[ck]) return
    this.setState({ loading: true })
    await this.loadForBuilding(curBid)
    this.setState({ loading: false })
  }

  openAdd = () => {
    this.setState({
      editId: null, name: '', phone: '', idCard: '', status: 'active',
      buildingId: String(this.state.curBid || ''), roomIds: [], modal: true,
      buildingMenuOpen: false, roomMenuOpen: false,
    })
  }

  openEdit = async (id: number) => {
    const t = await rental('tenants', 'get', { id })
    if (t && !t.error) {
      this.setState({
        editId: id, name: t.name || '', phone: t.phone || '', idCard: t.id_card || '',
        status: t.status === 'inactive' ? 'inactive' : 'active',
        buildingId: String(t.building_id || ''), roomIds: t.room_id ? String(t.room_id).split(',').filter(Boolean) : [],
        modal: true, buildingMenuOpen: false, roomMenuOpen: false,
      })
    }
  }

  save = async () => {
    const { name, phone, idCard, status, buildingId, roomIds, editId, curBid } = this.state
    if (!name.trim()) { showToast('请输入姓名'); return }
    const data = {
      name: name.trim(), phone: phone.trim(), id_card: idCard.trim(), status,
      building_id: parseInt(buildingId) || null,
      room_id: roomIds.join(',') || null,
    }
    const res = editId
      ? await rental('tenants', 'update', { ...data, id: editId })
      : await rental('tenants', 'add', data)
    if (res && !res.error) {
      this.setState({ modal: false })
      if (curBid) {
        const ck = this.cacheKey(curBid)
        const tenants = await rental('tenants', 'list', { active_only: this.state.activeOnly, building_id: curBid }) || []
        this.setState(s => ({ tenants: { ...s.tenants, [ck]: tenants } }))
      }
      showToast(editId ? '保存成功' : '添加成功')
    } else { showToast('保存失败') }
  }

  render() {
    const { buildings, curBid, activeOnly, loading } = this.state
    if (this.state.firstLoad) return <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div>

    if (buildings.length === 0) return (
      <div>
        <div className="toolbar"><button className="btn btn-primary btn-sm">+ 先添加楼栋</button></div>
        <div className="toolbar-divider" />
        <div className="empty-state"><div className="icon">👤</div><div>请先添加楼栋，再录入租客</div></div>
      </div>
    )

    const ck = this.cacheKey(curBid!)
    const curTenants: Tenant[] = curBid ? (this.state.tenants[ck] || []) : []
    const curRooms: Room[] = curBid ? (this.state.rooms[curBid] || []) : []
    const roomMap: Record<string,string> = {}
    curRooms.forEach(r => { roomMap[String(r.id)] = r.room_number })

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
          <span
            style={{
              marginRight:6, cursor:'pointer', display:'inline-flex', alignItems:'center', gap:4,
              padding:'4px 10px', borderRadius:14, fontSize:12,
              background: activeOnly ? 'var(--blue-light)' : '#f0f0f0',
              color: activeOnly ? 'var(--blue)' : 'var(--text-sec)',
            }}
            onClick={this.toggleActive}
          >
            <span style={{width:6,height:6,borderRadius:'50%',background:activeOnly?'var(--blue)':'#999'}} />
            {activeOnly ? '在租' : '全部'}
          </span>
          <button className="btn btn-primary btn-sm" onClick={this.openAdd}>+ 添加租客</button>
        </div>

        {loading ? <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div> :
          curTenants.length === 0 ? (
            <div className="empty-state"><div className="icon">👤</div><div>暂无租客，点击右上方按钮添加</div></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>姓名</th><th>房间号</th><th>手机号</th><th>证件号</th><th className="status-cell">状态</th></tr></thead>
                <tbody>
                  {curTenants.map(t => {
                    const active = t.status !== 'inactive'
                    const roomTags = t.room_id ? String(t.room_id).split(',').map(rid => (
                      <span key={rid} className="ms-tag">{roomMap[rid] || rid}</span>
                    )) : null
                    return (
                      <tr key={t.id}>
                        <td><span className="name-link" onClick={() => this.openEdit(t.id)}>{t.name}</span></td>
                        <td><div style={{display:'flex',flexWrap:'wrap',gap:3}}>{roomTags}</div></td>
                        <td>{t.phone || '-'}</td>
                        <td>{t.id_card || '-'}</td>
                        <td className="status-cell">
                          <span className={'status-dot ' + (active ? 'rented' : 'idle')} title={active ? '正常' : '停用'} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        }
        <div className="list-meta">共 {curTenants.length} 位租客</div>

        {this.renderModal(curRooms)}
      </div>
    )
  }

  renderModal(curRooms: Room[]) {
    const { modal, editId, buildingId, name, phone, idCard, status, roomIds, buildings, buildingMenuOpen, roomMenuOpen } = this.state
    if (!modal) return null
    const selectedBld = buildings.find(b => String(b.id) === buildingId) || buildings[0]

    return (
      <div className="modal-overlay" onClick={() => this.setState({ modal: false })}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-title">{editId ? '编辑租客' : '添加租客'}</div>
          <div className="soft-form">
            <div className="form-group">
              <label>所属楼栋</label>
              {editId ? (
                <div className="locked-field">{selectedBld?.name || ''}</div>
              ) : (
                <div className="custom-select" style={{position:'relative'}}>
                  <div className="select-trigger" onClick={() => this.setState({ buildingMenuOpen: !buildingMenuOpen })}>
                    <span>{selectedBld?.name || '请选择'}</span>
                  </div>
                  {buildingMenuOpen && (
                    <div className="select-menu" style={{display:'block',position:'absolute',left:0,right:0,top:'100%',marginTop:4,zIndex:10}}>
                      {buildings.map(b => (
                        <div key={b.id}
                          className={'select-option' + (String(b.id) === buildingId ? ' active' : '')}
                          onClick={() => this.setState({ buildingId: String(b.id), buildingMenuOpen: false })}>{b.name}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="form-group">
              <label>房间号</label>
              <div className="multi-select" style={{position:'relative'}}>
                <div className="multi-select-trigger" onClick={() => this.setState({ roomMenuOpen: !roomMenuOpen })}>
                  {roomIds.length === 0 && <span className="ms-placeholder">点击选择房间</span>}
                  {roomIds.map(rid => {
                    const rn = curRooms.find(r => String(r.id) === rid)
                    return (
                      <span key={rid} className="ms-tag">
                        {rn ? rn.room_number : rid}
                        <span className="ms-tag-x" onClick={e => { e.stopPropagation(); this.setState({ roomIds: roomIds.filter(r => r !== rid) }) }}>×</span>
                      </span>
                    )
                  })}
                  <span className="ms-arrow">▼</span>
                </div>
                {roomMenuOpen && (
                  <div className="multi-select-dropdown" style={{display:'block'}}>
                    <div className="ms-actions">
                      <button className="btn-xs" onClick={() => this.setState({ roomIds: curRooms.map(r => String(r.id)) })}>全选</button>
                      <button className="btn-xs" onClick={() => this.setState({ roomIds: [] })}>清空</button>
                    </div>
                    {curRooms.map(r => (
                      <label key={r.id} className="ms-option">
                        <input type="checkbox" checked={roomIds.includes(String(r.id))}
                          onChange={() => {
                            this.setState(s => ({
                              roomIds: s.roomIds.includes(String(r.id))
                                ? s.roomIds.filter(rid => rid !== String(r.id))
                                : [...s.roomIds, String(r.id)]
                            }))
                          }} />
                        {r.room_number} ({r.floor}楼)
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="form-group">
              <label>姓名</label>
              <input className="soft-input" value={name} onChange={e => this.setState({ name: e.target.value })} placeholder="如：张三" />
            </div>
            <div className="form-group">
              <label>手机号</label>
              <input className="soft-input" value={phone} onChange={e => this.setState({ phone: e.target.value })} placeholder="如：13800000000" />
            </div>
            <div className="form-group">
              <label>证件号</label>
              <input className="soft-input" value={idCard} onChange={e => this.setState({ idCard: e.target.value })} placeholder="身份证或其他证件" />
            </div>

            <div className="form-group">
              <label>状态</label>
              <div className="status-switch-row">
                <button
                  className={'status-switch' + (status === 'active' ? ' rented' : '')}
                  onClick={() => this.setState({ status: status === 'active' ? 'inactive' : 'active' })}
                  type="button"
                />
                <span className="status-switch-label">{status === 'active' ? '正常' : '停用'}</span>
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
