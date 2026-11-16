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

export async function api(path, { method = 'GET', body, headers = {}, signal } = {}) {
  let res
  try {
    res = await fetch(BASE + path, {
      method,
      signal,
      headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
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
