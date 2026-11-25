// P11b: brings rendered `:::gallery` blocks to life. Masonry needs its columns filled in reading order,
// pictures without a known size get their shape once loaded, and carousels run on Embla (loaded on demand).
import type { EmblaCarouselType } from 'embla-carousel'

type Carousel = { gallery: HTMLElement; api: EmblaCarouselType; stop: () => void }

/** Columns for the available width: wide 4, medium 3, phone 2. */
const columnsFor = (width: number) => width >= 1000 ? 4 : width >= 700 ? 3 : width >= 340 ? 2 : 1

function layoutMasonry(gallery: HTMLElement) {
  const box = gallery.querySelector<HTMLElement>(':scope > .g-items')
  if (!box) return
  const count = columnsFor(box.clientWidth)
  if (box.dataset.columns === String(count)) return
  const items = Array.from(box.querySelectorAll<HTMLElement>('.g-item'))
    .sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index))
  const heights = Array<number>(count).fill(0)
  const columns = Array.from({ length: count }, () => Object.assign(document.createElement('div'), { className: 'g-col' }))
  for (const item of items) {
    // Each picture goes into the shortest column, so reading left to right follows the original order.
    const target = heights.indexOf(Math.min(...heights))
    columns[target].append(item)
    heights[target] += 1 / (Number(getComputedStyle(item).getPropertyValue('--r')) || 1.3333) + 0.03
  }
  box.replaceChildren(...columns)
  box.dataset.columns = String(count)
  box.classList.add('g-laid')
}

function watchUnsized(gallery: HTMLElement) {
  for (const item of Array.from(gallery.querySelectorAll<HTMLElement>('.g-item[data-unsized]'))) {
    const image = item.querySelector('img')
    if (!image) continue
    const apply = () => {
      if (!image.naturalWidth || !image.naturalHeight) return
      item.style.setProperty('--r', (image.naturalWidth / image.naturalHeight).toFixed(4))
      item.removeAttribute('data-unsized')
      if (gallery.dataset.layout === 'masonry') {
        const box = gallery.querySelector<HTMLElement>(':scope > .g-items')
        if (box) delete box.dataset.columns
        layoutMasonry(gallery)
      }
    }
    if (image.complete) apply()
    else image.addEventListener('load', apply, { once: true })
  }
}

async function startCarousel(gallery: HTMLElement, start: number): Promise<Carousel | undefined> {
  const viewport = gallery.querySelector<HTMLElement>('.g-viewport')
  if (!viewport) return
  const { default: EmblaCarousel } = await import('embla-carousel')
  if (!gallery.isConnected) return
  const api = EmblaCarousel(viewport, { loop: true, startIndex: start })
  const thumbs = Array.from(gallery.querySelectorAll<HTMLButtonElement>('.g-thumb'))
  const slides = Array.from(gallery.querySelectorAll<HTMLElement>('.g-item'))
  const caption = gallery.querySelector('.g-caption')
  const count = gallery.querySelector('.g-count')
  const autoplay = gallery.querySelector<HTMLButtonElement>('.g-autoplay')
  const show = () => {
    const index = api.selectedScrollSnap()
    thumbs.forEach((thumb, position) => {
      thumb.classList.toggle('current', position === index)
      thumb.setAttribute('aria-current', String(position === index))
    })
    thumbs[index]?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    if (caption) caption.textContent = slides[index]?.querySelector('img')?.alt ?? ''
    if (count) count.textContent = `${index + 1} / ${slides.length}`
  }
  api.on('select', show)
  show()
  let timer = 0
  const stop = () => {
    window.clearInterval(timer)
    timer = 0
    autoplay?.setAttribute('aria-pressed', 'false')
    if (autoplay) autoplay.textContent = '自動播放'
  }
  const onClick = (event: Event) => {
    const target = event.target as Element
    const thumb = target.closest<HTMLButtonElement>('.g-thumb')
    if (thumb) { api.scrollTo(Number(thumb.dataset.index)); return }
    if (target.closest('.g-prev')) { api.scrollPrev(); return }
    if (target.closest('.g-next')) { api.scrollNext(); return }
    if (target.closest('.g-autoplay')) {
      if (timer) { stop(); return }
      timer = window.setInterval(() => api.scrollNext(), 3500)
      autoplay?.setAttribute('aria-pressed', 'true')
      if (autoplay) autoplay.textContent = '停止播放'
    }
  }
  const onKey = (event: KeyboardEvent) => {
    if ((event.target as Element).closest('.g-thumbs, .g-stage') === null) return
    if (event.key === 'ArrowLeft') { event.preventDefault(); api.scrollPrev() }
    else if (event.key === 'ArrowRight') { event.preventDefault(); api.scrollNext() }
  }
  gallery.addEventListener('click', onClick)
  gallery.addEventListener('keydown', onKey)
  gallery.classList.add('g-ready')
  return {
    gallery, api,
    stop: () => {
      stop()
      gallery.removeEventListener('click', onClick)
      gallery.removeEventListener('keydown', onKey)
      api.destroy()
    },
  }
}

/**
 * Enhances every gallery under `root`. `previous` carries the slide each carousel was on (by position on
 * the page) so the split preview's re-render does not send them back to the first picture.
 * Returns a cleanup function and a way to read the carousels' current slides.
 */
export function enhanceGalleries(root: HTMLElement, previous: number[] = []) {
  const galleries = Array.from(root.querySelectorAll<HTMLElement>('.md-gallery'))
  const carousels: (Carousel | undefined)[] = []
  const observers: ResizeObserver[] = []
  let stopped = false
  galleries.forEach(gallery => watchUnsized(gallery))
  for (const gallery of galleries.filter(item => item.dataset.layout === 'masonry')) {
    layoutMasonry(gallery)
    const observer = new ResizeObserver(() => layoutMasonry(gallery))
    observer.observe(gallery)
    observers.push(observer)
  }
  galleries.filter(item => item.dataset.layout === 'carousel' && item.querySelector('.g-viewport'))
    .forEach((gallery, position) => {
      void startCarousel(gallery, previous[position] ?? 0).then(carousel => {
        if (stopped) carousel?.stop()
        else carousels[position] = carousel
      })
    })
  return {
    slides: () => carousels.map(carousel => carousel?.api.selectedScrollSnap() ?? 0),
    stop: () => {
      stopped = true
      observers.forEach(observer => observer.disconnect())
      carousels.forEach(carousel => carousel?.stop())
    },
  }
}
