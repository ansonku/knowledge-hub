export type Format = 'html' | 'md'
export type Label = { id: string; name: string }
/** A tag from /api/tags/, with the number of non-trashed documents carrying it. */
export type TagItem = Label & { document_count?: number }
export type CollectionColor = 'blue' | 'teal' | 'green' | 'amber' | 'orange' | 'red' | 'purple' | 'gray'
export type Category = Label & {
  parent: string | null
  description?: string
  color?: CollectionColor | ''
  /** Direct, non-trashed documents (not including sub-collections). */
  document_count?: number
}

export type DocumentRow = {
  id: string
  title: string
  format: Format
  category: string | null
  category_name: string | null
  tags: Label[]
  current_version: { number: number }
  is_public?: boolean
  is_favorite?: boolean
  /** Published version number, or null when the document is private. */
  published_version?: number | null
  updated_at: string
}

export type Visibility = 'public' | 'private' | 'lagging'

/** Public / lagging / private state derived from list or detail fields. */
export function visibilityOf(row: Pick<DocumentRow, 'published_version' | 'is_public' | 'current_version'>) {
  const published = row.published_version
  if (!published && !row.is_public) return { kind: 'private' as const, label: '私人' }
  if (published && published < row.current_version.number) {
    return { kind: 'lagging' as const, label: `公開 · 落後 ${row.current_version.number - published} 版` }
  }
  return { kind: 'public' as const, label: '公開' }
}

export type DocumentPage = {
  count: number
  page: number
  page_size: number
  results: DocumentRow[]
  limits: { bytes: number; batch: number }
}

export const formatLabel = (format: Format) => (format === 'html' ? 'HTML' : 'Markdown')

const timeOnly = new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit', hour12: false })
const monthDay = new Intl.DateTimeFormat('zh-TW', { month: '2-digit', day: '2-digit' })
const fullDate = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium' })
const fullDateTime = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short' })

/** Compact timestamp for lists: 今天 14:32 · 昨天 09:10 · 11/18 · 2025/03/02 */
export function shortDate(value: string, now = new Date()) {
  const date = new Date(value)
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const day = 24 * 60 * 60 * 1000
  if (date.getTime() >= startOfToday) return `今天 ${timeOnly.format(date)}`
  if (date.getTime() >= startOfToday - day) return `昨天 ${timeOnly.format(date)}`
  if (date.getFullYear() === now.getFullYear()) return monthDay.format(date)
  return fullDate.format(date)
}

export const longDateTime = (value: string) => fullDateTime.format(new Date(value))
