// P24: first-run setup — what the server reports, and the client-side checks shown while typing.
// The server decides everything (the hour, the code, the password rules); these only guide the person.
import { ApiError, api, setCsrfToken } from '../api'

export type Terms = { title: string; body: string }[]
export type About = {
  version: string
  developer: { name: string; email: string; github: string }
  copyright: string
  license: string
  support: { github_sponsors: string; buy_me_a_coffee: string }
  terms_version: number
  terms: Terms
}
export type Checks = {
  https: boolean; origin: string; database: boolean; storage_writable: boolean
  disk: { total_bytes: number; free_bytes: number } | null
  smtp: boolean; google_login: boolean; mfa_key: boolean
}
export type SetupStatus =
  | { required: false }
  | { required: true; window_seconds: number; code_required: boolean; permitted: boolean; code_file: string; about: About; checks: Checks }

function csrfFromCookie() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  if (match) setCsrfToken(decodeURIComponent(match[1]))
}

export async function loadStatus() {
  const status = await api<SetupStatus>('/api/setup/')
  csrfFromCookie()  // the status call sets it; no one is signed in yet
  return status
}

export const verify = (code?: string) => api<{ permitted: boolean }>('/api/setup/verify', 'POST', code ? { code } : {})

export type AdminForm = { display_name: string; username: string; email: string; password: string }
export type SiteForm = { name: string; tagline: string; storage_limit_gb: number | null }
export function complete(termsVersion: number, admin: AdminForm, site: SiteForm | null) {
  return api<{ done: boolean; next: string }>('/api/setup/complete', 'POST', {
    terms_version: termsVersion, admin, ...(site ? { site } : {}),
  })
}

export const isApiError = (cause: unknown): cause is ApiError => cause instanceof ApiError

const COMMON = ['password', '12345678', '123456789', 'qwerty123', 'admin123', 'password1', 'iloveyou', '11111111']
/** The rules Django checks, as the person types (the server has the final say). */
export function passwordRules(form: AdminForm, confirm: string): [string, boolean][] {
  const password = form.password
  const lower = password.toLowerCase()
  const local = form.email.split('@')[0]?.toLowerCase() ?? ''
  const similar = (form.username.length > 2 && lower.includes(form.username.toLowerCase())) || (local.length > 2 && lower.includes(local))
  return [
    ['至少 8 個字元', password.length >= 8],
    ['不能只有數字', password.length > 0 && !/^\d+$/.test(password)],
    ['不能和帳號或 Email 太像', password.length > 0 && !similar],
    ['不是常見密碼', password.length > 0 && !COMMON.includes(lower)],
    ['兩次輸入相同', password.length > 0 && password === confirm],
  ]
}

export function strength(password: string) {
  if (!password) return 0
  let score = 0
  if (password.length >= 8) score++
  if (password.length >= 12) score++
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++
  if (/\d/.test(password) && /[^\w]/.test(password)) score++
  return Math.max(1, Math.min(4, score))
}

export function sizeText(bytes: number) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++ }
  return `${value >= 100 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`
}
