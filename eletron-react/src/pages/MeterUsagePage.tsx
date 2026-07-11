import React from 'react'
import { rental } from '../api'
import { showToast } from '../components/ui'

interface MeterReading { id: number; meter_no: string; room_number: string; building_name: string; floor: number; reading: number | null; previous_reading: number; usage: number | null; photo: string; status: string }
interface Building { id: number; name: string }

interface State {
  buildings: Building[]
  rows: MeterReading[]
  curBid: number | null
  usageYear: number
  usageMonth: number
  loading: boolean
  firstLoad: boolean
  overviewMode: boolean
  overviewData: any
  editingKey: string
  editReading: string
  editPhoto: string
}

class MeterUsagePage extends React.Component<{ type: string; title: string; icon: string; unit: string }, State> {
  state: State = {
    buildings: [],
    rows: [],
    curBid: null,
    usageYear: new Date().getFullYear(),
    usageMonth: new Date().getMonth() + 1,
    loading: true,
    firstLoad: true,
    overviewMode: false,
    overviewData: null,
    editingKey: '',
    editReading: '',
    editPhoto: '',
  }

  componentDidMount() { this.loadBuildings() }

  get monthKey() { return this.state.usageYear + '-' + String(this.state.usageMonth).padStart(2, '0') }

  fmtNum = (v: number | null) => v != null ? v.toFixed(1) : '--'

  loadBuildings = async () => {
    const data = await rental('buildings', 'list') || []
    const bid = data.length > 0 ? data[0].id : null
    this.setState({ buildings: data, curBid: bid, firstLoad: false })
    if (bid) this.loadData(bid)
  }

  loadData = async (bid: number) => {
    const timer = setTimeout(() => this.setState({ loading: true }), 200)
    const { type } = this.props
    const rows = await rental('readings', 'monthly', { type, building_id: bid, month: this.monthKey }) || []
    clearTimeout(timer)
    this.setState({ rows, loading: false })
  }

  switchBuilding = (id: number) => {
    this.setState({ curBid: id })
    this.loadData(id)
  }

  changeMonth = (delta: number) => {
    var { usageYear, usageMonth, curBid } = this.state
    usageMonth += delta
    if (usageMonth < 1) { usageMonth = 12; usageYear-- }
    if (usageMonth > 12) { usageMonth = 1; usageYear++ }
    this.setState({ usageYear, usageMonth })
    if (curBid) this.loadData(curBid)
  }

  loadOverview = async () => {
    const { curBid } = this.state
    if (!curBid) return
    this.setState({ loading: true })
    const data = await rental('readings', 'overview', { type: this.props.type, building_id: curBid, start_month: '2026-06', end_month: this.monthKey }) || {}
    this.setState({ overviewData: data, overviewMode: true, loading: false })
  }

  backToDetail = () => this.setState({ overviewMode: false })

  startEdit = (row: MeterReading) => {
    this.setState({
      editingKey: String(row.id),
      editReading: row.reading != null ? String(row.reading) : '',
      editPhoto: row.photo || '',
    })
  }

  cancelEdit = () => this.setState({ editingKey: '', editReading: '', editPhoto: '' })

  handlePhoto = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async () => {
      const dataUrl = reader.result as string
      this.setState({ editPhoto: dataUrl })
      // AI 识图读数
      try {
        const meterType = this.props.type === 'water' ? '水表' : '电表'
        const res = await rental('_ocr', 'read', { image: dataUrl, meter_type: meterType })
        if (res?.numbers?.length) {
          const num = res.numbers[0]
          this.setState({ editReading: String(num) })
          showToast('AI 识别读数：' + num)
        } else {
          showToast('未识别到数字，请手动输入')
        }
      } catch {
        showToast('识别失败，请手动输入')
      }
    }
    reader.readAsDataURL(file)
  }

  saveReading = async (meterId: number) => {
    const { editReading, editPhoto } = this.state
    const val = parseFloat(editReading)
    if (isNaN(val)) { showToast('请输入有效读数'); return }

    await rental('readings', 'save_monthly', { meter_id: meterId, month: this.monthKey, reading: val, photo: editPhoto })
    this.cancelEdit()
    if (this.state.curBid) this.loadData(this.state.curBid)
    showToast('已保存')
  }

  render() {
    const { buildings, rows, curBid, usageYear, usageMonth, loading, overviewMode, overviewData, editingKey, editReading, editPhoto } = this.state
    const { type, title, icon, unit } = this.props
    if (this.state.firstLoad) return <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div>

    if (buildings.length === 0) return (
      <div className="empty-state"><div className="icon">{icon}</div><div>请先添加楼栋和表具</div></div>
    )

    // Overview mode
    if (overviewMode && overviewData) {
      const months: string[] = overviewData.months || []
      const ovRows = overviewData.rows || []
      return (
        <div>
          <div className="month-filter">
            <span className="month-label" style={{minWidth:180}}>2026-06 — {this.monthKey}</span>
            <button className="month-nav month-nav-overview" style={{width:80}} onClick={this.backToDetail}>←</button>
          </div>
          <div className="tab-action-row">
            <div className="building-tabs">
              {buildings.map(b => (
                <button key={b.id} className={'building-tab' + (Number(b.id) === Number(curBid) ? ' active' : '')}
                  onClick={() => this.switchBuilding(b.id)}>{b.name}</button>
              ))}
            </div>
          </div>
          {ovRows.length === 0 ? (
            <div className="empty-state"><div className="icon">{icon}</div><div>暂无数据</div></div>
          ) : (
            <div className="table-wrap">
              <table style={{minWidth: 260 + months.length * 96}}>
                <thead><tr>
                  <th style={{position:'sticky',left:0,zIndex:2,background:'#F8FAFD',width:160}}>表具</th>
                  <th style={{width:88}}>房间</th>
                  {months.map((m: string) => <th key={m} style={{textAlign:'right'}}>{m}</th>)}
                </tr></thead>
                <tbody>
                  {ovRows.map((row: any) => (
                    <tr key={row.id}>
                      <td style={{position:'sticky',left:0,background:'var(--white)',zIndex:1}}>
                        <span className="name-link">{row.meter_no || ('表ID ' + row.id)}</span></td>
                      <td>{row.room_number || ''}</td>
                      {months.map((m: string) => {
                        const val = row.readings ? row.readings[m] : null
                        return <td key={m} style={{textAlign:'right',fontWeight: val != null ? 600 : 400, color: val != null ? 'var(--text)' : 'var(--text-third)'}}>{this.fmtNum(val)}</td>
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="list-meta">共 {ovRows.length} 个表，{months.length} 个月</div>
        </div>
      )
    }

    // Detail mode
    var totalUsage = 0, recordCount = 0
    rows.forEach(r => {
      if (r.usage != null) totalUsage += r.usage
      if (r.status === 'recorded') recordCount++
    })

    return (
      <div>
        {/* 月份切换 */}
        <div className="month-filter">
          <button className="month-nav" onClick={() => this.changeMonth(-1)}>◀</button>
          <span className="month-label">{usageYear}年{usageMonth}月</span>
          <button className="month-nav" onClick={() => this.changeMonth(1)}>▶</button>
          <button className="month-nav month-nav-overview" onClick={this.loadOverview}>统计概览</button>
        </div>

        {/* 楼栋 tabs */}
        <div className="tab-action-row">
          <div className="building-tabs">
            {buildings.map(b => (
              <button key={b.id} className={'building-tab' + (Number(b.id) === Number(curBid) ? ' active' : '')}
                onClick={() => this.switchBuilding(b.id)}>{b.name}</button>
            ))}
          </div>
        </div>

        {loading ? <div style={{padding:40,textAlign:'center',color:'var(--text-third)'}}>加载中...</div> : (
          <>
            {/* 汇总 */}
            <div className="summary-row">
              <div className="stat-card"><div>{title}</div><div className="stat-val" style={{color:type==='water'?'var(--blue)':'var(--orange)'}}>{this.fmtNum(totalUsage)} {unit}</div></div>
              <div className="stat-card"><div>已录入表数</div><div className="stat-val" style={{color:'var(--green)'}}>{recordCount}</div></div>
              <div className="stat-card"><div>未录入表数</div><div className="stat-val" style={{color:'var(--red)'}}>{rows.length - recordCount}</div></div>
            </div>

            {rows.length === 0 ? (
              <div className="empty-state"><div className="icon">{icon}</div><div>当前楼栋暂无表具</div></div>
            ) : (
              <div className="plan-cards">
                {rows.map(row => {
                  const mid = row.id
                  const editing = editingKey === String(mid)
                  return (
                    <div key={mid} className="plan-card">
                      <div className="card-header">
                        <span className="card-tenant">{row.room_number || ''}</span>
                        <span className="card-room">{row.meter_no || ('表ID ' + mid)}</span>
                      </div>
                      <div className="card-items">
                        <div className="card-item">楼栋 <span>{row.building_name || ''}</span></div>
                        <div className="card-item">楼层 <span>{row.floor || ''}</span></div>
                        <div className="card-item">上月读数 <span>{this.fmtNum(row.previous_reading)}</span></div>
                        <div className="card-item">当月结算读数 <span>{row.reading != null ? this.fmtNum(row.reading) : '--'}</span></div>
                        <div className="card-item">当月用量 <span>{row.usage != null ? this.fmtNum(row.usage) + ' ' + unit : '--'}</span></div>
                      </div>
                      <div className="card-total">
                        <span className={'tag ' + (row.status === 'recorded' ? 'tag-green' : 'tag-red')}>{row.status === 'recorded' ? '已录入' : '未录入'}</span>
                        <span className="amount">{row.usage != null ? this.fmtNum(row.usage) + ' ' + unit : '--'}</span>
                      </div>

                      {editing ? (
                        <div style={{marginTop:12,borderTop:'1px dashed var(--border-light)',paddingTop:12}}>
                          <div className="form-group">
                            <label>当月结算读数</label>
                            <input className="soft-input" type="number" step="0.1" value={editReading}
                              onChange={e => this.setState({ editReading: e.target.value })} placeholder="请输入读数" />
                          </div>
                          <div className="upload-area" style={{marginBottom:8}}>
                            <input type="file" accept="image/*" onChange={this.handlePhoto} />
                            <div className="upload-preview">
                              {editPhoto ? <img src={editPhoto} style={{maxWidth:'100%',maxHeight:80,borderRadius:4}} /> : '📷 上传照片'}
                            </div>
                          </div>
                          <div style={{display:'flex',gap:8,justifyContent:'flex-end'}}>
                            <button className="btn btn-outline btn-sm" onClick={this.cancelEdit}>取消</button>
                            <button className="btn btn-primary btn-sm" onClick={() => this.saveReading(mid)}>保存</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div style={{height:98,marginTop:12,borderTop:'1px dashed var(--border-light)',paddingTop:10,display:'flex',alignItems:'center',justifyContent:'center',background:'#F8FAFD',borderRadius:8,overflow:'hidden'}}>
                            {row.photo ? <img src={row.photo} style={{maxWidth:'100%',maxHeight:80,borderRadius:4}} /> : <span style={{color:'var(--text-third)'}}>暂无照片</span>}
                          </div>
                          <div style={{display:'flex',justifyContent:'flex-end',marginTop:10}}>
                            <button className="btn btn-outline btn-sm" onClick={() => this.startEdit(row)}>
                              {row.status === 'recorded' ? '编辑' : '录入'}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
        <div className="list-meta">共 {rows.length} 个表</div>
      </div>
    )
  }
}

export function WaterUsagePage() {
  return <MeterUsagePage type="water" title="水表用量" icon="💧" unit="吨" />
}

export function ElectricUsagePage() {
  return <MeterUsagePage type="electric" title="电表用量" icon="⚡" unit="度" />
}
