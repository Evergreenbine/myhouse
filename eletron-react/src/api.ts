function getDefaultApiBase() {
  if (window.location.protocol === 'file:') return 'http://127.0.0.1:18520'
  if (window.location.port === '5173') return window.location.protocol + '//' + window.location.hostname + ':18520'
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') return 'http://127.0.0.1:18520'
  return ''
}

const defaultApiBase = getDefaultApiBase()
const API = (import.meta.env.VITE_API_BASE_URL || defaultApiBase).replace(/\/$/, '')
const REQUEST_TIMEOUT_MS = 90000
const DEBUG_API = new URLSearchParams(window.location.search).has('debugApi')

export async function api(path: string, opts?: RequestInit) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    const headers: Record<string, string> = {}
    if (opts?.body) headers['Content-Type'] = 'application/json'

    const url = API + path
    if (DEBUG_API) console.log('[myhouse api]', url, opts?.method || 'GET')
    const r = await fetch(url, {
      method: opts?.method || 'GET',
      headers,
      body: opts?.body,
      signal: controller.signal,
    })
    const text = await r.text()
    let data: any = null
    try {
      data = text ? JSON.parse(text) : {}
    } catch {
      data = { error: r.ok ? '服务返回格式异常' : `接口请求失败：${r.status}` }
    }
    if (DEBUG_API) console.log('[myhouse api result]', url, r.status, data)
    return data
  } catch (e: any) {
    if (DEBUG_API) console.error('[myhouse api error]', API + path, e)
    return { error: e?.message || '接口请求失败' }
  } finally {
    window.clearTimeout(timer)
  }
}

export async function rental(table: string, action: string, data?: Record<string, any>) {
  const res = await api('/api/rental', {
    method: 'POST',
    body: JSON.stringify({ table, action, data: data || {} })
  })
  if (res && res.error) {
    console.error('[myhouse rental error]', { table, action, error: res.error, apiBase: API })
  }
  return res
}
