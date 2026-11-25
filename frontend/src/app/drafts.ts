// P12: unsaved Markdown drafts kept in this browser (localStorage), per account and document, so a crash,
// a closed tab or a reload does not lose them. Never sent to the server. Removed on save, on discard, on
// sign-out, and after three days. Every storage access is guarded: private windows and blocked storage
// simply mean no drafts.

export type Draft = {
  text: string
  /** The version the draft was edited from. */
  baseId: string
  baseNumber: number
  savedAt: number
}
export type DraftWrite = 'saved' | 'too-large' | 'unavailable'

const PREFIX = 'knowledge-hub.draft.'
export const DRAFT_TTL = 3 * 24 * 60 * 60 * 1000
export const DRAFT_MAX_BYTES = 2 * 1024 * 1024

const keyOf = (account: string, documentId: string) => `${PREFIX}${account}.${documentId}`

function storage(): Storage | undefined {
  try {
    return window.localStorage
  } catch {
    return undefined
  }
}

function parse(raw: string | null): Draft | undefined {
  if (!raw) return undefined
  try {
    const value = JSON.parse(raw) as Partial<Draft>
    if (typeof value.text !== 'string' || typeof value.baseId !== 'string' || typeof value.savedAt !== 'number') return undefined
    return { text: value.text, baseId: value.baseId, baseNumber: Number(value.baseNumber) || 0, savedAt: value.savedAt }
  } catch {
    return undefined
  }
}

export function readDraft(account: string, documentId: string): Draft | undefined {
  const store = storage()
  try {
    const draft = parse(store?.getItem(keyOf(account, documentId)) ?? null)
    if (draft && Date.now() - draft.savedAt > DRAFT_TTL) {
      store?.removeItem(keyOf(account, documentId))
      return undefined
    }
    return draft
  } catch {
    return undefined
  }
}

export function writeDraft(account: string, documentId: string, draft: Draft): DraftWrite {
  const store = storage()
  if (!store) return 'unavailable'
  if (new Blob([draft.text]).size > DRAFT_MAX_BYTES) {
    removeDraft(account, documentId)
    return 'too-large'
  }
  try {
    store.setItem(keyOf(account, documentId), JSON.stringify(draft))
    return 'saved'
  } catch {
    // Quota exceeded or storage blocked: editing goes on, only the safety net is missing.
    return 'unavailable'
  }
}

export function removeDraft(account: string, documentId: string) {
  try {
    storage()?.removeItem(keyOf(account, documentId))
  } catch {
    // Nothing to remove when storage is blocked.
  }
}

function keys() {
  const store = storage()
  const found: string[] = []
  try {
    for (let index = 0; store && index < store.length; index++) {
      const key = store.key(index)
      if (key?.startsWith(PREFIX)) found.push(key)
    }
  } catch {
    // Storage blocked: no drafts.
  }
  return found
}

/** On sign-out: this account's drafts leave the computer. */
export function removeAccountDrafts(account: string) {
  const store = storage()
  for (const key of keys()) {
    if (key.startsWith(`${PREFIX}${account}.`)) {
      try { store?.removeItem(key) } catch { /* blocked */ }
    }
  }
}

/** Drop drafts older than three days, of every account (run when the workspace opens). */
export function pruneDrafts() {
  const store = storage()
  for (const key of keys()) {
    try {
      const draft = parse(store?.getItem(key) ?? null)
      if (!draft || Date.now() - draft.savedAt > DRAFT_TTL) store?.removeItem(key)
    } catch {
      // Blocked: leave it.
    }
  }
}

/** This site's image ids a draft refers to (to warn about pictures removed by the 24-hour cleanup). */
export function draftImageIds(text: string) {
  return [...new Set(Array.from(text.matchAll(/\/api\/images\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\//g), match => match[1]))]
}
