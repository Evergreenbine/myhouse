import React from "react"
import { rental, api } from "../api"

interface AIChatState {
  open: boolean
  messages: { role: "user" | "assistant"; content: string }[]
  loading: boolean
  convId: number
  historyView: boolean
  historyChats: any[]
}

function esc(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function renderMarkdown(text: string): string {
  if (!text) return ""
  var t = text
  t = t.replace(/```(\w*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>")
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>")
  t = t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
  t = t.replace(/(\|[^\n]+\|\n\|[-:\|\s]+\|\n((?:\|[^\n]+\|\n?)*))/g, function(m) {
    var lines = m.trim().split("\n")
    var h = "<table>"
    lines.forEach(function(line, i) {
      if (i === 1) return
      var cells = line.split("|").filter(function(c) { return c.trim() })
      var tag = i === 0 ? "th" : "td"
      h += "<tr>" + cells.map(function(c) { return "<" + tag + ">" + c.trim() + "</" + tag + ">" }).join("") + "</tr>"
    })
    return h + "</table>"
  })
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "<a href=\"$2\" target=\"_blank\">$1</a>")
  t = t.replace(/\n\n/g, "</p><p>")
  t = t.replace(/\n/g, "<br>")
  return "<p>" + t + "</p>"
}
export class AIChat extends React.Component<{}, AIChatState> {
  state: AIChatState = {
    open: false,
    messages: [],
    loading: false,
    convId: 0,
    historyView: false,
    historyChats: []
  }
  private bodyRef = React.createRef<HTMLDivElement>()
  private inputRef = React.createRef<HTMLInputElement>()

  toggle = () => {
    this.setState(s => {
      if (!s.open) { setTimeout(() => this.inputRef.current?.focus(), 50) }
      return { open: !s.open, historyView: false }
    })
  }

  newChat = () => {
    if (this.state.messages.length > 0 && !confirm("确定开始新对话？当前对话将丢失。")) return
    this.setState({ messages: [], convId: 0 })
  }

  loadHistory = async () => {
    try {
      var chats = await rental("_ai", "list_chats") || []
      this.setState({ historyView: true, historyChats: chats })
    } catch { /* ignore */ }
  }

  restoreChat = async (id: number) => {
    try {
      var chats = await rental("_ai", "list_chats") || []
      var chat = chats.find(function(c: any) { return c.id === id })
      if (!chat) return
      this.setState({ messages: chat.messages || [], convId: id, historyView: false, open: true })
      this.scrollBottom()
    } catch { /* ignore */ }
  }

  deleteChat = async (id: number) => {
    if (!confirm("确定删除该对话？")) return
    await rental("_ai", "delete_chat", { id })
    if (this.state.convId === id) this.newChat()
    this.loadHistory()
  }

  send = async () => {
    var input = this.state.loading ? "" : (this.inputRef.current?.value || "").trim()
    if (!input) return
    if (this.inputRef.current) this.inputRef.current.value = ""
    var msgs = this.state.messages
    msgs = msgs.concat([{ role: "user" as const, content: input }])
    this.setState({ messages: msgs, loading: true, historyView: false })
    this.scrollBottom()
    try {
      var res = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({ table: "_ai", action: "chat", data: { prompt: input, history: msgs.slice(-10) } })
      })
      var reply = (res && res.reply) ? res.reply : "抱歉，AI 服务暂时不可用"
      msgs = msgs.concat([{ role: "assistant" as const, content: reply }])
      this.setState({ messages: msgs, loading: false })
      this.scrollBottom()
      var title = input.substring(0, 30)
      var saveRes = await rental("_ai", "save_chat", { id: this.state.convId, title, messages: msgs })
      if (saveRes && saveRes.id) this.setState({ convId: saveRes.id })
    } catch {
      msgs = msgs.concat([{ role: "assistant" as const, content: "抱歉，暂时无法连接 AI 服务" }])
      this.setState({ messages: msgs, loading: false })
      this.scrollBottom()
    }
  }

  scrollBottom = () => {
    setTimeout(() => {
      if (this.bodyRef.current) this.bodyRef.current.scrollTop = this.bodyRef.current.scrollHeight
    }, 50)
  }

  renderBody() {
    var s = this.state
    if (s.historyView) {
      if (s.historyChats.length === 0) return <div className="ai-msg bot">暂无历史对话</div>
      return (
        <div className="ai-chat-history-body">
          {s.historyChats.map((c: any) => {
            var title = c.title || "对话 " + c.id
            return (
              <div key={c.id} className="ai-chat-history-item" onClick={() => this.restoreChat(c.id)}>
                <span>{esc(title.substring(0, 40))}</span>
                <button className="btn btn-sm" style={{color:"var(--red)",fontSize:11,padding:"2px 8px"}}
                  onClick={(e: React.MouseEvent) => { e.stopPropagation(); this.deleteChat(c.id) }}>删除</button>
              </div>
            )
          })}
        </div>
      )
    }
    if (s.messages.length === 0) {
      return (
        <div className="ai-msg bot">你好！我是<b>租房小管家</b>，可以帮你：<br /><br />· 查询租客信息和合同<br />· 分析缴费情况<br />· 解答租房相关问题<br /><br />有什么可以帮你的？</div>
      )
    }
    return s.messages.map((m, i) => {
      if (m.role === "user") {
        return <div key={i} className="ai-msg user" dangerouslySetInnerHTML={{ __html: esc(m.content) }} />
      }
      return <div key={i} className="ai-msg bot" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
    })
  }

  render() {
    var s = this.state
    return (
      <>
        <button id="ai-float-btn" onClick={this.toggle} title="AI 助手">
          <span style={{fontSize:24}}>🤖</span>
          <span className="ai-dot" />
        </button>

        <div className={"ai-chat-panel" + (s.open ? " open" : "")}>
          <div className="ai-chat-header">
            <span className="ai-title">🤖 租房小管家</span>
            <div className="ai-actions">
              <button title="新对话" onClick={this.newChat}>＋</button>
              <button title="历史记录" onClick={this.loadHistory}>📋</button>
              <button title="关闭" onClick={this.toggle}>✕</button>
            </div>
          </div>
          <div className="ai-chat-body" ref={this.bodyRef}>
            {this.renderBody()}
            {s.loading && <div className="ai-msg loading">思考中...</div>}
          </div>
          <div className="ai-chat-footer">
            <input ref={this.inputRef} placeholder="输入你的问题..."
              onKeyDown={e => { if (e.key === "Enter") this.send() }} />
            <button onClick={this.send}>发送</button>
          </div>
        </div>
      </>
    )
  }
}