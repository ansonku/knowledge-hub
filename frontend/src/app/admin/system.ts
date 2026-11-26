// P19: shared by the three 系統 pages (狀態, 網站設定, 維護與備份).
import { api, ApiError } from '../../api'
import type { MaintenanceRun } from './maintenance'

export type Report = {
  generated_at: string
  content: { documents: number; trashed: number; versions: number; published: number; collections: number; tags: number; images: number; videos: number }
  storage: { versions_bytes: number; images_bytes: number; videos_bytes: number; database_bytes: number | null; disk: { total_bytes: number; free_bytes: number } | null }
  members: {
    total: number; active: number; pending: number; disabled: number
    by_role: { admin: number; editor: number; viewer: number }; active_admins: number; mfa_enabled: number
  }
  jobs: {
    pending_deletions: number; oldest_pending_deletion: string | null; unindexed_documents: number
    unused_images: number; unused_images_bytes: number
    unused_videos: number; unused_videos_bytes: number
  }
  config: { https: boolean; google_login: boolean; smtp: boolean; mfa_key: boolean; html_preview: boolean; max_upload_bytes: number; max_batch: number }
  warnings: { level: 'info' | 'warning' | 'danger'; key: string; text: string }[]
  maintenance: MaintenanceRun | null
}

export async function loadReport(): Promise<Report> {
  try {
    return await api<Report>('/api/admin/system/')
  } catch (cause) {
    throw new Error(cause instanceof ApiError && cause.status === 403 ? '只有 Admin 可以查看系統狀態。' : '無法載入系統狀態。')
  }
}

const units = ['B', 'KB', 'MB', 'GB', 'TB']
export function bytes(value: number | null | undefined) {
  if (value == null) return '—'
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++ }
  return `${size >= 100 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`
}
