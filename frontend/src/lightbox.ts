// P11a: the image lightbox for rendered Markdown (reading page, split preview, public article).
// Loaded on demand by MarkdownBody, so pages without images never download PhotoSwipe.
import PhotoSwipe from 'photoswipe'
import type { SlideData } from 'photoswipe'
import 'photoswipe/style.css'
import './lightbox.css'

export type LightboxEffect = 'center' | 'zoom' | 'fade'
export type LightboxLook = {
  effect: LightboxEffect
  /** Multiplies every duration: 0.75 fast, 1 standard, 1.25 slow. */
  speed: number
  /** Opacity of the dark backdrop. */
  backdrop: number
  /** Follow the browser's reduced-motion preference (no animation). Off: always animate. Default on. */
  respectReducedMotion?: boolean
}
/** The "standard" look picked on the comparison page (UI_REDESIGN.md 10.11). */
export const STANDARD_LOOK: LightboxLook = { effect: 'center', speed: 1, backdrop: 0.92 }
export type LightboxOptions = {
  /** Members get a download button for this site's images. */
  download: boolean
  look?: LightboxLook
}

// "Background first, then the picture grows out of the middle." Standard values picked on the comparison page
// (2026-11-25, revised): backdrop 300 ms, picture after 150 ms over 650 ms from 84 %, ease in-out.
const CENTER = { backdrop: 300, delay: 150, grow: 650, scale: 0.84, close: 400, easing: 'cubic-bezier(.4, 0, .2, 1)' }
const ZOOM = { open: 600, close: 400, easing: 'cubic-bezier(.4, 0, .2, 1)' }
const FADE = { open: 300, close: 250 }
const SITE_IMAGE = /^\/api\/images\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/$/
const FALLBACK = { width: 1600, height: 1200 }

const icon = (path: string) => `<svg class="pswp__icn" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg>`

/** Real pixel size of a picture; waits for it when the page has not loaded it yet (lazy images). */
function measure(image: HTMLImageElement): Promise<{ width: number; height: number }> {
  if (image.complete && image.naturalWidth) return Promise.resolve({ width: image.naturalWidth, height: image.naturalHeight })
  return new Promise(resolve => {
    const probe = new Image()
    const timer = setTimeout(() => resolve(FALLBACK), 6000)
    probe.onload = () => { clearTimeout(timer); resolve({ width: probe.naturalWidth || FALLBACK.width, height: probe.naturalHeight || FALLBACK.height }) }
    probe.onerror = () => { clearTimeout(timer); resolve(FALLBACK) }
    probe.referrerPolicy = 'no-referrer'
    probe.src = image.currentSrc || image.src
  })
}

function onScreen(element: Element | undefined) {
  const box = element?.getBoundingClientRect()
  return !!box && box.width > 0 && box.bottom > 0 && box.right > 0 && box.top < innerHeight && box.left < innerWidth
}

type Item = SlideData & { element: HTMLImageElement; alt: string; path: string }

/** Opens the pictures of one group (in page order) at `index`. Resolves once the lightbox is closed. */
export async function openLightbox(images: HTMLImageElement[], index: number, options: LightboxOptions) {
  const look = options.look ?? STANDARD_LOOK
  // Browsers on virtual desktops often report reduced motion although nobody asked for it; Admins can
  // choose to animate anyway (system setting).
  const still = look.respectReducedMotion !== false && matchMedia('(prefers-reduced-motion: reduce)').matches
  const items: Item[] = images.map(element => {
    const src = element.currentSrc || element.src
    const known = element.complete && element.naturalWidth
    return {
      element, src, msrc: src, alt: element.alt, path: new URL(src, location.href).pathname,
      width: known ? element.naturalWidth : FALLBACK.width, height: known ? element.naturalHeight : FALLBACK.height,
    }
  })
  // The opened picture needs its real size before the animation; the others catch up while browsing.
  Object.assign(items[index], await measure(images[index]))
  const speed = (ms: number) => Math.round(ms * look.speed)
  const effect = still ? 'none' : look.effect
  const pswp = new PhotoSwipe({
    dataSource: items, index,
    bgOpacity: look.backdrop,
    showHideAnimationType: effect === 'center' ? 'fade' : effect,
    showAnimationDuration: speed(effect === 'center' ? CENTER.backdrop : effect === 'zoom' ? ZOOM.open : FADE.open),
    hideAnimationDuration: speed(effect === 'center' ? CENTER.close : effect === 'zoom' ? ZOOM.close : FADE.close),
    easing: effect === 'zoom' ? ZOOM.easing : CENTER.easing,
    wheelToZoom: true, secondaryZoomLevel: 2, maxZoomLevel: 4, preload: [1, 2],
    paddingFn: viewport => ({ top: 48, bottom: items.length > 1 ? (viewport.x < 640 ? 104 : 124) : 56, left: 0, right: 0 }),
    closeTitle: '關閉（Esc）', zoomTitle: '縮放', arrowPrevTitle: '上一張', arrowNextTitle: '下一張',
    errorMsg: '圖片無法載入。', indexIndicatorSep: ' / ',
  })

  // Only animate from or to a thumbnail the reader can see; otherwise the lightbox fades.
  pswp.addFilter('thumbEl', (element, data) => onScreen((data as Item).element) ? (data as Item).element : undefined as never)
  pswp.addFilter('placeholderSrc', (src, content) => (content.data as Item).msrc || src)

  const holder = () => pswp.currSlide?.holderElement
  const hideThumb = (hidden: boolean) => {
    const thumb = items[pswp.currIndex]?.element
    if (thumb) thumb.style.visibility = hidden ? 'hidden' : ''
  }
  pswp.on('openingAnimationStart', () => {
    if (effect === 'zoom') hideThumb(true)
    if (effect !== 'center') return
    // The CSS scale property composes with PhotoSwipe's own transforms instead of replacing them.
    holder()?.animate([{ opacity: 0, scale: CENTER.scale }, { opacity: 1, scale: 1 }],
      { duration: speed(CENTER.grow), delay: speed(CENTER.delay), easing: CENTER.easing, fill: 'backwards' })
  })
  pswp.on('openingAnimationEnd', () => { if (effect === 'zoom') hideThumb(false) })
  pswp.on('closingAnimationStart', () => {
    if (effect === 'zoom') hideThumb(true)
    if (effect !== 'center') return
    holder()?.animate([{ opacity: 1, scale: 1 }, { opacity: 0, scale: (1 + CENTER.scale) / 2 }],
      { duration: speed(CENTER.close * 0.7), easing: 'cubic-bezier(.4, 0, 1, 1)', fill: 'forwards' })
  })
  pswp.on('destroy', () => { for (const item of items) item.element.style.visibility = '' })

  pswp.on('uiRegister', () => {
    pswp.ui?.registerElement({
      name: 'caption', appendTo: 'root', className: 'hub-pswp-caption',
      onInit: element => {
        element.setAttribute('aria-live', 'polite')
        const show = () => {
          const text = items[pswp.currIndex]?.alt.trim() ?? ''
          element.textContent = text
          element.hidden = !text
        }
        pswp.on('change', show)
        show()
      },
    })
    if (options.download) pswp.ui?.registerElement({
      name: 'download', order: 8, isButton: true, tagName: 'a', title: '下載原圖', html: icon('M12 4v11M7 10l5 5 5-5M5 20h14'),
      onInit: element => {
        const link = element as HTMLAnchorElement
        link.setAttribute('download', '')
        // Only this site's images: they are the stored copies the member may already read.
        const set = () => {
          const item = items[pswp.currIndex]
          const own = !!item && SITE_IMAGE.test(item.path)
          link.hidden = !own
          if (own) link.href = item.path
          else link.removeAttribute('href')
        }
        pswp.on('change', set)
        set()
      },
    })
    if (document.fullscreenEnabled) pswp.ui?.registerElement({
      name: 'fullscreen', order: 9, isButton: true, title: '全螢幕', html: icon('M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5'),
      onClick: () => { void (document.fullscreenElement ? document.exitFullscreen() : pswp.element?.requestFullscreen()) },
    })
    if (items.length > 1) pswp.ui?.registerElement({
      name: 'thumbnails', appendTo: 'root', className: 'hub-pswp-thumbs',
      onInit: element => {
        element.setAttribute('role', 'group')
        element.setAttribute('aria-label', '所有圖片')
        const buttons = items.map((item, position) => {
          const button = document.createElement('button')
          button.type = 'button'
          button.dataset.index = String(position)
          button.setAttribute('aria-label', `第 ${position + 1} 張${item.alt ? `：${item.alt}` : ''}`)
          const thumb = document.createElement('img')
          thumb.alt = ''
          thumb.referrerPolicy = 'no-referrer'
          thumb.src = item.src ?? ''
          button.append(thumb)
          return button
        })
        element.append(...buttons)
        element.addEventListener('click', event => {
          const button = (event.target as Element).closest('button')
          if (button) pswp.goTo(Number(button.dataset.index))
        })
        const mark = () => {
          buttons.forEach((button, position) => {
            const current = position === pswp.currIndex
            button.classList.toggle('current', current)
            button.setAttribute('aria-current', String(current))
          })
          buttons[pswp.currIndex]?.scrollIntoView({ block: 'nearest', inline: 'center' })
        }
        pswp.on('change', mark)
        mark()
      },
    })
  })

  // Sizes of pictures the page has not loaded yet arrive while the reader browses.
  items.forEach((item, position) => {
    if (position === index || (item.element.complete && item.element.naturalWidth)) return
    void measure(item.element).then(size => {
      Object.assign(item, size)
      if (!pswp.isDestroying) pswp.refreshSlideContent(position)
    })
  })

  const closed = new Promise<void>(resolve => pswp.on('destroy', () => resolve()))
  pswp.init()
  return closed
}
