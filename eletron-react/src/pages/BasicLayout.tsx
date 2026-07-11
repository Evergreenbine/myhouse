import { useUIStore } from "../store"
import { BuildingsPage } from "./BuildingsPage"
import { RoomsPage } from "./RoomsPage"
import { TenantsPage } from "./TenantsPage"
import { ContractsPage } from "./ContractsPage"
import { WaterMetersPage } from "./WaterMetersPage"
import { ElectricMetersPage } from "./WaterMetersPage"

export function BasicLayout() {
  const { sideBasic, setSideBasic } = useUIStore()
  return (
    <div id="content">
      <div id="sidebar">
        {([
          { key: "buildings", label: "楼栋信息" },
          { key: "rooms", label: "房间信息" },
          { key: "tenants", label: "租客信息" },
          { key: "contracts", label: "合同信息" },
          { key: "water", label: "水表信息" },
          { key: "electric", label: "电表信息" },
        ] as const).map(item => (
          <div
            key={item.key}
            className={"side-item" + (sideBasic === item.key ? " active" : "")}
            onClick={() => setSideBasic(item.key)}
          >{item.label}</div>
        ))}
      </div>
      <div id="main-content">
        {sideBasic === "buildings" && <BuildingsPage />}
        {sideBasic === "rooms" && <RoomsPage />}
        {sideBasic === "tenants" && <TenantsPage />}
        {sideBasic === "contracts" && <ContractsPage />}
        {sideBasic === "water" && <WaterMetersPage />}
        {sideBasic === "electric" && <ElectricMetersPage />}
      </div>
    </div>
  )
}