<script setup lang="ts">
// P17: pick a document to link to by browsing collections (one level at a time) or by searching everything.
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { computed, nextTick, ref, watch } from 'vue'
import { api } from './api'
import UiIcon from './app/components/UiIcon.vue'
import { shortDate, type DocumentPage, type DocumentRow } from './app/types'
import HighlightText from './HighlightText.vue'
import { searchTerms } from './searchTerms'
import { UNCATEGORIZED, useTaxonomy } from './stores/taxonomy'

const props = defineProps<{
  visible: boolean
  /** Where to start: the collection of the document being edited. */
  startCategory?: string | null
  /** The document being edited, which is never offered. */
  excludeId?: string
}>()
const emit = defineEmits<{ pick: [row: DocumentRow]; cancel: []; closed: [] }>()

const taxonomy = useTaxonomy()
const filter = ref('')
const category = ref<string>(UNCATEGORIZED)
const collapsed = ref(new Set<string>())
const rows = ref<DocumentRow[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const failed = ref('')
const active = ref(0)
const input = ref<HTMLInputElement>()
const list = ref<HTMLElement>()
const treePane = ref<HTMLElement>()
let request = 0

const terms = computed(() => searchTerms(filter.value))
const searching = computed(() => terms.value.length > 0)
const shown = computed(() => rows.value.filter(row => row.id !== props.excludeId))
const more = computed(() => rows.value.length < total.value)
/** The document being edited is counted by the server but never listed. */
const count = computed(() => total.value - (rows.value.some(row => row.id === props.excludeId) ? 1 : 0))
const visibleNodes = computed(() => taxonomy.tree.filter(node =>
  !taxonomy.pathOf(node.id).slice(0, -1).some(ancestor => collapsed.value.has(ancestor.id))))
const heading = computed(() => searching.value ? `搜尋「${filter.value.trim()}」`
  : category.value === UNCATEGORIZED ? '未分類' : taxonomy.pathLabel(category.value))

async function load(reset = true) {
  const current = ++request
  if (reset) { page.value = 1; active.value = 0 }
  loading.value = true
  failed.value = ''
  const params = new URLSearchParams({ page: String(page.value) })
  if (searching.value) params.set('q', terms.value.join(' '))
  else {
    params.set('category', category.value)
    if (category.value !== UNCATEGORIZED) params.set('category_scope', 'direct')
    params.set('ordering', 'title')
  }
  try {
    const data = await api<DocumentPage>(`/api/documents/?${params}`)
    if (current !== request) return
    rows.value = reset ? data.results : [...rows.value, ...data.results]
    total.value = data.count
  } catch (cause) {
    if (current === request) failed.value = cause instanceof Error ? cause.message : '無法載入文件。'
  } finally {
    if (current === request) loading.value = false
  }
}
function loadMore() {
  page.value += 1
  void load(false)
}

watch(() => props.visible, open => {
  if (!open) return
  filter.value = ''
  collapsed.value = new Set()
  const start = props.startCategory && taxonomy.byId(props.startCategory) ? props.startCategory
    : taxonomy.tree[0]?.id ?? UNCATEGORIZED
  category.value = start
  void load()
  // The starting collection may be far down a long tree (or a short one on a phone).
  window.setTimeout(() => treePane.value?.querySelector('.node-button.on')?.scrollIntoView({ block: 'nearest' }), 350)
})
let typing = 0
watch(filter, () => {
  window.clearTimeout(typing)
  typing = window.setTimeout(() => void load(), 200)
})

function choose(id: string) {
  category.value = id
  if (searching.value) filter.value = ''
  else void load()
}
function toggle(id: string) {
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsed.value = next
}

function reveal() {
  void nextTick(() => list.value?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }))
}
function onListKey(event: KeyboardEvent) {
  if (event.isComposing) return
  const count = shown.value.length
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (count) active.value = Math.min(count - 1, Math.max(0, active.value + (event.key === 'ArrowDown' ? 1 : -1)))
    reveal()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const row = shown.value[active.value]
    if (row) emit('pick', row)
  }
}
/** Tree: arrows move between collections, Right/Left open and close a branch, Enter shows it. */
function onTreeKey(event: KeyboardEvent, id: string) {
  const buttons = Array.from((event.currentTarget as HTMLElement).closest('.tree')?.querySelectorAll<HTMLElement>('.node-button') ?? [])
  const position = buttons.indexOf(event.currentTarget as HTMLElement)
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    buttons[Math.min(buttons.length - 1, Math.max(0, position + (event.key === 'ArrowDown' ? 1 : -1)))]?.focus()
  } else if ((event.key === 'ArrowRight' && collapsed.value.has(id)) || (event.key === 'ArrowLeft' && !collapsed.value.has(id))) {
    if (taxonomy.tree.find(node => node.id === id)?.hasChildren) {
      event.preventDefault()
      toggle(id)
    }
  }
}
function pathOf(row: DocumentRow) {
  return taxonomy.pathLabel(row.category)
}
</script>

<template>
  <Dialog :visible="visible" header="選擇文件" modal :style="{ width: 'min(96vw, 52rem)' }" class="doc-picker-dialog"
    @update:visible="open => { if (!open) emit('cancel') }" @show="input?.focus()" @after-hide="emit('closed')">
    <div class="picker">
      <label class="filter">
        <UiIcon name="search" :size="15" />
        <span class="ui-visually-hidden">搜尋全部文件</span>
        <input ref="input" v-model="filter" type="search" autofocus placeholder="搜尋全部文件，或從左邊的集合挑選" autocomplete="off"
          aria-controls="picker-list" @keydown="onListKey">
      </label>
      <div class="panes">
        <nav ref="treePane" class="tree-pane" aria-label="集合">
          <ul class="tree">
            <li v-for="node in visibleNodes" :key="node.id" class="node" :style="{ '--depth': node.depth }">
              <button v-if="node.hasChildren" type="button" class="twisty" tabindex="-1" :aria-label="collapsed.has(node.id) ? `展開「${node.name}」` : `收合「${node.name}」`"
                @click="toggle(node.id)">
                <UiIcon :name="collapsed.has(node.id) ? 'chevronRight' : 'chevronDown'" :size="14" />
              </button>
              <span v-else class="twisty-space" />
              <button type="button" class="node-button" :class="{ on: !searching && category === node.id }"
                :aria-current="!searching && category === node.id ? 'true' : undefined" :aria-expanded="node.hasChildren ? !collapsed.has(node.id) : undefined"
                @click="choose(node.id)" @keydown="onTreeKey($event, node.id)">
                <span class="ui-col-mark mark" :class="`ui-col-${node.color || 'gray'}`" aria-hidden="true">{{ Array.from(node.name)[0]?.toUpperCase() }}</span>
                <span class="name">{{ node.name }}</span>
              </button>
            </li>
            <li class="node" style="--depth: 0">
              <span class="twisty-space" />
              <button type="button" class="node-button" :class="{ on: !searching && category === UNCATEGORIZED }"
                :aria-current="!searching && category === UNCATEGORIZED ? 'true' : undefined"
                @click="choose(UNCATEGORIZED)" @keydown="onTreeKey($event, UNCATEGORIZED)">
                <span class="name muted">未分類</span>
              </button>
            </li>
          </ul>
        </nav>
        <section class="list-pane" :aria-label="heading" :aria-busy="loading">
          <p class="list-head">{{ heading }}<span v-if="!loading" class="count">{{ count }} 份</span></p>
          <p v-if="failed" class="state error">{{ failed }} <button type="button" class="link" @click="load()">重試</button></p>
          <ul v-else-if="shown.length" id="picker-list" ref="list" class="docs" role="listbox" aria-label="文件">
            <li v-for="(row, index) in shown" :key="row.id" role="option" class="doc" :aria-selected="index === active"
              @mousemove="active = index" @click="active = index" @dblclick="emit('pick', row)">
              <span class="doc-title"><HighlightText :text="row.title" :terms="terms" /></span>
              <span class="doc-meta"><template v-if="searching">{{ pathOf(row) }} · </template>{{ shortDate(row.updated_at) }}</span>
            </li>
          </ul>
          <p v-else-if="!loading" class="state">{{ searching ? '找不到符合的文件。' : '這個集合這一層沒有文件；子集合請在左邊展開。' }}</p>
          <button v-if="more && !failed" type="button" class="more" :disabled="loading" @click="loadMore">載入更多</button>
        </section>
      </div>
    </div>
    <template #footer>
      <span class="hint">↑↓ 選擇 · Enter 插入 · 雙擊插入 · Esc 取消</span>
      <Button label="取消" text severity="secondary" @click="emit('cancel')" />
      <Button label="插入連結" :disabled="!shown[active]" @click="shown[active] && emit('pick', shown[active])" />
    </template>
  </Dialog>
</template>

<style scoped>
.picker { display: grid; gap: var(--ui-space-3); }
.filter {
  display: flex; align-items: center; gap: var(--ui-space-2); padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-muted);
}
.filter:focus-within { outline: 2px solid var(--ui-accent); outline-offset: -1px; }
.filter input { flex: 1; min-width: 0; padding: .55rem 0; border: 0; background: transparent; color: var(--ui-text); font: inherit; outline: none; }
.panes { display: grid; grid-template-columns: minmax(12rem, 16rem) minmax(0, 1fr); gap: var(--ui-space-3); height: min(26rem, 58vh); }
.tree-pane, .list-pane { min-height: 0; overflow-y: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
.tree { list-style: none; margin: 0; padding: var(--ui-space-1); }
.node { display: flex; align-items: center; padding-left: calc(var(--depth) * .9rem); }
.twisty, .twisty-space { flex: none; width: 1.4rem; height: 1.6rem; }
.twisty { display: grid; place-items: center; border: 0; background: none; color: var(--ui-text-muted); cursor: pointer; border-radius: var(--ui-radius-sm); }
.node-button {
  flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--ui-space-2); padding: .3rem .4rem; border: 0;
  border-radius: var(--ui-radius-sm); background: none; color: var(--ui-text); font: inherit; font-size: var(--ui-text-sm); text-align: left; cursor: pointer;
}
.node-button:hover { background: var(--ui-bg-subtle); }
.node-button.on { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-weight: 600; }
.node-button:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: -2px; }
.mark { flex: none; width: 1.25rem; height: 1.25rem; font-size: .7rem; }
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.muted { color: var(--ui-text-muted); }
.list-pane { display: flex; flex-direction: column; }
.list-head { position: sticky; top: 0; display: flex; justify-content: space-between; gap: var(--ui-space-2); margin: 0; padding: .5rem .75rem;
  border-bottom: 1px solid var(--ui-border); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); font-weight: 600; }
.count { color: var(--ui-text-muted); font-weight: 400; }
.docs { list-style: none; margin: 0; padding: var(--ui-space-1); }
.doc { display: grid; gap: 1px; padding: .45rem .6rem; border-radius: var(--ui-radius-sm); cursor: pointer; }
.doc[aria-selected="true"] { background: var(--ui-accent-soft); }
.doc-title { color: var(--ui-text); font-weight: 500; overflow-wrap: anywhere; }
.doc[aria-selected="true"] .doc-title { color: var(--ui-accent-on-soft); }
.doc-meta { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.state { margin: 0; padding: var(--ui-space-4); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.state.error { color: var(--ui-danger); }
.link { border: 0; background: none; color: var(--ui-accent); cursor: pointer; font: inherit; }
.more { margin: var(--ui-space-2) auto var(--ui-space-3); padding: .3rem .8rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-pill);
  background: var(--ui-bg-surface); color: var(--ui-accent); font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.hint { margin-right: auto; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
@media (max-width: 640px) {
  .panes { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(8rem, 30vh) minmax(10rem, 1fr); height: min(34rem, 66vh); }
  .hint { display: none; }
}
</style>
