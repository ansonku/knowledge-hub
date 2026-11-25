// P11b: `:::gallery [layout]` blocks in Markdown.
//
//   :::gallery masonry
//   ![機箱正面](/api/images/…/)
//   ![背板接口](/api/images/…/)
//   :::
//
// The pictures inside become one gallery; anything else inside the block (text, videos, linked pictures)
// is shown right below it. Raw HTML stays off: the layout name comes from a fixed list and every value
// written into the output is escaped.
import type { MarkdownIt, StateBlock, StateCore, Token } from 'markdown-it'

export const GALLERY_LAYOUTS = ['justified', 'grid', 'masonry', 'vertical', 'carousel'] as const
export type GalleryLayout = (typeof GALLERY_LAYOUTS)[number]
export const LAYOUT_LABELS: Record<GalleryLayout, string> = {
  justified: '齊邊', grid: '方格', masonry: '瀑布流', vertical: '直列', carousel: '輪播',
}
/** Until the system setting exists (P11d), galleries without a layout name use this one. */
export const DEFAULT_LAYOUT: GalleryLayout = 'justified'

export type GalleryContext = {
  /** {image id: [width, height]} for this site's images, so layouts know shapes before pictures load. */
  imageSizes?: Record<string, [number, number]>
  galleryDefault?: GalleryLayout
  /** The editor's split preview: show hints about mistakes in gallery blocks. */
  hints?: boolean
}
type Picture = { src: string; alt: string; title: string }
type GalleryMeta = { layout: GalleryLayout; asked: string; pictures: Picture[]; leftover: boolean }

const OPEN = /^:::[ \t]*gallery(?:[ \t]+([^\s]+))?[ \t]*$/i
const CLOSE = /^:::[ \t]*$/
const SITE_IMAGE = /^\/api\/images\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/$/
const VIDEO = /^\/api\/videos\//

function block(state: StateBlock, startLine: number, endLine: number, silent: boolean) {
  if (state.sCount[startLine] - state.blkIndent >= 4) return false
  const text = (line: number) => state.src.slice(state.bMarks[line] + state.tShift[line], state.eMarks[line])
  const opening = OPEN.exec(text(startLine))
  if (!opening) return false
  if (silent) return true
  let next = startLine
  let closed = false
  while (++next < endLine) {
    const indent = state.sCount[next]
    const content = text(next)
    if (content && indent < state.blkIndent) break
    if (indent - state.blkIndent < 4 && CLOSE.test(content)) { closed = true; break }
  }
  const parent = state.parentType, lineMax = state.lineMax
  state.parentType = 'gallery' as typeof state.parentType
  state.lineMax = next
  const open = state.push('gallery_open', 'div', 1)
  open.block = true
  open.info = opening[1] ?? ''
  open.map = [startLine, next]
  state.md.block.tokenize(state, startLine + 1, next)
  state.push('gallery_close', 'div', -1).block = true
  state.parentType = parent
  state.lineMax = lineMax
  state.line = next + (closed ? 1 : 0)
  return true
}

/** A paragraph made only of pictures (and line breaks) feeds the gallery; anything else stays as content. */
function picturesOf(inline: Token | undefined, md: MarkdownIt): Picture[] | undefined {
  const parts = inline?.children ?? []
  const pictures: Picture[] = []
  for (const part of parts) {
    if (part.type === 'softbreak' || part.type === 'hardbreak' || (part.type === 'text' && !part.content.trim())) continue
    const src = part.type === 'image' ? String(part.attrGet('src') ?? '') : ''
    if (!src || VIDEO.test(src)) return undefined
    pictures.push({ src, alt: md.renderer.renderInlineAsText(part.children ?? [], md.options, {}), title: String(part.attrGet('title') ?? '') })
  }
  return pictures.length ? pictures : undefined
}

function collect(state: StateCore) {
  const tokens = state.tokens
  const out: Token[] = []
  for (let index = 0; index < tokens.length; index++) {
    const open = tokens[index]
    if (open.type !== 'gallery_open') { out.push(open); continue }
    let depth = 1, end = index + 1
    for (; end < tokens.length; end++) {
      if (tokens[end].type === 'gallery_open') depth++
      else if (tokens[end].type === 'gallery_close' && --depth === 0) break
    }
    const inner = tokens.slice(index + 1, end)
    const pictures: Picture[] = []
    const rest: Token[] = []
    for (let at = 0; at < inner.length; at++) {
      const token = inner[at]
      const found = token.type === 'paragraph_open' && inner[at + 2]?.type === 'paragraph_close' ? picturesOf(inner[at + 1], state.md) : undefined
      if (found) { pictures.push(...found); at += 2; continue }
      // Nested galleries are flattened into this one's leftover content.
      if (token.type !== 'gallery_open' && token.type !== 'gallery_close') rest.push(token)
    }
    const asked = open.info.trim().toLowerCase()
    const known = (GALLERY_LAYOUTS as readonly string[]).includes(asked)
    const gallery = new state.Token('gallery', 'div', 0)
    gallery.block = true
    gallery.map = open.map
    gallery.level = open.level
    gallery.meta = { layout: known ? asked : '', asked: open.info.trim(), pictures, leftover: rest.length > 0 } satisfies Omit<GalleryMeta, 'layout'> & { layout: string }
    for (const token of rest) token.level = Math.max(0, token.level - 1)
    out.push(gallery, ...rest)
    index = end
  }
  state.tokens = out
}

export function galleryPlugin(md: MarkdownIt) {
  md.block.ruler.before('fence', 'gallery', block, { alt: ['paragraph', 'reference', 'blockquote', 'list'] })
  md.core.ruler.push('gallery', collect)
  md.renderer.rules.gallery = (tokens, index, _options, context) => {
    const env = context as GalleryContext
    const token = tokens[index]
    const meta = token.meta as GalleryMeta
    const escape = md.utils.escapeHtml
    const layout = (meta.layout || env.galleryDefault || DEFAULT_LAYOUT) as GalleryLayout
    const line = token.attrGet('data-source-line') ?? ''
    const lineAttr = line === '' ? '' : ` data-source-line="${escape(String(line))}"`
    const hints: string[] = []
    if (env.hints) {
      if (meta.asked && !meta.layout) hints.push(`不認得的版面「${meta.asked}」，改用預設版面。可用：${GALLERY_LAYOUTS.join('、')}。`)
      if (!meta.pictures.length) hints.push('相簿裡還沒有圖片：每行放一張 ![說明](網址)。')
      if (meta.leftover) hints.push('相簿區塊裡只能放圖片，其他內容顯示在相簿下方。')
    }
    const items = meta.pictures.map((picture, position) => {
      const id = SITE_IMAGE.exec(picture.src)?.[1]
      const size = id ? env.imageSizes?.[id] : undefined
      const ratio = size && size[1] ? (size[0] / size[1]).toFixed(4) : '1.3333'
      const dimensions = size ? ` width="${size[0]}" height="${size[1]}"` : ''
      const title = picture.title ? ` title="${escape(picture.title)}"` : ''
      const image = `<img src="${escape(picture.src)}" alt="${escape(picture.alt)}"${title}${dimensions} loading="lazy" referrerpolicy="no-referrer">`
      const caption = layout === 'vertical' && picture.alt ? `<figcaption>${escape(picture.alt)}</figcaption>` : ''
      return `<figure class="g-item" data-index="${position}" style="--r:${ratio}"${size ? '' : ' data-unsized=""'}>${image}${caption}</figure>`
    })
    const head = `<div class="md-gallery" data-layout="${layout}" data-count="${items.length}"${lineAttr}>`
    const notes = hints.map(hint => `<p class="md-gallery-hint" role="note">${escape(hint)}</p>`).join('')
    if (layout !== 'carousel' || !items.length) return `${head}${notes}<div class="g-items">${items.join('')}</div></div>\n`
    const thumbs = meta.pictures.map((picture, position) =>
      `<button type="button" class="g-thumb" data-index="${position}" aria-label="第 ${position + 1} 張${picture.alt ? `：${escape(picture.alt)}` : ''}"><img class="g-thumb-img" src="${escape(picture.src)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>`)
    return `${head}${notes}<div class="g-stage"><div class="g-viewport"><div class="g-items">${items.join('')}</div></div>`
      + '<button type="button" class="g-arrow g-prev" aria-label="上一張">‹</button><button type="button" class="g-arrow g-next" aria-label="下一張">›</button></div>'
      + `<div class="g-bar"><span class="g-caption"></span><span class="g-count">1 / ${items.length}</span>`
      + '<button type="button" class="g-autoplay" aria-pressed="false">自動播放</button></div>'
      + `<div class="g-thumbs"><div class="g-thumbs-track">${thumbs.join('')}</div></div></div>\n`
  }
}
