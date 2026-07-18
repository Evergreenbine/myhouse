import React from 'react'
import { rental } from '../api'
import { Modal, Button, Input, showToast } from '../components/ui'

interface Building { id: number; name: string; address: string; rent_day: number }

interface State {
  buildings: Building[]
  roomCount: Record<number,number>
  loading: boolean
  modal: boolean
  editId: number | null
  name: string
  address: string
  rentDay: string
}

export class BuildingsPage extends React.Component<{}, State> {
  state: State = {
    buildings: [],
    roomCount: {},
    loading: true,
    modal: false,
    editId: null,
    name: '',
    address: '',
    rentDay: '1',
  }

  componentDidMount() { this.load() }

  load = async () => {
    const [blds, rooms] = await Promise.all([
      rental('buildings', 'list'),
      rental('rooms', 'list'),
    ])
    var rc: Record<number,number> = {}
    ;(rooms || []).forEach(function(r: any){ rc[r.building_id] = (rc[r.building_id] || 0) + 1 })
    this.setState({ buildings: blds || [], roomCount: rc, loading: false })
  }

  openAdd = () => { this.setState({ editId: null, name: '', address: '', rentDay: '1', modal: true }) }
  openEdit = async (id: number) => {
    const b = await rental('buildings', 'get', { id })
    if (b && !b.error) {
      this.setState({ editId: id, name: b.name || '', address: b.address || '', rentDay: String(b.rent_day || 1), modal: true })
    }
  }

  save = async () => {
    const { name, address, rentDay, editId } = this.state
    if (!name.trim()) { showToast('请输入楼栋名称'); return }
    const data = { name: name.trim(), address: address.trim(), rent_day: parseInt(rentDay) || 1 }
    const res = editId
      ? await rental('buildings', 'update', { ...data, id: editId })
      : await rental('buildings', 'add', data)
    if (res && !res.error) { this.setState({ modal: false }); this.load(); showToast('保存成功') }
    else { showToast('保存失败') }
  }

  render() {
    const { buildings, roomCount, loading, modal, editId, name, address, rentDay } = this.state
    if (loading) return <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div>

    return (
      <div>
        <div className="toolbar toolbar-end">
          <Button type="primary" size="sm" onClick={this.openAdd}>+ 添加楼栋</Button>
        </div>
        <div className="toolbar-divider" />

        {buildings.length === 0 ? (
          <div className="empty-state"><div className="icon">🏢</div><div>暂无楼栋，点击上方按钮添加</div></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>名称</th><th>地址</th><th>房间数</th></tr></thead>
              <tbody>
                {buildings.map(b => (
                  <tr key={b.id}>
                    <td><span className="name-link" onClick={() => this.openEdit(b.id)}>{b.name}</span></td>
                    <td>{b.address || '-'}</td>
                    <td>{roomCount[b.id] || 0} 间</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="list-meta">共 {buildings.length} 栋楼</div>

        <Modal open={modal} onClose={() => this.setState({ modal: false })} title={editId ? '编辑楼栋' : '添加楼栋'}>
          <div className="soft-form">
            <div className="form-group">
              <label>名称</label>
              <Input value={name} onChange={v => this.setState({ name: v })} placeholder="如：A栋" />
            </div>
            <div className="form-group">
              <label>地址</label>
              <Input value={address} onChange={v => this.setState({ address: v })} placeholder="如：XX路XX号" />
            </div>
            <div className="form-group">
              <label>收租日期（每月几号）</label>
              <Input type="number" value={rentDay} onChange={v => this.setState({ rentDay: v })} min="1" max="28" placeholder="1" />
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
