// P16: search words and highlighting, matching the server: whitespace-separated words, case-insensitive substrings.
export type SearchMatches = { fields: ('title' | 'collection' | 'tags' | 'body')[]; snippets: string[] }

export const MAX_TERMS = 10

export function searchTerms(keywords: string | undefined | null): string[] {
  return (keywords ?? '').normalize('NFC').trim().split(/\s+/).filter(Boolean).slice(0, MAX_TERMS)
}

/** One pattern for every word, longest first so a longer word wins over its prefix. */
export function termPattern(terms: string[]): RegExp | undefined {
  const words = [...new Set(terms.filter(Boolean))].sort((a, b) => b.length - a.length)
  if (!words.length) return undefined
  return new RegExp(words.map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'giu')
}

/** Text split into plain and matched parts, for rendering with <mark> without HTML. */
export function splitMatches(text: string, terms: string[]): { text: string; hit: boolean }[] {
  const pattern = termPattern(terms)
  if (!pattern || !text) return [{ text, hit: false }]
  const parts: { text: string; hit: boolean }[] = []
  let last = 0
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0
    if (start > last) parts.push({ text: text.slice(last, start), hit: false })
    parts.push({ text: match[0], hit: true })
    last = start + match[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), hit: false })
  return parts
}

const FIELD_LABELS: Record<SearchMatches['fields'][number], string> = { title: '標題', collection: '集合', tags: '標籤', body: '內文' }
/** 「符合：標題、標籤」 for results without a body snippet. */
export function matchedFields(matches: SearchMatches | undefined) {
  const fields = (matches?.fields ?? []).filter(field => field !== 'body')
  return fields.length ? `符合：${fields.map(field => FIELD_LABELS[field]).join('、')}` : ''
}
