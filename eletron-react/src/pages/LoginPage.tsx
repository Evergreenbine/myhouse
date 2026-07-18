import React from "react"
import { LockOutlined, LoginOutlined, UserOutlined } from "@ant-design/icons"

import { api, setAuthToken } from "../api"

export interface AuthUser {
  id: number
  username: string
  display_name: string
  role: "owner" | "family"
  is_active: boolean
  avatar?: string
}

export const USER_PROFILE_UPDATED_EVENT = "myhouse-user-profile-updated"

export function LoginPage({ onLogin }: { onLogin: (user: AuthUser) => void }) {
  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState("")

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!username.trim() || !password) {
      setError("请输入账号和密码")
      return
    }
    setLoading(true)
    setError("")
    var res = await api("/api/user/login", {
      method: "POST",
      body: JSON.stringify({ username: username.trim(), password }),
    })
    setLoading(false)
    if (!res || res.error || !res.access_token || !res.user) {
      setError(res?.error || "登录失败，请稍后重试")
      return
    }
    setAuthToken(res.access_token)
    onLogin(res.user)
  }

  return (
    <div className="login-page">
      <form className="login-panel" onSubmit={submit}>
        <div className="login-brand">FU的小家</div>
        <div className="login-title">登录</div>
        <div className="login-subtitle">使用屋主或家人账号进入</div>
        {error && <div className="login-error">{error}</div>}
        <label className="login-field">
          <span>账号</span>
          <div><UserOutlined /><input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" autoFocus /></div>
        </label>
        <label className="login-field">
          <span>密码</span>
          <div><LockOutlined /><input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" /></div>
        </label>
        <button type="submit" className="btn login-submit" disabled={loading}>
          <LoginOutlined />{loading ? "登录中" : "登录"}
        </button>
      </form>
    </div>
  )
}
