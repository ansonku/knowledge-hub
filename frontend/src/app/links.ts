// P13: links between documents (client side).
import { api } from '../api'

/** Addresses that name a document of this site: /app/docs/<id>/, /read/<id>/, /articles/<id>/. */
export const DOC_LINK = /^\/(?:app\/docs|read|articles)\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\/|$)/i

export type LinkTarget = { status: 'ok' | 'trashed' | 'missing'; title?: string; category_name?: string | null }

/** The document id an anchor points to, when it is a link to one of this site's documents. */
export function linkedDocument(anchor: HTMLAnchorElement) {
  try {
    const url = new URL(anchor.getAttribute('href') ?? '', location.href)
    if (url.origin !== location.origin) return undefined
    return DOC_LINK.exec(url.pathname)?.[1]?.toLowerCase()
  } catch {
    return undefined
  }
}

const cache = new Map<string, { at: number; target: LinkTarget }>()
const FRESH = 60_000

/** States of linked documents, asked once a minute at most per id. */
export async function resolveLinks(ids: string[]): Promise<Record<string, LinkTarget>> {
  const now = Date.now()
  const wanted = [...new Set(ids)].filter(id => (cache.get(id)?.at ?? 0) < now - FRESH)
  for (let start = 0; start < wanted.length; start += 200) {
    const chunk = wanted.slice(start, start + 200)
    try {
      const found = await api<Record<string, LinkTarget>>(`/api/documents/resolve/?ids=${chunk.join(',')}`)
      for (const id of chunk) if (found[id]) cache.set(id, { at: now, target: found[id] })
    } catch {
      // Without states, links simply stay plain links.
    }
  }
  return Object.fromEntries(ids.filter(id => cache.has(id)).map(id => [id, cache.get(id)!.target]))
}

/** Before moving documents to the trash: how many other documents link to each. Failures count as none. */
export async function incomingLinks(ids: string[]): Promise<Record<string, number>> {
  if (!ids.length) return {}
  try {
    return await api<Record<string, number>>(`/api/documents/incoming-links/?ids=${ids.join(',')}`)
  } catch {
    return {}
  }
}
