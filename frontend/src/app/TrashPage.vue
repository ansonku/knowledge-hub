<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import { useSession } from '../stores/session'
import { useTaxonomy } from '../stores/taxonomy'
import { useWorkspace } from '../stores/workspace'
import UiIcon from './components/UiIcon.vue'
import { longDateTime, shortDate, type Format } from './types'

type TrashRow = {
  id: string; title: string; format: Format; category: string | null; category_id: string | null
  trashed_at: string; trashed_by: string | null; version_count: number
}
type TrashPage = { count: number; page_size: number; results: TrashRow[] }

const session = useSession()
const taxonomy = useTaxonomy()
const workspace = useWorkspace()
const toast = useToast()

const rows = ref<TrashRow[]>([])
const count = ref(0)
const pageSize = ref(25)
const page = ref(1)
const loading = ref(true)
const error = ref('')
const selected = ref<string[]>([])
const working = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<TrashPage>(`/api/trash/?page=${page.value}`)
    rows.value = data.results
    count.value = data.count
    pageSize.value = data.page_size
    selected.value = selected.value.filter(id => data.results.some(row => row.id === id))
    if (!data.results.length && page.value > 1) page.value--
  } catch (cause) {
    error.value = cause instanceof ApiError && cause.status === 403
      ? '回收桶只開放給 Editor 與 Admin。'
      : cause instanceof Error ? cause.message : '無法載入回收桶。'
  } finally {
    loading.value = false
  }
}
watch(page, load)

const allSelected = computed(() => rows.value.length > 0 && rows.value.every(row => selected.value.includes(row.id)))
const pageCount = computed(() => Math.max(1, Math.ceil(count.value / pageSize.value)))
function toggleRow(id: string) {
  selected.value = selected.value.includes(id) ? selected.value.filter(item => item !== id) : [...selected.value, id]
}
function toggleAll() {
  selected.value = allSelected.value ? [] : rows.value.map(row => row.id)
}

async function restore(ids: string[]) {
  if (working.value || !ids.length) return
  working.value = true
  let restored = 0
  const failed: string[] = []
  for (const id of ids) {
    try {
      await api(`/api/trash/${id}/restore/`, 'POST')
      restored++
    } catch {
      failed.push(rows.value.find(row => row.id === id)?.title ?? id)
    }
  }
  working.value = false
  if (restored) toast.add({ severity: 'success', summary: `已還原 ${restored} 份文件`, detail: '文件與所有版本已回到文件庫，公開狀態維持私人。', life: 4000 })
  if (failed.length) toast.add({ severity: 'error', summary: '部分文件無法還原', detail: failed.join('、'), life: 6000 })
  selected.value = []
  await load()
  void workspace.refresh(true)
  window.dispatchEvent(new CustomEvent('hub:documents-changed'))
}

// ---- Permanent deletion (Admin, typed title) ----------------------------------------
const deleting = ref<TrashRow>()
const typedTitle = ref('')
const deleteError = ref('')
function requestDelete(row: TrashRow) {
  deleting.value = row
  typedTitle.value = ''
  deleteError.value = ''
}
// Permanent deletion lives in a row menu (Admin only) so the destructive action is not repeated on every row.
const rowMenu = ref<InstanceType<typeof Menu>>()
const menuRow = ref<TrashRow>()
const menuItems = computed<MenuItem[]>(() => menuRow.value
  ? [{ label: '永久刪除', class: 'danger-item', command: () => requestDelete(menuRow.value!) }]
  : [])
function openRowMenu(event: Event, row: TrashRow) {
  menuRow.value = row
  rowMenu.value?.toggle(event)
}
/** Full collection path when the collection still exists, else the name the API returned. */
function collectionLabel(row: TrashRow) {
  if (row.category_id && taxonomy.byId(row.category_id)) return taxonomy.pathLabel(row.category_id)
  return row.category ?? '未分類'
}

async function permanentDelete() {
  const row = deleting.value
  if (!row || typedTitle.value !== row.title || working.value) return
  working.value = true
  deleteError.value = ''
  try {
    await api(`/api/trash/${row.id}/delete/`, 'POST', { title: typedTitle.value, confirm: true })
    toast.add({ severity: 'success', summary: '已永久刪除', detail: row.title, life: 4000 })
    deleting.value = undefined
    await load()
    void workspace.refresh(true)
  } catch (cause) {
    deleteError.value = cause instanceof Error ? cause.message : '無法永久刪除。'
  } finally {
    working.value = false
  }
}

onMounted(() => {
  document.title = '回收桶 · Knowledge Hub'
  // The trash API is limited to editors; skip the request instead of letting it fail.
  if (!session.canEdit) {
    loading.value = false
    error.value = '回收桶只開放給 Editor 與 Admin。'
    return
  }
  void load()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <h1>回收桶</h1>
      <p class="subtitle" aria-live="polite">
        <template v-if="session.canEdit">{{ loading ? '正在載入…' : `${count} 份文件` }} · </template>還原會把文件與所有版本放回文件庫，公開狀態維持私人。<template v-if="session.isAdmin">永久刪除無法復原。</template>
      </p>
    </header>

    <Message v-if="error" severity="error">{{ error }}</Message>
    <template v-else>
      <div v-if="selected.length" class="bulk" role="toolbar" aria-label="批次操作">
        <span class="bulk-count">已選 {{ selected.length }} 份</span>
        <button type="button" class="bulk-button" :disabled="working" @click="restore(selected)">還原</button>
        <button type="button" class="bulk-button ghost" @click="selected = []">取消選取</button>
      </div>

      <div class="table-wrap" role="region" aria-label="回收桶文件" tabindex="0">
        <table class="table" :aria-busy="loading">
          <thead>
            <tr>
              <th scope="col" class="col-select">
                <input type="checkbox" class="check" :checked="allSelected" :disabled="!rows.length" aria-label="選取本頁所有文件" @change="toggleAll">
              </th>
              <th scope="col">文件</th>
              <th scope="col" class="col-by">移入者</th>
              <th scope="col" class="col-versions">版本數</th>
              <th scope="col" class="col-date">移入時間</th>
              <th scope="col" class="col-actions"><span class="ui-visually-hidden">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-if="loading && !rows.length">
              <tr v-for="index in 4" :key="index"><td /><td colspan="5"><Skeleton width="60%" /></td></tr>
            </template>
            <tr v-for="row in rows" :key="row.id" :class="{ selected: selected.includes(row.id) }">
              <td class="cell-select">
                <input type="checkbox" class="check" :checked="selected.includes(row.id)" :aria-label="`選取 ${row.title}`" @change="toggleRow(row.id)">
              </td>
              <td class="cell-doc">
                <div class="doc">
                  <span class="format" :class="row.format">{{ row.format === 'html' ? 'HTML' : 'MD' }}</span>
                  <div class="doc-text">
                    <span class="doc-title">{{ row.title }}</span>
                    <span class="doc-path">{{ collectionLabel(row) }}</span>
                  </div>
                </div>
              </td>
              <td class="cell-by">{{ row.trashed_by ?? '—' }}</td>
              <td class="cell-versions">{{ row.version_count }} 個版本</td>
              <td class="cell-date"><time :datetime="row.trashed_at" :title="longDateTime(row.trashed_at)">{{ shortDate(row.trashed_at) }}</time></td>
              <td class="cell-actions">
                <Button label="還原" size="small" outlined :disabled="working" @click="restore([row.id])" />
                <button v-if="session.isAdmin" type="button" class="row-menu" :aria-label="`${row.title} 的更多操作`" aria-haspopup="menu"
                  aria-controls="trash-row-menu" :disabled="working" @click="openRowMenu($event, row)">
                  <UiIcon name="more" :size="18" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!loading && !rows.length" class="empty">
          <UiIcon name="trash" :size="28" />
          <p class="empty-title">回收桶是空的</p>
          <p>移入回收桶的文件會出現在這裡，可以隨時還原。</p>
        </div>
      </div>

      <nav v-if="pageCount > 1" class="pager" aria-label="分頁">
        <Button label="上一頁" text size="small" :disabled="page === 1" @click="page--" />
        <span>第 {{ page }} / {{ pageCount }} 頁，共 {{ count }} 份</span>
        <Button label="下一頁" text size="small" :disabled="page === pageCount" @click="page++" />
      </nav>
    </template>

    <Menu id="trash-row-menu" ref="rowMenu" :model="menuItems" popup />
    <Dialog :visible="Boolean(deleting)" header="永久刪除文件" modal :closable="!working" :close-on-escape="!working"
      :style="{ width: 'min(94vw, 32rem)' }" @update:visible="open => { if (!open && !working) deleting = undefined }">
      <form v-if="deleting" class="confirm" @submit.prevent="permanentDelete">
        <Message severity="error" size="small">將永久刪除「{{ deleting.title }}」與全部 {{ deleting.version_count }} 個版本，這個動作無法復原。</Message>
        <label for="typed-title">輸入完整文件標題以確認</label>
        <InputText id="typed-title" v-model="typedTitle" autocomplete="off" :disabled="working" />
        <Message v-if="deleteError" severity="error" size="small">{{ deleteError }}</Message>
        <div class="confirm-actions">
          <Button type="button" label="取消" text severity="secondary" :disabled="working" @click="deleting = undefined" />
          <Button type="submit" label="永久刪除" severity="danger" :loading="working" :disabled="typedTitle !== deleting.title" />
        </div>
      </form>
    </Dialog>
  </div>
</template>

<style scoped>
/* Same frame as the library pages: left aligned, up to 100rem. */
.page { box-sizing: border-box; max-width: 100rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); }
.head { margin-bottom: var(--ui-space-5); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.bulk { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-1); margin-bottom: var(--ui-space-3); padding: var(--ui-space-2) var(--ui-space-2) var(--ui-space-2) var(--ui-space-4); border-radius: var(--ui-radius-lg); background: var(--ui-bg-inverse); color: var(--ui-text-inverse); }
.bulk-count { margin-right: var(--ui-space-2); font-weight: 600; font-size: var(--ui-text-sm); }
.bulk-button { min-height: 2rem; padding: 0 var(--ui-space-3); border: 0; border-radius: var(--ui-radius-md); background: rgb(255 255 255 / .12); color: inherit; font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.bulk-button.ghost { margin-left: auto; background: transparent; }
.table-wrap { position: relative; overflow-x: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.table { width: 100%; border-collapse: collapse; }
.table th { padding: .625rem var(--ui-space-3); background: var(--ui-bg-subtle); border-bottom: 1px solid var(--ui-border); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; text-align: left; white-space: nowrap; }
.table td { padding: var(--ui-space-3); border-bottom: 1px solid var(--ui-border-subtle); color: var(--ui-text-secondary); vertical-align: middle; }
.table tbody tr:last-child td { border-bottom: 0; }
.table tr.selected td { background: var(--ui-accent-soft); }
.col-select, .cell-select { width: 2.5rem; padding-left: var(--ui-space-4) !important; }
.col-by { width: 10rem; } .col-versions { width: 7rem; } .col-date { width: 8rem; } .col-actions { width: 8rem; }
.check { width: 1rem; height: 1rem; margin: 0; accent-color: var(--ui-accent); }
.doc { display: flex; align-items: center; gap: var(--ui-space-3); }
.format { flex: none; display: grid; place-items: center; min-width: 2.25rem; height: 2rem; padding: 0 .25rem; box-sizing: border-box; border-radius: var(--ui-radius-md); font-size: .65625rem; font-weight: 700; }
.format.md { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); }
.format.html { background: var(--ui-format-html-bg); color: var(--ui-format-html-text); }
.doc-text { display: grid; gap: 2px; min-width: 0; }
.doc-title { color: var(--ui-text); font-weight: 600; overflow-wrap: anywhere; }
.doc-path { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.cell-by, .cell-versions, .cell-date { white-space: nowrap; }
/* Keep the cell a table-cell; inline children sit side by side. */
.cell-actions { text-align: right; white-space: nowrap; }
.cell-actions > * { vertical-align: middle; }
.cell-actions .row-menu { margin-left: var(--ui-space-1); }
.row-menu { display: inline-grid; place-items: center; width: 2.25rem; height: 2.25rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.row-menu:hover:not(:disabled) { background: var(--ui-bg-muted); color: var(--ui-text); }
.row-menu:disabled { opacity: .45; cursor: default; }
.empty { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-7) var(--ui-space-4); color: var(--ui-text-muted); text-align: center; }
.empty p { margin: 0; }
.empty-title { color: var(--ui-text); font-weight: 600; font-size: var(--ui-text-lg); }
.pager { display: flex; align-items: center; justify-content: center; gap: var(--ui-space-3); margin-top: var(--ui-space-3); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.confirm { display: grid; gap: var(--ui-space-3); }
.confirm label { font-weight: 600; }
.confirm-actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
@media (max-width: 720px) {
  .table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .table, .table tbody { display: block; }
  .table tbody tr { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; grid-template-areas: "select doc doc" "select by by" "select meta meta" "select actions actions"; gap: var(--ui-space-1) var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
  .table td { padding: 0 !important; border: 0 !important; background: transparent !important; }
  .table tr.selected { background: var(--ui-accent-soft); }
  .cell-select { grid-area: select; width: auto; padding-top: .5rem !important; }
  .cell-doc { grid-area: doc; }
  .cell-by { grid-area: by; padding-left: 2.75rem !important; font-size: var(--ui-text-sm); }
  .cell-by::before { content: '移入者 '; color: var(--ui-text-muted); }
  .cell-versions { grid-area: meta; padding-left: 2.75rem !important; font-size: var(--ui-text-sm); }
  .cell-date { grid-area: meta; justify-self: end; font-size: var(--ui-text-sm); }
  .cell-actions { grid-area: actions; padding-left: 2.25rem !important; text-align: left; }
}
</style>
