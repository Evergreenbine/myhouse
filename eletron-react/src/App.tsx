import { useUIStore } from "./store"
import { BasicLayout } from "./pages/BasicLayout"
import { RentLayout } from "./pages/RentLayout"
import { SettingsPage } from "./pages/SettingsPage"
import { AIChat } from "./pages/AIChat"

export default function App() {
  const { section, setSection } = useUIStore()
  return (
    <div id="app">
      <div id="top-bar">
        <span id="app-title" onClick={() => setSection("settings")}>FU的小家</span>
        <div className={"section-tab" + (section === "basic" ? " active" : "")} onClick={() => setSection("basic")}>基础信息</div>
        <div className={"section-tab" + (section === "rent" ? " active" : "")} onClick={() => setSection("rent")}>收租管理</div>
        <div className="spacer" />
      </div>

      {section === "basic" && <BasicLayout />}
      {section === "rent" && <RentLayout />}
      {section === "settings" && <div id="content"><div id="main-content" style={{margin:0,padding:"24px 28px",flex:1,overflowY:"auto"}}><SettingsPage /></div></div>}

      <div id="bottom-bar">
        <span id="bottom-status">FU的小家 v1.0</span>
      </div>
      <AIChat />
    </div>
  )
}
