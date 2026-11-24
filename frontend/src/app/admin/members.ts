import type { Role } from '../../stores/session'

/** Shapes from /api/users/ (admin only); mutations go through the Django form endpoints. */
export type MemberRow = {
  id: string
  username: string
  email: string
  display_name: string
  role: Role
  is_active: boolean
  pending_activation: boolean
  last_login: string | null
  date_joined: string
}
/** Django messages from the last form submission. */
export type Notice = { text: string; warning: boolean }
export type MemberContext = { csrf_token: string; roles: [Role, string][]; notices: Notice[] }
export type MemberListing = MemberContext & { results: MemberRow[]; count: number; page: number; page_count: number }
export type MemberDetail = MemberContext & {
  account: MemberRow & { mfa_enabled: boolean; google_linked: boolean; is_self: boolean }
  actions: [string, string][]
  audit: { id: number; action: string; created_at: string; actor: string | null; reason: string | null }[]
}

export const FORM_LIST = '/accounts/manage/'
export const formFor = (id: string) => `/accounts/manage/${encodeURIComponent(id)}/`

export const roleLabels: Record<Role, string> = { admin: 'Admin', editor: 'Editor', viewer: 'Viewer' }
export const roleHints: Record<Role, string> = {
  admin: '管理成員、集合與標籤、公開文章，可永久刪除文件',
  editor: '上傳與編輯文件、管理集合與標籤',
  viewer: '閱讀、搜尋、下載與比較版本',
}

export type MemberStatus = 'active' | 'pending' | 'disabled'
export function statusOf(member: Pick<MemberRow, 'is_active' | 'pending_activation'>): MemberStatus {
  if (member.pending_activation) return 'pending'
  return member.is_active ? 'active' : 'disabled'
}
export const statusLabels: Record<MemberStatus, string> = { active: '使用中', pending: '待啟用', disabled: '已停用' }

const auditLabels: Record<string, string> = {
  invited: '建立帳號並寄出邀請',
  activated: '完成帳號啟用',
  activation_resent: '重寄啟用信',
  role_changed: '變更角色',
  enabled: '重新啟用帳號',
  disabled: '停用帳號',
  password_reset_requested: '寄送密碼重設信',
  password_changed: '變更密碼',
  password_reset: '重設密碼',
  mfa_enabled: '啟用雙因素驗證',
  mfa_disabled: '停用雙因素驗證',
  mfa_admin_reset: '管理員重設雙因素驗證',
  display_name_changed: '變更顯示名稱',
  google_linked: '綁定 Google 帳號',
  google_unlinked: '解除 Google 綁定',
  login: '登入',
  logout: '登出',
}
export const auditLabel = (action: string) => auditLabels[action] ?? action
export const memberName = (member: Pick<MemberRow, 'display_name' | 'username'>) => member.display_name || member.username
export const initialOf = (name: string) => Array.from(name)[0]?.toUpperCase() ?? '?'
