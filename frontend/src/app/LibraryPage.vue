<script setup lang="ts">
import Button from 'primevue/button'
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Skeleton from 'primevue/skeleton'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { api, getCsrfToken } from '../api'
import PublicationDialog from '../PublicationDialog.vue'
import { useSession } from '../stores/session'
import { UNCATEGORIZED, useTaxonomy } from '../stores/taxonomy'
import MetadataDialog from './components/MetadataDialog.vue'
import UiIcon from './components/UiIcon.vue'
import UploadDialog from './components/UploadDialog.vue'
import { formatLabel, longDateTime, shortDate, type DocumentPage, type DocumentRow, type Format } from './types'

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
const hasFilters = computed(() => Boolean(keywords.value || format.value || tag.value))

// ---- Data ----------------------------------------------------------------
const rows = ref<DocumentRow[]>([])
const count = ref(0)
const pageSize = ref(25)
const limits = ref({ bytes: 50 * 1024 * 1024, batch: 20 })
const loading = ref(true)
const error = ref('')
let request = 0

async function load() {
  const current = ++request
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ page: String(page.value) })
  if (keywords.value) params.set('q', keywords.value)
  if (category.value) params.set('category', category.value)
  if (format.value) params.set('file_format', format.value)
  if (tag.value) params.set('tag', tag.value)
  try {
    const data = await api<DocumentPage>(`/api/documents/?${params}`)
    if (current !== request) return
    rows.value = data.results
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

watch([category, keywords, format, tag, page], load, { immediate: true })
watch(() => taxonomy.categories, () => {
  if (category.value && category.value !== UNCATEGORIZED && !taxonomy.byId(category.value)) void router.replace({ name: 'app-library' })
  else void load()
})

// ---- Heading ---------------------------------------------------------------
const heading = computed(() => {
  if (!category.value) return '全部文件'
  if (category.value === UNCATEGORIZED) return '未分類'
  return taxonomy.byId(category.value)?.name ?? '集合'
})
const breadcrumb = computed(() => taxonomy.pathOf(category.value).slice(0, -1))
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
        <h1>{{ heading }}</h1>
        <p class="subtitle" aria-live="polite">{{ loading ? '正在載入…' : `${count} 份文件` }}</p>
      </div>
      <Button v-if="session.canEdit" class="upload-button" @click="openUpload()">
        <UiIcon name="upload" :size="16" /><span>上傳</span>
      </Button>
    </header>

    <div class="toolbar" role="search">
      <label class="search-box">
        <span class="ui-visually-hidden">搜尋文件</span>
        <UiIcon name="search" :size="16" />
        <input id="library-search" v-model="searchText" type="search" maxlength="240" placeholder="搜尋標題、集合、標籤或全文">
      </label>
      <Select :model-value="format || null" :options="formatOptions" option-label="name" option-value="id" show-clear
        placeholder="所有格式" aria-label="依格式篩選" class="facet" @update:model-value="value => setQuery({ format: value ?? '' })" />
      <Select :model-value="tag || null" :options="taxonomy.tags" option-label="name" option-value="id" show-clear filter
        placeholder="所有標籤" aria-label="依標籤篩選" class="facet" @update:model-value="value => setQuery({ tag: value ?? '' })" />
      <Button v-if="hasFilters" label="清除篩選" text severity="secondary" @click="searchText = ''; setQuery({ q: '', format: '', tag: '' })" />
    </div>

    <Message v-if="error" severity="error" class="error">
      {{ error }}
      <Button label="重試" size="small" text @click="load" />
    </Message>

    <div v-else class="table-wrap" role="region" aria-label="文件清單" tabindex="0">
      <table class="table" :aria-busy="loading">
        <thead>
          <tr>
            <th scope="col">文件</th>
            <th scope="col">標籤</th>
            <th scope="col">可見性</th>
            <th scope="col">版本</th>
            <th scope="col">更新</th>
            <th scope="col"><span class="ui-visually-hidden">操作</span></th>
          </tr>
        </thead>
        <tbody v-if="loading && !rows.length">
          <tr v-for="index in 6" :key="index">
            <td><div class="doc"><Skeleton width="2rem" height="2rem" /><Skeleton width="14rem" /></div></td>
            <td><Skeleton width="5rem" /></td>
            <td><Skeleton width="3.5rem" /></td>
            <td><Skeleton width="2rem" /></td>
            <td><Skeleton width="4rem" /></td>
            <td />
          </tr>
        </tbody>
        <tbody v-else-if="rows.length" :class="{ stale: loading }">
          <tr v-for="row in rows" :key="row.id">
            <td>
              <div class="doc">
                <span class="format" :class="row.format">{{ row.format === 'html' ? 'HTML' : 'MD' }}</span>
                <div class="doc-text">
                  <RouterLink :to="{ name: 'app-document', params: { id: row.id } }" class="doc-title">{{ row.title }}</RouterLink>
                  <span class="doc-path">{{ taxonomy.pathLabel(row.category) }} · {{ formatLabel(row.format) }}</span>
                </div>
              </div>
            </td>
            <td>
              <div class="tags">
                <span v-for="item in row.tags" :key="item.id" class="tag">{{ item.name }}</span>
                <span v-if="!row.tags.length" class="none">—</span>
              </div>
            </td>
            <td>
              <span class="status" :class="row.is_public ? 'public' : 'private'">
                <span class="dot" aria-hidden="true" />{{ row.is_public ? '公開' : '私人' }}
              </span>
            </td>
            <td class="num">v{{ row.current_version.number }}</td>
            <td class="date"><time :datetime="row.updated_at" :title="longDateTime(row.updated_at)">{{ shortDate(row.updated_at) }}</time></td>
            <td class="actions">
              <button type="button" class="row-menu" :aria-label="`${row.title} 的更多操作`" aria-haspopup="menu"
                aria-controls="row-menu" @click="openRowMenu($event, row)">
                <UiIcon name="more" :size="18" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!loading && !rows.length" class="empty">
        <UiIcon name="folder" :size="28" />
        <p class="empty-title">{{ hasFilters ? '找不到符合條件的文件' : '這裡還沒有文件' }}</p>
        <p class="empty-text">{{ hasFilters ? '換個關鍵字，或清除篩選條件再試一次。' : (session.canEdit ? '上傳 Markdown 或 HTML 檔案開始建立知識庫。' : '有文件加入後會顯示在這裡。') }}</p>
        <Button v-if="hasFilters" label="清除篩選" outlined size="small" @click="searchText = ''; setQuery({ q: '', format: '', tag: '' })" />
        <Button v-else-if="session.canEdit" label="上傳文件" size="small" @click="openUpload()" />
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
    <MetadataDialog :document="editing" @close="editing = undefined" @saved="onSaved" />
    <PublicationDialog v-if="publishing" :id="publishing.id" :format="publishing.format" :csrf="getCsrfToken()"
      @close="publishing = undefined" @changed="load" />
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 80rem; margin: 0 auto; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); }
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
.facet { min-width: 9.5rem; }
.error { margin-bottom: var(--ui-space-4); }

.table-wrap { overflow-x: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
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
.format { flex: none; display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: var(--ui-radius-md); font-size: .65625rem; font-weight: 700; letter-spacing: .02em; }
.format.md { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); }
.format.html { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
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
.num, .date { white-space: nowrap; }
.actions { width: 3rem; text-align: right; }
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

@media (max-width: 640px) {
  .facet { flex: 1 1 8rem; min-width: 0; }
  .upload-button { width: 100%; justify-content: center; }
}
</style>
