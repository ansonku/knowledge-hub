import { followSetup } from '../api'
import type { SearchMatches } from '../searchTerms'
import { computed, ref, type Ref } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import type { CollectionColor, Format } from '../app/types'

/** Shapes returned by the public (visitor) API; see backend/documents/publication.py. */
export type PublicCollection = { id: string; name: string; color: CollectionColor | '' }
/** A collection on the path to a published article (decision 6, revised in P5b). */
export type PublicNode = PublicCollection & { parent: string | null; depth: number; article_count: number; total_count: number }
/** `date` is the publication date on the public site and the last update in the member portal. */
/** P21b: an article's cover (a thumbnail; url is null for an album without pictures). P22: count is null unless an album. */
export type AlbumCover = { url: string | null; count: number | null }
export type PublicNavArticle = { document_id: string; title: string; collection_id: string | null; date: string; cover?: AlbumCover }
export type PublicNav = { collections: PublicNode[]; articles: PublicNavArticle[] }
export type PublicCard = {
  document_id: string
  title: string
  format: Format
  /** Public site: publication date. Member portal: `updated_at` instead, plus `public`. */
  published_at?: string
  updated_at?: string
  public?: boolean
  excerpt: string
  cover?: AlbumCover
  /** P16: present when the list was searched. */
  matches?: SearchMatches
  reading_minutes: number
  collection: PublicCollection | null
  path: PublicCollection[]
}
export type PublicCardPage = { results: PublicCard[]; page: number; pages: number; count: number }
export type PublicArticle = {
  title: string
  format: Format
  body: string
  /** Sizes of this site's pictures the article shows, for gallery layouts. */
  image_sizes?: Record<string, [number, number]>
  presentation?: 'article' | 'gallery'
  gallery_layout?: string
  /** Linked documents the reader may open (published ones on the public site). */
  linked_documents?: string[]
  published_at?: string
  updated_at?: string
  public?: boolean
  version_number?: number
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
  if (response.status === 503) followSetup(503, await response.clone().json().catch(() => null))  // P24
  if (!response.ok) throw Object.assign(new Error(response.status === 404 ? '找不到內容。' : '暫時無法載入，請稍後再試。'), { status: response.status })
  return response.json() as Promise<T>
}

// ---- Portal modes -------------------------------------------------------------------------------------
/**
 * The same portal renders two sites: the public knowledge site (/articles/, published articles only,
 * no login) and the member reading portal (/read/, every readable document, login required).
 */
export type PortalMode = 'public' | 'member'
export const portals = {
  public: {
    nav: '/api/public/nav/', list: '/api/public/articles/', article: (id: string) => `/api/public/articles/${encodeURIComponent(id)}/`,
    home: 'site-home', articleRoute: 'public-article',
  },
  member: {
    nav: '/api/read/nav/', list: '/api/read/articles/', article: (id: string) => `/api/read/articles/${encodeURIComponent(id)}/`,
    home: 'read-home', articleRoute: 'read-article',
  },
} as const
export const portalMode = (route: RouteLocationNormalizedLoaded): PortalMode => route.meta.portal === 'member' ? 'member' : 'public'
export const cardDate = (item: { published_at?: string; updated_at?: string }) => item.published_at ?? item.updated_at ?? ''

// ---- Shared navigation data (one request per portal) -------------------------------------------------------
type RawNav = { collections: PublicNode[]; articles: (Omit<PublicNavArticle, 'date'> & { published_at?: string; updated_at?: string })[] }
const caches: Record<PortalMode, { nav: Ref<PublicNav>; loaded: Ref<boolean>; pending?: Promise<void> }> = {
  public: { nav: ref({ collections: [], articles: [] }), loaded: ref(false) },
  member: { nav: ref({ collections: [], articles: [] }), loaded: ref(false) },
}

export function usePublicNav(mode: PortalMode = 'public') {
  const cache = caches[mode]
  const nav = cache.nav
  const navLoaded = cache.loaded
  function load(force = false) {
    if (cache.pending && !force) return cache.pending
    cache.pending = publicApi<RawNav>(portals[mode].nav)
      .then(data => {
        nav.value = { collections: data.collections, articles: data.articles.map(article => ({ ...article, date: cardDate(article) })) }
        navLoaded.value = true
      })
      .catch(() => { cache.pending = undefined })
    return cache.pending
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
    !latest || article.date > latest ? article.date : latest, null))
  void load()
  return { nav, navLoaded, load, byId, childrenOf, articlesOf, pathIds, subtree, ordered, lastUpdated }
}
