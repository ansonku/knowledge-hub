import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api } from '../api'

export type NoticeLevel = 'info' | 'warning' | 'urgent'
/** The announcement currently shown (P6c); `id` changes whenever an Admin edits it. */
export type SiteNotice = { id: string; text: string; link: string; level: NoticeLevel }
/** The stored announcement, returned to Admins only. */
export type NoticeSettings = { enabled: boolean; text: string; link: string; level: NoticeLevel; starts_at: string | null; ends_at: string | null }
export type SiteSettings = { name: string; tagline: string; notice?: SiteNotice | null; notice_settings?: NoticeSettings }

const DEFAULT_NAME = 'Knowledge Hub'

/**
 * Site name and tagline from /api/site/ (editable by Admins), plus the browser tab title.
 * Pages call setTitle('頁名'); the tab shows "頁名 · 站名" and follows later name changes.
 */
export const useSite = defineStore('site', () => {
  const name = ref(DEFAULT_NAME)
  const tagline = ref('')
  const notice = ref<SiteNotice | null>(null)
  const noticeSettings = ref<NoticeSettings>()
  const loaded = ref(false)
  const page = ref<string | undefined>()
  let pending: Promise<void> | undefined

  function apply(settings: SiteSettings) {
    name.value = settings.name || DEFAULT_NAME
    tagline.value = settings.tagline
    notice.value = settings.notice ?? null
    noticeSettings.value = settings.notice_settings
    loaded.value = true
  }

  function load() {
    pending ??= fetch('/api/site/', { cache: 'no-store', credentials: 'same-origin' })
      .then(response => response.ok ? response.json() as Promise<SiteSettings> : Promise.reject(new Error()))
      .then(apply)
      .catch(() => { pending = undefined })
    return pending
  }

  async function save(settings: Pick<SiteSettings, 'name' | 'tagline'>) {
    apply(await api<SiteSettings>('/api/site/', 'PATCH', settings))
  }

  async function saveNotice(settings: NoticeSettings) {
    apply(await api<SiteSettings>('/api/site/notice/', 'PUT', settings))
  }

  /** Reload, e.g. after signing in, so Admins receive the stored announcement settings. */
  function refresh() {
    pending = undefined
    return load()
  }

  function setTitle(next?: string) {
    page.value = next
  }

  watch([page, name], ([current, site]) => {
    document.title = current ? `${current} · ${site}` : site
  })

  void load()
  return { name, tagline, notice, noticeSettings, loaded, load, refresh, save, saveNotice, setTitle }
})
