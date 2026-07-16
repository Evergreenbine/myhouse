const API = 'http://127.0.0.1:18520'
const REQUEST_TIMEOUT_MS = 90000

export async function api(path: string, opts?: RequestInit) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    const r = await fetch(API + path, {
      method: opts?.method || 'GET',
      headers: opts?.body ? { 'Content-Type': 'application/json' } : {},
      body: opts?.body,
      signal: controller.signal,
    })
    return await r.json()
  } catch {
    return null
  } finally {
    window.clearTimeout(timer)
  }
}

export async function rental(table: string, action: string, data?: Record<string, any>) {
  return api('/api/rental', {
    method: 'POST',
    body: JSON.stringify({ table, action, data: data || {} })
  })
}
