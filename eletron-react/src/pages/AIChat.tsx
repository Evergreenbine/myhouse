import React from "react";
import { CheckOutlined, CloseOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, InboxOutlined, LoadingOutlined, MenuFoldOutlined, MenuUnfoldOutlined, PaperClipOutlined, RedoOutlined, RightOutlined, RollbackOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import html2canvas from "html2canvas";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DayPicker, Select, showToast } from "../components/ui";
import { rental, api } from "../api";
import { formatChineseMoney } from "../utils/money";

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
  contract_id?: number | null
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
  status?: "pending" | "confirmed" | "cancelled" | "failed"
  statusMessage?: string
}

interface AISuggestedAction {
  id?: string
  label: string
  prompt: string
  description?: string
}

interface AIFormField {
  name: string
  label: string
  type?: "text" | "number" | "date"
  required?: boolean
  placeholder?: string
}

interface AIFormAction {
  id?: string
  type: string
  title: string
  description?: string
  submit_label?: string
  prompt_template: string
  fields: AIFormField[]
  values?: Record<string, any>
  missing?: string[]
}

interface AISessionContext {
  [key: string]: any
}

interface AIImageAttachment {
  id: string
  dataUrl: string
  fileName: string
  meterType: string
  status: "reading" | "done" | "error"
  ocrNumber: number | null
  meterNumber?: string
  buildingId?: number | null
  buildingName?: string
  roomId?: number | null
  roomNumber?: string
  tenantId?: number | null
  tenantName?: string
  confidence?: Record<string, number>
  warnings?: string[]
  error?: string
}

interface AIMeterBuilding {
  id: number
  name: string
}

interface AIMeterRoom {
  id: number
  room_number: string
  building_id: number
  tenant_id?: number | null
  tenant_name?: string
}

interface AIFormTenant {
  id: number
  name: string
  building_id?: number | null
  room_id?: string | number | null
}

interface AIMessageImage {
  id: string
  dataUrl: string
  fileName: string
  meterType?: string
  ocrNumber?: number | null
  buildingId?: number | null
  buildingName?: string
  roomId?: number | null
  roomNumber?: string
  tenantId?: number | null
  tenantName?: string
  meterNumber?: string
}

interface AIMessage {
  role: "user" | "assistant"
  content: string
  billImages?: BillReceiptImage[]
  images?: AIMessageImage[]
  pendingActions?: AIPendingAction[]
  suggestedActions?: AISuggestedAction[]
  formActions?: AIFormAction[]
  sessionContext?: AISessionContext
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
  attachmentPanelOpen: boolean
  attachmentDragActive: boolean
  hoverPreviewImage: string
  activePreviewImage: string
  pendingActions: AIPendingAction[]
  pendingActionLoadingId: string
  formValues: Record<string, Record<string, string>>
  sessionContext: AISessionContext
  meterBuildings: AIMeterBuilding[]
  meterRooms: Record<number, AIMeterRoom[]>
  formTenants: Record<number, AIFormTenant[]>
}

const QUICK_PROMPTS = [
  { label: "本月待收", prompt: "本月有哪些房间待收款？请按楼栋、房间、租客、待收金额列出来。" },
  { label: "账单汇总", prompt: "帮我汇总本月账单：应收、已收、待收，以及各状态户数。" },
  { label: "录入进度", prompt: "本月哪些房间还未录入或正在录入中？" },
  { label: "收款异常", prompt: "本月有没有部分收款、待发送、待收款的账单？请分别列出来。" },
]

const AI_GUIDED_HELP_REPLY = "我还不能确定你遇到的具体问题。请告诉我你正在做什么（查询、录入读数、生成账单或收款），涉及哪个楼栋、房间和月份，以及现在卡在哪一步或页面显示了什么。我会根据这些信息告诉你下一步怎么处理。"

function safeAssistantReply(value: any, fallback = AI_GUIDED_HELP_REPLY) {
  var text = String(value || "").trim()
  var technicalMarkers = ["连接失败", "API错误", "API 错误", "请求失败", "服务暂时不可用", "timeout", "traceback", "exception", "工具不在白名单", "🐱"]
  if (!text || technicalMarkers.some(marker => text.toLowerCase().includes(marker.toLowerCase()))) return fallback
  return text
}

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
    attachmentPanelOpen: false,
    attachmentDragActive: false,
    hoverPreviewImage: "",
    activePreviewImage: "",
    pendingActions: [],
    pendingActionLoadingId: "",
    formValues: {},
    sessionContext: {},
    meterBuildings: [],
    meterRooms: {},
    formTenants: {},
  }
  private bodyRef = React.createRef<HTMLDivElement>()
  private inputRef = React.createRef<HTMLInputElement>()
  private fileRef = React.createRef<HTMLInputElement>()
  private sidebarRef = React.createRef<HTMLDivElement>()
  private skipNextHistoryAutoRestore = false
  private deletedChatIds = new Set<number>()
  private meterOptionsLoading = false
  private tenantOptionsLoading = new Set<number>()
  private aiThreadId = "client:" + Date.now().toString(36) + ":" + Math.random().toString(36).slice(2)

  makeThreadId = () => {
    return "client:" + Date.now().toString(36) + ":" + Math.random().toString(36).slice(2)
  }

  syncThreadIdFromContext = (context: AISessionContext) => {
    if (context?.thread_id) this.aiThreadId = String(context.thread_id)
  }

  componentDidMount() {
    this.loadHistory({ restoreLatest: true })
  }

  formatMoney = (value: any) => {
    var num = Number(value || 0)
    return "¥" + num.toFixed(2)
  }

  replaceExistingBillImages = (messages: AIMessage[], images: BillReceiptImage[]) => {
    var savedReplacements = (images || []).filter(image => image.source === "saved_bill" && Number(image.bill_id || 0) > 0)
    var replacementIds = new Set(
      savedReplacements.map(image => Number(image.bill_id || 0)).filter(id => id > 0)
    )
    var replacementContractIds = new Set(
      savedReplacements.map(image => Number(image.contract_id || 0)).filter(id => id > 0)
    )
    var replacementReceiptKeys = new Set(savedReplacements.map(image => {
      var receipt = image.receipt || ({} as BillReceiptImage['receipt'])
      return `${receipt.month || ''}|${receipt.room_number || ''}`
    }).filter(key => key !== '|'))
    if (replacementIds.size === 0 && replacementContractIds.size === 0 && replacementReceiptKeys.size === 0) return messages
    return messages.map(message => ({
      ...message,
      billImages: message.billImages?.filter(image => {
        if (replacementIds.has(Number(image.bill_id || 0))) return false
        if (replacementContractIds.has(Number(image.contract_id || 0))) return false
        var key = `${image.receipt?.month || ''}|${image.receipt?.room_number || ''}`
        return !replacementReceiptKeys.has(key)
      }),
    }))
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
        backgroundColor: "#FFF4E1",
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
    if (window.electronClipboard?.writeImage) {
      var result = await window.electronClipboard.writeImage(canvas.toDataURL("image/png"))
      showToast(result.success ? "已复制账单图片" : (result.message || "复制失败"))
      return
    }
    canvas.toBlob(async (blob: Blob | null) => {
      if (!blob) { showToast("复制失败"); return }
      if (!navigator.clipboard || typeof ClipboardItem === "undefined") {
        showToast("当前浏览器不支持复制图片")
        return
      }
      try {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })])
        showToast("已复制账单图片")
      } catch {
        showToast("浏览器限制复制图片，请使用保存图片")
      }
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

  copyMessageText = async (content: string) => {
    var text = String(content || "").trim()
    if (!text) {
      showToast("没有可复制的文字")
      return
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        var textarea = document.createElement("textarea")
        textarea.value = text
        textarea.style.position = "fixed"
        textarea.style.opacity = "0"
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand("copy")
        document.body.removeChild(textarea)
      }
      showToast("已复制")
    } catch {
      showToast("复制失败")
    }
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
          <div className="ai-bill-title">{receipt.title || "房租及费用收据"}</div>
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
          <div className="receipt-total-cn">大写：{formatChineseMoney(receipt.total_amount)}</div>
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
        this.skipNextHistoryAutoRestore = false
        setTimeout(() => { this.inputRef.current?.focus(); this.loadHistory({ restoreLatest: true }) }, 50)
      }
      return { open: !s.open }
    })
  }

  newChat = () => {
    this.skipNextHistoryAutoRestore = true
    this.aiThreadId = this.makeThreadId()
    this.setState({ messages: [], convId: 0, pendingActions: [], pendingActionLoadingId: "", attachments: [], attachmentPanelOpen: false, attachmentDragActive: false, formValues: {}, sessionContext: {} })
    setTimeout(() => this.inputRef.current?.focus(), 50)
  }

  getRestoredChatState = (chat: any) => {
    var restoredMessages: AIMessage[] = chat.messages || []
    var restoredPending = restoredMessages
      .flatMap(message => message.pendingActions || [])
      .filter(action => !action.status || action.status === "pending" || action.status === "failed")
      .filter((action, index, actions) => actions.findIndex(item => item.id === action.id) === index)
    var restoredContext = [...restoredMessages].reverse().find(message => message.sessionContext)?.sessionContext || {}
    this.aiThreadId = restoredContext.thread_id || ("chat:" + String(chat.id || this.makeThreadId()))
    return {
      messages: restoredMessages,
      convId: Number(chat.id || 0),
      sidebarCollapsed: false,
      pendingActions: restoredPending,
      pendingActionLoadingId: "",
      formValues: {},
      sessionContext: restoredContext,
    }
  }

  loadHistory = async (options?: { restoreLatest?: boolean }) => {
    try {
      var chats = await rental("_ai", "list_chats", {
        keyword: this.state.historySearch,
        archived: this.state.historyArchived,
      }) || []
      var shouldRestoreLatest = Boolean(
        options?.restoreLatest
        && !this.skipNextHistoryAutoRestore
        && !this.state.convId
        && this.state.messages.length === 0
        && !this.state.historyArchived
        && !this.state.historySearch.trim()
        && chats.length > 0
      )
      if (shouldRestoreLatest) {
        this.setState({ historyChats: chats, ...this.getRestoredChatState(chats[0]) }, () => {
          this.scrollBottom()
          setTimeout(() => this.inputRef.current?.focus(), 50)
        })
      } else {
        this.setState({ historyChats: chats })
      }
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
      this.skipNextHistoryAutoRestore = false
      this.setState(this.getRestoredChatState(chat))
      this.scrollBottom()
      setTimeout(() => this.inputRef.current?.focus(), 50)
    } catch { /* ignore */ }
  }

  runHistoryRemoval = (id: number, action: () => Promise<void>) => {
    this.setState(s => ({ historyRemovingIds: Array.from(new Set([...s.historyRemovingIds, id])) }))
    setTimeout(async () => {
      try {
        await action()
        this.setState(s => ({
          historyChats: s.historyChats.filter((chat: any) => chat.id !== id),
          historyRemovingIds: s.historyRemovingIds.filter(x => x !== id),
        }))
        this.loadHistory()
      } catch {
        this.setState(s => ({ historyRemovingIds: s.historyRemovingIds.filter(x => x !== id) }))
        showToast("操作失败，请稍后重试")
      }
    }, 180)
  }

  askDeleteChat = (id: number) => {
    this.setState({ deleteConfirmId: id })
  }

  confirmDeleteChat = () => {
    var id = this.state.deleteConfirmId
    if (!id) return
    this.deletedChatIds.add(id)
    this.setState({ deleteConfirmId: 0 })
    this.runHistoryRemoval(id, async () => {
      try {
        await rental("_ai", "delete_chat", { id })
      } catch (err) {
        this.deletedChatIds.delete(id)
        throw err
      }
      if (this.state.convId === id) {
        this.skipNextHistoryAutoRestore = true
        this.aiThreadId = this.makeThreadId()
        this.setState({ messages: [], convId: 0, pendingActions: [], pendingActionLoadingId: "", attachments: [], attachmentPanelOpen: false, attachmentDragActive: false, loading: false })
      }
      showToast("已删除")
    })
  }

  archiveChat = async (id: number) => {
    this.runHistoryRemoval(id, async () => {
      await rental("_ai", "archive_chat", { id })
      if (this.state.convId === id) {
        this.aiThreadId = this.makeThreadId()
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
    this.sendPrompt(prompt)
  }

  runSuggestedAction = (action: AISuggestedAction) => {
    if (this.state.loading) return
    if (!action.prompt) return
    this.sendPrompt(action.prompt)
  }

  send = async () => {
    var input = this.state.loading ? "" : (this.inputRef.current?.value || "").trim()
    if (!input) return
    if (this.inputRef.current) this.inputRef.current.value = ""
    this.sendPrompt(input)
  }

  sendPrompt = async (input: string) => {
    input = String(input || "").trim()
    if (this.state.loading || !input) return
    var convIdAtStart = this.state.convId
    var msgs = [...this.state.messages, { role: "user" as const, content: input }]
    this.setState({ messages: msgs, loading: true })
    this.scrollBottom()
    try {
      var res = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({ table: "_ai", action: "chat", data: { prompt: input, history: this.state.messages.slice(-10), pending_actions: this.state.pendingActions, session_context: { ...this.state.sessionContext, thread_id: this.aiThreadId }, chat_thread_id: this.aiThreadId, conversation_id: this.state.convId || "" } })
      })
      var reply = safeAssistantReply(res?.response?.content || res?.reply)
      var nextPendingActions = res?.response?.pending_actions || res?.pending_actions || []
      var responseBillImages = res?.response?.bill_images || res?.bill_images || []
      var suggestedActions = res?.response?.suggested_actions || res?.suggested_actions || []
      var formActions = res?.response?.form_actions || res?.form_actions || []
      var sessionContext = res?.response?.session_context || res?.session_context || this.state.sessionContext
      this.syncThreadIdFromContext(sessionContext)
      msgs = [...this.replaceExistingBillImages(msgs, responseBillImages), { role: "assistant" as const, content: reply, billImages: responseBillImages, pendingActions: nextPendingActions, suggestedActions, formActions, sessionContext }]
      if (convIdAtStart > 0 && this.deletedChatIds.has(convIdAtStart)) return
      this.setState({ messages: msgs, loading: false, pendingActions: nextPendingActions, sessionContext })
      this.scrollBottom()
      var title = input.substring(0, 30)
      if (this.state.convId > 0 && this.deletedChatIds.has(this.state.convId)) return
      var saveRes = await rental("_ai", "save_chat", { id: this.state.convId, title, messages: msgs })
      if (saveRes && saveRes.id) {
        this.setState({ convId: saveRes.id })
        this.loadHistory()
      }
    } catch {
      if (convIdAtStart > 0 && this.deletedChatIds.has(convIdAtStart)) return
      msgs = [...msgs, { role: "assistant" as const, content: AI_GUIDED_HELP_REPLY }]
      this.setState({ messages: msgs, loading: false })
      this.scrollBottom()
    }
  }

  persistMessages = async (messages: AIMessage[], title: string) => {
    if (this.state.convId > 0 && this.deletedChatIds.has(this.state.convId)) return
    var saveRes = await rental("_ai", "save_chat", { id: this.state.convId, title, messages })
    if (saveRes && saveRes.id) {
      this.setState({ convId: saveRes.id })
      this.loadHistory()
    }
  }

  runPendingAction = async (action: AIPendingAction, command: "confirm" | "cancel") => {
    if (this.state.loading) return
    var pendingActions = this.state.pendingActions
    if (!pendingActions.some(item => item.id === action.id)) return
    var convIdAtStart = this.state.convId
    this.setState({ loading: true, pendingActionLoadingId: action.id })
    try {
      var res = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({
          table: "_ai",
          action: "chat",
          data: {
            prompt: "",
            history: this.state.messages.slice(-10),
            pending_actions: pendingActions,
            pending_action_command: command,
            pending_action_id: action.id,
            session_context: { ...this.state.sessionContext, thread_id: this.aiThreadId },
            chat_thread_id: this.aiThreadId,
            conversation_id: this.state.convId || "",
          },
        }),
      })
      var reply = safeAssistantReply(res?.response?.content || res?.reply, command === "cancel" ? "已取消这项操作" : AI_GUIDED_HELP_REPLY)
      var remainingActions = res?.response?.pending_actions || res?.pending_actions || []
      var responseBillImages = res?.response?.bill_images || res?.bill_images || []
      var actionResult = res?.response?.action_result || res?.action_result || {}
      var sessionContext = res?.response?.session_context || res?.session_context || this.state.sessionContext
      this.syncThreadIdFromContext(sessionContext)
      var actionRemains = remainingActions.some((item: AIPendingAction) => item.id === action.id)
      var actionSucceeded = typeof actionResult.success === "boolean" ? actionResult.success : !actionRemains
      var actionStatus: AIPendingAction["status"] = actionSucceeded ? (command === "cancel" ? "cancelled" : "confirmed") : "failed"
      if (convIdAtStart > 0 && this.deletedChatIds.has(convIdAtStart)) return
      var firstActionMessageIndex = this.state.messages.findIndex(message => message.pendingActions?.some(item => item.id === action.id))
      var updatedMessages = this.replaceExistingBillImages(this.state.messages, responseBillImages).map((message, messageIndex) => {
        var containsAction = message.pendingActions?.some(item => item.id === action.id)
        if (!containsAction) return message
        if (messageIndex !== firstActionMessageIndex) {
          return { ...message, pendingActions: message.pendingActions?.filter(item => item.id !== action.id) }
        }
        return {
          ...message,
          sessionContext,
          billImages: responseBillImages.length > 0 ? [...(message.billImages || []), ...responseBillImages] : message.billImages,
          pendingActions: message.pendingActions?.map(item => item.id === action.id ? {
            ...item,
            status: actionStatus,
            statusMessage: actionStatus === "failed" ? reply : "",
          } : item),
        }
      }).filter(message => {
        var wasLegacyDuplicate = message.role === "assistant"
          && /^(已确认并完成：|已取消：)/.test(message.content || "")
          && Boolean(action.label && message.content.includes(action.label))
        var stillContainsAction = message.pendingActions?.some(item => item.id === action.id)
        return !wasLegacyDuplicate || stillContainsAction
      })
      var messages = updatedMessages
      this.setState({ messages, loading: false, pendingActionLoadingId: "", pendingActions: remainingActions, sessionContext })
      await this.persistMessages(messages, action.label || "AI 操作")
    } catch {
      if (convIdAtStart > 0 && this.deletedChatIds.has(convIdAtStart)) return
      var fallbackMessages = this.state.messages.map(message => ({
        ...message,
        pendingActions: message.pendingActions?.map(item => item.id === action.id ? {
          ...item,
          status: "failed" as const,
          statusMessage: AI_GUIDED_HELP_REPLY,
        } : item),
      }))
      this.setState({ messages: fallbackMessages, loading: false, pendingActionLoadingId: "" })
      await this.persistMessages(fallbackMessages, action.label || "AI 操作")
    }
  }

  renderPendingAction = (action: AIPendingAction) => {
    var preview = action.preview || {}
    var fields = [
      ["楼栋", preview.building_name || preview.building],
      ["房间", preview.room_number],
      ["租客", preview.tenant_name],
      ["月份", preview.month],
      ["类型", preview.meter_type_label || preview.meter_type],
      ["读数", preview.reading],
      ["上月读数", preview.previous_reading],
      ["用量", preview.usage],
      ["照片", preview.photo_saved ? "已包含" : undefined],
      ["旧账单", preview.existing_total_amount === undefined || preview.existing_total_amount === null ? undefined : this.formatMoney(preview.existing_total_amount)],
      ["旧状态", preview.existing_status],
      ["合计", preview.total_amount === undefined ? undefined : this.formatMoney(preview.total_amount)],
      ["应收", preview.receivable === undefined ? undefined : this.formatMoney(preview.receivable)],
      ["已收", preview.paid_amount === undefined ? undefined : this.formatMoney(preview.paid_amount)],
      ["本次收款", preview.payment_amount === undefined ? undefined : this.formatMoney(preview.payment_amount)],
      ["收款后待收", preview.remaining_amount === undefined ? undefined : this.formatMoney(preview.remaining_amount)],
      ["收款日期", preview.pay_date],
      ["收款方式", preview.pay_method],
    ].filter(item => item[1] !== undefined && item[1] !== null && item[1] !== "")
    var isBill = action.type === "create_bill"
    var isContract = action.type === "update_contract"
    var isCreateContract = action.type === "create_contract"
    var isPayment = action.type === "record_payment"
    var actionStatus = action.status || "pending"
    var actionFinished = actionStatus === "confirmed" || actionStatus === "cancelled"
    var pendingTitle = isBill ? "待确认账单" : isCreateContract ? "待确认新建合同" : isContract ? "待确认合同修改" : isPayment ? "待确认收款" : "待确认读数"
    var finishedTitle = isBill ? "账单操作" : isCreateContract ? "合同新建" : isContract ? "合同修改" : isPayment ? "收款确认" : "读数录入"
    var actionTitle = actionFinished ? finishedTitle : pendingTitle
    var confirmText = isBill ? (preview.overwrite ? "确认覆盖" : "确认保存") : isCreateContract ? "确认新建" : isContract ? "确认修改" : isPayment ? "确认收款" : "确认录入"
    var statusText = actionStatus === "confirmed" ? "已确认" : actionStatus === "cancelled" ? "已取消" : actionStatus === "failed" ? "执行失败" : "需要确认"
    var changeItems = Array.isArray(preview.change_items) ? preview.change_items : []
    var otherFeeDetails = Array.isArray(preview.other_fee_details) ? preview.other_fee_details : []
    return (
      <div className={'ai-pending-action ' + actionStatus} key={action.id}>
        <div className="ai-pending-action-title">
          <span>{actionTitle}</span>
          <em className={'status-' + actionStatus}>{actionStatus === "confirmed" && <CheckOutlined />}{statusText}</em>
        </div>
        <div className="ai-pending-action-label">{action.label}</div>
        {fields.length > 0 && (
          <div className="ai-pending-action-fields">
            {fields.map(item => <span key={String(item[0])}><b>{item[0]}</b>{String(item[1])}</span>)}
          </div>
        )}
        {changeItems.length > 0 && (
          <div className="ai-contract-changes">
            {changeItems.map((item: any) => (
              <div className="ai-contract-change" key={String(item.field || item.label)}>
                <b>{item.label}</b>
                <span>{String(item.before ?? '')}</span>
                <i>→</i>
                <strong>{String(item.after ?? '')}</strong>
              </div>
            ))}
          </div>
        )}
        {otherFeeDetails.length > 0 && (
          <div className="ai-other-fee-preview">
            <div className="ai-other-fee-preview-head"><span>其他费用项目</span><span>费用</span></div>
            {otherFeeDetails.map((item: any, index: number) => (
              <div className="ai-other-fee-preview-row" key={`${item.name || 'fee'}-${index}`}>
                <span>{String(item.name || '')}</span>
                <strong>{this.formatMoney(item.amount)}</strong>
              </div>
            ))}
          </div>
        )}
        {action.statusMessage && <div className="ai-pending-action-error">{action.statusMessage}</div>}
        {!actionFinished && (
          <div className="ai-pending-action-buttons">
            <button type="button" className="ai-pending-confirm" onClick={() => this.runPendingAction(action, "confirm")} disabled={this.state.loading}>
              {this.state.pendingActionLoadingId === action.id ? <LoadingOutlined /> : <CheckOutlined />}{actionStatus === "failed" ? "重新" + confirmText : confirmText}
            </button>
            <button type="button" className="ai-pending-cancel" onClick={() => this.runPendingAction(action, "cancel")} disabled={this.state.loading}>
              <CloseOutlined />取消
            </button>
          </div>
        )}
      </div>
    )
  }

  renderPendingActions = (actions: AIPendingAction[]) => {
    if (!actions.length) return null
    return <div className="ai-pending-action-list">{actions.map(action => this.renderPendingAction(action))}</div>
  }

  renderSuggestedActions = (actions: AISuggestedAction[]) => {
    var validActions = (actions || []).filter(action => action && action.label && action.prompt)
    if (!validActions.length) return null
    return (
      <div className="ai-suggested-actions">
        {validActions.map((action, index) => (
          <button
            type="button"
            key={action.id || action.label + index}
            onClick={() => this.runSuggestedAction(action)}
            disabled={this.state.loading}
          >
            <span className="ai-suggested-action-index">{index + 1}</span>
            <span className="ai-suggested-action-text">
              <strong>{action.label}</strong>
              {action.description && <em>{action.description}</em>}
            </span>
            <RightOutlined />
          </button>
        ))}
      </div>
    )
  }

  getFormKey = (form: AIFormAction, index: number) => {
    var initialValues = JSON.stringify(form.values || {})
    return (form.id || form.type + "_" + index) + "_" + initialValues
  }

  getFormValues = (form: AIFormAction, index: number) => {
    var key = this.getFormKey(form, index)
    var stored = this.state.formValues[key]
    if (stored) return stored
    var values: Record<string, string> = {}
    Object.entries(form.values || {}).forEach(([name, value]) => {
      values[name] = value === undefined || value === null ? "" : String(value)
    })
    ;(form.fields || []).forEach(field => {
      var value = form.values?.[field.name]
      values[field.name] = value === undefined || value === null ? "" : String(value)
    })
    return values
  }

  getFormBuilding = (values: Record<string, string>) => {
    var buildingId = String(values.building_id || "").trim()
    if (buildingId) {
      var byId = this.state.meterBuildings.find(building => String(building.id) === buildingId)
      if (byId) return byId
    }
    var buildingValue = String(values.building_name || "").trim()
    return this.state.meterBuildings.find(building => String(building.name) === buildingValue || String(building.id) === buildingValue)
  }

  tenantMatchesRoom = (tenant: AIFormTenant, roomId: number) => {
    var ids = String(tenant.room_id || "").split(",").map(item => item.trim()).filter(Boolean)
    return ids.includes(String(roomId))
  }

  getTenantForFormRoom = (buildingId: number, roomNumber: string) => {
    var room = (this.state.meterRooms[buildingId] || []).find(item => String(item.room_number) === String(roomNumber))
    if (!room) return undefined
    var roomId = room.id
    return (this.state.formTenants[buildingId] || []).find(tenant => this.tenantMatchesRoom(tenant, roomId))
  }

  updateFormValue = (form: AIFormAction, index: number, name: string, value: string) => {
    var key = this.getFormKey(form, index)
    var current = this.getFormValues(form, index)
    this.setState(s => ({
      formValues: {
        ...s.formValues,
        [key]: { ...current, [name]: value },
      },
    }))
  }

  updateFormBuilding = (form: AIFormAction, index: number, value: string) => {
    var key = this.getFormKey(form, index)
    var current = this.getFormValues(form, index)
    var building = this.state.meterBuildings.find(item => String(item.id) === String(value) || String(item.name) === String(value))
    if (building) this.loadTenantsForBuilding(building.id)
    var previousRoomNumber = current.room_number || ""
    var matchedRoom = building && previousRoomNumber ? (this.state.meterRooms[building.id] || []).find(room => String(room.room_number) === String(previousRoomNumber)) : undefined
    var matchedTenant = building && matchedRoom ? this.getTenantForFormRoom(building.id, matchedRoom.room_number) : undefined
    this.setState(s => ({
      formValues: {
        ...s.formValues,
        [key]: {
          ...current,
          building_id: building ? String(building.id) : "",
          building_name: building?.name || value,
          room_id: matchedRoom ? String(matchedRoom.id) : "",
          room_number: matchedRoom?.room_number || previousRoomNumber,
          tenant_id: matchedTenant ? String(matchedTenant.id) : "",
          tenant_name: matchedTenant?.name || "",
        },
      },
    }))
  }

  updateFormRoom = (form: AIFormAction, index: number, value: string) => {
    var key = this.getFormKey(form, index)
    var current = this.getFormValues(form, index)
    var building = this.getFormBuilding(current)
    var room = building ? (this.state.meterRooms[building.id] || []).find(item => String(item.id) === String(value) || String(item.room_number) === String(value)) : undefined
    var tenant = building && room ? this.getTenantForFormRoom(building.id, room.room_number) : undefined
    this.setState(s => ({
      formValues: {
        ...s.formValues,
        [key]: { ...current, room_id: room ? String(room.id) : "", room_number: room?.room_number || value, tenant_id: tenant ? String(tenant.id) : current.tenant_id || "", tenant_name: tenant?.name || current.tenant_name || "" },
      },
    }))
  }

  updateFormTenant = (form: AIFormAction, index: number, value: string) => {
    var key = this.getFormKey(form, index)
    var current = this.getFormValues(form, index)
    var building = this.getFormBuilding(current)
    var tenant = building ? (this.state.formTenants[building.id] || []).find(item => String(item.id) === String(value) || item.name === value) : undefined
    this.setState(s => ({
      formValues: {
        ...s.formValues,
        [key]: { ...current, tenant_id: tenant ? String(tenant.id) : "", tenant_name: tenant?.name || value },
      },
    }))
  }

  syncFormTenantFromRoom = (form: AIFormAction, index: number, values: Record<string, string>) => {
    if (form.type !== "create_contract" || values.tenant_name || !values.room_number) return
    var building = this.getFormBuilding(values)
    if (!building) return
    var tenant = this.getTenantForFormRoom(building.id, values.room_number)
    if (!tenant?.name) return
    var tenantName = tenant.name
    var key = this.getFormKey(form, index)
    setTimeout(() => {
      this.setState(s => {
        var current = s.formValues[key] || this.getFormValues(form, index)
        if (current.tenant_name) return null
        return { formValues: { ...s.formValues, [key]: { ...current, tenant_name: tenantName } } }
      })
    }, 0)
  }

  runFormAction = (form: AIFormAction, index: number) => {
    if (this.state.loading) return
    var values = this.getFormValues(form, index)
    var missing = (form.fields || []).filter(field => field.required && !String(values[field.name] || "").trim())
    if (missing.length) {
      showToast("请补充" + missing.map(field => field.label).join("、"))
      return
    }
    var prompt = form.prompt_template || ""
    if (form.type === "create_contract") {
      prompt = "请根据以下表单内容新建合同："
        + "楼栋ID " + (values.building_id || "") + "，楼栋名称 " + (values.building_name || "") + "，"
        + "房间ID " + (values.room_id || "") + "，房间号 " + (values.room_number || "") + "，"
        + "租户ID " + (values.tenant_id || "") + "，租户姓名 " + (values.tenant_name || "") + "，"
        + "合同开始日期 " + (values.start_date || "") + "，合同结束日期 " + (values.end_date || "") + "，"
        + "月租 " + (values.monthly_rent || "") + "，水费单价 " + (values.water_unit_price || "") + "，"
        + "电费单价 " + (values.electric_unit_price || "") + "，保证金 " + (values.deposit || "") + "，"
        + "其它费用 " + (values.other_fee_details || "") + "。"
    }
    Object.keys(values).forEach(key => {
      prompt = prompt.split("{" + key + "}").join(values[key] || "")
    })
    if (!prompt.trim()) return
    this.sendPrompt(prompt)
  }

  renderFormActions = (forms: AIFormAction[]) => {
    var validForms = (forms || []).filter(form => form && form.prompt_template && Array.isArray(form.fields))
    if (!validForms.length) return null
    var needsRoomOptions = validForms.some(form => form.type === "create_contract")
    if (needsRoomOptions && this.state.meterBuildings.length === 0) {
      setTimeout(() => this.loadMeterOptions(), 0)
    }
    return (
      <div className="ai-form-action-list">
        {validForms.map((form, index) => {
          var values = this.getFormValues(form, index)
          var missingSet = new Set(form.missing || [])
          var selectedBuilding = this.getFormBuilding(values)
          var selectedBuildingId = selectedBuilding?.id || 0
          var roomOptions = selectedBuilding ? (this.state.meterRooms[selectedBuilding.id] || []) : []
          var tenantOptions = selectedBuilding ? (this.state.formTenants[selectedBuilding.id] || []) : []
          var roomSelectOptions = roomOptions.map(room => ({ value: String(room.id), label: room.room_number }))
          if (!values.room_id && values.room_number && !roomSelectOptions.some(option => option.value === values.room_number)) {
            roomSelectOptions = [{ value: values.room_number, label: values.room_number }, ...roomSelectOptions]
          }
          var tenantSelectOptions = tenantOptions.map(tenant => ({ value: String(tenant.id), label: tenant.name }))
          if (!values.tenant_id && values.tenant_name && !tenantSelectOptions.some(option => option.value === values.tenant_name)) {
            tenantSelectOptions = [{ value: values.tenant_name, label: values.tenant_name }, ...tenantSelectOptions]
          }
          if (selectedBuildingId && !this.state.formTenants[selectedBuildingId]) {
            setTimeout(() => this.loadTenantsForBuilding(selectedBuildingId), 0)
          }
          this.syncFormTenantFromRoom(form, index, values)
          return (
            <div className="ai-form-action" key={this.getFormKey(form, index)}>
              <div className="ai-form-action-head">
                <span>{form.title || "补充信息"}</span>
                {form.description && <em>{form.description}</em>}
              </div>
              <div className="ai-form-action-grid">
                {form.fields.map(field => (
                  <label className={missingSet.has(field.name) ? "missing" : ""} key={field.name}>
                    <span>{field.label}{field.required && <b>*</b>}</span>
                    {form.type === "create_contract" && field.name === "building_name" ? (
                      <Select
                        value={selectedBuilding ? String(selectedBuilding.id) : values.building_id || values.building_name || ""}
                        placeholder={field.placeholder || "选择楼栋"}
                        options={this.state.meterBuildings.map(building => ({ value: String(building.id), label: building.name }))}
                        onChange={value => this.updateFormBuilding(form, index, value)}
                      />
                    ) : form.type === "create_contract" && field.name === "room_number" ? (
                      <Select
                        value={values.room_id || values.room_number || ""}
                        placeholder={selectedBuilding ? (field.placeholder || "选择房间") : "请先选择楼栋"}
                        options={roomSelectOptions}
                        onChange={value => this.updateFormRoom(form, index, value)}
                      />
                    ) : form.type === "create_contract" && field.name === "tenant_name" ? (
                      <Select
                        value={values.tenant_id || values.tenant_name || ""}
                        placeholder={selectedBuilding ? (field.placeholder || "选择租客") : "请先选择楼栋"}
                        options={tenantSelectOptions}
                        onChange={value => this.updateFormTenant(form, index, value)}
                      />
                    ) : field.type === "date" ? (
                      <DayPicker
                        value={values[field.name] || ""}
                        onChange={value => this.updateFormValue(form, index, field.name, value)}
                        ariaLabel={field.label}
                      />
                    ) : (
                      <input
                        type={field.type === "number" ? "number" : "text"}
                        value={values[field.name] || ""}
                        placeholder={field.placeholder || ""}
                        onChange={e => this.updateFormValue(form, index, field.name, e.target.value)}
                        disabled={this.state.loading}
                      />
                    )}
                  </label>
                ))}
              </div>
              <div className="ai-form-action-buttons">
                <button type="button" onClick={() => this.runFormAction(form, index)} disabled={this.state.loading}>
                  <CheckOutlined />{form.submit_label === "生成确认卡" ? "提交表单" : (form.submit_label || "提交表单")}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    )
  }


  inferMeterType = () => {
    var input = this.inputRef.current?.value || ""
    if (/水表|水费|用水|水读数/.test(input)) return "水表"
    if (/电表|电费|用电|电读数/.test(input)) return "电表"
    return "未知"
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

  isImageFile = (file: File) => {
    return file.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp|heic|heif)$/i.test(file.name || "")
  }

  loadMeterOptions = async () => {
    if (this.state.meterBuildings.length > 0 || this.meterOptionsLoading) return
    this.meterOptionsLoading = true
    try {
      var buildings = await rental("buildings", "list") || []
      var roomEntries = await Promise.all((buildings || []).map(async (building: AIMeterBuilding) => {
        var [rooms, contracts, tenants] = await Promise.all([
          rental("rooms", "list", { building_id: building.id }),
          rental("contracts", "list", { active_only: true, building_id: building.id }),
          rental("tenants", "list", { active_only: true, building_id: building.id }),
        ])
        var contractByRoom: Record<number, any> = {}
        ;(contracts || []).forEach((contract: any) => { contractByRoom[Number(contract.room_id)] = contract })
        return [building.id, (rooms || []).map((room: any) => ({
          id: Number(room.id),
          room_number: String(room.room_number || ""),
          building_id: Number(building.id),
          tenant_id: contractByRoom[Number(room.id)]?.tenant_id || null,
          tenant_name: contractByRoom[Number(room.id)]?.tenant_name || "",
        })), tenants || []] as const
      }))
      var rooms: Record<number, AIMeterRoom[]> = {}
      var tenantsByBuilding: Record<number, AIFormTenant[]> = {}
      roomEntries.forEach(entry => {
        rooms[entry[0]] = entry[1]
        tenantsByBuilding[entry[0]] = (entry[2] || []).map((tenant: any) => ({
          id: Number(tenant.id),
          name: String(tenant.name || ""),
          building_id: tenant.building_id ? Number(tenant.building_id) : null,
          room_id: tenant.room_id || "",
        }))
      })
      this.setState({ meterBuildings: buildings || [], meterRooms: rooms, formTenants: tenantsByBuilding })
    } catch {
      this.setState({ meterBuildings: [], meterRooms: {}, formTenants: {} })
    } finally {
      this.meterOptionsLoading = false
    }
  }

  loadTenantsForBuilding = async (buildingId: number) => {
    if (!buildingId || this.state.formTenants[buildingId] || this.tenantOptionsLoading.has(buildingId)) return
    this.tenantOptionsLoading.add(buildingId)
    try {
      var tenants = await rental("tenants", "list", { active_only: true, building_id: buildingId }) || []
      this.setState(s => ({
        formTenants: {
          ...s.formTenants,
          [buildingId]: tenants.map((tenant: any) => ({
            id: Number(tenant.id),
            name: String(tenant.name || ""),
            building_id: tenant.building_id ? Number(tenant.building_id) : null,
            room_id: tenant.room_id || "",
          })),
        },
      }))
    } finally {
      this.tenantOptionsLoading.delete(buildingId)
    }
  }

  normalizeMeterType = (value: any, fallback = "未知") => {
    var text = String(value || "").toLowerCase()
    if (text.includes("水") || text.includes("water")) return "水表"
    if (text.includes("电") || text.includes("electric")) return "电表"
    return fallback
  }

  recognizeAttachment = async (id: string, dataUrl: string, meterType: string) => {
    this.setState(s => ({
      attachments: s.attachments.map(a => a.id === id ? { ...a, meterType, status: "reading", error: undefined } : a)
    }))
    try {
      var base64Data = dataUrl.includes("base64,") ? dataUrl.split("base64,")[1] : dataUrl
      var analysisRes = await api("/api/rental", {
        method: "POST",
        body: JSON.stringify({ table: "_ocr", action: "analyze", data: { image: base64Data, meter_type: meterType } })
      })
      if (analysisRes?.success === false) throw new Error("recognition_unavailable")
      var rawNumber = analysisRes?.reading
      var num = rawNumber === null || rawNumber === undefined || rawNumber === "" ? null : Number(rawNumber)
      if (!Number.isFinite(num as number)) num = null
      var recognizedType = this.normalizeMeterType(analysisRes?.meter_type, meterType)
      var matchedBuilding = this.state.meterBuildings.find(building =>
        Number(building.id) === Number(analysisRes?.building_id)
        || (!!analysisRes?.building_name && String(building.name).includes(String(analysisRes.building_name)))
      )
      var buildingId = analysisRes?.building_id ? Number(analysisRes.building_id) : matchedBuilding?.id || null
      var candidateRooms = buildingId ? (this.state.meterRooms[buildingId] || []) : []
      var matchedRoom = candidateRooms.find(room =>
        Number(room.id) === Number(analysisRes?.room_id)
        || (!!analysisRes?.room_number && String(room.room_number) === String(analysisRes.room_number))
      )
      this.setState(s => ({
        attachments: s.attachments.map(a => a.id === id
          ? {
            ...a,
            status: num !== null ? "done" : "error",
            ocrNumber: num,
            meterType: recognizedType,
            meterNumber: analysisRes?.meter_number || "",
            buildingId,
            buildingName: matchedBuilding?.name || analysisRes?.building_name || "",
            roomId: analysisRes?.room_id ? Number(analysisRes.room_id) : matchedRoom?.id || null,
            roomNumber: matchedRoom?.room_number || analysisRes?.room_number || "",
            tenantId: analysisRes?.tenant_id || matchedRoom?.tenant_id || null,
            tenantName: analysisRes?.tenant_name || matchedRoom?.tenant_name || "",
            confidence: analysisRes?.confidence || {},
            warnings: analysisRes?.warnings || [],
            error: num === null ? (analysisRes?.error || "未识别到有效读数") : undefined,
          }
          : a)
      }))
    } catch {
      this.setState(s => ({
        attachments: s.attachments.map(a => a.id === id ? { ...a, status: "error", ocrNumber: null, error: "没有识别清楚，请手动选择表具类型、楼栋和房间，并填写读数" } : a)
      }))
    }
  }

  handleImageFiles = async (files: File[]) => {
    var imageFiles = files.filter(file => this.isImageFile(file))
    if (!imageFiles.length) {
      showToast("请上传图片文件")
      return
    }
    await this.loadMeterOptions()
    var newItems: AIImageAttachment[] = []
    for (var i = 0; i < imageFiles.length; i++) {
      var file = imageFiles[i]
      var dataUrl = await this.readFileAsDataUrl(file)
      var meterType = this.inferMeterTypeForFile(file, i, imageFiles.length)
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
    if (imageFiles.length !== files.length) showToast("已忽略非图片文件")
    if (this.fileRef.current) this.fileRef.current.value = ""
  }

  handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    await this.handleImageFiles(Array.from(e.target.files || []))
  }

  handleAttachmentDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (!this.state.loading) this.setState({ attachmentDragActive: true })
  }

  handleAttachmentDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (!this.state.loading && !this.state.attachmentDragActive) this.setState({ attachmentDragActive: true })
  }

  handleAttachmentDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    var nextTarget = e.relatedTarget as Node | null
    if (nextTarget && e.currentTarget.contains(nextTarget)) return
    this.setState({ attachmentDragActive: false })
  }

  handleAttachmentDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (this.state.loading) return
    this.setState({ attachmentDragActive: false, attachmentPanelOpen: true })
    await this.handleImageFiles(Array.from(e.dataTransfer.files || []))
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

  setAttachmentBuilding = (id: string, value: string) => {
    var buildingId = value ? Number(value) : null
    var building = this.state.meterBuildings.find(item => Number(item.id) === buildingId)
    this.setState(s => ({
      attachments: s.attachments.map(item => item.id === id ? {
        ...item,
        buildingId,
        buildingName: building?.name || "",
        roomId: null,
        roomNumber: "",
        tenantId: null,
        tenantName: "",
      } : item),
    }))
  }

  setAttachmentRoom = (id: string, value: string) => {
    var roomId = value ? Number(value) : null
    var item = this.state.attachments.find(attachment => attachment.id === id)
    var room = item?.buildingId ? (this.state.meterRooms[item.buildingId] || []).find(candidate => Number(candidate.id) === roomId) : undefined
    this.setState(s => ({
      attachments: s.attachments.map(attachment => attachment.id === id ? {
        ...attachment,
        roomId,
        roomNumber: room?.room_number || "",
        tenantId: room?.tenant_id || null,
        tenantName: room?.tenant_name || "",
      } : attachment),
    }))
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
    var convIdAtStart = this.state.convId
    
    if (this.inputRef.current) this.inputRef.current.value = ""
    
    // Show user message (possibly with image context)
    var userMsg = input || "请识别这几张水电表图片"
    var messageImages = attachments.map(item => ({
      id: item.id,
      dataUrl: item.dataUrl,
      fileName: item.fileName,
      meterType: item.meterType,
      ocrNumber: item.ocrNumber,
      buildingId: item.buildingId,
      buildingName: item.buildingName,
      roomId: item.roomId,
      roomNumber: item.roomNumber,
      tenantId: item.tenantId,
      tenantName: item.tenantName,
      meterNumber: item.meterNumber,
    }))
    var msgs = [...this.state.messages, { role: "user" as const, content: userMsg, images: messageImages }]
    this.setState({ messages: msgs, loading: true, attachments: [], attachmentPanelOpen: false, attachmentDragActive: false })
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
            session_context: { ...this.state.sessionContext, thread_id: this.aiThreadId },
            chat_thread_id: this.aiThreadId,
            conversation_id: this.state.convId || "",
            uploaded_images: attachments.map((item, index) => ({
              image_index: index,
              image: item.dataUrl,
              file_name: item.fileName,
              ocr_number: item.ocrNumber,
              meter_type: item.meterType,
              ocr_meter_type: item.meterType,
              meter_number: item.meterNumber,
              building_id: item.buildingId,
              building_name: item.buildingName,
              room_id: item.roomId,
              room_number: item.roomNumber,
              tenant_id: item.tenantId,
              tenant_name: item.tenantName,
            })),
          }
        })
      })
      var reply = safeAssistantReply(res?.response?.content || res?.reply)
      var nextPendingActions = res?.response?.pending_actions || res?.pending_actions || []
      var responseBillImages = res?.response?.bill_images || res?.bill_images || []
      var suggestedActions = res?.response?.suggested_actions || res?.suggested_actions || []
      var formActions = res?.response?.form_actions || res?.form_actions || []
      var sessionContext = res?.response?.session_context || res?.session_context || this.state.sessionContext
      this.syncThreadIdFromContext(sessionContext)
      msgs = [...this.replaceExistingBillImages(msgs, responseBillImages), { role: "assistant" as const, content: reply, billImages: responseBillImages, pendingActions: nextPendingActions, suggestedActions, formActions, sessionContext }]
      if (convIdAtStart > 0 && this.deletedChatIds.has(convIdAtStart)) return
      this.setState({ messages: msgs, loading: false, pendingActions: nextPendingActions, sessionContext })
      this.scrollBottom()
      var title = input.substring(0, 30) || "图片识别"
      if (this.state.convId > 0 && this.deletedChatIds.has(this.state.convId)) return
      var saveRes = await rental("_ai", "save_chat", { id: this.state.convId, title, messages: msgs })
      if (saveRes && saveRes.id) {
        this.setState({ convId: saveRes.id })
        this.loadHistory()
      }
    } catch {
      if (convIdAtStart > 0 && this.deletedChatIds.has(convIdAtStart)) return
      msgs = [...msgs, { role: "assistant" as const, content: AI_GUIDED_HELP_REPLY }]
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
        <button id="ai-float-btn" className={s.loading && !s.open ? "running" : ""} onClick={this.toggle} title={s.loading && !s.open ? "AI 正在处理" : "AI 助手"}>
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
                  <h2>你好，大王，我是哈基米</h2>
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
                      <div className="ai-msg-stack">
                        <div className="ai-msg-bubble user-bubble">
                          {m.content && <div>{m.content}</div>}
                          {m.images && m.images.length > 0 && (
                            <div className="ai-message-images">
                              {m.images.map(image => (
                                <div key={image.id} className="ai-message-image-wrap">
                                  <button type="button" className="ai-message-image" onClick={() => this.setState({ activePreviewImage: image.dataUrl })} title="查看图片">
                                    <img src={image.dataUrl} alt={image.fileName} />
                                  </button>
                                  <div className="ai-message-image-meta">
                                    <span>{image.meterType || "表具"}{image.roomNumber ? " · " + image.roomNumber : ""}</span>
                                    {image.tenantName && <span>{image.tenantName}</span>}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                        {m.content && (
                          <button type="button" className="ai-msg-copy" onClick={() => this.copyMessageText(m.content)} title="复制这条消息" aria-label="复制这条消息">
                            <CopyOutlined />
                          </button>
                        )}
                      </div>
                    </div>
                  )
                }
                return (
                  <div key={i} className="ai-msg-v2 bot">
                    <div className="ai-msg-avatar"><img src="/robot-avatar.jpg" className="ai-bot-avatar" /></div>
                    <div className="ai-msg-stack">
                      <div className="ai-msg-bubble bot-bubble">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {m.content}
                        </ReactMarkdown>
                        {m.billImages && m.billImages.map((image, j) => this.renderBillImage(image, i + "-" + j))}
                        {this.renderPendingActions(m.pendingActions || [])}
                        {this.renderFormActions(m.formActions || [])}
                        {this.renderSuggestedActions(m.suggestedActions || [])}
                      </div>
                      {m.content && (
                        <button type="button" className="ai-msg-copy" onClick={() => this.copyMessageText(m.content)} title="复制这条回复" aria-label="复制这条回复">
                          <CopyOutlined />
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
              {s.loading && !s.pendingActionLoadingId && (
                <div className="ai-msg-v2 bot">
                  <div className="ai-msg-avatar"><img src="/robot-avatar.jpg" className="ai-bot-avatar" /></div>
                  <div className="ai-msg-bubble bot-bubble ai-loading">
                    <span className="ai-dot-typing" />
                  </div>
                </div>
              )}
            </div>
            <div className="ai-chat-footer-v2">
              {s.attachmentPanelOpen && (
                <div
                  className="ai-attachment-panel"
                  onDragEnter={this.handleAttachmentDragEnter}
                  onDragOver={this.handleAttachmentDragOver}
                  onDragLeave={this.handleAttachmentDragLeave}
                  onDrop={this.handleAttachmentDrop}
                >
                  <div className={"ai-attachment-dropzone" + (s.attachmentDragActive ? " active" : "")}>
                    <div className="ai-attachment-drop-icon"><UploadOutlined /></div>
                    <div className="ai-attachment-drop-copy">
                      <strong>{s.attachmentDragActive ? "松开上传图片" : "拖拽图片到这里"}</strong>
                      <span>{s.attachments.length ? "已添加 " + s.attachments.length + " 张图片" : "支持一次拖入多张图片"}</span>
                    </div>
                    <button type="button" onClick={() => this.fileRef.current?.click()} disabled={s.loading}>
                      选择图片
                    </button>
                  </div>
                </div>
              )}
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
                      <div className="ai-attachment-fields">
                        <select value={item.buildingId || ""} onChange={e => this.setAttachmentBuilding(item.id, e.target.value)} title="选择楼栋">
                          <option value="">选择楼栋</option>
                          {s.meterBuildings.map(building => <option key={building.id} value={building.id}>{building.name}</option>)}
                        </select>
                        <select value={item.roomId || ""} onChange={e => this.setAttachmentRoom(item.id, e.target.value)} disabled={!item.buildingId} title="选择房间">
                          <option value="">选择房间</option>
                          {(s.meterRooms[item.buildingId || 0] || []).map(room => <option key={room.id} value={room.id}>{room.room_number}</option>)}
                        </select>
                        <div className="ai-attachment-tenant">租客：{item.tenantName || "未匹配"}</div>
                        {item.meterNumber && <div className="ai-attachment-meter-no">表号：{item.meterNumber}</div>}
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
                <button
                  className={"ai-attach-btn ai-attach-panel-toggle" + (s.attachmentPanelOpen ? " active" : "")}
                  onClick={() => this.setState({ attachmentPanelOpen: !s.attachmentPanelOpen, attachmentDragActive: false })}
                  title={s.attachmentPanelOpen ? "收起上传面板" : "展开上传面板"}
                  type="button"
                >
                  <UploadOutlined />
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
