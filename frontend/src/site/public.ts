import { computed, ref } from 'vue'
import type { CollectionColor, Format } from '../app/types'

/** Shapes returned by the public (visitor) API; see backend/documents/publication.py. */
export type PublicCollection = { id: string; name: string; color: CollectionColor | '' }
/** A collection on the path to a published article (decision 6, revised in P5b). */
export type PublicNode = PublicCollection & { parent: string | null; depth: number; article_count: number; total_count: number }
export type PublicNavArticle = { document_id: string; title: string; collection_id: string | null; published_at: string }
export type PublicNav = { collections: PublicNode[]; articles: PublicNavArticle[] }
export type PublicCard = {
  document_id: string
  title: string
  format: Format
  published_at: string
  excerpt: string
  reading_minutes: number
  collection: PublicCollection | null
  path: PublicCollection[]
}
export type PublicCardPage = { results: PublicCard[]; page: number; pages: number; count: number }
export type PublicArticle = {
  title: string
  format: Format
  body: string
  published_at: string
  reading_minutes: number
  collection: PublicCollection | null
  path: PublicCollection[]
  siblings: { document_id: string; title: string }[]
}

const publishedDate = new Intl.DateTimeFormat('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit' })
const monthDay = new Intl.DateTimeFormat('zh-TW', { month: '2-digit', day: '2-digit' })
export const publicDate = (value: string) => publishedDate.format(new Date(value))
export const shortPublicDate = (value: string) => monthDay.format(new Date(value))
export const markOf = (name: string) => Array.from(name)[0]?.toUpperCase() ?? '?'
export const colorClass = (collection: Pick<PublicCollection, 'color'> | null | undefined) => `ui-col-${collection?.color || 'gray'}`
/** Inline style exposing a collection's colour as CSS variables for bands and bars. */
export const collectionStyle = (collection: Pick<PublicCollection, 'color'> | null | undefined) => {
  const color = collection?.color || 'gray'
  return { '--col-bg': `var(--ui-col-${color}-bg)`, '--col-fg': `var(--ui-col-${color}-fg)` }
}

/** Fetch without credentials-dependent redirects: visitors are expected here. */
export async function publicApi<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin', signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw Object.assign(new Error(response.status === 404 ? '找不到內容。' : '暫時無法載入，請稍後再試。'), { status: response.status })
  return response.json() as Promise<T>
}

// ---- Shared navigation data (one request for the whole public site) ----------------------------------
const nav = ref<PublicNav>({ collections: [], articles: [] })
const navLoaded = ref(false)
let pending: Promise<void> | undefined

export function usePublicNav() {
  function load(force = false) {
    if (pending && !force) return pending
    pending = publicApi<PublicNav>('/api/public/nav/')
      .then(data => { nav.value = data; navLoaded.value = true })
      .catch(() => { pending = undefined })
    return pending
  }
  const byId = (id: string | null | undefined) => nav.value.collections.find(node => node.id === id)
  const childrenOf = (id: string | null) => nav.value.collections.filter(node => node.parent === id)
  const articlesOf = (id: string | null) => nav.value.articles.filter(article => article.collection_id === id)
  /** Collection ids from the root down to `id`. */
  function pathIds(id: string | null | undefined) {
    const ids: string[] = []
    let node = byId(id)
    while (node && !ids.includes(node.id)) {
      ids.unshift(node.id)
      node = byId(node.parent)
    }
    return ids
  }
  function subtree(id: string): string[] {
    return [id, ...childrenOf(id).flatMap(child => subtree(child.id))]
  }
  /** Reading order used by the navigation and by previous/next links. */
  const ordered = computed(() => {
    const result: PublicNavArticle[] = []
    const walk = (parent: string | null) => {
      for (const node of childrenOf(parent)) {
        result.push(...articlesOf(node.id))
        walk(node.id)
      }
    }
    walk(null)
    result.push(...articlesOf(null))
    return result
  })
  const lastUpdated = computed(() => nav.value.articles.reduce<string | null>((latest, article) =>
    !latest || article.published_at > latest ? article.published_at : latest, null))
  void load()
  return { nav, navLoaded, load, byId, childrenOf, articlesOf, pathIds, subtree, ordered, lastUpdated }
}
