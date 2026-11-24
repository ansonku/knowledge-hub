import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import { useSession } from './session'
import { useTaxonomy } from './taxonomy'

type Counted = { count: number }

/** Small counters shown in navigation (sidebar badges, home "needs attention"). */
export const useWorkspace = defineStore('workspace', () => {
  const lagging = ref(0)
  const uncategorized = ref(0)
  const trash = ref(0)
  let last = 0
  let pending: Promise<void> | undefined

  async function refresh(force = false) {
    if (pending) return pending
    if (!force && Date.now() - last < 15_000) return
    const session = useSession()
    pending = (async () => {
      try {
        const [lag, loose, trashed] = await Promise.all([
          api<Counted>('/api/documents/?visibility=lagging'),
          api<Counted>('/api/documents/?category=uncategorized'),
          session.canEdit ? api<Counted>('/api/trash/') : Promise.resolve({ count: 0 }),
          force ? useTaxonomy().load() : Promise.resolve(),
        ])
        lagging.value = lag.count
        uncategorized.value = loose.count
        trash.value = trashed.count
        last = Date.now()
      } catch {
        // Counters are decorative; keep the previous values.
      } finally {
        pending = undefined
      }
    })()
    return pending
  }

  return { lagging, uncategorized, trash, refresh }
})
