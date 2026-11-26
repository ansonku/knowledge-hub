<script setup lang="ts">
// P14a: a document's outline with the section being read marked. Shared by the workspace inspector,
// the public article and the reading portal. The page scrolls the window; the list keeps the marked
// entry in view inside its own scrolling box.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type Heading = { id: string; text: string; level: number }
const props = defineProps<{
  headings: Heading[]
  /** The rendered article holding the headings (their ids are section-N). */
  root?: HTMLElement
  title?: string
}>()
const emit = defineEmits<{ jump: [id: string] }>()

const nav = ref<HTMLElement>()
const active = ref<string>()
// Indent relative to the shallowest heading, at most three steps.
const topLevel = computed(() => Math.min(...props.headings.map(heading => heading.level), 6))
const indent = (level: number) => `${.75 + Math.min(Math.max(0, level - topLevel.value), 2) * .75}rem`

let frame = 0
let holdUntil = 0
function measure() {
  frame = 0
  if (performance.now() < holdUntil || !props.root) return
  const elements = props.headings
    .map(heading => props.root?.querySelector<HTMLElement>(`[id="${heading.id}"]`))
    .filter((element): element is HTMLElement => Boolean(element))
  if (!elements.length) { active.value = undefined; return }
  // A heading counts as reached once it sits where a jump would put it (its scroll-margin), plus a little.
  const line = (parseFloat(getComputedStyle(elements[0]).scrollMarginTop) || 0) + 12
  let current = elements[0].id
  for (const element of elements) {
    if (element.getBoundingClientRect().top <= line) current = element.id
    else break
  }
  // At the very bottom the last sections may never reach the line: mark the last one shown.
  const bottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2
  if (bottom) {
    const shown = elements.filter(element => element.getBoundingClientRect().top < window.innerHeight)
    const last = shown[shown.length - 1]
    if (last && elements.indexOf(last) > elements.findIndex(element => element.id === current)) current = last.id
  }
  active.value = current
}
const schedule = () => { if (!frame) frame = requestAnimationFrame(measure) }

/** Keep the marked entry visible inside the nearest scrolling box (never scrolls the page itself). */
function reveal() {
  const link = nav.value?.querySelector<HTMLElement>('.outline-link.on')
  let box = nav.value?.parentElement ?? null
  while (box && box !== document.body) {
    const style = getComputedStyle(box)
    if (/(auto|scroll)/.test(style.overflowY) && box.scrollHeight > box.clientHeight) break
    box = box.parentElement
  }
  if (!link || !box || box === document.body) return
  const linkBox = link.getBoundingClientRect(), outer = box.getBoundingClientRect()
  const margin = 48
  if (linkBox.top < outer.top + margin) box.scrollTop -= outer.top + margin - linkBox.top
  else if (linkBox.bottom > outer.bottom - margin) box.scrollTop += linkBox.bottom - (outer.bottom - margin)
}
watch(active, () => void nextTick(reveal))

function choose(id: string) {
  active.value = id
  // The jump scrolls the page; keep the chosen entry marked even if it cannot reach the top (end of the page).
  holdUntil = performance.now() + 400
  emit('jump', id)
}

watch(() => [props.root, props.headings], () => schedule(), { flush: 'post' })
onMounted(() => {
  window.addEventListener('scroll', schedule, { passive: true })
  window.addEventListener('resize', schedule, { passive: true })
  schedule()
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', schedule)
  window.removeEventListener('resize', schedule)
  cancelAnimationFrame(frame)
})
</script>

<template>
  <nav ref="nav" class="outline" :aria-label="title ?? '本頁目錄'">
    <span v-if="title" class="outline-title">{{ title }}</span>
    <a v-for="heading in headings" :key="heading.id" :href="`#${heading.id}`" class="outline-link"
      :class="{ on: active === heading.id }" :aria-current="active === heading.id ? 'location' : undefined"
      :style="{ paddingInlineStart: indent(heading.level) }" @click.prevent="choose(heading.id)">{{ heading.text }}</a>
  </nav>
</template>

<style scoped>
.outline { display: flex; flex-direction: column; gap: 2px; }
.outline-title { margin-bottom: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }
.outline-link {
  padding-block: .3125rem; padding-inline-end: var(--ui-space-2); border-left: 2px solid var(--ui-border);
  color: var(--ui-text-secondary); font-size: var(--ui-text-sm); line-height: 1.45; text-decoration: none; overflow-wrap: anywhere;
}
.outline-link:hover { border-left-color: var(--ui-accent); color: var(--ui-accent); }
.outline-link.on { border-left-color: var(--ui-accent); color: var(--ui-accent-on-soft); font-weight: 600; background: var(--ui-accent-soft); }
.outline-link:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: -2px; }
</style>
