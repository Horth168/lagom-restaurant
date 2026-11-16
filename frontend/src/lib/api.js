// Small wrapper around fetch for the LAGOM API.
const BASE = import.meta.env.VITE_API_URL || ''

export class ApiError extends Error {
  constructor(status, detail) {
    const message =
      typeof detail === 'string' ? detail : detail?.message || (Array.isArray(detail) ? detail[0]?.msg : '') || 'Error'
    super(message)
    this.status = status
    this.detail = detail
  }
}

// Server messages come back in the language the person chose (see backend app/i18n.py)
function currentLang() {
  try {
    return localStorage.getItem('lagom.lang') || document.documentElement.lang || 'en'
  } catch {
    return 'en'
  }
}

export async function api(path, { method = 'GET', body, headers = {}, signal } = {}) {
  let res
  try {
    res = await fetch(BASE + path, {
      method,
      signal,
      headers: { 'Accept-Language': currentLang(), ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(0, 'network')
  }
  const isJson = res.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await res.json() : null
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? res.statusText)
  return data
}
