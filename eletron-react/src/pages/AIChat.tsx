import React from "react";
import { CloseOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, InboxOutlined, LoadingOutlined, MenuFoldOutlined, MenuUnfoldOutlined, PaperClipOutlined, RedoOutlined, RollbackOutlined, SearchOutlined } from "@ant-design/icons";
import html2canvas from "html2canvas";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { showToast } from "../components/ui";
import { rental, api } from "../api";

interface BillReceiptItem {
  name: string
  current?: number | string | null
  last?: number | string | null
  usage?: number | string | null
  unit_price?: number | string | null
  amount: number
}

interface BillReceiptImage {
  image_type: "bill_receipt"
  source: string
  bill_id?: number | null
  file_name?: string
  receipt: {
    title: string
    no: string
    month: string
    room_number: string
    tenant_name: string
    collector: string
    issue_date: string
    items: BillReceiptItem[]
    total_amount: number
    water_photo?: string
    electric_photo?: string
  }
}

interface AIPendingAction {
  id: string
  type: string
  label: string
  tool: string
  args: any
  preview?: any
}

interface AIImageAttachment {
  id: string
  dataUrl: string
  fileName: string
  meterType: "水表" | "电表"
  status: "reading" | "done" | "error"
  ocrNumber: number | null
  error?: string
}

interface AIMessage {
  role: "user" | "assistant"
  content: string
  billImages?: BillReceiptImage[]
}

interface AIChatState {
  open: boolean
  messages: AIMessage[]
  loading: boolean
  convId: number
  historyChats: any[]
  historySearch: string
  historyArchived: boolean
  historyRemovingIds: number[]
  deleteConfirmId: number
  sidebarCollapsed: boolean
  attachments: AIImageAttachment[]
  hoverPreviewImage: string
  activePreviewImage: string
  pendingActions: AIPendingAction[]
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
    historySearch: "",
    historyArchived: false,
    historyRemovingIds: [],
    deleteConfirmId: 0,
    sidebarCollapsed: false,
    attachments: [],
    hoverPreviewImage: "",
    activePreviewImage: "",
    pendingActions: [],
  }
  private bodyRef = React.createRef<HTMLDivElement>()
  private inputRef = React.createRef<HTMLInputElement>()
  private fileRef = React.createRef<HTMLInputElement>()
  private sidebarRef = React.createRef<HTMLDivElement>()

  formatMoney = (value: any) => {
    var num = Number(value || 0)
    return "¥" + num.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  formatCell = (value: any) => {
    if (value === null || value === undefined || value === "") return ""
    return String(value)
  }

  waitForImages = async (el: HTMLElement) => {
    const images = Array.from(el.querySelectorAll("img"))
    await Promise.all(images.map(img => {
      if (img.complete && img.naturalWidth > 0) return Promise.resolve()
      return new Promise<void>(resolve => {
        img.onload = () => resolve()
        img.onerror = () => resolve()
        setTimeout(() => resolve(), 1500)
      })
    }))
  }

  billImageToCanvas = async (targetId: string): Promise<HTMLCanvasElement | null> => {
    const el = document.getElementById(targetId)
    if (!el) return null
    try {
      await this.waitForImages(el)
      return await html2canvas(el, {
        backgroundColor: "#FFFEF9",
        scale: 2,
        useCORS: true,
        width: el.scrollWidth,
        height: el.scrollHeight,
      })
    } catch {
      return null
    }
  }

  copyBillImage = async (targetId: string) => {
    var canvas = await this.billImageToCanvas(targetId)
    if (!canvas) { showToast("复制失败，请手动截图"); return }
    canvas.toBlob(async (blob: Blob | null) => {
      if (!blob) { showToast("复制失败"); return }
      if (!navigator.clipboard || typeof ClipboardItem === "undefined") {
        showToast("当前浏览器不支持复制图片")
        return
      }
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })])
      showToast("已复制账单图片")
    }, "image/png")
  }

  saveBillImage = async (targetId: string, fileName?: string) => {
    var canvas = await this.billImageToCanvas(targetId)
    if (!canvas) { showToast("保存失败"); return }
    var a = document.createElement("a")
    a.href = canvas.toDataURL("image/png")
    a.download = fileName || "bill_receipt.png"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    showToast("已保存账单图片")
  }

  renderBillImage = (image: BillReceiptImage, key: string) => {
    var receipt = image.receipt
    var targetId = "ai-bill-receipt-" + key
    var items = receipt.items || []
    return (
      <div className="ai-bill-image-card" key={key}>
        <div className="ai-bill-image-toolbar">
          <div className="ai-bill-image-heading">
            <span>账单图片</span>
            {image.source === "draft" && <em>草稿未保存</em>}
          </div>
          <div className="ai-bill-image-tools">
            <button type="button" onClick={() => this.copyBillImage(targetId)} title="复制账单图片" aria-label="复制账单图片">
              <CopyOutlined />
            </button>
            <button type="button" onClick={() => this.saveBillImage(targetId, image.file_name)} title="保存账单图片" aria-label="保存账单图片">
              <DownloadOutlined />
            </button>
          </div>
        </div>
        <div id={targetId} className="ai-bill-receipt-capture">
          <div className="ai-bill-title">{receipt.title || "房租、水、电费（专用）收据"}</div>
          <div className="ai-bill-no">No.{receipt.no}</div>
          <div className="ai-bill-room">房间：<b>{receipt.room_number}</b></div>
          <table className="ai-bill-table">
            <thead>
              <tr>
                <th>项目</th>
                <th>本月读数</th>
                <th>上月读数</th>
                <th>实用量</th>
                <th>单价</th>
                <th>金额</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr key={idx}>
                  <td>{item.name}</td>
                  <td>{this.formatCell(item.current)}</td>
                  <td>{this.formatCell(item.last)}</td>
                  <td>{this.formatCell(item.usage)}</td>
                  <td>{item.unit_price === null || item.unit_price === undefined ? "" : Number(item.unit_price).toFixed(2)}</td>
                  <td><b>{this.formatMoney(item.amount)}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="ai-bill-total">合计：<span>{this.formatMoney(receipt.total_amount)}</span></div>
          <div className="ai-bill-meta">
            <div>交款人：{receipt.tenant_name}</div>
            <div>收款人：{receipt.collector}</div>
            <div>发单日期：{receipt.issue_date}</div>
          </div>
          {(receipt.water_photo || receipt.electric_photo) && (
            <div className="ai-bill-photos">
              {receipt.water_photo && <img src={receipt.water_photo} alt="水表照片" />}
              {receipt.electric_photo && <img src={receipt.electric_photo} alt="电表照片" />}
            </div>
          )}
        </div>
      </div>
    )
  }

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
    this.setState({ messages: [], convId: 0, pendingActions: [] })
    setTimeout(() => this.inputRef.current?.focus(), 50)
  }

  loadHistory = async () => {
    try {
      var chats = await rental("_ai", "list_chats", {
        keyword: this.state.historySearch,
        archived: this.state.historyArchived,
      }) || []
      this.setState({ historyChats: chats })
    } catch { /* ignore */ }
  }

  restoreChat = async (id: number) => {
    try {
      var chats = await rental("_ai", "list_chats", {
        keyword: this.state.historySearch,
        archived: this.state.historyArchived,
      }) || []
      var chat = chats.find(function(c: any) { return c.id === id })
      if (!chat) return
      this.setState({ messages: chat.messages || [], convId: id, sidebarCollapsed: false })
      this.scrollBottom()
      setTimeout(() => this.inputRef.current?.focus(), 50)
    } catch { /* ignore */ }
  }

  runHistoryRemoval = (id: number, action: () => Promise<void>) => {
    this.setState(s => ({ historyRemovingIds: Array.from(new Set([...s.historyRemovingIds, id])) }))
    setTimeout(async () => {
      await action()
      this.setState(s => ({ historyRemovingIds: s.historyRemovingIds.filter(x => x !== id) }))
      this.loadHistory()
    }, 180)
  }

  askDeleteChat = (id: number) => {
    this.setState({ deleteConfirmId: id })
  }

  confirmDeleteChat = () => {
    var id = this.state.deleteConfirmId
    if (!id) return
    this.setState({ deleteConfirmId: 0 })
    this.runHistoryRemoval(id, async () => {
      await rental("_ai", "delete_chat", { id })
      if (this.state.convId === id) {
        this.setState({ messages: [], convId: 0, pendingActions: [] })
      }
      showToast("已删除")
    })
  }

  archiveChat = async (id: number) => {
    this.runHistoryRemoval(id, async () => {
      await rental("_ai", "archive_chat", { id })
      if (this.state.convId === id) {
        this.setState({ messages: [], convId: 0, pendingActions: [] })
      }
      showToast("已归档")
    })
  }

  restoreArchivedChat = async (id: number) => {
    this.runHistoryRemoval(id, async () => {
      await rental("_ai", "restore_chat", { id })
      showToast("已恢复")
    })
  }

  setHistorySearch = (keyword: string) => {
    this.setState({ historySearch: keyword }, () => this.loadHistory())
  }

  setHistoryArchived = (archived: boolean) => {
    this.setState({ historyArchived: archived }, () => this.loadHistory())
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
        body: JSON.stringify({ table: "_ai", action: "chat", data: { prompt: input, history: this.state.messages.slice(-10), pending_actions: this.state.pendingActions } })
      })
      var reply = (res && res.reply) ? res.reply : "抱歉，AI 服务暂时不可用"
      msgs = [...msgs, { role: "assistant" as const, content: reply, billImages: res?.bill_images || [] }]
      this.setState({ messages: msgs, loading: false, pendingActions: res?.pending_actions || [] })
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


  inferMeterType = () => {
    var input = this.inputRef.current?.value || ""
    return /水表|水费|用水|水读数/.test(input) ? "水表" as const : "电表" as const
  }

  inferMeterTypeForFile = (file: File, index: number, total: number) => {
    var input = this.inputRef.current?.value || ""
    var name = file.name || ""
    if (/水表|水费|用水|水读数|水/.test(name)) return "水表" as const
    if (/电表|电费|用电|电读数|电/.test(name)) return "电表" as const
    var hasWater = /水表|水费|用水|水读数/.test(input)
    var hasElectric = /电表|电费|用电|电读数/.test(input)
    if (hasWater && !hasElectric) return "水表" as const
    if (hasElectric && !hasWater) return "电表" as const
    if (total >= 2) return index % 2 === 0 ? "水表" as const : "电表" as const
    return this.inferMeterType()
  }

  readFileAsDataUrl = (file: File) => {
    return new Promise<string>(resolve => {
      var reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.readAsDataURL(file)
    })
  }

  recognizeAttachment = async (id: string, dataUrl: string, meterType: "水表" | "电表") => {
    this.setState(s => ({
      attachments: s.attachments.map(a => a.id === id ? { ...a, meterType, status: "reading", error: undefined } : a)
    }))
    try {
      var base64Data = dataUrl.includes("base64,") ? dataUrl.split("base64,")[1] : dataUrl
      var ocrRes = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({ table: "_ocr", action: "read", data: { image: base64Data, meter_type: meterType } })
      })
      var num = ocrRes?.numbers?.length ? Number(ocrRes.numbers[0]) : null
      this.setState(s => ({
        attachments: s.attachments.map(a => a.id === id
          ? { ...a, status: num !== null ? "done" : "error", ocrNumber: num, error: num === null ? (ocrRes?.error || "未识别") : undefined }
          : a)
      }))
    } catch {
      this.setState(s => ({
        attachments: s.attachments.map(a => a.id === id ? { ...a, status: "error", ocrNumber: null, error: "识别失败" } : a)
      }))
    }
  }

  handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    var files = Array.from(e.target.files || [])
    if (!files.length) return
    var newItems: AIImageAttachment[] = []
    for (var i = 0; i < files.length; i++) {
      var file = files[i]
      var dataUrl = await this.readFileAsDataUrl(file)
      var meterType = this.inferMeterTypeForFile(file, i, files.length)
      newItems.push({
        id: Date.now() + "_" + Math.random().toString(16).slice(2),
        dataUrl,
        fileName: file.name,
        meterType,
        status: "reading",
        ocrNumber: null,
      })
    }
    this.setState(s => ({ attachments: [...s.attachments, ...newItems] }))
    newItems.forEach(item => this.recognizeAttachment(item.id, item.dataUrl, item.meterType))
    if (this.fileRef.current) this.fileRef.current.value = ""
  }

  removeAttachment = (id: string) => {
    this.setState(s => {
      var removed = s.attachments.find(a => a.id === id)
      var removedUrl = removed?.dataUrl || ""
      return {
        attachments: s.attachments.filter(a => a.id !== id),
        hoverPreviewImage: s.hoverPreviewImage === removedUrl ? "" : s.hoverPreviewImage,
        activePreviewImage: s.activePreviewImage === removedUrl ? "" : s.activePreviewImage,
      }
    })
  }

  setAttachmentMeterType = (id: string, meterType: "水表" | "电表") => {
    var item = this.state.attachments.find(a => a.id === id)
    if (!item) return
    this.recognizeAttachment(id, item.dataUrl, meterType)
  }

  updateAttachmentReading = (id: string, value: string) => {
    var parsed = value.trim() === "" ? null : Number(value)
    this.setState(s => ({
      attachments: s.attachments.map(a => a.id === id
        ? { ...a, ocrNumber: Number.isFinite(parsed as number) ? parsed : null, status: value.trim() === "" ? "error" : "done", error: value.trim() === "" ? "请填写读数" : undefined }
        : a)
    }))
  }

  retryAttachmentOCR = (id: string) => {
    var item = this.state.attachments.find(a => a.id === id)
    if (!item) return
    this.recognizeAttachment(id, item.dataUrl, item.meterType)
  }

  sendWithImages = async () => {
    var input = (this.inputRef.current?.value || "").trim()
    var attachments = this.state.attachments
    if (!input && attachments.length === 0) return
    if (attachments.some(a => a.status === "reading")) {
      showToast("图片还在识别中，请稍等")
      return
    }
    
    if (this.inputRef.current) this.inputRef.current.value = ""
    
    // Show user message (possibly with image context)
    var userMsg = input || "请识别这几张水电表图片"
    if (attachments.length) userMsg += "（已上传" + attachments.length + "张图片）"
    var msgs = [...this.state.messages, { role: "user" as const, content: userMsg }]
    this.setState({ messages: msgs, loading: true, attachments: [] })
    this.scrollBottom()

    try {
      // Send to chat AI with OCR result
      var ocrResult = attachments.map((item, index) => {
        if (item.ocrNumber !== null) return "\n[图片" + (index + 1) + " OCR识别到" + item.meterType + "读数: " + item.ocrNumber + "]"
        return "\n[图片" + (index + 1) + " OCR未识别到读数: " + (item.error || "未知错误") + "]"
      }).join("")
      var chatPrompt = input + ocrResult
      var res = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({
          table: "_ai",
          action: "chat",
          data: {
            prompt: chatPrompt,
            history: this.state.messages.slice(-10),
            pending_actions: this.state.pendingActions,
            uploaded_images: attachments.map((item, index) => ({
              image_index: index,
              image: item.dataUrl,
              file_name: item.fileName,
              ocr_number: item.ocrNumber,
              ocr_meter_type: item.meterType,
            })),
          }
        })
      })
      var reply = (res && res.reply) ? res.reply : "抱歉，AI 服务暂时不可用"
      msgs = [...msgs, { role: "assistant" as const, content: reply, billImages: res?.bill_images || [] }]
      this.setState({ messages: msgs, loading: false, pendingActions: res?.pending_actions || [] })
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
                {s.sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              </button>
            </div>
            <div className="ai-sidebar-body">
              <button className="ai-new-chat-btn" onClick={this.newChat}>
                ＋ 新对话
              </button>
              <div className="ai-history-search-box">
                <SearchOutlined />
                <input
                  value={s.historySearch}
                  onChange={e => this.setHistorySearch(e.target.value)}
                  placeholder={s.historyArchived ? "搜索归档对话" : "搜索对话记录"}
                />
              </div>
              <div className="ai-history-tabs">
                <button className={!s.historyArchived ? "active" : ""} onClick={() => this.setHistoryArchived(false)}>对话</button>
                <button className={s.historyArchived ? "active" : ""} onClick={() => this.setHistoryArchived(true)}>归档</button>
              </div>
              {!hasHistory && (
                <div className="ai-sidebar-empty">{s.historySearch ? "没有匹配的对话" : (s.historyArchived ? "暂无归档对话" : "暂无对话记录")}</div>
              )}
              {hasHistory && s.historyChats.map((c: any) => {
                var title = c.title || "对话 " + c.id
                var isActive = c.id === s.convId
                var isRemoving = s.historyRemovingIds.includes(c.id)
                return (
                  <div key={c.id}
                    className={"ai-history-item" + (isActive ? " active" : "") + (isRemoving ? " removing" : "")}
                    onClick={() => this.restoreChat(c.id)}
                  >
                    <span className="ai-history-title">{title.substring(0, 30)}</span>
                    <div className="ai-history-actions">
                      <button
                        onClick={(e: React.MouseEvent) => { e.stopPropagation(); s.historyArchived ? this.restoreArchivedChat(c.id) : this.archiveChat(c.id) }}
                        title={s.historyArchived ? "恢复对话" : "归档对话"}
                      >
                        {s.historyArchived ? <RollbackOutlined /> : <InboxOutlined />}
                      </button>
                      <button
                        className="danger"
                        onClick={(e: React.MouseEvent) => { e.stopPropagation(); this.askDeleteChat(c.id) }}
                        title="删除"
                      >
                        <DeleteOutlined />
                      </button>
                    </div>
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
                {s.sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
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
                    <div className="ai-msg-bubble bot-bubble">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {m.content}
                      </ReactMarkdown>
                      {m.billImages && m.billImages.map((image, j) => this.renderBillImage(image, i + "-" + j))}
                    </div>
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
            <div className="ai-chat-footer-v2">
              {s.attachments.length > 0 && (
                <div className="ai-attachment-strip">
                  {s.attachments.map(item => (
                    <div className="ai-attachment-card" key={item.id}
                      onMouseEnter={() => this.setState({ hoverPreviewImage: item.dataUrl })}
                      onMouseLeave={() => this.setState({ hoverPreviewImage: "" })}>
                      <img src={item.dataUrl} alt={item.fileName} onClick={() => this.setState({ activePreviewImage: item.dataUrl })} />
                      <button className="ai-attachment-remove" onClick={(e: React.MouseEvent) => { e.stopPropagation(); this.removeAttachment(item.id) }} title="移除图片" type="button">
                        <CloseOutlined />
                      </button>
                      <div className="ai-attachment-type">
                        <button type="button" className={item.meterType === "水表" ? "active" : ""} onClick={() => this.setAttachmentMeterType(item.id, "水表")}>水</button>
                        <button type="button" className={item.meterType === "电表" ? "active" : ""} onClick={() => this.setAttachmentMeterType(item.id, "电表")}>电</button>
                      </div>
                      <div className={"ai-attachment-status " + item.status}>
                        {item.status === "reading" && <><LoadingOutlined /> 识别中</>}
                        {item.status === "done" && (
                          <input
                            type="number"
                            value={item.ocrNumber ?? ""}
                            onChange={e => this.updateAttachmentReading(item.id, e.target.value)}
                            title="可手动修改识别读数"
                          />
                        )}
                        {item.status === "error" && (
                          <div className="ai-attachment-error-row">
                            <input
                              type="number"
                              value={item.ocrNumber ?? ""}
                              placeholder="读数"
                              onChange={e => this.updateAttachmentReading(item.id, e.target.value)}
                              title={item.error || "可手动输入读数"}
                            />
                            <button type="button" onClick={() => this.retryAttachmentOCR(item.id)} title={item.error || "重新识别"}>
                              <RedoOutlined />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {s.hoverPreviewImage && (
                <div className="ai-image-hover-preview">
                  <img src={s.hoverPreviewImage} alt="图片预览" />
                </div>
              )}
              <div className="ai-input-wrap">
                <button className="ai-attach-btn" onClick={() => this.fileRef.current?.click()} title="上传水电表图片" type="button">
                  <PaperClipOutlined />
                </button>
                <input type="file" ref={this.fileRef} accept="image/*" multiple style={{display:"none"}}
                  onChange={this.handleImageUpload} />
                
                <input
                  ref={this.inputRef}
                  placeholder={s.attachments.length ? "描述图片（如：7月302房水表和电表，准备录入）..." : "输入你的问题，按 Enter 发送..."}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); (s.attachments.length ? this.sendWithImages : this.send)() } }}
                  disabled={s.loading}
                />
                <button onClick={s.attachments.length ? this.sendWithImages : this.send}
                  disabled={s.loading} className="ai-send-btn">
                  {s.loading ? "..." : "发送"}
                </button>
              </div>
              <div className="ai-footer-hint">支持上传电表/水表图片自动识别读数 · 按 Enter 发送</div>
            </div>          </div>
        </div>
        {s.activePreviewImage && (
          <div className="ai-image-lightbox" onClick={() => this.setState({ activePreviewImage: "" })}>
            <button className="ai-image-lightbox-close" type="button" title="关闭" onClick={() => this.setState({ activePreviewImage: "" })}>
              <CloseOutlined />
            </button>
            <img src={s.activePreviewImage} alt="大图预览" onClick={(e: React.MouseEvent) => e.stopPropagation()} />
          </div>
        )}
        {s.deleteConfirmId > 0 && (
          <div className="ai-confirm-overlay" onClick={() => this.setState({ deleteConfirmId: 0 })}>
            <div className="ai-confirm-dialog" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
              <div className="ai-confirm-title">删除这条对话？</div>
              <div className="ai-confirm-text">删除后无法恢复。只是暂时不想看到的话，可以选择归档。</div>
              <div className="ai-confirm-actions">
                <button type="button" onClick={() => this.setState({ deleteConfirmId: 0 })}>取消</button>
                <button type="button" className="danger" onClick={this.confirmDeleteChat}>删除</button>
              </div>
            </div>
          </div>
        )}
      </>
    )
  }
}
