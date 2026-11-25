<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
// Pictures inside links keep opening the link; diagrams and pending placeholders are not photos.
function lightboxImages() {
  return Array.from(root.value?.querySelectorAll<HTMLImageElement>('img') ?? [])
    .filter(image => image.getAttribute('src') && !image.closest('a, figure[data-diagram]'))
}
let lightboxModule: Promise<typeof import('./lightbox')> | undefined
const loadLightbox = () => (lightboxModule ??= import('./lightbox'))
function prepareImages() {
  if (!props.lightbox) return
  const images = lightboxImages()
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
  const images = lightboxImages()
  const index = images.indexOf(target)
  if (index < 0) return
  event.preventDefault()
  opening = true
  try {
    const { openLightbox } = await loadLightbox()
    void openLightbox(images, index, { download: props.download })
  } finally {
    opening = false
  }
}
function onImageKey(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') void openImage(event.target, event)
}

watch(() => props.rendered, () => { keepPlayers(); revision.value++ }, { flush: 'sync' })
watch(() => props.rendered, () => { restorePlayers(); renderDiagrams(); prepareImages() }, { flush: 'post' })
watch(renderer, () => { frameReady.value = false })
onMounted(() => {
  window.addEventListener('message', showResults)
  prepareImages()
})
onBeforeUnmount(() => {
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
.markdown-body :deep(img.zoomable:focus-visible) { outline: 2px solid var(--ui-accent, #1d4ed8); outline-offset: 2px; }
.markdown-body :deep(.md-pending) { color: #6b7a90; font-style: italic; }
.markdown-body :deep(.md-video) { display: block; margin: 1rem 0; }
.markdown-body :deep(.md-video video) { display: block; width: 100%; max-height: 75vh; border-radius: .5rem; background: #000; }
.markdown-body :deep(.md-video-error) { display: block; margin-top: .4rem; color: var(--ui-danger, #b42318); font-size: .9rem; }
.markdown-body :deep(.md-video-error[hidden]) { display: none; }
</style>
