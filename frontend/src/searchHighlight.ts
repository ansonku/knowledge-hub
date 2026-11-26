// P16c: mark every match of the search words inside a rendered article and step through them.
// Works on text nodes only (never HTML strings), and puts the text back when closed.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { termPattern } from './searchTerms'

const SKIP = 'script, style, svg, textarea, video, .katex-mathml, mark.search-hit'
const MARK = 'search-hit in-doc'

type Options = {
  /** The rendered article (its text is searched). */
  root: () => HTMLElement | undefined
  terms: () => string[]
  /** Changes whenever the article re-renders, so the marks are put back. */
  content: () => unknown
  /** False while the article is not shown (editing, HTML in a sandbox). */
  enabled: () => boolean
  onClose: () => void
}

export function useSearchHighlight(options: Options) {
  const marks = shallowRef<HTMLElement[]>([])
  const index = ref(0)
  const active = computed(() => options.enabled() && options.terms().length > 0)
  let scrolledFor = ''

  function clear(root = options.root()) {
    if (!root) return
    const parents = new Set<Node>()
    for (const mark of Array.from(root.querySelectorAll<HTMLElement>('mark.in-doc'))) {
      const parent = mark.parentNode
      if (!parent) continue
      parent.replaceChild(document.createTextNode(mark.textContent ?? ''), mark)
      parents.add(parent)
    }
    for (const parent of parents) parent.normalize()
    marks.value = []
  }

  function apply() {
    const root = options.root()
    clear(root)
    if (!root || !active.value) return
    const pattern = termPattern(options.terms())
    if (!pattern) return
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: node => (node.parentElement?.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    })
    const nodes: Text[] = []
    for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text)
    for (const node of nodes) {
      const text = node.data
      const found = Array.from(text.matchAll(pattern))
      if (!found.length) continue
      const fragment = document.createDocumentFragment()
      let last = 0
      for (const match of found) {
        const start = match.index ?? 0
        if (start > last) fragment.append(text.slice(last, start))
        const mark = document.createElement('mark')
        mark.className = MARK
        mark.textContent = match[0]
        fragment.append(mark)
        last = start + match[0].length
      }
      if (last < text.length) fragment.append(text.slice(last))
      node.replaceWith(fragment)
    }
    marks.value = Array.from(root.querySelectorAll<HTMLElement>('mark.in-doc'))
    index.value = Math.min(index.value, Math.max(0, marks.value.length - 1))
    // Scroll to the first match once per set of words; later re-renders keep the reader where they are.
    const key = options.terms().join(' ')
    show(scrolledFor !== key)
    scrolledFor = key
  }

  function show(scroll: boolean) {
    marks.value.forEach((mark, position) => mark.classList.toggle('current', position === index.value))
    const current = marks.value[index.value]
    if (scroll && current) current.scrollIntoView({ block: 'center' })
  }

  function move(step: number) {
    const count = marks.value.length
    if (!count) return
    index.value = (index.value + step + count) % count
    show(true)
  }

  function close() {
    clear()
    scrolledFor = ''
    index.value = 0
    options.onClose()
  }

  let frame = 0
  function schedule() {
    cancelAnimationFrame(frame)
    // After the Markdown body's own post-render work (galleries, link marks).
    void nextTick(() => { frame = requestAnimationFrame(apply) })
  }
  watch(() => [options.root(), options.content(), options.terms().join(' '), options.enabled()], schedule, { flush: 'post' })

  function onKey(event: KeyboardEvent) {
    if (!active.value || event.isComposing || event.defaultPrevented) return
    const target = event.target as HTMLElement | null
    const inBar = Boolean(target?.closest('.search-bar'))
    const typing = target?.closest('input, textarea, select, [contenteditable="true"], .monaco-editor')
    if (typing && !inBar) return
    // Dialogs and the lightbox handle their own keys.
    if (document.querySelector('.p-dialog, .pswp, .p-confirmdialog')) return
    if (event.key === 'Enter' && marks.value.length && (inBar || !target?.closest('a, button'))) {
      event.preventDefault()
      move(event.shiftKey ? -1 : 1)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      close()
    }
  }
  onMounted(() => document.addEventListener('keydown', onKey))
  onBeforeUnmount(() => {
    document.removeEventListener('keydown', onKey)
    cancelAnimationFrame(frame)
  })

  return { active, count: computed(() => marks.value.length), index, next: () => move(1), previous: () => move(-1), close }
}
