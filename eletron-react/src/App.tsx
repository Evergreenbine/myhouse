import React from "react"
import { LogoutOutlined, UserOutlined } from "@ant-design/icons"

import { api, AUTH_EXPIRED_EVENT, clearAuthToken } from "./api"
import { useUIStore } from "./store"
import { BasicLayout } from "./pages/BasicLayout"
import { RentLayout } from "./pages/RentLayout"
import { SettingsPage } from "./pages/SettingsPage"
import { AIChat } from "./pages/AIChat"
import { AuthUser, LoginPage, USER_PROFILE_UPDATED_EVENT } from "./pages/LoginPage"

export default function App() {
  const { section, setSection } = useUIStore()
  const [authLoading, setAuthLoading] = React.useState(true)
  const [currentUser, setCurrentUser] = React.useState<AuthUser | null>(null)

  React.useEffect(() => {
    var active = true
    api("/api/user/status").then(res => {
      if (!active) return
      if (res?.authenticated && res?.user) setCurrentUser(res.user)
      else {
        clearAuthToken()
        setCurrentUser(null)
      }
      setAuthLoading(false)
    })
    var expired = () => setCurrentUser(null)
    var profileUpdated = (event: Event) => {
      var detail = (event as CustomEvent<AuthUser>).detail
      if (detail) setCurrentUser(detail)
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, expired)
    window.addEventListener(USER_PROFILE_UPDATED_EVENT, profileUpdated)
    return () => {
      active = false
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired)
      window.removeEventListener(USER_PROFILE_UPDATED_EVENT, profileUpdated)
    }
  }, [])

  const logout = async () => {
    await api("/api/user/logout", { method: "POST" })
    clearAuthToken()
    setCurrentUser(null)
  }

  if (authLoading) return <div className="app-auth-loading">FU的小家</div>
  if (!currentUser) return <LoginPage onLogin={setCurrentUser} />

  return (
    <div id="app">
      <div id="top-bar">
        <span id="app-title" onClick={() => setSection("settings")}>FU的小家</span>
        <div className={"section-tab" + (section === "basic" ? " active" : "")} onClick={() => setSection("basic")}>基础信息</div>
        <div className={"section-tab" + (section === "rent" ? " active" : "")} onClick={() => setSection("rent")}>收租管理</div>
        <div className="spacer" />
        <div className="top-account">{currentUser.avatar ? <img src={currentUser.avatar} alt="" /> : <UserOutlined />}<span>{currentUser.display_name || currentUser.username}</span></div>
        <button type="button" className="top-logout" onClick={logout} title="退出登录"><LogoutOutlined /></button>
      </div>

      {section === "basic" && <BasicLayout />}
      {section === "rent" && <RentLayout />}
      {section === "settings" && <div id="content"><div id="main-content" style={{margin:0,padding:"24px 28px",flex:1,overflowY:"auto"}}><SettingsPage currentUser={currentUser} /></div></div>}

      <div id="bottom-bar">
        <span id="bottom-status">FU的小家 v1.0</span>
      </div>
      <AIChat currentUser={currentUser} />
    </div>
  )
}
