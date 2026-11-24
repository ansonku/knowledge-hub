// Shared HTTP helpers for the redesigned workspace (/app/).
// Legacy pages keep their own copies until they are removed in P4.

export class ApiError extends Error {
  constructor(readonly status: number, message: string, readonly body?: unknown) {
    super(message)
  }
}

let csrfToken = ''

export function setCsrfToken(token: string) {
  csrfToken = token
}

export function getCsrfToken() {
  return csrfToken
}

export function errorMessage(body: unknown): string {
  if (typeof body === 'string') return body
  if (Array.isArray(body)) return body.map(errorMessage).filter(Boolean).join(' ')
  if (body && typeof body === 'object') return Object.values(body).map(errorMessage).filter(Boolean).join(' ')
  return ''
}

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

export async function api<T = unknown>(url: string, method: Method = 'GET', data?: object): Promise<T> {
  const headers: Record<string, string> = { 'X-CSRFToken': csrfToken }
  if (data) headers['Content-Type'] = 'application/json'
  const response = await fetch(url, {
    method,
    cache: 'no-store',
    headers,
    body: data ? JSON.stringify(data) : undefined,
  })
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, errorMessage(body) || '無法完成操作。', body)
  return body as T
}

export function isAuthError(error: unknown) {
  return error instanceof ApiError && (error.status === 401 || error.status === 403)
}

/** Multipart upload with progress; resolves with the JSON body of a 200 or 201 response. */
export function upload<T = unknown>(url: string, data: FormData, onProgress?: (percent: number) => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', url)
    request.responseType = 'json'
    request.timeout = 180_000
    request.setRequestHeader('X-CSRFToken', csrfToken)
    request.upload.onprogress = event => {
      if (event.lengthComputable) onProgress?.(Math.round(event.loaded * 100 / event.total))
    }
    request.onload = () => {
      if (request.status === 201 || request.status === 200) resolve(request.response as T)
      else reject(new ApiError(request.status, errorMessage(request.response) || '上傳失敗，請重新整理後再試。', request.response))
    }
    request.onerror = request.ontimeout = () => reject(new Error('連線中斷，請先確認文件清單再重試。'))
    request.send(data)
  })
}
