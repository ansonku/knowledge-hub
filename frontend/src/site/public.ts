import type { CollectionColor, Format } from '../app/types'

/** Shapes returned by the public (visitor) API; see backend/documents/publication.py. */
export type PublicCollection = { id: string; name: string; color: CollectionColor | '' }
export type PublicCollectionCount = PublicCollection & { article_count: number }
export type PublicCard = {
  document_id: string
  title: string
  format: Format
  published_at: string
  excerpt: string
  reading_minutes: number
  collection: PublicCollection | null
}
export type PublicCardPage = { results: PublicCard[]; page: number; pages: number; count: number }
export type PublicArticle = {
  title: string
  format: Format
  body: string
  published_at: string
  reading_minutes: number
  collection: PublicCollection | null
  siblings: { document_id: string; title: string }[]
}

const publishedDate = new Intl.DateTimeFormat('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit' })
export const publicDate = (value: string) => publishedDate.format(new Date(value))
export const markOf = (name: string) => Array.from(name)[0]?.toUpperCase() ?? '?'
export const colorClass = (collection: PublicCollection | null) => `ui-col-${collection?.color || 'gray'}`

/** Fetch without credentials-dependent redirects: visitors are expected here. */
export async function publicApi<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin', signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw Object.assign(new Error(response.status === 404 ? '找不到內容。' : '暫時無法載入，請稍後再試。'), { status: response.status })
  return response.json() as Promise<T>
}
