import React from 'react'
import { rental } from '../api'
import { Modal, Button, Input, showToast } from '../components/ui'
import { resolveBuildingId, useUIStore } from '../store'

interface Room { id: number; room_number: string; floor: number; status: string; building_name: string; building_id: number }
interface Building { id: number; name: string; rent_day?: number }

interface State {
  rooms: Record<number, Room[]>
  buildings: Building[]
  curBid: number | null
  loading: boolean
  modal: boolean
  editId: number | null
  roomNumber: string
  floor: string
  buildingId: string
  status: 'idle' | 'rented'
}

export class RoomsPage extends React.Component<{}, State> {
  state: State = {
    rooms: {},
    buildings: [],
    curBid: null,
    loading: true,
    modal: false,
    editId: null,
    roomNumber: '',
    floor: '1',
    buildingId: '',
    status: 'idle',
  }

  componentDidMount() { this.loadBuildings() }

  loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = resolveBuildingId(data)
    useUIStore.getState().setSelectedBuildingId(bid)
    if (bid) {
      const rooms = await rental('rooms', 'list', { building_id: bid }) || []
      this.setState({ buildings: data, curBid: bid, rooms: { [bid]: rooms }, loading: false })
    } else {
      this.setState({ buildings: data, loading: false })
    }
  }

  switchBuilding = async (id: number) => {
    useUIStore.getState().setSelectedBuildingId(id)
    const { rooms } = this.state
    // 有缓存直接切
    if (rooms[id]) {
      this.setState({ curBid: id })
      return
    }
    // 无缓存才显示加载
    this.setState({ curBid: id, loading: true })
    const data = await rental('rooms', 'list', { building_id: id }) || []
    this.setState(s => ({ rooms: { ...s.rooms, [id]: data }, loading: false }))
  }

  openAdd = () => {
    this.setState({
      editId: null, roomNumber: '', floor: '1',
      buildingId: String(this.state.curBid || ''), status: 'idle', modal: true,
    })
  }
  openEdit = async (id: number) => {
    const r = await rental('rooms', 'get', { id })
    if (r && !r.error) {
      this.setState({
        editId: id, roomNumber: r.room_number || '', floor: String(r.floor || 1),
        buildingId: String(r.building_id || ''), status: r.status === 'rented' ? 'rented' : 'idle', modal: true,
      })
    }
  }

  save = async () => {
    const { roomNumber, floor, buildingId, status, editId, curBid } = this.state
    if (!roomNumber.trim()) { showToast('请输入房间号'); return }
    const data = { room_number: roomNumber.trim(), floor: parseInt(floor) || 1, building_id: parseInt(buildingId), status }
    const res = editId
      ? await rental('rooms', 'update', { ...data, id: editId })
      : await rental('rooms', 'add', data)
    if (res && !res.error) {
      const newBid = parseInt(buildingId)
      this.setState({ modal: false })
      // 刷新缓存
      const rooms = await rental('rooms', 'list', { building_id: newBid }) || []
      this.setState(s => ({ rooms: { ...s.rooms, [newBid]: rooms }, curBid: newBid }))
      showToast(editId ? '保存成功' : '添加成功')
    } else { showToast('保存失败') }
  }

  render() {
    const { rooms, buildings, curBid, loading, modal, editId, roomNumber, floor, buildingId, status } = this.state

    if (buildings.length === 0) return (
      <div>
        <div className="toolbar"><Button type="primary" size="sm" onClick={() => {}}>+ 先添加楼栋</Button></div>
        <div className="toolbar-divider" />
        <div className="empty-state"><div className="icon">🏠</div><div>请先添加楼栋，再录入房间</div></div>
      </div>
    )

    const curBuilding = buildings.find(b => Number(b.id) === Number(curBid))
    const curRooms = curBid ? (rooms[curBid] || []) : []

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
          <Button type="primary" size="sm" onClick={this.openAdd}>+ 添加房间</Button>
        </div>

        {loading ? <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div> :
          curRooms.length === 0 ? (
            <div className="empty-state"><div className="icon">🏠</div><div>当前楼栋暂无房间，点击上方按钮添加</div></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>房间号</th><th className="status-cell">状态</th></tr></thead>
                <tbody>
                  {curRooms.map((r: Room) => {
                    const rented = r.status === 'rented'
                    return (
                      <tr key={r.id}>
                        <td><span className="name-link" onClick={() => this.openEdit(r.id)}>{r.room_number}</span></td>
                        <td className="status-cell">
                          <span className={'status-dot ' + (rented ? 'rented' : 'idle')} title={rented ? '在租' : '闲置'} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        }
        <div className="list-meta">共 {curRooms.length} 个房间</div>

        <Modal open={modal} onClose={() => this.setState({ modal: false })} title={editId ? '编辑房间' : '添加房间'}>
          <div className="soft-form">
            {editId ? (
              <div className="form-group">
                <label>所属楼栋</label>
                <div className="locked-field">{curBuilding?.name || ''}</div>
              </div>
            ) : (
              <div className="form-group">
                <label>所属楼栋</label>
                <select className="soft-input" value={buildingId} onChange={e => this.setState({ buildingId: e.target.value })}>
                  {buildings.map(b => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="form-group">
              <label>楼层</label>
              <Input type="number" value={floor} onChange={v => this.setState({ floor: v })} placeholder="如：1" />
            </div>
            <div className="form-group">
              <label>房间号</label>
              <Input value={roomNumber} onChange={v => this.setState({ roomNumber: v })} placeholder="如：101" />
            </div>
            <div className="form-group">
              <label>状态</label>
              <div className="status-switch-row">
                <button
                  className={'status-switch' + (status === 'rented' ? ' rented' : '')}
                  onClick={() => this.setState({ status: status === 'rented' ? 'idle' : 'rented' })}
                  type="button"
                />
                <span className="status-switch-label">{status === 'rented' ? '在租' : '闲置'}</span>
              </div>
            </div>
            <div className="modal-actions">
              <Button onClick={() => this.setState({ modal: false })}>取消</Button>
              <Button type="primary" onClick={this.save}>保存</Button>
            </div>
          </div>
        </Modal>
      </div>
    )
  }
}
