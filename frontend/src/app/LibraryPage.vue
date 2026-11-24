<script setup lang="ts">
import Button from 'primevue/button'
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Skeleton from 'primevue/skeleton'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { api, getCsrfToken } from '../api'
import PublicationDialog from '../PublicationDialog.vue'
import { useSession } from '../stores/session'
import { UNCATEGORIZED, useTaxonomy } from '../stores/taxonomy'
import BulkDialog, { type BulkAction } from './components/BulkDialog.vue'
import CollectionDialog from './components/CollectionDialog.vue'
import MetadataDialog from './components/MetadataDialog.vue'
import UiIcon from './components/UiIcon.vue'
import UploadDialog from './components/UploadDialog.vue'
import { formatLabel, longDateTime, shortDate, visibilityOf, type Category, type DocumentPage, type DocumentRow, type Format, type Visibility } from './types'
import { useSite } from '../stores/site'

const site = useSite()
const emit = defineEmits<{ upload: [] }>()
const route = useRoute()
const router = useRouter()
const session = useSession()
const taxonomy = useTaxonomy()
const confirm = useConfirm()
const toast = useToast()

// ---- URL-backed filters -------------------------------------------------
const queryText = (key: string) => typeof route.query[key] === 'string' ? route.query[key] as string : ''
const category = computed(() => route.name === 'app-collection' ? String(route.params.id) : '')
const keywords = computed(() => queryText('q'))
const format = computed(() => queryText('format') as Format | '')
const tag = computed(() => queryText('tag'))
/**
 * Fixed views reached from the sidebar. "recent" lists the viewer's own reading history
 * (newest first, at most 50) and has no search, filters, sorting or paging.
 */
const preset = computed(() => route.meta.preset as 'favorites' | 'published' | 'recent' | undefined)
const isRecent = computed(() => preset.value === 'recent')
type Row = DocumentRow & { viewed_at?: string }
const visibility = computed<Visibility | ''>(() => {
  const value = queryText('visibility')
  if (preset.value === 'published') return value === 'lagging' ? 'lagging' : 'public'
  return value === 'public' || value === 'private' || value === 'lagging' ? value : ''
})
const ordering = computed(() => queryText('ordering') || '-updated_at')
const sortOptions = [
  { id: '-updated_at', name: '最近更新' }, { id: 'updated_at', name: '最早更新' },
  { id: 'title', name: '標題 A → Z' }, { id: '-title', name: '標題 Z → A' },
]
const visibilityOptions = [{ id: 'public', name: '公開' }, { id: 'lagging', name: '公開 · 落後' }, { id: 'private', name: '私人' }]
const page = computed(() => Math.max(1, Number.parseInt(queryText('page') || '1', 10) || 1))

function setQuery(patch: Record<string, string | number | undefined>, resetPage = true) {
  const query: LocationQueryRaw = { ...route.query, ...(resetPage ? { page: undefined } : {}), ...patch }
  for (const key of Object.keys(query)) if (query[key] === '' || query[key] === undefined || query[key] === 1) delete query[key]
  void router.replace({ query })
}

const searchText = ref(keywords.value)
watch(keywords, value => { if (value !== searchText.value.trim()) searchText.value = value })
watch(searchText, (text, _, onCleanup) => {
  const timer = setTimeout(() => { if (text.trim() !== keywords.value) setQuery({ q: text.trim() }) }, 250)
  onCleanup(() => clearTimeout(timer))
})

const formatOptions = [{ id: 'md', name: 'Markdown' }, { id: 'html', name: 'HTML' }]
const hasFilters = computed(() => !isRecent.value && Boolean(keywords.value || format.value || tag.value || (!preset.value && visibility.value)))
function clearFilters() {
  searchText.value = ''
  setQuery({ q: '', format: '', tag: '', ...(preset.value ? {} : { visibility: '' }) })
}

// ---- Data ----------------------------------------------------------------
const rows = ref<Row[]>([])
const count = ref(0)
const pageSize = ref(25)
const limits = ref({ ...session.limits })
const loading = ref(true)
const error = ref('')
let request = 0

async function load() {
  const current = ++request
  loading.value = true
  error.value = ''
  if (isRecent.value) return loadRecent(current)
  const params = new URLSearchParams({ page: String(page.value) })
  if (keywords.value) params.set('q', keywords.value)
  if (category.value) params.set('category', category.value)
  if (format.value) params.set('file_format', format.value)
  if (tag.value) params.set('tag', tag.value)
  if (preset.value === 'favorites') params.set('favorite', '1')
  if (visibility.value) params.set('visibility', visibility.value)
  if (ordering.value !== '-updated_at') params.set('ordering', ordering.value)
  try {
    const data = await api<DocumentPage>(`/api/documents/?${params}`)
    if (current !== request) return
    rows.value = data.results
    selected.value = selected.value.filter(id => data.results.some(row => row.id === id))
    count.value = data.count
    pageSize.value = data.page_size
    limits.value = data.limits
    const lastPage = Math.max(1, Math.ceil(data.count / data.page_size))
    if (page.value > lastPage) setQuery({ page: lastPage }, false)
  } catch (cause) {
    if (current === request) error.value = cause instanceof Error ? cause.message : '無法載入文件。'
  } finally {
    if (current === request) loading.value = false
  }
}

async function loadRecent(current: number) {
  try {
    const data = await api<{ results: Row[] }>('/api/me/recent/?limit=50')
    if (current !== request) return
    rows.value = data.results
    selected.value = selected.value.filter(id => data.results.some(row => row.id === id))
    count.value = data.results.length
    pageSize.value = Math.max(1, data.results.length)
  } catch (cause) {
    if (current === request) error.value = cause instanceof Error ? cause.message : '無法載入最近閱讀。'
  } finally {
    if (current === request) loading.value = false
  }
}

const selected = ref<string[]>([])
watch([category, keywords, format, tag, preset, visibility, ordering], () => { selected.value = [] })
watch([category, keywords, format, tag, page, preset, visibility, ordering], load, { immediate: true })
// Uploads started from the layout (header button, command palette) refresh the list.
const onChanged = () => { void load() }
onMounted(() => window.addEventListener('hub:documents-changed', onChanged))
onBeforeUnmount(() => window.removeEventListener('hub:documents-changed', onChanged))
watch(() => taxonomy.categories, () => {
  if (category.value && category.value !== UNCATEGORIZED && !taxonomy.byId(category.value)) void router.replace({ name: 'app-library' })
  else void load()
})

// ---- Heading ---------------------------------------------------------------
const heading = computed(() => {
  if (preset.value === 'recent') return '最近閱讀'
  if (preset.value === 'favorites') return '收藏'
  if (preset.value === 'published') return '已公開文章'
  if (!category.value) return '全部文件'
  if (category.value === UNCATEGORIZED) return '未分類'
  return taxonomy.byId(category.value)?.name ?? '集合'
})
watch(heading, value => site.setTitle(value), { immediate: true })
const breadcrumb = computed(() => taxonomy.pathOf(category.value).slice(0, -1))
const collection = computed(() => category.value && category.value !== UNCATEGORIZED ? taxonomy.byId(category.value) : undefined)
const editingCollection = ref<Category>()
const markOf = (name: string) => Array.from(name)[0]?.toUpperCase() ?? '?'
const pageCount = computed(() => Math.max(1, Math.ceil(count.value / pageSize.value)))
const rangeLabel = computed(() => {
  if (!count.value) return '沒有文件'
  const start = (page.value - 1) * pageSize.value + 1
  return `第 ${start}–${Math.min(count.value, start + rows.value.length - 1)} 筆，共 ${count.value} 筆`
})
const pages = computed(() => {
  const total = pageCount.value
  const current = page.value
  const wanted = new Set([1, total, current - 1, current, current + 1].filter(value => value >= 1 && value <= total))
  const sorted = [...wanted].sort((a, b) => a - b)
  const result: (number | 'gap')[] = []
  sorted.forEach((value, index) => {
    if (index && value - sorted[index - 1] > 1) result.push('gap')
    result.push(value)
  })
  return result
})

// ---- Row actions ---------------------------------------------------------
const uploadOpen = ref(false)
const versionTarget = ref<DocumentRow>()
const editing = ref<DocumentRow>()
const publishing = ref<DocumentRow>()
const rowMenu = ref<InstanceType<typeof Menu>>()
const menuRow = ref<DocumentRow>()

function openUpload(target?: DocumentRow) {
  versionTarget.value = target
  uploadOpen.value = true
}

function moveToTrash(row: DocumentRow) {
  confirm.require({
    header: '移入回收桶',
    message: `「${row.title}」與所有版本會移入回收桶，之後可以從回收桶還原。`,
    acceptProps: { label: '移入回收桶', severity: 'danger' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      try {
        await api(`/api/documents/${row.id}/`, 'DELETE')
        toast.add({ severity: 'success', summary: '已移入回收桶', detail: row.title, life: 3000 })
        await load()
      } catch (cause) {
        toast.add({ severity: 'error', summary: '無法移入回收桶', detail: cause instanceof Error ? cause.message : '', life: 5000 })
      }
    },
  })
}

const menuItems = computed<MenuItem[]>(() => {
  const row = menuRow.value
  if (!row) return []
  const items: MenuItem[] = [
    { label: '開啟', command: () => router.push({ name: 'app-document', params: { id: row.id } }) },
    { label: '下載原始檔', url: `/api/documents/${row.id}/download/` },
    { label: '版本歷史', command: () => router.push({ name: 'app-document', params: { id: row.id }, query: { panel: 'versions' } }) },
  ]
  if (session.canEdit) {
    items.push(
      { separator: true },
      { label: '編輯資料', command: () => { editing.value = row } },
      { label: '新增版本', command: () => openUpload(row) },
    )
  }
  if (session.isAdmin) items.push({ label: '公開設定', command: () => { publishing.value = row } })
  if (session.canEdit) items.push({ separator: true }, { label: '移入回收桶', class: 'danger-item', command: () => moveToTrash(row) })
  return items
})

// ---- Favourites (optimistic) ------------------------------------------------
async function toggleFavorite(row: DocumentRow) {
  const next = !row.is_favorite
  row.is_favorite = next
  try {
    await api(`/api/documents/${row.id}/favorite/`, next ? 'PUT' : 'DELETE')
    if (!next && preset.value === 'favorites') void load()
  } catch (cause) {
    row.is_favorite = !next
    toast.add({ severity: 'error', summary: '無法更新收藏', detail: cause instanceof Error ? cause.message : '', life: 4000 })
  }
}

// ---- Selection and bulk changes ------------------------------------------------
const allSelected = computed(() => rows.value.length > 0 && rows.value.every(row => selected.value.includes(row.id)))
function toggleRow(id: string) {
  selected.value = selected.value.includes(id) ? selected.value.filter(item => item !== id) : [...selected.value, id]
}
function toggleAll() {
  selected.value = allSelected.value ? [] : rows.value.map(row => row.id)
}
const bulkAction = ref<BulkAction>()
function bulkDone() {
  bulkAction.value = undefined
  selected.value = []
  void load()
  window.dispatchEvent(new CustomEvent('hub:documents-changed'))
}
function bulkTrash() {
  const ids = [...selected.value]
  confirm.require({
    header: '移入回收桶',
    message: `${ids.length} 份文件與所有版本會移入回收桶，公開中的文章會一併下架。之後可以從回收桶還原。`,
    acceptProps: { label: '移入回收桶', severity: 'danger' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      try {
        const result = await api<{ count: number }>('/api/documents/bulk/', 'POST', { ids, action: 'trash' })
        toast.add({ severity: 'success', summary: `已將 ${result.count} 份文件移入回收桶`, life: 3000 })
        bulkDone()
      } catch (cause) {
        toast.add({ severity: 'error', summary: '無法移入回收桶', detail: cause instanceof Error ? cause.message : '', life: 5000 })
      }
    },
  })
}

function openRowMenu(event: Event, row: DocumentRow) {
  menuRow.value = row
  rowMenu.value?.toggle(event)
}

function onSaved() {
  editing.value = undefined
  void load()
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="titles">
        <nav v-if="breadcrumb.length" class="crumbs" aria-label="上層集合">
          <template v-for="(item, index) in breadcrumb" :key="item.id">
            <span v-if="index" aria-hidden="true">/</span>
            <RouterLink :to="{ name: 'app-collection', params: { id: item.id } }">{{ item.name }}</RouterLink>
          </template>
        </nav>
        <div class="title-row">
          <span v-if="collection" class="ui-col-mark title-mark" :class="`ui-col-${collection.color || 'gray'}`" aria-hidden="true">{{ markOf(collection.name) }}</span>
          <h1>{{ heading }}</h1>
          <button v-if="collection && session.canEdit" type="button" class="edit-collection" aria-label="編輯集合"
            @click="editingCollection = collection">
            <UiIcon name="edit" :size="16" />
          </button>
        </div>
        <p v-if="collection?.description" class="description">{{ collection.description }}</p>
        <p class="subtitle" aria-live="polite">{{ loading ? '正在載入…' : `${count} 份文件` }}<template v-if="isRecent"> · 只有你看得到這份清單，最多保留最近 50 份文件。</template></p>
        <div v-if="preset === 'published'" class="segments" role="group" aria-label="公開狀態">
          <button type="button" class="segment" :class="{ on: visibility === 'public' }" :aria-pressed="visibility === 'public'"
            @click="setQuery({ visibility: '' })">全部公開</button>
          <button type="button" class="segment" :class="{ on: visibility === 'lagging' }" :aria-pressed="visibility === 'lagging'"
            @click="setQuery({ visibility: 'lagging' })">落後內部版本</button>
        </div>
      </div>
      <Button v-if="session.canEdit && !preset" class="upload-button" @click="emit('upload')">
        <UiIcon name="upload" :size="16" /><span>上傳</span>
      </Button>
    </header>

    <div v-if="!isRecent" class="toolbar" role="search">
      <label class="search-box">
        <span class="ui-visually-hidden">搜尋文件</span>
        <UiIcon name="search" :size="16" />
        <input id="library-search" v-model="searchText" type="search" maxlength="240" placeholder="搜尋標題、集合、標籤或全文">
      </label>
      <Select :model-value="format || null" :options="formatOptions" option-label="name" option-value="id" show-clear
        placeholder="所有格式" aria-label="依格式篩選" class="facet" @update:model-value="value => setQuery({ format: value ?? '' })" />
      <Select :model-value="tag || null" :options="taxonomy.tags" option-label="name" option-value="id" show-clear filter
        placeholder="所有標籤" aria-label="依標籤篩選" class="facet" @update:model-value="value => setQuery({ tag: value ?? '' })" />
      <Select v-if="!preset" :model-value="visibility || null" :options="visibilityOptions" option-label="name" option-value="id"
        show-clear placeholder="所有可見性" aria-label="依可見性篩選" class="facet" @update:model-value="value => setQuery({ visibility: value ?? '' })" />
      <Button v-if="hasFilters" label="清除篩選" text severity="secondary" @click="clearFilters" />
      <span class="toolbar-spacer" />
      <Select :model-value="ordering" :options="sortOptions" option-label="name" option-value="id" aria-label="排序方式"
        class="facet sort" @update:model-value="value => setQuery({ ordering: value === '-updated_at' ? '' : value })" />
    </div>

    <div v-if="selected.length" class="bulk" role="toolbar" aria-label="批次操作">
      <span class="bulk-count">已選 {{ selected.length }} 份</span>
      <button type="button" class="bulk-button" @click="bulkAction = 'move'">移動到集合</button>
      <button type="button" class="bulk-button" @click="bulkAction = 'add_tags'">加標籤</button>
      <button type="button" class="bulk-button" @click="bulkAction = 'remove_tags'">移除標籤</button>
      <button type="button" class="bulk-button danger" @click="bulkTrash">移入回收桶</button>
      <button type="button" class="bulk-button ghost" @click="selected = []">取消選取</button>
    </div>

    <Message v-if="error" severity="error" class="error">
      {{ error }}
      <Button label="重試" size="small" text @click="load" />
    </Message>

    <div v-else class="table-wrap" role="region" aria-label="文件清單" tabindex="0">
      <table class="table" :aria-busy="loading">
        <thead>
          <tr>
            <th v-if="session.canEdit" scope="col" class="col-select">
              <input type="checkbox" class="check" :checked="allSelected" :disabled="!rows.length" aria-label="選取本頁所有文件" @change="toggleAll">
            </th>
            <th scope="col">文件</th>
            <th scope="col" class="col-tags">標籤</th>
            <th scope="col" class="col-status">可見性</th>
            <th scope="col" class="col-version">版本</th>
            <th scope="col" class="col-date">{{ isRecent ? '閱讀' : '更新' }}</th>
            <th scope="col" class="col-actions"><span class="ui-visually-hidden">操作</span></th>
          </tr>
        </thead>
        <tbody v-if="loading && !rows.length">
          <tr v-for="index in 6" :key="index">
            <td v-if="session.canEdit" />
            <td><div class="doc"><Skeleton width="2rem" height="2rem" /><Skeleton width="14rem" /></div></td>
            <td><Skeleton width="5rem" /></td>
            <td><Skeleton width="3.5rem" /></td>
            <td><Skeleton width="2rem" /></td>
            <td><Skeleton width="4rem" /></td>
            <td />
          </tr>
        </tbody>
        <tbody v-else-if="rows.length" :class="{ stale: loading }">
          <tr v-for="row in rows" :key="row.id" :class="{ selected: selected.includes(row.id) }">
            <td v-if="session.canEdit" class="cell-select">
              <input type="checkbox" class="check" :checked="selected.includes(row.id)" :aria-label="`選取 ${row.title}`"
                @change="toggleRow(row.id)">
            </td>
            <td class="cell-doc">
              <div class="doc">
                <span class="format" :class="row.format" :title="formatLabel(row.format)">{{ row.format === 'html' ? 'HTML' : 'MD' }}</span>
                <div class="doc-text">
                  <RouterLink :to="{ name: 'app-document', params: { id: row.id } }" class="doc-title">{{ row.title }}</RouterLink>
                  <span class="doc-path">{{ taxonomy.pathLabel(row.category) }}</span>
                </div>
              </div>
            </td>
            <td class="cell-tags" :class="{ 'no-tags': !row.tags.length }">
              <div class="tags">
                <span v-for="item in row.tags" :key="item.id" class="tag">{{ item.name }}</span>
                <span v-if="!row.tags.length" class="none">—</span>
              </div>
            </td>
            <td class="cell-status">
              <span class="status" :class="visibilityOf(row).kind">
                <span class="dot" aria-hidden="true" />{{ visibilityOf(row).kind === 'lagging' ? `落後 ${row.current_version.number - (row.published_version ?? 0)} 版` : visibilityOf(row).label }}
              </span>
            </td>
            <td class="num">v{{ row.current_version.number }}</td>
            <td class="date">
              <time :datetime="row.viewed_at ?? row.updated_at" :title="longDateTime(row.viewed_at ?? row.updated_at)">{{ shortDate(row.viewed_at ?? row.updated_at) }}</time>
            </td>
            <td class="actions">
              <button type="button" class="row-menu star" :class="{ on: row.is_favorite }" :aria-pressed="Boolean(row.is_favorite)"
                :aria-label="row.is_favorite ? `取消收藏 ${row.title}` : `收藏 ${row.title}`" @click="toggleFavorite(row)">
                <UiIcon name="star" :size="16" :filled="row.is_favorite" />
              </button>
              <button type="button" class="row-menu" :aria-label="`${row.title} 的更多操作`" aria-haspopup="menu"
                aria-controls="row-menu" @click="openRowMenu($event, row)">
                <UiIcon name="more" :size="18" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!loading && !rows.length" class="empty">
        <UiIcon :name="isRecent ? 'clock' : 'folder'" :size="28" />
        <p class="empty-title">{{ hasFilters ? '找不到符合條件的文件' : isRecent ? '還沒有閱讀紀錄' : preset === 'favorites' ? '還沒有收藏的文件' : preset === 'published' ? (visibility === 'lagging' ? '所有公開文章都是最新版本' : '還沒有公開文章') : '這裡還沒有文件' }}</p>
        <p class="empty-text">{{ hasFilters ? '換個關鍵字，或清除篩選條件再試一次。' : isRecent ? '開啟任何文件後，就會出現在這裡。' : preset === 'favorites' ? '在文件頁按下星號，就能把常用文件收進這裡。' : preset === 'published' ? 'Admin 可在文件頁的「公開」分頁發布文章。' : (session.canEdit ? '上傳 Markdown 或 HTML 檔案開始建立知識庫。' : '有文件加入後會顯示在這裡。') }}</p>
        <Button v-if="hasFilters" label="清除篩選" outlined size="small" @click="clearFilters" />
        <Button v-else-if="session.canEdit && !preset" label="上傳文件" size="small" @click="emit('upload')" />
      </div>
    </div>

    <nav v-if="pageCount > 1" class="pager" aria-label="分頁">
      <span>{{ rangeLabel }}</span>
      <div class="pages">
        <button type="button" class="page-button" :disabled="page === 1" aria-label="上一頁" @click="setQuery({ page: page - 1 }, false)">
          <UiIcon name="chevronLeft" :size="16" />
        </button>
        <template v-for="(item, index) in pages" :key="`${item}-${index}`">
          <span v-if="item === 'gap'" class="gap" aria-hidden="true">…</span>
          <button v-else type="button" class="page-button" :class="{ current: item === page }"
            :aria-current="item === page ? 'page' : undefined" @click="setQuery({ page: item }, false)">{{ item }}</button>
        </template>
        <button type="button" class="page-button" :disabled="page === pageCount" aria-label="下一頁" @click="setQuery({ page: page + 1 }, false)">
          <UiIcon name="chevronRight" :size="16" />
        </button>
      </div>
    </nav>

    <Menu id="row-menu" ref="rowMenu" :model="menuItems" popup />
    <UploadDialog v-model:visible="uploadOpen" :target="versionTarget" :default-category="category"
      :max-bytes="limits.bytes" :max-batch="limits.batch" @uploaded="load" />
    <BulkDialog :action="bulkAction" :ids="selected" @close="bulkAction = undefined" @done="bulkDone" />
    <CollectionDialog :collection="editingCollection" @close="editingCollection = undefined" />
    <MetadataDialog :document="editing" @close="editing = undefined" @saved="onSaved" />
    <PublicationDialog v-if="publishing" :id="publishing.id" :format="publishing.format" :csrf="getCsrfToken()"
      @close="publishing = undefined" @changed="load" />
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 100rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); }
.page-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--ui-space-4); margin-bottom: var(--ui-space-5); }
.titles { min-width: 0; }
.crumbs { display: flex; flex-wrap: wrap; gap: .375rem; margin-bottom: var(--ui-space-1); font-size: var(--ui-text-sm); color: var(--ui-text-muted); }
.crumbs a { color: inherit; text-decoration: none; }
.crumbs a:hover { color: var(--ui-accent); text-decoration: underline; }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); font-weight: 700; letter-spacing: -.01em; overflow-wrap: anywhere; }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.upload-button { gap: var(--ui-space-2); }

.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); margin-bottom: var(--ui-space-4); }
.search-box {
  flex: 1 1 18rem; display: flex; align-items: center; gap: var(--ui-space-2); min-height: 2.5rem; padding: 0 var(--ui-space-3);
  border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-muted); box-sizing: border-box;
}
.search-box:focus-within { border-color: var(--ui-accent); box-shadow: var(--ui-focus-ring); }
.search-box input { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; color: var(--ui-text); font: inherit; font-size: var(--ui-text-md); }
.search-box input:focus-visible { box-shadow: none; }
.facet { min-width: 9.5rem; min-height: 2.5rem; align-items: center; }
.error { margin-bottom: var(--ui-space-4); }

/* position: relative keeps visually hidden header text inside the scroller. */
.table-wrap { position: relative; overflow-x: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.table { width: 100%; min-width: 50rem; border-collapse: collapse; }
.table th {
  padding: .625rem var(--ui-space-3); background: var(--ui-bg-subtle); border-bottom: 1px solid var(--ui-border);
  color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; text-align: left; white-space: nowrap;
}
.table th:first-child, .table td:first-child { padding-left: var(--ui-space-4); }
.table td { padding: var(--ui-space-3); border-bottom: 1px solid var(--ui-border-subtle); vertical-align: middle; color: var(--ui-text-secondary); }
.table tbody tr:last-child td { border-bottom: 0; }
.table tbody tr:hover td { background: var(--ui-bg-subtle); }
.stale { opacity: .6; transition: opacity .15s; }
.doc { display: flex; align-items: center; gap: var(--ui-space-3); }
.format { flex: none; display: grid; place-items: center; min-width: 2.25rem; height: 2rem; padding: 0 .25rem; box-sizing: border-box; border-radius: var(--ui-radius-md); font-size: .65625rem; font-weight: 700; letter-spacing: .02em; }
.format.md { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); }
.format.html { background: var(--ui-format-html-bg); color: var(--ui-format-html-text); }
.doc-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.doc-title { color: var(--ui-text); font-weight: 600; text-decoration: none; overflow-wrap: anywhere; }
.doc-title:hover { color: var(--ui-accent); text-decoration: underline; text-underline-offset: .18em; }
.doc-path { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.tags { display: flex; flex-wrap: wrap; gap: var(--ui-space-1); }
.tag { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-pill); background: var(--ui-bg-muted); color: var(--ui-text-secondary); font-size: var(--ui-text-xs); white-space: nowrap; }
.none { color: var(--ui-text-muted); }
.status { display: inline-flex; align-items: center; gap: .375rem; padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); font-size: var(--ui-text-sm); font-weight: 600; white-space: nowrap; }
.status .dot { width: 6px; height: 6px; border-radius: 50%; }
.status.public { background: var(--ui-public-bg); color: var(--ui-public-text); }
.status.public .dot { background: var(--ui-public-dot); }
.status.private { background: var(--ui-private-bg); color: var(--ui-private-text); }
.status.private .dot { background: var(--ui-private-dot); }
.status.lagging { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.status.lagging .dot { background: var(--ui-lagging-dot); }
.segments { display: inline-flex; gap: 2px; margin-top: var(--ui-space-3); padding: 3px; border-radius: var(--ui-radius-md); background: var(--ui-bg-muted); }
.segment { min-height: 1.875rem; padding: 0 .875rem; border: 0; border-radius: .375rem; background: transparent; color: var(--ui-text-muted); font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.segment.on { background: var(--ui-bg-surface); color: var(--ui-text); font-weight: 600; box-shadow: var(--ui-shadow-sm); }
.num, .date { white-space: nowrap; }
.actions { text-align: right; white-space: nowrap; }
.star { color: var(--ui-text-muted); }
.star.on { color: #d99a00; }
.col-select, .cell-select { width: 2.5rem; }
.check { width: 1rem; height: 1rem; margin: 0; accent-color: var(--ui-accent); cursor: pointer; }
.table tbody tr.selected td { background: var(--ui-accent-soft); }
.title-row { display: flex; align-items: center; gap: var(--ui-space-3); }
.title-mark { width: 2.25rem; height: 2.25rem; font-size: 1rem; border-radius: var(--ui-radius-md); }
.edit-collection { display: grid; place-items: center; width: 2rem; height: 2rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.edit-collection:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.description { max-width: 48rem; margin: var(--ui-space-2) 0 0; color: var(--ui-text-secondary); line-height: 1.6; white-space: pre-line; }
.toolbar-spacer { flex: 1 1 0; }
.sort { min-width: 8.5rem; }
.bulk {
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-1); margin-bottom: var(--ui-space-3);
  padding: var(--ui-space-2) var(--ui-space-2) var(--ui-space-2) var(--ui-space-4); border-radius: var(--ui-radius-lg);
  background: var(--ui-bg-inverse); color: var(--ui-text-inverse);
}
.bulk-count { margin-right: var(--ui-space-2); font-weight: 600; font-size: var(--ui-text-sm); }
.bulk-button { min-height: 2rem; padding: 0 var(--ui-space-3); border: 0; border-radius: var(--ui-radius-md); background: rgb(255 255 255 / .12); color: inherit; font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.hub-dark .bulk-button { background: rgb(16 24 40 / .1); }
.bulk-button:hover { background: rgb(255 255 255 / .2); }
.bulk-button.danger { color: #fecdca; }
.hub-dark .bulk-button.danger { color: #b42318; }
.bulk-button.ghost { margin-left: auto; background: transparent; opacity: .85; }
/* Fixed side columns keep the table compact on wide screens; the document column takes the rest. */
.col-tags { width: 14rem; }
.col-status { width: 8rem; }
.col-version { width: 4.5rem; }
.col-date { width: 8rem; }
.col-actions { width: 3rem; }
.row-menu { display: inline-grid; place-items: center; width: 2.25rem; height: 2.25rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.row-menu:hover { background: var(--ui-bg-muted); color: var(--ui-text); }

.empty { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-7) var(--ui-space-4); color: var(--ui-text-muted); text-align: center; }
.empty p { margin: 0; }
.empty-title { color: var(--ui-text); font-weight: 600; font-size: var(--ui-text-lg); }
.empty .p-button { margin-top: var(--ui-space-2); }

.pager { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-space-3); margin-top: var(--ui-space-4); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.pages { display: flex; align-items: center; gap: var(--ui-space-1); }
.page-button {
  display: inline-grid; place-items: center; min-width: 2.25rem; height: 2.25rem; padding: 0 var(--ui-space-2);
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface);
  color: var(--ui-text-secondary); font: inherit; cursor: pointer;
}
.page-button:hover:not(:disabled) { border-color: var(--ui-border-strong); }
.page-button:disabled { opacity: .45; cursor: default; }
.page-button.current { border-color: var(--ui-accent); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-weight: 600; }
.gap { padding: 0 var(--ui-space-1); }

/* Below tablet width each row becomes a card: no horizontal scrolling, menu stays reachable. */
@media (max-width: 860px) {
  .table { min-width: 0; }
  .table, .table tbody { display: block; }
  .table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .table tbody tr {
    display: grid; grid-template-columns: auto auto minmax(0, 1fr) auto; align-items: center;
    grid-template-areas: "doc doc doc actions" "status version date actions" "tags tags tags tags";
    column-gap: var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-2) var(--ui-space-3) var(--ui-space-4);
    border-bottom: 1px solid var(--ui-border-subtle);
  }
  .table tbody tr:has(.cell-select) {
    grid-template-columns: auto auto auto minmax(0, 1fr) auto;
    grid-template-areas: "select doc doc doc actions" "select status version date actions" "select tags tags tags tags";
  }
  .table tbody tr.selected { background: var(--ui-accent-soft); }
  .table tbody tr.selected td { background: transparent; }
  .cell-select { grid-area: select; align-self: start; padding-top: .5rem !important; width: auto; }
  .table tbody tr:last-child { border-bottom: 0; }
  .table td, .table td:first-child { padding: 0; border: 0; }
  .table tbody tr:hover td { background: transparent; }
  .cell-doc { grid-area: doc; }
  .cell-status { grid-area: status; padding-top: var(--ui-space-2) !important; padding-left: 2.75rem !important; }
  .num { grid-area: version; padding-top: var(--ui-space-2) !important; font-size: var(--ui-text-sm); }
  .date { grid-area: date; padding-top: var(--ui-space-2) !important; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
  .actions { grid-area: actions; align-self: start; width: auto; }
  .cell-tags { grid-area: tags; padding: var(--ui-space-2) 0 0 2.75rem !important; }
  .cell-tags.no-tags { display: none; }
}
@media (max-width: 640px) {
  .facet { flex: 1 1 8rem; min-width: 0; }
  .toolbar-spacer { display: none; }
  .bulk-button.ghost { margin-left: 0; }
  .upload-button { width: 100%; justify-content: center; }
}
</style>
