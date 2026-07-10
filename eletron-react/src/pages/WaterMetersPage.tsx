import React from 'react'
import { rental } from '../api'
import { showToast } from '../components/ui'

interface Meter { id: number; meter_no: string; room_number: string; room_id: number; init_reading: number; photo: string; building_id: number }
interface Building { id: number; name: string }
interface Room { id: number; room_number: string; floor: number }

interface MeterPageState {
  meters: Record<number, Meter[]>
  buildings: Building[]
  curBid: number | null
  loading: boolean
  firstLoad: boolean
  modal: boolean
  editId: number | null
  roomId: string
  meterNo: string
  initReading: string
  photo: string
  modalRooms: Room[]
  roomMenuOpen: boolean
  zoomImg: string | null
}

class MeterPage extends React.Component<{ type: string; title: string; icon: string }, MeterPageState> {
  state: MeterPageState = {
    meters: {},
    buildings: [],
    curBid: null,
    loading: true,
    firstLoad: true,
    modal: false,
    editId: null,
    roomId: '', meterNo: '', initReading: '', photo: '',
    modalRooms: [],
    roomMenuOpen: false,
    zoomImg: null,
  }

  componentDidMount() { this.loadBuildings() }

  loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = data.length > 0 ? data[0].id : null
    if (bid) {
      const ms = await rental('meters', 'list', { building_id: bid, type: this.props.type }) || []
      this.setState({ buildings: data, curBid: bid, meters: { [bid]: ms }, loading: false, firstLoad: false })
    } else {
      this.setState({ buildings: data, loading: false, firstLoad: false })
    }
  }

  switchBuilding = async (id: number) => {
    if (this.state.meters[id]) { this.setState({ curBid: id }); return }
    this.setState({ curBid: id, loading: true })
    const ms = await rental('meters', 'list', { building_id: id, type: this.props.type }) || []
    this.setState(s => ({ meters: { ...s.meters, [id]: ms }, loading: false }))
  }

  openAdd = async () => {
    const bid = this.state.curBid!
    const rooms = await rental('rooms', 'list', { building_id: bid }) || []
    if (rooms.length === 0) { showToast('该楼栋没有房间，请先添加房间'); return }
    this.setState({
      editId: null, modal: true, roomId: rooms[0]?.id || '', meterNo: '', initReading: '', photo: '',
      modalRooms: rooms, roomMenuOpen: false,
    })
  }

  openEdit = async (id: number) => {
    const m = await rental('meters', 'get', { id })
    if (!m || m.error) { showToast('未找到'); return }
    const bid = this.state.curBid!
    const rooms = await rental('rooms', 'list', { building_id: bid }) || []
    this.setState({
      editId: id, modal: true,
      roomId: String(m.room_id || ''), meterNo: m.meter_no || '', initReading: String(m.init_reading || 0),
      photo: m.photo || '', modalRooms: rooms, roomMenuOpen: false,
    })
  }

  handlePhoto = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => this.setState({ photo: reader.result as string })
    reader.readAsDataURL(file)
  }

  save = async () => {
    const { roomId, meterNo, initReading, photo, editId, curBid } = this.state
    const { type } = this.props
    const data = { room_id: parseInt(roomId), type, meter_no: meterNo.trim(), init_reading: parseFloat(initReading) || 0, photo }
    const res = editId
      ? await rental('meters', 'update', { ...data, id: editId })
      : await rental('meters', 'add', data)
    if (res && !res.error) {
      this.setState({ modal: false })
      if (curBid) {
        const ms = await rental('meters', 'list', { building_id: curBid, type }) || []
        this.setState(s => ({ meters: { ...s.meters, [curBid]: ms } }))
      }
      showToast(editId ? '保存成功' : '添加成功')
    } else { showToast('保存失败') }
  }

  render() {
    const { buildings, curBid, loading } = this.state
    const { title, icon } = this.props
    if (this.state.firstLoad) return <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div>

    if (buildings.length === 0) return (
      <div>
        <div className="toolbar"><button className="btn btn-primary btn-sm">+ 先添加楼栋</button></div>
        <div className="toolbar-divider" />
        <div className="empty-state"><div className="icon">{icon}</div><div>请先添加楼栋，再录入</div></div>
      </div>
    )

    const curMeters: Meter[] = curBid ? (this.state.meters[curBid] || []) : []

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
          <button className="btn btn-primary btn-sm" onClick={this.openAdd}>+ 添加</button>
        </div>

        {loading ? <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div> :
          curMeters.length === 0 ? (
            <div className="empty-state"><div className="icon">{icon}</div><div>当前楼栋暂无数据，点击上方按钮添加</div></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th style={{width:60}}>照片</th><th>表编号</th><th>房间</th><th>初始读数</th></tr></thead>
                <tbody>
                  {curMeters.map(m => (
                    <tr key={m.id}>
                      <td>
                        {m.photo ? <img src={m.photo} className="meter-list-img"
                          onMouseEnter={() => this.setState({ zoomImg: m.photo })}
                          onMouseLeave={() => this.setState({ zoomImg: null })} /> : null}
                      </td>
                      <td><span className="name-link" onClick={() => this.openEdit(m.id)}>{m.meter_no || '-'}</span></td>
                      <td>{m.room_number || ''}</td>
                      <td>{m.init_reading || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
        <div className="list-meta">共 {curMeters.length} 个</div>

        {this.renderModal()}
        {this.renderZoom()}
      </div>
    )
  }

  renderModal() {
    const { modal, editId, roomId, meterNo, initReading, photo, modalRooms, roomMenuOpen } = this.state
    if (!modal) return null
    const selRoom = modalRooms.find(r => String(r.id) === roomId)

    return (
      <div className="modal-overlay" onClick={() => this.setState({ modal: false })}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-title">{editId ? '编辑' : '添加'}</div>
          <div className="soft-form">
            <div className="form-group">
              <label>房间</label>
              <div className="custom-select" style={{position:'relative'}}>
                <div className="select-trigger" onClick={() => this.setState({ roomMenuOpen: !roomMenuOpen })}>
                  <span>{selRoom?.room_number || '请选择'}</span>
                </div>
                {roomMenuOpen && (
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
              <label>表编号</label>
              <input className="soft-input" value={meterNo} onChange={e => this.setState({ meterNo: e.target.value })} placeholder="如：WS-001" />
            </div>
            <div className="form-group">
              <label>初始读数</label>
              <input className="soft-input" type="number" value={initReading} onChange={e => this.setState({ initReading: e.target.value })} placeholder="0" />
            </div>
            <div className="form-group">
              <label>照片</label>
              <input type="file" accept="image/*" onChange={this.handlePhoto} />
              {photo && (
                <div style={{marginTop:6}}>
                  <img src={photo} className="meter-preview-img"
                    onMouseEnter={() => this.setState({ zoomImg: photo })}
                    onMouseLeave={() => this.setState({ zoomImg: null })} />
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

  renderZoom() {
    const { zoomImg } = this.state
    if (!zoomImg) return null
    return (
      <div id="meter_zoom" style={{position:'fixed',zIndex:9999,pointerEvents:'none',borderRadius:8,boxShadow:'0 8px 32px rgba(0,0,0,0.3)',overflow:'hidden',display:'block',left:10,top:10}}>
        <img src={zoomImg} style={{maxWidth:500,maxHeight:500,display:'block'}} />
      </div>
    )
  }
}

export function WaterMetersPage() {
  return <MeterPage type="water" title="水表信息" icon="💧" />
}

export function ElectricMetersPage() {
  return <MeterPage type="electric" title="电表信息" icon="⚡" />
}
