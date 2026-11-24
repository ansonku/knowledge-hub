import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api } from '../api'

export type SiteSettings = { name: string; tagline: string }

const DEFAULT_NAME = 'Knowledge Hub'

/**
 * Site name and tagline from /api/site/ (editable by Admins), plus the browser tab title.
 * Pages call setTitle('頁名'); the tab shows "頁名 · 站名" and follows later name changes.
 */
export const useSite = defineStore('site', () => {
  const name = ref(DEFAULT_NAME)
  const tagline = ref('')
  const loaded = ref(false)
  const page = ref<string | undefined>()
  let pending: Promise<void> | undefined

  function apply(settings: SiteSettings) {
    name.value = settings.name || DEFAULT_NAME
    tagline.value = settings.tagline
    loaded.value = true
  }

  function load() {
    pending ??= fetch('/api/site/', { cache: 'no-store', credentials: 'same-origin' })
      .then(response => response.ok ? response.json() as Promise<SiteSettings> : Promise.reject(new Error()))
      .then(apply)
      .catch(() => { pending = undefined })
    return pending
  }

  async function save(settings: SiteSettings) {
    apply(await api<SiteSettings>('/api/site/', 'PATCH', settings))
  }

  function setTitle(next?: string) {
    page.value = next
  }

  watch([page, name], ([current, site]) => {
    document.title = current ? `${current} · ${site}` : site
  })

  void load()
  return { name, tagline, loaded, load, save, setTitle }
})
