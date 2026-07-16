import React from "react"
import { api, rental } from "../api"
import { showToast } from "../components/ui"
import { useUIStore } from "../store"

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
  cfg: any
}

export class SettingsPage extends React.Component<{}, SettingsState> {
  private _saveTimer: any = null
  private _ocrSaveTimer: any = null

  constructor(props: {}) {
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
  }

  _onDocClick = () => {
    this.setState({ modelMenuOpen: false, ocrModelMenuOpen: false })
  }

  async load() {
    var cfg = await api("/api/user/config") || {}
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
      ocrKey: cfg.ocr_key || ""
    })
  }

  selectProvider = (pid: string) => {
    var selP = ALL_PROVIDERS.find(function(p: any) { return p.id === pid }) || ALL_PROVIDERS[0]
    this.setState({ curProvider: pid, curModel: selP.models[0].id, modelMenuOpen: false })
    this.autoSave()
  }

  selectModel = (mid: string) => {
    this.setState({ curModel: mid, modelMenuOpen: false })
    this.autoSave()
  }

  selectOcrProvider = (pid: string) => {
    var selP = OCR_PROVIDERS.find(function(p: any) { return p.id === pid }) || OCR_PROVIDERS[0]
    this.setState({ ocrProvider: pid, ocrModel: selP.models[0].id })
    this.autoSaveOcr()
  }

  selectOcrModel = (mid: string) => {
    this.setState({ ocrModel: mid, ocrModelMenuOpen: false })
    this.autoSaveOcr()
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

  render() {
    var s = this.state
    if (s.loading) return <div style={{color:"var(--text-third)",fontSize:13,padding:24}}>加载中...</div>
    return (
      <div style={{padding:"24px 0"}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20}}>
          <div className="page-title" style={{marginBottom:0}}>系统设置</div>
          <button className="btn btn-sm" onClick={() => useUIStore.getState().setSection("basic")} style={{color:"var(--text-sec)",background:"var(--bg)",border:"1px solid var(--border)",borderRadius:6,width:32,height:32,justifyContent:"center",padding:0,fontSize:16}}>←</button>
        </div>
        {this.renderAiSettings()}
      </div>
    )
  }
}
