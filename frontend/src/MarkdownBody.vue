<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { enhanceGalleries } from './galleryView'
import { useSite } from './stores/site'
import type { RenderedMarkdown } from './markdown'

const props = withDefaults(defineProps<{
  rendered: RenderedMarkdown
  /** Clicking a picture opens it in the lightbox. */
  lightbox?: boolean
  /** Members get a "download" button in the lightbox for this site's images. */
  download?: boolean
}>(), { lightbox: true, download: false })
const root = ref<HTMLElement>()
const renderer = ref<HTMLIFrameElement>()
const frameReady = ref(false)
const revision = ref(0)
let currentId = ''
let diagramUrls: string[] = []

function releaseUrls() {
  for (const url of diagramUrls) URL.revokeObjectURL(url)
  diagramUrls = []
}

function renderDiagrams() {
  currentId = ''
  releaseUrls()
  if (!frameReady.value || !renderer.value?.contentWindow || !props.rendered.diagrams.length) return
  currentId = crypto.randomUUID()
  renderer.value.contentWindow.postMessage({
    type: 'diagram-render', id: currentId, diagrams: props.rendered.diagrams.slice(0, 20),
  }, '*')
}

function showResults(event: MessageEvent) {
  if (!currentId || !renderer.value?.contentWindow || event.source !== renderer.value.contentWindow || event.origin !== 'null') return
  const data = event.data
  if (data?.type !== 'diagram-result' || data.id !== currentId || !Array.isArray(data.results)) return
  currentId = ''
  const figures = root.value?.querySelectorAll('figure[data-diagram]')
  for (const [index, svg] of data.results.entries()) {
    const figure = figures?.[index]
    if (!figure) continue
    if (typeof svg !== 'string' || !svg.startsWith('<svg')) {
      const message = document.createElement('figcaption')
      message.textContent = '圖表無法繪製，以下為原始圖表語法。'
      figure.prepend(message)
      continue
    }
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
    diagramUrls.push(url)
    const image = document.createElement('img')
    image.src = url
    image.alt = 'Mermaid 圖表'
    image.addEventListener('load', () => figure.querySelector('pre')?.remove(), { once: true })
    figure.prepend(image)
  }
}

// ---- Videos --------------------------------------------------------------------
// The split preview re-renders a moment after each keystroke. Players already on the page are carried over
// (matched by address and order), so a video keeps playing while the writer types around it.
let players = new Map<string, HTMLVideoElement>()
function videoKeys(scope: ParentNode) {
  const seen = new Map<string, number>()
  return Array.from(scope.querySelectorAll<HTMLVideoElement>('video[data-video]')).map(video => {
    const source = video.getAttribute('src') ?? ''
    const count = seen.get(source) ?? 0
    seen.set(source, count + 1)
    return [`${source}#${count}`, video] as const
  })
}
function keepPlayers() {
  players = root.value ? new Map(videoKeys(root.value)) : new Map()
}
function restorePlayers() {
  if (root.value) {
    for (const [key, fresh] of videoKeys(root.value)) {
      const kept = players.get(key)
      if (!kept || kept === fresh) continue
      fresh.replaceWith(kept)
      // The hint follows its own player's state.
      const hint = kept.nextElementSibling
      if (hint instanceof HTMLElement && hint.classList.contains('md-video-error')) hint.hidden = !kept.error
    }
  }
  players = new Map()
}
/** Media errors do not bubble; this listens in the capture phase and reveals the hint under that player. */
function onMediaError(event: Event) {
  const video = event.target
  if (!(video instanceof HTMLVideoElement) || !video.hasAttribute('data-video')) return
  const hint = video.nextElementSibling
  if (hint instanceof HTMLElement && hint.classList.contains('md-video-error')) hint.hidden = false
}

// ---- Lightbox (P11a) -------------------------------------------------------------
// Pictures inside links keep opening the link; diagrams, carousel thumbnails and pending placeholders are
// not photos. A gallery's pictures are one group (in their written order); the rest of the page is another.
const photo = (image: HTMLImageElement) => !!image.getAttribute('src') && !image.closest('a, figure[data-diagram], .g-thumb')
function lightboxImages(from?: HTMLImageElement) {
  const gallery = from?.closest<HTMLElement>('.md-gallery')
  if (gallery) {
    return Array.from(gallery.querySelectorAll<HTMLImageElement>('.g-item img'))
      .sort((a, b) => Number(a.closest<HTMLElement>('.g-item')?.dataset.index) - Number(b.closest<HTMLElement>('.g-item')?.dataset.index))
  }
  return Array.from(root.value?.querySelectorAll<HTMLImageElement>('img') ?? []).filter(image => photo(image) && !image.closest('.md-gallery'))
}
const site = useSite()
let lightboxModule: Promise<typeof import('./lightbox')> | undefined
const loadLightbox = () => (lightboxModule ??= import('./lightbox'))
function prepareImages() {
  if (!props.lightbox) return
  const images = Array.from(root.value?.querySelectorAll<HTMLImageElement>('img') ?? []).filter(photo)
  for (const image of images) {
    image.classList.add('zoomable')
    image.tabIndex = 0
  }
  // Fetch the lightbox code while the reader is still reading, so the first click opens at once.
  if (images.length) {
    const idle = window.requestIdleCallback ?? ((callback: () => void) => window.setTimeout(callback, 600))
    idle(() => { void loadLightbox() })
  }
}
let opening = false
async function openImage(target: EventTarget | null, event: Event) {
  if (!props.lightbox || opening || !(target instanceof HTMLImageElement) || !target.classList.contains('zoomable')) return
  const images = lightboxImages(target)
  const index = images.indexOf(target)
  if (index < 0) return
  event.preventDefault()
  opening = true
  try {
    const { openLightbox } = await loadLightbox()
    // Site-wide choices (P11d): effect, speed, backdrop, and whether members may download.
    void openLightbox(images, index, { download: props.download && site.gallery.member_download, look: site.lightboxLook })
  } finally {
    opening = false
  }
}
function onImageKey(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') void openImage(event.target, event)
}

// ---- Galleries (P11b) -------------------------------------------------------------
let galleries: ReturnType<typeof enhanceGalleries> | undefined
let carouselSlides: number[] = []
function startGalleries() {
  if (!root.value) return
  galleries = enhanceGalleries(root.value, carouselSlides)
  clampAlbumText()
}
// Gallery mode (P11c): a long description folds to a few lines above the album, with a button to unfold.
function clampAlbumText() {
  const text = root.value?.querySelector<HTMLElement>('.md-album-text')
  if (!text || text.scrollHeight <= 300) return
  text.classList.add('clamped')
  const toggle = document.createElement('button')
  toggle.type = 'button'
  toggle.className = 'md-album-toggle'
  toggle.textContent = '顯示完整說明'
  toggle.setAttribute('aria-expanded', 'false')
  toggle.addEventListener('click', () => {
    const open = text.classList.toggle('clamped') === false
    toggle.textContent = open ? '收合說明' : '顯示完整說明'
    toggle.setAttribute('aria-expanded', String(open))
  })
  text.after(toggle)
}
function stopGalleries() {
  carouselSlides = galleries?.slides() ?? carouselSlides
  galleries?.stop()
  galleries = undefined
}

watch(() => props.rendered, () => { keepPlayers(); stopGalleries(); revision.value++ }, { flush: 'sync' })
watch(() => props.rendered, () => { restorePlayers(); renderDiagrams(); startGalleries(); prepareImages() }, { flush: 'post' })
watch(renderer, () => { frameReady.value = false })
onMounted(() => {
  window.addEventListener('message', showResults)
  startGalleries()
  prepareImages()
})
onBeforeUnmount(() => {
  stopGalleries()
  window.removeEventListener('message', showResults)
  releaseUrls()
})
</script>

<template>
  <article class="markdown-body" @error.capture="onMediaError" @click="openImage($event.target, $event)"
    @keydown="onImageKey">
    <!-- Rendered Markdown escapes raw HTML. Diagram output is inserted only as an image. -->
    <div :key="revision" ref="root" v-html="rendered.html" />
    <iframe v-if="rendered.diagrams.length" ref="renderer" src="/markdown-diagram.html" sandbox="allow-scripts"
      referrerpolicy="no-referrer" tabindex="-1" aria-hidden="true" title="Mermaid 圖表渲染"
      class="diagram-frame" @load="frameReady = true; renderDiagrams()" />
  </article>
</template>

<style scoped>
.diagram-frame { position: fixed; left: -10000px; top: 0; width: 960px; height: 640px; visibility: hidden; }
.markdown-body :deep(.katex-display) { overflow-x: auto; overflow-y: hidden; padding-block: .25rem; }
.markdown-body :deep(.task-list-item) { list-style: none; }
.markdown-body :deep(.task-list-item input) { margin-inline-end: .4rem; }
.markdown-body :deep(figure[data-diagram]) { margin: 1.25rem 0; overflow-x: auto; }
.markdown-body :deep(figure[data-diagram] img) { display: block; width: auto; max-width: 100%; }
.markdown-body :deep(figcaption) { color: #52647c; font-size: .9rem; }
.markdown-body :deep(code.hljs) { padding: 0; background: transparent; }
.markdown-body :deep(img.zoomable) { cursor: zoom-in; }
/* ---- Gallery mode (P11c) ---- */
.markdown-body :deep(.md-album-text.clamped) { max-height: 12rem; overflow: hidden; -webkit-mask-image: linear-gradient(#000 60%, transparent); mask-image: linear-gradient(#000 60%, transparent); }
.markdown-body :deep(.md-album-toggle) { margin: .25rem 0 0; padding: .25rem .75rem; border: 1px solid var(--ui-border, #e4e7ec); border-radius: .4rem; background: var(--ui-bg-surface, #fff); color: var(--ui-accent, #1d4ed8); font: inherit; font-size: .9rem; cursor: pointer; }
.markdown-body :deep(.md-album) { margin-top: 1.5rem; }
/* ---- Galleries (P11b) ---- */
.markdown-body :deep(.md-gallery) { margin: 1.25rem 0; }
.markdown-body :deep(.md-gallery-hint) { margin: 0 0 .5rem; padding: .35rem .7rem; border-radius: .4rem; background: var(--ui-lagging-bg, #fff6e5); color: var(--ui-lagging-text, #8a5a00); font-size: .88rem; }
.markdown-body :deep(.g-item) { position: relative; margin: 0; overflow: hidden; border-radius: .4rem; background: var(--ui-bg-subtle, #eef1f5); }
.markdown-body :deep(.g-item img) { display: block; width: 100%; max-width: none; margin: 0; border-radius: 0; }
/* justified: rows of equal height, widths follow each picture's shape */
.markdown-body :deep([data-layout="justified"] .g-items) { display: flex; flex-wrap: wrap; gap: 6px; }
.markdown-body :deep([data-layout="justified"] .g-items::after) { content: ""; flex-grow: 1000000; }
.markdown-body :deep([data-layout="justified"] .g-item) { flex-grow: calc(var(--r) * 100); flex-basis: calc(var(--r) * 190px); }
.markdown-body :deep([data-layout="justified"] .g-item img) { height: 100%; aspect-ratio: var(--r); object-fit: cover; }
/* grid: square tiles */
.markdown-body :deep([data-layout="grid"] .g-items) { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 6px; }
.markdown-body :deep([data-layout="grid"] .g-item) { aspect-ratio: 1; }
.markdown-body :deep([data-layout="grid"] .g-item img) { height: 100%; object-fit: cover; }
/* masonry: script fills the columns in reading order; plain CSS columns until then */
.markdown-body :deep([data-layout="masonry"] .g-items) { columns: 3 180px; column-gap: 8px; }
.markdown-body :deep([data-layout="masonry"] .g-items:not(.g-laid) .g-item) { break-inside: avoid; margin-bottom: 8px; }
.markdown-body :deep([data-layout="masonry"] .g-items.g-laid) { display: flex; gap: 8px; align-items: flex-start; columns: auto; }
.markdown-body :deep([data-layout="masonry"] .g-col) { flex: 1; min-width: 0; display: grid; gap: 8px; }
.markdown-body :deep([data-layout="masonry"] .g-item img) { height: auto; aspect-ratio: var(--r); }
/* vertical: one after another, caption below */
.markdown-body :deep([data-layout="vertical"] .g-items) { display: grid; gap: 1.5rem; }
.markdown-body :deep([data-layout="vertical"] .g-item) { overflow: visible; background: none; }
/* Tall (portrait) pictures stop at 80% of the screen height and sit in the middle. */
.markdown-body :deep([data-layout="vertical"] .g-item img) { width: auto; max-width: 100%; height: auto; max-height: 80vh; margin: 0 auto; aspect-ratio: var(--r); border-radius: .5rem; }
.markdown-body :deep([data-layout="vertical"] figcaption) { text-align: center; }
.markdown-body :deep([data-layout="vertical"] figcaption) { margin-top: .5rem; color: var(--ui-text-muted, #667085); font-size: .92rem; }
/* carousel: one large picture, arrows, caption and counter, thumbnail strip */
.markdown-body :deep([data-layout="carousel"]) { padding: .6rem; border: 1px solid var(--ui-border, #e4e7ec); border-radius: .6rem; }
.markdown-body :deep(.g-stage) { position: relative; }
.markdown-body :deep(.g-viewport) { overflow: hidden; border-radius: .4rem; background: #0d1017; }
.markdown-body :deep([data-layout="carousel"] .g-items) { display: flex; }
.markdown-body :deep([data-layout="carousel"] .g-item) { flex: 0 0 100%; min-width: 0; height: min(60vh, 32rem); display: grid; place-items: center; border-radius: 0; background: none; }
.markdown-body :deep([data-layout="carousel"] .g-item img) { width: auto; max-width: 100%; max-height: 100%; object-fit: contain; }
.markdown-body :deep(.g-arrow) { position: absolute; top: 50%; transform: translateY(-50%); width: 2.5rem; height: 2.5rem; border: 0; border-radius: 50%; background: rgb(255 255 255 / .85); color: #111; font-size: 1.4rem; line-height: 1; cursor: pointer; }
.markdown-body :deep(.g-prev) { left: .6rem; }
.markdown-body :deep(.g-next) { right: .6rem; }
.markdown-body :deep(.md-gallery:not(.g-ready) .g-arrow), .markdown-body :deep(.md-gallery[data-count="1"] .g-arrow) { display: none; }
.markdown-body :deep(.g-bar) { display: flex; align-items: center; gap: .75rem; margin: .5rem .15rem; font-size: .9rem; color: var(--ui-text-muted, #667085); }
.markdown-body :deep(.g-caption) { flex: 1; min-width: 0; color: var(--ui-text, #1d2939); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.markdown-body :deep(.g-autoplay) { padding: .2rem .7rem; border: 1px solid var(--ui-border, #e4e7ec); border-radius: .35rem; background: var(--ui-bg-surface, #fff); color: inherit; font: inherit; cursor: pointer; }
.markdown-body :deep(.g-thumbs) { overflow-x: auto; scrollbar-width: thin; }
.markdown-body :deep(.g-thumbs-track) { display: flex; gap: 6px; padding-bottom: 2px; }
.markdown-body :deep(.g-thumb) { flex: 0 0 5.5rem; height: 3.7rem; padding: 0; border: 2px solid transparent; border-radius: .35rem; overflow: hidden; background: #0d1017; opacity: .55; cursor: pointer; }
.markdown-body :deep(.g-thumb.current) { border-color: var(--ui-accent, #1d4ed8); opacity: 1; }
.markdown-body :deep(.g-thumb img) { display: block; width: 100%; height: 100%; object-fit: cover; margin: 0; }
@media (max-width: 640px) {
  .markdown-body :deep([data-layout="justified"] .g-item) { flex-basis: calc(var(--r) * 120px); }
  .markdown-body :deep([data-layout="grid"] .g-items) { grid-template-columns: repeat(3, 1fr); gap: 4px; }
  .markdown-body :deep([data-layout="carousel"] .g-item) { height: 16rem; }
  .markdown-body :deep(.g-thumb) { flex-basis: 4rem; height: 2.8rem; }
}
.markdown-body :deep(img.zoomable:focus-visible) { outline: 2px solid var(--ui-accent, #1d4ed8); outline-offset: 2px; }
.markdown-body :deep(.md-pending) { color: #6b7a90; font-style: italic; }
.markdown-body :deep(.md-video) { display: block; margin: 1rem 0; }
.markdown-body :deep(.md-video video) { display: block; width: 100%; max-height: 75vh; border-radius: .5rem; background: #000; }
.markdown-body :deep(.md-video-error) { display: block; margin-top: .4rem; color: var(--ui-danger, #b42318); font-size: .9rem; }
.markdown-body :deep(.md-video-error[hidden]) { display: none; }
</style>
