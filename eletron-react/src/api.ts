const API = 'http://localhost:18520'

export async function api(path: string, opts?: RequestInit) {
  try {
    const r = await fetch(API + path, {
      method: opts?.method || 'GET',
      headers: opts?.body ? { 'Content-Type': 'application/json' } : {},
      body: opts?.body
    })
    return await r.json()
  } catch { return null }
}

export async function rental(table: string, action: string, data?: Record<string, any>) {
  return api('/api/rental', {
    method: 'POST',
    body: JSON.stringify({ table, action, data: data || {} })
  })
}
