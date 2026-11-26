// P19 (E2＋): the management area — its groups and pages, who sees them, and where 管理 opens.
import type { IconName } from '../components/UiIcon.vue'

export type AdminPage = { name: string; label: string; icon: IconName; admin: boolean; also?: string[] }
export type AdminGroup = { name: string; pages: AdminPage[] }

export const ADMIN_GROUPS: AdminGroup[] = [
  { name: '內容', pages: [
    { name: 'app-taxonomy', label: '集合與標籤', icon: 'sliders', admin: false },
    { name: 'app-broken-links', label: '失效連結', icon: 'link', admin: false },
  ] },
  { name: '成員與紀錄', pages: [
    { name: 'app-members', label: '成員管理', icon: 'users', admin: true, also: ['app-member'] },
    { name: 'app-audit', label: '稽核紀錄', icon: 'history', admin: true },
    { name: 'app-public-overview', label: '公開站總覽', icon: 'chart', admin: true },
  ] },
  { name: '系統', pages: [
    { name: 'app-system', label: '系統狀態', icon: 'alert', admin: true },
    { name: 'app-site-settings', label: '網站設定', icon: 'globe', admin: true },
    { name: 'app-maintenance', label: '維護與備份', icon: 'history', admin: true },
  ] },
]

/** The groups (and pages) this member may open: Editors get 內容 only, Viewers nothing. */
export function groupsFor(canEdit: boolean, isAdmin: boolean): AdminGroup[] {
  if (!canEdit) return []
  return ADMIN_GROUPS.map(group => ({ ...group, pages: group.pages.filter(page => isAdmin || !page.admin) }))
    .filter(group => group.pages.length)
}

export const pageOf = (groups: AdminGroup[], routeName: string) =>
  groups.flatMap(group => group.pages).find(page => page.name === routeName || page.also?.includes(routeName))
export const groupOf = (groups: AdminGroup[], routeName: string) =>
  groups.find(group => group.pages.some(page => page.name === routeName || page.also?.includes(routeName)))

// Where 管理 (and each group) opens: the page last visited there, kept in this browser.
const KEY = 'knowledge-hub.app.admin-last'
type Last = { page?: string; groups?: Record<string, string> }
function read(): Last {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Last } catch { return {} }
}
export function rememberAdminPage(group: string, page: string) {
  const last = read()
  try { localStorage.setItem(KEY, JSON.stringify({ page, groups: { ...last.groups, [group]: page } })) } catch { /* storage may be disabled */ }
}
export function lastAdminPage(groups: AdminGroup[]) {
  const name = read().page
  const pages = groups.flatMap(group => group.pages)
  return pages.find(page => page.name === name)?.name ?? pages[0]?.name
}
export function lastPageOfGroup(group: AdminGroup) {
  const name = read().groups?.[group.name]
  return group.pages.find(page => page.name === name)?.name ?? group.pages[0].name
}
