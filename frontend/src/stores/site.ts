import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api } from '../api'

export type NoticeLevel = 'info' | 'warning' | 'urgent'
/** The announcement currently shown (P6c); `id` changes whenever an Admin edits it. */
export type SiteNotice = { id: string; text: string; link: string; level: NoticeLevel }
/** The stored announcement, returned to Admins only. */
export type NoticeSettings = { enabled: boolean; text: string; link: string; level: NoticeLevel; starts_at: string | null; ends_at: string | null }
/** P11d: how pictures open and galleries lay out, site-wide (decision 27: choices only, no raw timings). */
export type GallerySettings = {
  effect: 'center' | 'zoom' | 'fade'
  speed: 'fast' | 'normal' | 'slow'
  /** Backdrop opacity in percent, 60–100. */
  backdrop: number
  layout: 'justified' | 'grid' | 'masonry' | 'vertical' | 'carousel'
  member_download: boolean
  /** Skip the animation when the browser asks for reduced motion (off: always animate). */
  respect_reduced_motion: boolean
  /** P20: seconds between pictures in the lightbox slideshow. */
  interval: 3 | 5 | 8 | 12
}
export const STANDARD_GALLERY: GallerySettings = { effect: 'center', speed: 'normal', backdrop: 92, layout: 'justified', member_download: true, respect_reduced_motion: true, interval: 5 }
export const SPEED_FACTORS: Record<GallerySettings['speed'], number> = { fast: 0.75, normal: 1, slow: 1.25 }
export type SiteSettings = {
  name: string; tagline: string; notice?: SiteNotice | null; notice_settings?: NoticeSettings; gallery?: GallerySettings
}

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
  const gallery = ref<GallerySettings>({ ...STANDARD_GALLERY })
  /** What the lightbox needs from the settings. */
  const lightboxLook = computed(() => ({
    effect: gallery.value.effect, speed: SPEED_FACTORS[gallery.value.speed] ?? 1, backdrop: gallery.value.backdrop / 100,
    respectReducedMotion: gallery.value.respect_reduced_motion !== false, interval: gallery.value.interval ?? 5,
  }))
  const loaded = ref(false)
  const page = ref<string | undefined>()
  let pending: Promise<void> | undefined

  function apply(settings: SiteSettings) {
    name.value = settings.name || DEFAULT_NAME
    tagline.value = settings.tagline
    notice.value = settings.notice ?? null
    noticeSettings.value = settings.notice_settings
    if (settings.gallery) gallery.value = settings.gallery
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

  async function saveGallery(settings: GallerySettings) {
    apply(await api<SiteSettings>('/api/site/gallery/', 'PUT', settings))
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
  return {
    name, tagline, notice, noticeSettings, gallery, lightboxLook, loaded, load, refresh, save, saveNotice, saveGallery, setTitle,
  }
})
