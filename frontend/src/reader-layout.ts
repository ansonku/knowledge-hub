import { ref, watch } from 'vue'
import type { Ref } from 'vue'

type Format = 'md' | 'html'
type Layout = 'standard' | 'wide' | 'full'

export const layouts: { value: Layout; label: string }[] = [
  { value: 'standard', label: '標準' },
  { value: 'wide', label: '寬版' },
  { value: 'full', label: '全頁' },
]
const preferenceKey = (format: Format) => `knowledge-hub.${format}.reader-layout`

export function useReaderLayout(format: Readonly<Ref<Format | undefined>>) {
  const layout = ref<Layout>('standard')
  const lastContainedLayout = ref<Exclude<Layout, 'full'>>('standard')

  function restoreLayout(kind: Format) {
    lastContainedLayout.value = 'standard'
    layout.value = kind === 'html' ? 'full' : 'standard'
    try {
      const stored = localStorage.getItem(preferenceKey(kind))
      if (stored === 'standard' || stored === 'wide' || stored === 'full') layout.value = stored
      if (layout.value !== 'full') lastContainedLayout.value = layout.value
    } catch {
      // Browser storage may be disabled.
    }
  }

  watch(layout, value => {
    if (value !== 'full') lastContainedLayout.value = value
    if (!format.value) return
    try {
      localStorage.setItem(preferenceKey(format.value), value)
    } catch {
      // Keep the current preference for this page.
    }
  })

  function toggleFullPage() {
    layout.value = layout.value === 'full' ? lastContainedLayout.value : 'full'
  }

  return { layout, restoreLayout, toggleFullPage }
}

export function jumpToHeading(article: HTMLElement | undefined, id: string, updateAddress = true) {
  const target = article?.querySelector<HTMLElement>(`[id="${id}"]`)
  if (!target) return
  target.focus({ preventScroll: true })
  target.scrollIntoView({ block: 'start' })
  if (updateAddress) history.replaceState(history.state, '', `#${id}`)
}
