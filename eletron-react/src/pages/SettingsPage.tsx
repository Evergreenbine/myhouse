import React from "react"
import { DeleteOutlined, KeyOutlined, PlusOutlined, RobotOutlined, StopOutlined, TeamOutlined } from "@ant-design/icons"
import { api, rental } from "../api"
import { showToast } from "../components/ui"
import { useUIStore } from "../store"
import { ASSISTANT_PROFILE_EVENT, DEFAULT_AI_AVATAR, DEFAULT_AI_NICKNAME, DEFAULT_USER_NICKNAME, normalizeAssistantProfile } from "../utils/assistantProfile"
import { USER_PROFILE_UPDATED_EVENT, type AuthUser } from "./LoginPage"

var ALL_PROVIDERS = [
  {
    "id": "deepseek",
    "name": "DeepSeek",
    "models": [
      {
        "id": "deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "desc": "纯文本，深度推理"
      },
      {
        "id": "deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "desc": "纯文本，速度快"
      },
      {
        "id": "deepseek-chat",
        "name": "DeepSeek V3",
        "desc": "纯文本，通用对话"
      },
      {
        "id": "deepseek-reasoner",
        "name": "DeepSeek R1",
        "desc": "纯文本，深度推理"
      }
    ],
    "keyField": "api_key",
    "keyLabel": "API Key",
    "keyPlaceholder": "sk-..."
  },
  {
    "id": "openai",
    "name": "OpenAI",
    "models": [
      {
        "id": "openai-gpt-4o",
        "name": "GPT-4o",
        "desc": "多模态，支持图片识别"
      },
      {
        "id": "openai-gpt-4o-mini",
        "name": "GPT-4o Mini",
        "desc": "多模态，轻量快速"
      }
    ],
    "keyField": "openai_key",
    "keyLabel": "API Key",
    "keyPlaceholder": "sk-..."
  },
  {
    "id": "zhipu",
    "name": "智谱",
    "models": [
      {
        "id": "zhipu-glm-4-plus",
        "name": "GLM-4-Plus",
        "desc": "多模态，支持图片识别"
      },
      {
        "id": "zhipu-glm-4-flash",
        "name": "GLM-4-Flash",
        "desc": "纯文本，速度快"
      }
    ],
    "keyField": "zhipu_key",
    "keyLabel": "API Key",
    "keyPlaceholder": "..."
  },
  {
    "id": "qwen",
    "name": "千问 (DashScope)",
    "models": [
      {
        "id": "qwen-vl-max",
        "name": "Qwen-VL-Max",
        "desc": "多模态，支持图片识别"
      },
      {
        "id": "qwen-plus",
        "name": "Qwen-Plus",
        "desc": "纯文本，通用对话"
      },
      {
        "id": "qwen-turbo",
        "name": "Qwen-Turbo",
        "desc": "纯文本，速度快"
      }
    ],
    "keyField": "qwen_key",
    "keyLabel": "DashScope API Key",
    "keyPlaceholder": "sk-..."
  },
  {
    "id": "custom",
    "name": "自定义",
    "models": [
      {
        "id": "custom-model",
        "name": "自定义模型",
        "desc": "手动配置"
      }
    ],
    "keyField": "custom_api_key",
    "keyLabel": "API Key",
    "keyPlaceholder": "sk-...",
    "hasUrl": true,
    "hasCustomModel": true
  }
];

var OCR_PROVIDERS = [
  {
    "id": "qwen",
    "name": "千问 (DashScope)",
    "models": [
      {
        "id": "qwen-vl-max",
        "name": "Qwen-VL-Max"
      }
    ]
  },
  {
    "id": "openai",
    "name": "OpenAI",
    "models": [
      {
        "id": "openai-gpt-4o",
        "name": "GPT-4o"
      },
      {
        "id": "openai-gpt-4o-mini",
        "name": "GPT-4o Mini"
      }
    ]
  },
  {
    "id": "zhipu",
    "name": "智谱",
    "models": [
      {
        "id": "zhipu-glm-4-plus",
        "name": "GLM-4-Plus"
      }
    ]
  }
];

interface SettingsState {
  loading: boolean
  curProvider: string
  curModel: string
  apiKey: string
  customUrl: string
  customModel: string
  ocrProvider: string
  ocrModel: string
  ocrKey: string
  modelMenuOpen: boolean
  ocrModelMenuOpen: boolean
  aiNickname: string
  userNickname: string
  aiAvatar: string
  settingsView: "ai" | "profile" | "accounts"
  selfUsername: string
  selfDisplayName: string
  selfAvatar: string
  currentPassword: string
  newPassword: string
  selfSaving: boolean
  accounts: FamilyAccount[]
  accountsLoading: boolean
  newUsername: string
  newDisplayName: string
  newAccountPassword: string
  accountSaving: boolean
  resetAccountId: number
  resetPassword: string
  cfg: any
}

interface FamilyAccount {
  id: number
  username: string
  display_name: string
  role: "owner" | "family"
  is_active: boolean
  created_at?: string | null
  last_login_at?: string | null
  avatar?: string
}

interface SettingsPageProps {
  currentUser: AuthUser
}

export class SettingsPage extends React.Component<SettingsPageProps, SettingsState> {
  private _saveTimer: any = null
  private _ocrSaveTimer: any = null
  private _profileSaveTimer: any = null
  private avatarInputRef = React.createRef<HTMLInputElement>()
  private selfAvatarInputRef = React.createRef<HTMLInputElement>()

  constructor(props: SettingsPageProps) {
    super(props)
    this.state = {
      loading: true,
      curProvider: "deepseek",
      curModel: "deepseek-v4-flash",
      apiKey: "",
      customUrl: "",
      customModel: "",
      ocrProvider: "qwen",
      ocrModel: "qwen-vl-max",
      ocrKey: "",
      modelMenuOpen: false,
      ocrModelMenuOpen: false,
      aiNickname: DEFAULT_AI_NICKNAME,
      userNickname: DEFAULT_USER_NICKNAME,
      aiAvatar: DEFAULT_AI_AVATAR,
      settingsView: "profile",
      selfUsername: props.currentUser.username,
      selfDisplayName: props.currentUser.display_name,
      selfAvatar: props.currentUser.avatar || "",
      currentPassword: "",
      newPassword: "",
      selfSaving: false,
      accounts: [],
      accountsLoading: false,
      newUsername: "",
      newDisplayName: "",
      newAccountPassword: "",
      accountSaving: false,
      resetAccountId: 0,
      resetPassword: "",
      cfg: {}
    }
  }

  componentDidMount() {
    this.load()
    document.addEventListener("mousedown", this._onDocClick)
  }

  componentWillUnmount() {
    document.removeEventListener("mousedown", this._onDocClick)
    clearTimeout(this._saveTimer)
    clearTimeout(this._ocrSaveTimer)
    clearTimeout(this._profileSaveTimer)
  }

  _onDocClick = (event: MouseEvent) => {
    if (event.target instanceof Element && event.target.closest(".custom-select")) return
    this.setState({ modelMenuOpen: false, ocrModelMenuOpen: false })
  }

  async load() {
    var cfg = await api("/api/user/config") || {}
    var profile = normalizeAssistantProfile(cfg)
    this.setState({
      loading: false,
      cfg,
      curProvider: cfg.ai_provider || "deepseek",
      curModel: cfg.ai_model || "deepseek-v4-flash",
      apiKey: cfg.api_key || cfg.deepseek_key || "",
      customUrl: cfg.custom_base_url || "",
      customModel: cfg.custom_model || "",
      ocrProvider: cfg.ocr_provider || "qwen",
      ocrModel: cfg.ocr_model || "qwen-vl-max",
      ocrKey: cfg.ocr_key || "",
      ...profile,
    })
  }

  imageFileToAvatar = (file: File) => new Promise<string>((resolve, reject) => {
    var objectUrl = URL.createObjectURL(file)
    var image = new Image()
    image.onload = () => {
      try {
        var size = Math.min(image.naturalWidth, image.naturalHeight)
        var sourceX = (image.naturalWidth - size) / 2
        var sourceY = (image.naturalHeight - size) / 2
        var canvas = document.createElement("canvas")
        canvas.width = 192
        canvas.height = 192
        var context = canvas.getContext("2d")
        if (!context) throw new Error("无法处理图片")
        context.drawImage(image, sourceX, sourceY, size, size, 0, 0, 192, 192)
        var avatar = canvas.toDataURL("image/jpeg", 0.8)
        if (avatar.length > 60000) avatar = canvas.toDataURL("image/jpeg", 0.6)
        resolve(avatar)
      } catch (error) {
        reject(error)
      } finally {
        URL.revokeObjectURL(objectUrl)
      }
    }
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      reject(new Error("图片读取失败"))
    }
    image.src = objectUrl
  })

  chooseAvatar = async (event: React.ChangeEvent<HTMLInputElement>) => {
    var file = event.target.files?.[0]
    event.target.value = ""
    if (!file) return
    if (!file.type.startsWith("image/")) {
      showToast("请选择图片文件")
      return
    }
    try {
      var aiAvatar = await this.imageFileToAvatar(file)
      clearTimeout(this._profileSaveTimer)
      this.setState({ aiAvatar }, this.saveAssistantProfile)
    } catch {
      showToast("头像处理失败，请换一张图片")
    }
  }

  autoSaveAssistantProfile = () => {
    clearTimeout(this._profileSaveTimer)
    this._profileSaveTimer = setTimeout(this.saveAssistantProfile, 500)
  }

  saveAssistantProfile = async () => {
    var aiNickname = this.state.aiNickname.trim()
    var userNickname = this.state.userNickname.trim()
    if (!aiNickname || !userNickname) return
    var data = { ai_nickname: aiNickname, user_nickname: userNickname, ai_avatar: this.state.aiAvatar }
    var res = await api("/api/user/config", { method: "POST", body: JSON.stringify(data) })
    if (res && !res.error) {
      var profile = normalizeAssistantProfile(data)
      this.setState(state => ({ ...profile, cfg: { ...state.cfg, ...data } }))
      window.dispatchEvent(new CustomEvent(ASSISTANT_PROFILE_EVENT, { detail: profile }))
    } else {
      showToast("保存失败")
    }
  }

  restoreEmptyProfileField = (field: "aiNickname" | "userNickname") => {
    if (this.state[field].trim()) return
    var fallback = field === "aiNickname" ? DEFAULT_AI_NICKNAME : DEFAULT_USER_NICKNAME
    this.setState({ [field]: fallback } as Pick<SettingsState, typeof field>, this.autoSaveAssistantProfile)
  }

  switchSettingsView = (settingsView: "ai" | "profile" | "accounts") => {
    this.setState({ settingsView })
    if (settingsView === "accounts" && !this.state.accounts.length) this.loadAccounts()
  }

  applyCurrentUser = (user: AuthUser) => {
    this.setState({
      selfUsername: user.username,
      selfDisplayName: user.display_name,
      selfAvatar: user.avatar || "",
    })
    window.dispatchEvent(new CustomEvent(USER_PROFILE_UPDATED_EVENT, { detail: user }))
  }

  saveMyProfile = async () => {
    var username = this.state.selfUsername.trim()
    var displayName = this.state.selfDisplayName.trim()
    if (!username || !displayName) {
      showToast("请填写登录账号和显示称呼")
      return
    }
    this.setState({ selfSaving: true })
    var res = await api("/api/user/profile", {
      method: "PATCH",
      body: JSON.stringify({
        username,
        display_name: displayName,
        avatar: this.state.selfAvatar,
        current_password: this.state.currentPassword,
        new_password: this.state.newPassword,
      }),
    })
    if (res && !res.error && res.user) {
      this.setState({ selfSaving: false, currentPassword: "", newPassword: "" })
      this.applyCurrentUser(res.user)
      showToast("账号设置已保存")
    } else {
      this.setState({ selfSaving: false })
      showToast(res?.error || "保存失败")
    }
  }

  chooseMyAvatar = async (event: React.ChangeEvent<HTMLInputElement>) => {
    var file = event.target.files?.[0]
    event.target.value = ""
    if (!file) return
    if (!file.type.startsWith("image/")) {
      showToast("请选择图片文件")
      return
    }
    try {
      var avatar = await this.imageFileToAvatar(file)
      var res = await api("/api/user/profile", {
        method: "PATCH",
        body: JSON.stringify({
          username: this.state.selfUsername.trim(),
          display_name: this.state.selfDisplayName.trim(),
          avatar,
        }),
      })
      if (res && !res.error && res.user) {
        this.applyCurrentUser(res.user)
      } else showToast(res?.error || "头像保存失败")
    } catch {
      showToast("头像处理失败，请换一张图片")
    }
  }

  loadAccounts = async () => {
    if (this.props.currentUser.role !== "owner") return
    this.setState({ accountsLoading: true })
    var res = await api("/api/user/accounts")
    if (res && !res.error) {
      this.setState({ accounts: res.items || [], accountsLoading: false })
    } else {
      this.setState({ accountsLoading: false })
      showToast(res?.error || "账号加载失败")
    }
  }

  createFamilyAccount = async () => {
    var username = this.state.newUsername.trim()
    var displayName = this.state.newDisplayName.trim()
    var password = this.state.newAccountPassword
    if (!username || !displayName || !password) {
      showToast("请填写账号、称呼和初始密码")
      return
    }
    this.setState({ accountSaving: true })
    var res = await api("/api/user/accounts", {
      method: "POST",
      body: JSON.stringify({ username, display_name: displayName, password }),
    })
    if (res && !res.error) {
      this.setState({ newUsername: "", newDisplayName: "", newAccountPassword: "", accountSaving: false })
      await this.loadAccounts()
      showToast("家人账号已添加")
    } else {
      this.setState({ accountSaving: false })
      showToast(res?.error || "添加失败")
    }
  }

  toggleFamilyAccount = async (account: FamilyAccount) => {
    var res = await api("/api/user/accounts/" + account.id, {
      method: "PATCH",
      body: JSON.stringify({ display_name: account.display_name, is_active: !account.is_active }),
    })
    if (res && !res.error) await this.loadAccounts()
    else showToast(res?.error || "操作失败")
  }

  chooseFamilyAvatar = async (event: React.ChangeEvent<HTMLInputElement>, account: FamilyAccount) => {
    var file = event.target.files?.[0]
    event.target.value = ""
    if (!file) return
    if (!file.type.startsWith("image/")) {
      showToast("请选择图片文件")
      return
    }
    try {
      var avatar = await this.imageFileToAvatar(file)
      var res = await api("/api/user/accounts/" + account.id, {
        method: "PATCH",
        body: JSON.stringify({ display_name: account.display_name, is_active: account.is_active, avatar }),
      })
      if (!res || res.error) {
        showToast(res?.error || "头像保存失败")
        return
      }
      if (account.id === this.props.currentUser.id) {
        this.applyCurrentUser(res.account)
      }
      await this.loadAccounts()
    } catch {
      showToast("头像处理失败，请换一张图片")
    }
  }

  saveResetPassword = async (account: FamilyAccount) => {
    if (this.state.resetPassword.length < 6) {
      showToast("新密码至少6位")
      return
    }
    var res = await api("/api/user/accounts/" + account.id + "/password", {
      method: "POST",
      body: JSON.stringify({ password: this.state.resetPassword }),
    })
    if (res && !res.error) {
      this.setState({ resetAccountId: 0, resetPassword: "" })
      showToast("密码已重置")
    } else showToast(res?.error || "重置失败")
  }

  removeFamilyAccount = async (account: FamilyAccount) => {
    if (!window.confirm("确定删除家人账号“" + account.display_name + "”吗？")) return
    var res = await api("/api/user/accounts/" + account.id, { method: "DELETE" })
    if (res && !res.error) await this.loadAccounts()
    else showToast(res?.error || "删除失败")
  }

  formatAccountTime = (value?: string | null) => {
    if (!value) return "尚未登录"
    var date = new Date(value)
    if (Number.isNaN(date.getTime())) return String(value)
    return date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
  }

  selectProvider = (pid: string) => {
    var selP = ALL_PROVIDERS.find(function(p: any) { return p.id === pid }) || ALL_PROVIDERS[0]
    this.setState({ curProvider: pid, curModel: selP.models[0].id, modelMenuOpen: false }, this.autoSave)
  }

  selectModel = (mid: string) => {
    this.setState({ curModel: mid, modelMenuOpen: false }, this.autoSave)
  }

  selectOcrProvider = (pid: string) => {
    var selP = OCR_PROVIDERS.find(function(p: any) { return p.id === pid }) || OCR_PROVIDERS[0]
    this.setState({ ocrProvider: pid, ocrModel: selP.models[0].id }, this.autoSaveOcr)
  }

  selectOcrModel = (mid: string) => {
    this.setState({ ocrModel: mid, ocrModelMenuOpen: false }, this.autoSaveOcr)
  }

  autoSave = () => {
    clearTimeout(this._saveTimer)
    this._saveTimer = setTimeout(() => this.save(), 300)
  }

  autoSaveOcr = () => {
    clearTimeout(this._ocrSaveTimer)
    this._ocrSaveTimer = setTimeout(() => this.saveOcr(), 300)
  }

  async save() {
    var s = this.state
    var selP = ALL_PROVIDERS.find(function(p: any) { return p.id === s.curProvider }) || ALL_PROVIDERS[0]
    var data: any = { ai_provider: s.curProvider, ai_model: s.curModel }
    data[selP.keyField] = s.apiKey
    if (selP.hasUrl) data.custom_base_url = s.customUrl
    if (selP.hasCustomModel) data.custom_model = s.customModel
    var res = await api("/api/user/config", { method: "POST", body: JSON.stringify(data) })
    if (res && !res.error) {
      var cfg = this.state.cfg
      cfg.ai_provider = s.curProvider;
      cfg.ai_model = s.curModel;
      cfg[selP.keyField] = s.apiKey;
      if (selP.hasUrl) cfg.custom_base_url = s.customUrl;
      if (selP.hasCustomModel) cfg.custom_model = s.customModel;
      this.setState({ cfg })
      showToast("✅ 已自动保存")
    } else { showToast("保存失败") }
  }

  async saveOcr() {
    var s = this.state
    var data = { ocr_provider: s.ocrProvider, ocr_model: s.ocrModel, ocr_key: s.ocrKey }
    var res = await api("/api/user/config", { method: "POST", body: JSON.stringify(data) })
    if (res && !res.error) {
      var cfg = this.state.cfg;
      cfg.ocr_provider = s.ocrProvider;
      cfg.ocr_model = s.ocrModel;
      cfg.ocr_key = s.ocrKey;
      this.setState({ cfg })
      showToast("✅ 已自动保存")
    } else { showToast("保存失败") }
  }

  testConnection = async () => {
    var s = this.state
    var key = s.apiKey
    if (!key) { showToast("请先填写 API Key"); return }
    showToast("正在测试连通性...")
    try {
      var res = await rental("_ai", "chat", { prompt: "hi", _test: true, _provider: s.curProvider, _key: key, _model: s.curModel, _url: s.customUrl })
      showToast(res && res.reply ? res.reply : "连通性测试通过 ✅")
    } catch(e) { showToast("连接失败 ❌") }
  }

  testOcrConnection = async () => {
    var s = this.state
    var key = s.ocrKey
    if (!key) { showToast("请先填写 API Key"); return }
    showToast("正在测试连通性...")
    try {
      var res = await rental("_ai", "chat", { prompt: "hi", _test: true, _provider: s.ocrProvider, _key: key, _model: s.ocrModel })
      showToast(res && res.reply ? res.reply : "连通性测试通过 ✅")
    } catch(e) { showToast("连接失败 ❌") }
  }

  renderProviderDetail() {
    var s = this.state
    var selP = ALL_PROVIDERS.find(function(p: any) { return p.id === s.curProvider }) || ALL_PROVIDERS[0]
    var curM = selP.models.find(function(m: any) { return m.id === s.curModel }) || selP.models[0]
    return (
      <div className="provider-detail">
        <div className="provider-title">{selP.name} 配置</div>
        <div className="form-group">
          <label>模型</label>
          <div className="custom-select" style={{position:"relative"}}>
            <div className="soft-input" style={{display:"flex",alignItems:"center",justifyContent:"space-between",cursor:"pointer",paddingRight:8}}
              onClick={() => this.setState({ modelMenuOpen: !s.modelMenuOpen })}>
              <span>{curM.name + (curM.desc ? " - " + curM.desc : "")}</span>
              <span style={{fontSize:10,color:"var(--text-third)"}}>▼</span>
            </div>
            {s.modelMenuOpen && (
              <div className="select-menu" style={{display:"block",position:"absolute",left:0,right:0,top:"100%",marginTop:4,background:"var(--white)",border:"1px solid var(--border-light)",borderRadius:8,boxShadow:"var(--shadow-md)",padding:6,zIndex:50,maxHeight:200,overflow:"auto"}}>
                {selP.models.map((m: any) => {
                  var active = m.id === s.curModel ? " active" : ""
                  return <div key={m.id} className={"select-option" + active}
                    onClick={() => this.selectModel(m.id)}>{m.name + (m.desc ? " - " + m.desc : "")}</div>
                })}
              </div>
            )}
          </div>
        </div>
        <div className="form-group">
          <label>{selP.keyLabel}</label>
          <input className="soft-input" value={s.apiKey}
            onChange={e => { this.setState({ apiKey: e.target.value }); this.autoSave() }}
            placeholder={selP.keyPlaceholder} />
        </div>
        {selP.hasUrl && (
          <div className="form-group">
            <label>API 地址</label>
            <input className="soft-input" value={s.customUrl}
              onChange={e => { this.setState({ customUrl: e.target.value }); this.autoSave() }}
              placeholder="https://api.xxx.com/v1" />
          </div>
        )}
        {selP.hasCustomModel && (
          <div className="form-group">
            <label>自定义模型名</label>
            <input className="soft-input" value={s.customModel}
              onChange={e => { this.setState({ customModel: e.target.value }); this.autoSave() }}
              placeholder="gpt-4o" />
          </div>
        )}
        <button className="btn btn-sm" onClick={this.testConnection}
          style={{marginTop:4,color:"var(--blue)",background:"var(--blue-light)",border:"none",padding:"5px 14px",borderRadius:6,fontSize:12,display:"flex",alignItems:"center",gap:4}}>
          🔌 测试连通性</button>
      </div>
    )
  }

  renderOcrDetail() {
    var s = this.state
    var selP = OCR_PROVIDERS.find(function(p: any) { return p.id === s.ocrProvider }) || OCR_PROVIDERS[0]
    var curM = selP.models.find(function(m: any) { return m.id === s.ocrModel }) || selP.models[0]
    return (
      <div className="provider-detail">
        <div className="form-group">
          <label>模型</label>
          <div className="custom-select" style={{position:"relative"}}>
            <div className="soft-input" style={{display:"flex",alignItems:"center",justifyContent:"space-between",cursor:"pointer",paddingRight:8}}
              onClick={() => this.setState({ ocrModelMenuOpen: !s.ocrModelMenuOpen })}>
              <span>{curM.name}</span>
              <span style={{fontSize:10,color:"var(--text-third)"}}>▼</span>
            </div>
            {s.ocrModelMenuOpen && (
              <div className="select-menu" style={{display:"block",position:"absolute",left:0,right:0,top:"100%",marginTop:4,background:"var(--white)",border:"1px solid var(--border-light)",borderRadius:8,boxShadow:"var(--shadow-md)",padding:6,zIndex:50,maxHeight:200,overflow:"auto"}}>
                {selP.models.map((m: any) => {
                  var active = m.id === s.ocrModel ? " active" : ""
                  return <div key={m.id} className={"select-option" + active}
                    onClick={() => this.selectOcrModel(m.id)}>{m.name}</div>
                })}
              </div>
            )}
          </div>
        </div>
        <div className="form-group">
          <label>API Key</label>
          <input className="soft-input" value={s.ocrKey}
            onChange={e => { this.setState({ ocrKey: e.target.value }); this.autoSaveOcr() }}
            placeholder="sk-..." />
        </div>
        <button className="btn btn-sm" onClick={this.testOcrConnection}
          style={{marginTop:4,color:"var(--blue)",background:"var(--blue-light)",border:"none",padding:"5px 14px",borderRadius:6,fontSize:12,display:"flex",alignItems:"center",gap:4}}>
          🔌 测试连通性</button>
      </div>
    )
  }

  renderAiSettings() {
    var s = this.state
    return (
      <>
        <div className="drawer-section assistant-profile-section">
          <div className="section-label">AI 助手</div>
          <div className="assistant-profile-panel">
            <div className="assistant-avatar-setting" title="点击更换头像">
              <button type="button" className="assistant-avatar-preview" onClick={() => this.avatarInputRef.current?.click()} aria-label="更换助手头像">
                <img src={s.aiAvatar} alt="助手头像" />
              </button>
              <input ref={this.avatarInputRef} type="file" accept="image/*" onChange={this.chooseAvatar} hidden />
            </div>
            <div className="assistant-profile-fields">
              <div className="form-group">
                <label>助手昵称</label>
                <input className="soft-input" maxLength={20} value={s.aiNickname}
                  onChange={e => this.setState({ aiNickname: e.target.value }, this.autoSaveAssistantProfile)}
                  onBlur={() => this.restoreEmptyProfileField("aiNickname")} />
              </div>
              <div className="form-group">
                <label>对我的称呼</label>
                <input className="soft-input" maxLength={20} value={s.userNickname}
                  onChange={e => this.setState({ userNickname: e.target.value }, this.autoSaveAssistantProfile)}
                  onBlur={() => this.restoreEmptyProfileField("userNickname")} />
              </div>
            </div>
          </div>
        </div>
        <div className="drawer-section">
          <div className="section-label">🤖 AI 模型设置</div>
          <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
            {ALL_PROVIDERS.map((p: any) => {
              var active = s.curProvider === p.id
              return (
                <div key={p.id}
                  className={"provider-card" + (active ? " active" : "")}
                  onClick={() => this.selectProvider(p.id)}>
                  <div className="provider-name">{p.name}</div>
                  <div className="provider-hint">{p.models[0] ? p.models[0].name : ""}</div>
                </div>
              )
            })}
          </div>
          {this.renderProviderDetail()}
        </div>
        <div className="drawer-section" style={{marginTop:24}}>
          <div className="section-label">📷 图片识别 AI（水电表识别）</div>
          <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
            {OCR_PROVIDERS.map((p: any) => {
              var active = s.ocrProvider === p.id
              return (
                <div key={p.id}
                  className={"provider-card" + (active ? " active" : "")}
                  onClick={() => this.selectOcrProvider(p.id)}>
                  <div className="provider-name">{p.name}</div>
                </div>
              )
            })}
          </div>
          {this.renderOcrDetail()}
        </div>
      </>
    )
  }

  renderFamilyAccounts() {
    var s = this.state
    return (
      <div className="family-account-page">
        <div className="drawer-section">
          <div className="section-label">添加家人账号</div>
          <div className="family-account-create">
            <div className="form-group"><label>登录账号</label><input className="soft-input" maxLength={32} value={s.newUsername} onChange={e => this.setState({ newUsername: e.target.value })} placeholder="例如：xiaomei" /></div>
            <div className="form-group"><label>家人称呼</label><input className="soft-input" maxLength={20} value={s.newDisplayName} onChange={e => this.setState({ newDisplayName: e.target.value })} placeholder="例如：小美" /></div>
            <div className="form-group"><label>初始密码</label><input className="soft-input" type="password" maxLength={64} value={s.newAccountPassword} onChange={e => this.setState({ newAccountPassword: e.target.value })} placeholder="至少6位" /></div>
            <button type="button" className="btn family-account-add" onClick={this.createFamilyAccount} disabled={s.accountSaving}><PlusOutlined />{s.accountSaving ? "添加中" : "添加账号"}</button>
          </div>
        </div>
        <div className="drawer-section">
          <div className="section-label">账号列表</div>
          {s.accountsLoading && <div className="family-account-empty">加载中...</div>}
          {!s.accountsLoading && !s.accounts.length && <div className="family-account-empty">暂无账号</div>}
          <div className="family-account-list">
            {s.accounts.map(account => {
              var isOwner = account.role === "owner"
              var isSelf = account.id === this.props.currentUser.id
              var resetting = s.resetAccountId === account.id
              return (
                <div className="family-account-row" key={account.id}>
                  <button type="button" className="family-account-avatar" onClick={() => document.getElementById("family-avatar-" + account.id)?.click()} title="点击更换头像" aria-label={"更换" + account.display_name + "的头像"}>
                    {account.avatar ? <img src={account.avatar} alt="" /> : (account.display_name || account.username).slice(0, 1)}
                  </button>
                  <input id={"family-avatar-" + account.id} type="file" accept="image/*" hidden onChange={event => this.chooseFamilyAvatar(event, account)} />
                  <div className="family-account-info">
                    <strong>{account.display_name}<em>{isOwner ? "屋主" : "家人"}</em>{!account.is_active && <em className="disabled">已停用</em>}</strong>
                    <span>{account.username} · {this.formatAccountTime(account.last_login_at)}</span>
                    {resetting && (
                      <div className="family-password-reset">
                        <input className="soft-input" type="password" autoFocus value={s.resetPassword} onChange={e => this.setState({ resetPassword: e.target.value })} placeholder="输入新密码，至少6位" />
                        <button type="button" onClick={() => this.saveResetPassword(account)}>保存</button>
                        <button type="button" onClick={() => this.setState({ resetAccountId: 0, resetPassword: "" })}>取消</button>
                      </div>
                    )}
                  </div>
                  <div className="family-account-actions">
                    <button type="button" onClick={() => this.setState({ resetAccountId: account.id, resetPassword: "" })} title="重置密码"><KeyOutlined /></button>
                    {!isOwner && <button type="button" onClick={() => this.toggleFamilyAccount(account)} title={account.is_active ? "停用账号" : "启用账号"}><StopOutlined /></button>}
                    {!isOwner && !isSelf && <button type="button" className="danger" onClick={() => this.removeFamilyAccount(account)} title="删除账号"><DeleteOutlined /></button>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    )
  }

  renderMyProfile() {
    var s = this.state
    return (
      <div className="my-account-page">
        <div className="drawer-section">
          <div className="section-label">我的账号</div>
          <div className="my-account-form">
            <div className="my-account-avatar-wrap">
              <button type="button" className="my-account-avatar" onClick={() => this.selfAvatarInputRef.current?.click()} title="点击更换头像">
                {s.selfAvatar ? <img src={s.selfAvatar} alt="" /> : (s.selfDisplayName || s.selfUsername).slice(0, 1)}
              </button>
              <input ref={this.selfAvatarInputRef} type="file" accept="image/*" hidden onChange={this.chooseMyAvatar} />
            </div>
            <div className="my-account-fields">
              <div className="form-group"><label>登录账号</label><input className="soft-input" maxLength={32} value={s.selfUsername} onChange={e => this.setState({ selfUsername: e.target.value })} /></div>
              <div className="form-group"><label>显示称呼</label><input className="soft-input" maxLength={20} value={s.selfDisplayName} onChange={e => this.setState({ selfDisplayName: e.target.value })} /></div>
              <div className="form-group"><label>当前密码</label><input className="soft-input" type="password" value={s.currentPassword} onChange={e => this.setState({ currentPassword: e.target.value })} placeholder="修改密码时填写" /></div>
              <div className="form-group"><label>新密码</label><input className="soft-input" type="password" value={s.newPassword} onChange={e => this.setState({ newPassword: e.target.value })} placeholder="至少6位" /></div>
              <button type="button" className="btn my-account-save" onClick={this.saveMyProfile} disabled={s.selfSaving}>{s.selfSaving ? "保存中" : "保存账号设置"}</button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  render() {
    var s = this.state
    if (s.loading) return <div style={{color:"var(--text-third)",fontSize:13,padding:24}}>加载中...</div>
    return (
      <div style={{padding:"24px 0"}}>
        <div className="settings-tabs-row">
          <div className="settings-view-tabs" role="tablist" aria-label="系统设置分类">
            <button type="button" role="tab" aria-selected={s.settingsView === "profile"} className={s.settingsView === "profile" ? "active" : ""} onClick={() => this.switchSettingsView("profile")}><KeyOutlined />我的账号</button>
            <button type="button" role="tab" aria-selected={s.settingsView === "ai"} className={s.settingsView === "ai" ? "active" : ""} onClick={() => this.switchSettingsView("ai")}><RobotOutlined />AI 设置</button>
            {this.props.currentUser.role === "owner" && <button type="button" role="tab" aria-selected={s.settingsView === "accounts"} className={s.settingsView === "accounts" ? "active" : ""} onClick={() => this.switchSettingsView("accounts")}><TeamOutlined />家人账号</button>}
          </div>
          <button className="btn btn-sm" onClick={() => useUIStore.getState().setSection("basic")} style={{color:"var(--text-sec)",background:"var(--bg)",border:"1px solid var(--border)",borderRadius:6,width:32,height:32,justifyContent:"center",padding:0,fontSize:16}}>←</button>
        </div>
        {s.settingsView === "accounts" ? this.renderFamilyAccounts() : s.settingsView === "profile" ? this.renderMyProfile() : this.renderAiSettings()}
      </div>
    )
  }
}
