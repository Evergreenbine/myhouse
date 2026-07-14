import React from "react";
import { rental, api } from "../api";

interface AIChatState {
  open: boolean
  messages: { role: "user" | "assistant"; content: string }[]
  loading: boolean
  convId: number
  historyChats: any[]
  sidebarCollapsed: boolean
  uploadedImage: string
  imagePreview: string
}

function esc(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function escAttr(text: string): string {
  return esc(text).replace(/"/g, "&quot;")
}

function safeHref(url: string): string {
  var u = (url || "").trim()
  if (/^(https?:|mailto:|tel:)/i.test(u) || u.startsWith("/") || u.startsWith("#")) {
    return escAttr(u)
  }
  return "#"
}

function renderMarkdown(text: string): string {
  if (!text) return ""
  var t = esc(text)
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
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function(_, label, url) {
    return "<a href=\"" + safeHref(url) + "\" target=\"_blank\" rel=\"noreferrer\">" + label + "</a>"
  })
  t = t.replace(/\n\n/g, "</p><p>")
  t = t.replace(/\n/g, "<br>")
  return "<p>" + t + "</p>"
}

const QUICK_PROMPTS = [
  { label: "本月待收", prompt: "本月有哪些房间待收款？请按楼栋、房间、租客、待收金额列出来。" },
  { label: "账单汇总", prompt: "帮我汇总本月账单：应收、已收、待收，以及各状态户数。" },
  { label: "录入进度", prompt: "本月哪些房间还未录入或正在录入中？" },
  { label: "收款异常", prompt: "本月有没有部分收款、待发送、待收款的账单？请分别列出来。" },
]

export class AIChat extends React.Component<{}, AIChatState> {
  state: AIChatState = {
    open: false,
    messages: [],
    loading: false,
    convId: 0,
    historyChats: [],
    sidebarCollapsed: false,
    uploadedImage: "",
    imagePreview: "",
  }
  private bodyRef = React.createRef<HTMLDivElement>()
  private inputRef = React.createRef<HTMLInputElement>()
  private fileRef = React.createRef<HTMLInputElement>()
  private sidebarRef = React.createRef<HTMLDivElement>()

  toggle = () => {
    this.setState(s => {
      if (!s.open) {
        setTimeout(() => { this.inputRef.current?.focus(); this.loadHistory() }, 50)
      }
      return { open: !s.open }
    })
  }

  newChat = () => {
    if (this.state.messages.length > 0 && !confirm("确定开始新对话？当前对话将丢失。")) return
    this.setState({ messages: [], convId: 0 })
    setTimeout(() => this.inputRef.current?.focus(), 50)
  }

  loadHistory = async () => {
    try {
      var chats = await rental("_ai", "list_chats") || []
      this.setState({ historyChats: chats })
    } catch { /* ignore */ }
  }

  restoreChat = async (id: number) => {
    try {
      var chats = await rental("_ai", "list_chats") || []
      var chat = chats.find(function(c: any) { return c.id === id })
      if (!chat) return
      this.setState({ messages: chat.messages || [], convId: id, sidebarCollapsed: false })
      this.scrollBottom()
      setTimeout(() => this.inputRef.current?.focus(), 50)
    } catch { /* ignore */ }
  }

  deleteChat = async (id: number) => {
    if (!confirm("确定删除该对话？")) return
    await rental("_ai", "delete_chat", { id })
    if (this.state.convId === id) {
      this.setState({ messages: [], convId: 0 })
    }
    this.loadHistory()
  }

  sendQuick = (prompt: string) => {
    if (this.state.loading) return
    if (this.inputRef.current) this.inputRef.current.value = prompt
    this.send()
  }

  send = async () => {
    var input = this.state.loading ? "" : (this.inputRef.current?.value || "").trim()
    if (!input) return
    if (this.inputRef.current) this.inputRef.current.value = ""
    var msgs = [...this.state.messages, { role: "user" as const, content: input }]
    this.setState({ messages: msgs, loading: true })
    this.scrollBottom()
    try {
      var res = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({ table: "_ai", action: "chat", data: { prompt: input, history: this.state.messages.slice(-10) } })
      })
      var reply = (res && res.reply) ? res.reply : "抱歉，AI 服务暂时不可用"
      msgs = [...msgs, { role: "assistant" as const, content: reply }]
      this.setState({ messages: msgs, loading: false })
      this.scrollBottom()
      var title = input.substring(0, 30)
      var saveRes = await rental("_ai", "save_chat", { id: this.state.convId, title, messages: msgs })
      if (saveRes && saveRes.id) {
        this.setState({ convId: saveRes.id })
        this.loadHistory()
      }
    } catch {
      msgs = [...msgs, { role: "assistant" as const, content: "抱歉，暂时无法连接 AI 服务" }]
      this.setState({ messages: msgs, loading: false })
      this.scrollBottom()
    }
  }


  handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    var file = e.target.files?.[0]
    if (!file) return
    var reader = new FileReader()
    reader.onload = () => {
      var base64 = reader.result as string
      this.setState({ uploadedImage: base64, imagePreview: base64 })
    }
    reader.readAsDataURL(file)
  }

  removeImage = () => {
    this.setState({ uploadedImage: "", imagePreview: "" })
  }

  sendWithImage = async () => {
    var input = (this.inputRef.current?.value || "").trim()
    var image = this.state.uploadedImage
    if (!input && !image) return
    
    if (this.inputRef.current) this.inputRef.current.value = ""
    
    // Show user message (possibly with image context)
    var userMsg = input || "请识别这张电表图片"
    var msgs = [...this.state.messages, { role: "user" as const, content: userMsg }]
    this.setState({ messages: msgs, loading: true, imagePreview: "", uploadedImage: "" })
    this.scrollBottom()

    try {
      // If image is attached, first do OCR
      var ocrResult = ""
      if (image) {
        var base64Data = image.includes("base64,") ? image.split("base64,")[1] : image
        var ocrRes = await api("/api/rental", {
          method: "POST",
          body: JSON.stringify({ table: "_ocr", action: "read", data: { image: base64Data, meter_type: "电表" } })
        })
        if (ocrRes && ocrRes.numbers && ocrRes.numbers.length > 0) {
          ocrResult = "\n[OCR识别到电表读数: " + ocrRes.numbers.join(", ") + "]"
        } else {
          ocrResult = "\n[OCR未识别到读数: " + (ocrRes?.error || "未知错误") + "]"
        }
      }

      // Send to chat AI with OCR result
      var chatPrompt = input + ocrResult
      var res = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({ table: "_ai", action: "chat", data: { prompt: chatPrompt, history: this.state.messages.slice(-10) } })
      })
      var reply = (res && res.reply) ? res.reply : "抱歉，AI 服务暂时不可用"
      msgs = [...msgs, { role: "assistant" as const, content: reply }]
      this.setState({ messages: msgs, loading: false })
      this.scrollBottom()
      var title = input.substring(0, 30) || "图片识别"
      var saveRes = await rental("_ai", "save_chat", { id: this.state.convId, title, messages: msgs })
      if (saveRes && saveRes.id) {
        this.setState({ convId: saveRes.id })
        this.loadHistory()
      }
    } catch {
      msgs = [...msgs, { role: "assistant" as const, content: "抱歉，暂时无法连接 AI 服务" }]
      this.setState({ messages: msgs, loading: false })
      this.scrollBottom()
    }
  }
  scrollBottom = () => {
    setTimeout(() => {
      if (this.bodyRef.current) this.bodyRef.current.scrollTop = this.bodyRef.current.scrollHeight
    }, 50)
  }

  render() {
    var s = this.state
    var hasHistory = s.historyChats.length > 0
    var todayLabel = new Date().toLocaleDateString("zh-CN", { month: "short", day: "numeric" })

    return (
      <>
        <button id="ai-float-btn" onClick={this.toggle} title="AI 助手">
          <span style={{fontSize:24}}><img src="/robot-avatar.jpg" className="ai-bot-avatar" /></span>
        </button>

        {s.open && (
          <div className="ai-overlay" onClick={this.toggle} />
        )}

        <div className={"ai-chat-window" + (s.open ? " open" : "")}>
          {/* Sidebar */}
          <div className={"ai-sidebar" + (s.sidebarCollapsed ? " collapsed" : "")} ref={this.sidebarRef}>
            <div className="ai-sidebar-header">
              <span className="ai-sidebar-title">对话记录</span>
              <button className="ai-sidebar-collapse" onClick={() => this.setState({ sidebarCollapsed: !s.sidebarCollapsed })} title="收起侧栏">
                {s.sidebarCollapsed ? "☰" : "◀"}
              </button>
            </div>
            <div className="ai-sidebar-body">
              <button className="ai-new-chat-btn" onClick={this.newChat}>
                ＋ 新对话
              </button>
              {!hasHistory && (
                <div className="ai-sidebar-empty">暂无对话记录</div>
              )}
              {hasHistory && s.historyChats.map((c: any) => {
                var title = c.title || "对话 " + c.id
                var isActive = c.id === s.convId
                return (
                  <div key={c.id}
                    className={"ai-history-item" + (isActive ? " active" : "")}
                    onClick={() => this.restoreChat(c.id)}
                  >
                    <span className="ai-history-title">{title.substring(0, 30)}</span>
                    <button className="ai-history-del"
                      onClick={(e: React.MouseEvent) => { e.stopPropagation(); this.deleteChat(c.id) }}
                      title="删除"
                    >🗑</button>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Main Chat Area */}
          <div className="ai-chat-main">
            <div className="ai-chat-topbar">
              <button className="ai-toggle-sidebar" onClick={() => this.setState({ sidebarCollapsed: !s.sidebarCollapsed })}
                title={s.sidebarCollapsed ? "展开侧栏" : "收起侧栏"}>
                ☰
              </button>
              <span className="ai-chat-topbar-title">
                {s.convId ? "对话 " + s.convId : "新对话"}
              </span>
              <button className="ai-chat-close" onClick={this.toggle} title="关闭">✕</button>
            </div>
            <div className="ai-chat-body-v2" ref={this.bodyRef}>
              {s.messages.length === 0 && (
                  <div className="ai-welcome">
                  <div className="ai-welcome-icon"><img src="/robot-avatar.jpg" className="ai-bot-avatar" /></div>
                  <h2>你好，我是租房小管家</h2>
                  <p>可以帮你查询租客信息、分析缴费情况、解答租房相关问题</p>
                  <p className="ai-welcome-hint">在下方输入你的问题开始对话</p>
                  <div className="ai-quick-prompts">
                    {QUICK_PROMPTS.map(q => (
                      <button key={q.label} onClick={() => this.sendQuick(q.prompt)} disabled={s.loading}>
                        {q.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {s.messages.map((m, i) => {
                if (m.role === "user") {
                  return (
                    <div key={i} className="ai-msg-v2 user">
                      <div className="ai-msg-avatar">👤</div>
                      <div className="ai-msg-bubble user-bubble">{m.content}</div>
                    </div>
                  )
                }
                return (
                  <div key={i} className="ai-msg-v2 bot">
                    <div className="ai-msg-avatar"><img src="/robot-avatar.jpg" className="ai-bot-avatar" /></div>
                    <div className="ai-msg-bubble bot-bubble"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}
                    />
                  </div>
                )
              })}
              {s.loading && (
                <div className="ai-msg-v2 bot">
                  <div className="ai-msg-avatar"><img src="/robot-avatar.jpg" className="ai-bot-avatar" /></div>
                  <div className="ai-msg-bubble bot-bubble ai-loading">
                    <span className="ai-dot-typing" />
                  </div>
                </div>
              )}
            </div>
            <div className="ai-chat-toolbar">
              <button className="ai-tool-btn" onClick={() => this.fileRef.current?.click()} title="上传图片">＋</button>
              <span className="ai-tool-hint">上传电表/水表图片自动识别</span>
            </div>
            <div className="ai-chat-footer-v2">
              {s.imagePreview && (
                <div className="ai-image-preview">
                  <img src={s.imagePreview} alt="预览" />
                  <button className="ai-remove-img" onClick={this.removeImage} title="移除图片">✕</button>
                </div>
              )}
              <div className="ai-input-wrap">
                <input type="file" ref={this.fileRef} accept="image/*" style={{display:"none"}}
                  onChange={this.handleImageUpload} />
                
                <input
                  ref={this.inputRef}
                  placeholder={s.uploadedImage ? "描述这张图片（如：7月302房电表）..." : "输入你的问题，按 Enter 发送..."}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); (s.uploadedImage ? this.sendWithImage : this.send)() } }}
                  disabled={s.loading}
                />
                <button onClick={s.uploadedImage ? this.sendWithImage : this.send}
                  disabled={s.loading} className="ai-send-btn">
                  {s.loading ? "..." : "发送"}
                </button>
              </div>
              <div className="ai-footer-hint">支持上传电表/水表图片自动识别读数 · 按 Enter 发送</div>
            </div>          </div>
        </div>
      </>
    )
  }
}
