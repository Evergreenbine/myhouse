import { useUIStore } from '../store'
import { RentPlanPage } from './RentPlanPage'
import { WaterUsagePage } from './MeterUsagePage'
import { ElectricUsagePage } from './MeterUsagePage'

export function RentLayout() {
  const { sideRent, setSideRent } = useUIStore()
  return (
    <div id="content">
      <div id="sidebar-rent">
        {([
          { key: 'plan', label: '收租计划' },
          { key: 'waterUsage', label: '水表用量' },
          { key: 'electricUsage', label: '电表用量' },
        ] as const).map(item => (
          <div
            key={item.key}
            className={'side-item' + (sideRent === item.key ? ' active' : '')}
            onClick={() => setSideRent(item.key)}
          >{item.label}</div>
        ))}
      </div>
      <div id="main-content-rent">
        <div style={{display: sideRent === 'plan' ? 'block' : 'none'}}><RentPlanPage /></div>
        <div style={{display: sideRent === 'waterUsage' ? 'block' : 'none'}}><WaterUsagePage /></div>
        <div style={{display: sideRent === 'electricUsage' ? 'block' : 'none'}}><ElectricUsagePage /></div>
      </div>
    </div>
  )
}
