// P19 (E2＋): what in the management area needs attention — documents with broken links (Editors and Admins)
// and system warnings (Admins). Shown as marks on 管理, its groups and pages, and on the home page.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api'
import { useSession } from './session'

const FRESH_MS = 60_000

export const useAttention = defineStore('attention', () => {
  const session = useSession()
  const brokenDocuments = ref(0)
  const systemWarnings = ref(0)
  let loadedAt = 0
  let pending: Promise<void> | undefined

  async function load(force = false) {
    if (!session.canEdit) return
    if (!force && Date.now() - loadedAt < FRESH_MS) return
    if (pending) return pending
    pending = (async () => {
      const broken = api<{ documents: { issues: { severity: string }[] }[] }>('/api/admin/broken-links/')
        .then(report => { brokenDocuments.value = report.documents.filter(row => row.issues.some(item => item.severity === 'broken')).length })
        .catch(() => undefined)
      const system = session.isAdmin
        ? api<{ warnings: { level: string }[] }>('/api/admin/system/')
          .then(report => { systemWarnings.value = report.warnings.filter(note => note.level !== 'info').length })
          .catch(() => undefined)
        : Promise.resolve()
      await Promise.all([broken, system])
      loadedAt = Date.now()
    })().finally(() => { pending = undefined })
    return pending
  }

  /** Marks for a page of the management area: a number, a dot, or nothing. */
  function markOf(page: string): number | 'dot' | undefined {
    if (page === 'app-broken-links' && brokenDocuments.value) return brokenDocuments.value
    if (page === 'app-system' && systemWarnings.value) return 'dot'
    return undefined
  }
  const any = computed(() => brokenDocuments.value > 0 || systemWarnings.value > 0)
  return { brokenDocuments, systemWarnings, load, markOf, any }
})
