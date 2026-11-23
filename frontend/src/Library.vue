<script setup lang="ts">
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PublicationDialog from './PublicationDialog.vue'

type Format = 'html' | 'md'
type Mode = 'single' | 'batch' | 'version'
type Label = { id: string; name: string }
type Category = Label & { parent: string | null }
type DocumentRow = {
  id: string
  title: string
  category: string | null
  category_name: string | null
  tags: Label[]
  format: Format
  current_version: { number: number }
  is_public: boolean
  updated_at: string
}
type UploadRow = {
  file: File
  title: string
  result: 'ready' | 'invalid' | 'duplicate' | 'complete'
  message: string
  progress: number
  override?: boolean
}

const rows = ref<DocumentRow[]>([])
const categories = ref<Category[]>([])
const tags = ref<Label[]>([])
const formats = [{ id: '', name: '全部格式' }, { id: 'html', name: 'HTML' }, { id: 'md', name: 'Markdown' }]
type PublicRow = { document_id: string; title: string }
const publicRows = ref<PublicRow[]>([])
const publicPages = ref(1)
const access = ref<'loading' | 'guest' | 'member' | 'error'>('loading')
const isMember = computed(() => access.value === 'member')
const isGuest = computed(() => access.value === 'guest')
const role = ref('')
const csrf = ref('')
const route = useRoute()
const searchText = ref(typeof route.query.q === 'string' ? route.query.q : '')
const keywords = ref(searchText.value.trim())
watch(searchText, (text, _, onCleanup) => {
  const timer = setTimeout(() => { keywords.value = text.trim() }, 250)
  onCleanup(() => clearTimeout(timer))
})
const category = ref(typeof route.query.category === 'string' ? route.query.category : '')
const format = ref('')
const tag = ref<string | null>(null)
const page = ref(1)
const count = ref(0)
const pageSize = ref(25)
const loading = ref(true)
const libraryError = ref('')
const canUpload = computed(() => role.value === 'admin' || role.value === 'editor')
const selected = ref<DocumentRow>()
const mode = ref<Mode>('single')
const uploadOpen = ref(false)
const chooser = ref<HTMLInputElement>()
const uploads = ref<UploadRow[]>([])
const processing = ref(false)
const dragging = ref(false)
const notice = ref('')
const fileNotice = ref('')
const newCategory = ref<string | null>(null)
const uploadTags = ref<string[]>([])
const note = ref('')
const maxBatch = ref(20)
const maxBytes = ref(50 * 1024 * 1024)
const maxMB = computed(() => maxBytes.value / (1024 * 1024))
const ready = computed(() => uploads.value.some(item => item.result === 'ready' || (item.result === 'duplicate' && item.override)))
const dialogTitle = computed(() => mode.value === 'version' ? '新增版本' : '上傳文件')
const taxonomyOpen = ref(false)
const taxonomyType = ref<'categories' | 'tags'>('categories')
const taxonomyId = ref<string | null>(null)
const taxonomyName = ref('')
const taxonomyParent = ref<string | null>(null)
const metadata = ref<DocumentRow>()
const publication = ref<DocumentRow>()
const metadataName = ref('')
const metadataCategory = ref<string | null>(null)
const metadataTags = ref<string[]>([])
const submitError = ref('')
const working = ref(false)
const removing = ref(false)
const dateFormatter = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short' })

const categoryOptions = computed(() => {
  const options: (Label & { depth: number })[] = []
  function append(parent: string | null, depth: number) {
    for (const item of categories.value.filter(item => item.parent === parent)) {
      options.push({ ...item, name: `${'　'.repeat(depth)}${item.name}`, depth })
      append(item.id, depth + 1)
    }
  }
  append(null, 0)
  return options
})
const navigation = computed(() => [
  { id: '', name: '全部文件' },
  ...categoryOptions.value,
  { id: 'uncategorized', name: '未分類' },
])
const taxonomyOptions = computed(() => taxonomyType.value === 'categories' ? categoryOptions.value : tags.value)

class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message) }
}

function errorMessage(body: unknown): string {
  if (typeof body === 'string') return body
  if (Array.isArray(body)) return body.map(errorMessage).filter(Boolean).join(' ')
  if (body && typeof body === 'object') return Object.values(body).map(errorMessage).filter(Boolean).join(' ')
  return ''
}

async function api(url: string, method = 'GET', data?: object) {
  const response = await fetch(url, {
    method, cache: 'no-store',
    headers: data ? { 'Content-Type': 'application/json', 'X-CSRFToken': csrf.value } : { 'X-CSRFToken': csrf.value },
    body: data ? JSON.stringify(data) : undefined,
  })
  if (response.status === 204) return
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, errorMessage(body) || '無法完成操作。')
  return body
}

let listRequest = 0
async function loadDocuments() {
  const request = ++listRequest
  loading.value = true
  libraryError.value = ''
  try {
    const params = new URLSearchParams({ page: String(page.value) })
    if (keywords.value) params.set('q', keywords.value)
    if (isGuest.value) {
      const data = await api(`/api/public/articles/?${params}`)
      if (request !== listRequest) return
      publicRows.value = data.results
      publicPages.value = data.pages
      if (page.value !== data.page) page.value = data.page
      return
    }
    if (category.value) params.set('category', category.value)
    if (format.value) params.set('file_format', format.value)
    if (tag.value) params.set('tag', tag.value)
    const data = await api(`/api/documents/?${params}`)
    if (request !== listRequest) return
    rows.value = data.results
    count.value = data.count
    pageSize.value = data.page_size
    maxBytes.value = data.limits.bytes
    maxBatch.value = data.limits.batch
    if (!data.results.length && page.value > 1) page.value = Math.max(1, Math.ceil(data.count / data.page_size))
  } catch (error) {
    if (request === listRequest) libraryError.value = error instanceof Error ? error.message : '無法載入文件。'
  } finally {
    if (request === listRequest) loading.value = false
  }
}

async function loadTaxonomy() {
  const [availableCategories, availableTags] = await Promise.all([api('/api/categories/'), api('/api/tags/')])
  categories.value = availableCategories
  tags.value = availableTags
}

onMounted(async () => {
  try {
    const account = await api('/api/auth/me')
    role.value = account.role
    csrf.value = account.csrf_token
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      access.value = 'guest'
      await loadDocuments()
    } else {
      access.value = 'error'
      loading.value = false
      libraryError.value = '無法載入文件庫，請重新整理頁面。'
    }
    return
  }
  try {
    await loadTaxonomy()
    if (!navigation.value.some(item => item.id === category.value)) category.value = ''
    access.value = 'member'
    await loadDocuments()
  } catch {
    access.value = 'error'
    loading.value = false
    libraryError.value = '無法載入文件庫，請重新整理頁面。'
  }
})

watch([category, format, tag, keywords], () => {
  if (page.value !== 1) page.value = 1
  else if (isMember.value || isGuest.value) void loadDocuments()
})
watch(page, () => { if (isMember.value || isGuest.value) void loadDocuments() })

function formatLabel(kind: Format) { return kind === 'html' ? 'HTML' : 'Markdown' }

function fileFormat(name: string): Format | undefined {
  if (/\.html$/i.test(name)) return 'html'
  if (/\.md$/i.test(name)) return 'md'
}

function openUpload(next: Mode, target?: DocumentRow) {
  if (!canUpload.value) return
  mode.value = next
  selected.value = target
  newCategory.value = categories.value.some(item => item.id === category.value) ? category.value : null
  uploadTags.value = []
  note.value = ''
  uploads.value = []
  fileNotice.value = ''
  notice.value = ''
  uploadOpen.value = true
}

function changeMode(next: Mode) {
  mode.value = next
  uploads.value = []
  fileNotice.value = ''
}

function addFiles(files: FileList | null) {
  if (!files || processing.value || !files.length) return
  fileNotice.value = ''
  const existing = mode.value === 'batch' ? uploads.value : []
  const limit = mode.value === 'batch' ? maxBatch.value : 1
  if (existing.length + files.length > limit) fileNotice.value = `此模式一次最多可選擇 ${limit} 個檔案。`
  const added = Array.from(files).slice(0, limit - existing.length).map(file => {
    const kind = fileFormat(file.name)
    let message = ''
    if (!kind) message = '請選擇 .md 或 .html 檔案。'
    else if (selected.value && kind !== selected.value.format) message = `新版本必須維持 ${formatLabel(selected.value.format)} 格式。`
    else if (!file.size) message = '空白檔案無法上傳。'
    else if (file.size > maxBytes.value) message = `超過每檔 ${maxMB.value} MB 上限。`
    return { file, title: file.name.replace(/\.[^.]+$/, ''), result: message ? 'invalid' : 'ready', message, progress: 0 } satisfies UploadRow
  })
  uploads.value = [...existing, ...added]
}

function choose(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(input.files)
  input.value = ''
}

function drop(event: DragEvent) {
  dragging.value = false
  addFiles(event.dataTransfer?.files ?? null)
}

function uploadFile(item: UploadRow, target?: DocumentRow) {
  return new Promise<DocumentRow>((resolve, reject) => {
    const data = new FormData()
    data.append('file', item.file)
    if (item.override) data.append('force', 'true')
    if (target) data.append('note', note.value)
    else {
      if (mode.value === 'single' && item.title.trim()) data.append('title', item.title.trim())
      if (newCategory.value) data.append('category', newCategory.value)
      for (const id of uploadTags.value) data.append('tags', id)
    }
    const request = new XMLHttpRequest()
    request.open('POST', target ? `/api/documents/${target.id}/versions/` : '/api/documents/')
    request.responseType = 'json'
    request.timeout = 180_000
    request.setRequestHeader('X-CSRFToken', csrf.value)
    request.upload.onprogress = event => {
      if (event.lengthComputable) item.progress = Math.round(event.loaded * 100 / event.total)
    }
    request.onload = () => {
      if (request.status === 201) resolve(request.response)
      else reject(new ApiError(request.status, errorMessage(request.response) || '上傳失敗，請重新整理後再試。'))
    }
    request.onerror = request.ontimeout = () => reject(new Error('連線中斷，請先確認文件清單再重試。'))
    request.send(data)
  })
}

async function saveUploads() {
  if (!canUpload.value || processing.value) return
  processing.value = true
  let complete = 0
  try {
    for (const item of uploads.value) {
      if (item.result !== 'ready' && !(item.result === 'duplicate' && item.override)) continue
      try {
        const document = await uploadFile(item, selected.value)
        item.result = 'complete'
        item.message = selected.value ? `已建立 v${document.current_version.number}` : '已新增文件 · v1'
        if (selected.value) selected.value = document
        complete++
      } catch (error) {
        item.result = error instanceof ApiError && error.status === 409 ? 'duplicate' : 'invalid'
        item.message = error instanceof Error ? error.message : '上傳失敗。'
      }
    }
    if (complete) {
      notice.value = `已儲存 ${complete} 個檔案。`
      await loadDocuments()
    }
  } finally {
    processing.value = false
  }
}

function selectTaxonomy(id: string | null) {
  taxonomyId.value = id
  const item = taxonomyType.value === 'categories'
    ? categories.value.find(category => category.id === id) : tags.value.find(tag => tag.id === id)
  taxonomyName.value = item?.name ?? ''
  taxonomyParent.value = item && 'parent' in item ? item.parent as string | null : null
  submitError.value = ''
  removing.value = false
}

async function saveTaxonomy(remove = false) {
  if (working.value) return
  working.value = true
  submitError.value = ''
  try {
    const id = taxonomyId.value
    const endpoint = `/api/${taxonomyType.value}/${id ? id + '/' : ''}`
    if (remove) {
      await api(endpoint, 'DELETE')
      if (category.value === id) category.value = ''
      if (tag.value === id) tag.value = null
    } else {
      const payload = taxonomyType.value === 'categories'
        ? { name: taxonomyName.value, parent: taxonomyParent.value } : { name: taxonomyName.value }
      await api(endpoint, id ? 'PATCH' : 'POST', payload)
    }
    await loadTaxonomy()
    await loadDocuments()
    selectTaxonomy(null)
  } catch (error) {
    submitError.value = error instanceof Error ? error.message : '無法儲存。'
  } finally {
    working.value = false
  }
}

function editMetadata(row: DocumentRow) {
  metadata.value = row
  metadataName.value = row.title
  metadataCategory.value = row.category
  metadataTags.value = row.tags.map(tag => tag.id)
  submitError.value = ''
  removing.value = false
}

async function saveMetadata(remove = false) {
  if (!metadata.value || working.value) return
  working.value = true
  submitError.value = ''
  try {
    const row = metadata.value
    const endpoint = `/api/documents/${row.id}/`
    if (remove) {
      await api(endpoint, 'DELETE')
      notice.value = '已將文件移入回收桶。'
    } else {
      await api(endpoint, 'PATCH', { title: metadataName.value, category: metadataCategory.value, tags: metadataTags.value })
      notice.value = '已更新文件資料。'
    }
    metadata.value = undefined
    await loadDocuments()
  } catch (error) {
    submitError.value = error instanceof Error ? error.message : '無法儲存。'
  } finally {
    working.value = false
  }
}

function sizeLabel(size: number) {
  return size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`
}
</script>


<template>
  <div class="library">
    <header class="library-header">
      <RouterLink to="/" class="site-brand">Knowledge Hub</RouterLink>
      <nav v-if="isMember" aria-label="帳號">
        <a href="/accounts/profile/">個人設定</a>
        <a v-if="role === 'admin'" href="/accounts/manage/">帳號管理</a>
        <a href="/accounts/logout/">登出</a>
      </nav>
      <a v-else-if="isGuest" :href="`/accounts/login/?next=${encodeURIComponent(route.fullPath)}`">登入</a>
    </header>
    <div class="library-layout">
      <aside class="library-sidebar" aria-label="文件導覽">
        <h2>文件庫</h2>
        <nav v-if="isMember">
          <button v-for="item in navigation" :key="item.id" type="button" :class="{ current: category === item.id }"
            :aria-pressed="category === item.id" @click="category = item.id">{{ item.name }}</button>
        </nav>
        <nav v-else-if="isGuest">
          <span class="current" aria-current="page">全部文件</span>
        </nav>
      </aside>
      <main class="library-main">
        <div class="library-heading">
          <div>
            <h1>知識總覽</h1>
          </div>
          <div v-if="canUpload" class="document-actions">
            <RouterLink to="/library/trash/">回收桶</RouterLink>
            <Button label="管理分類與標籤" outlined @click="selectTaxonomy(null); taxonomyOpen = true" />
          </div>
        </div>

        <Message v-if="libraryError" severity="error" size="small">{{ libraryError }}</Message>
        <Message v-if="notice" severity="success" size="small">{{ notice }}</Message>
        <section v-if="access !== 'error'" class="library-panel" aria-label="文件清單">
          <div class="library-toolbar">
            <form class="library-search" role="search" @submit.prevent="keywords = searchText.trim()">
              <InputText v-model="searchText" maxlength="240" :placeholder="isMember ? '搜尋標題、分類、標籤或全文' : '搜尋公開標題或正文'" aria-label="搜尋文件" />
              <Button v-if="searchText" type="button" label="清除" text @click="searchText = ''; keywords = ''" />
              <Button type="submit" label="搜尋" outlined />
            </form>
            <div v-if="isMember" class="library-filters" aria-label="文件格式">
              <Button v-for="item in formats" :key="item.id" :label="item.name" size="small"
                :outlined="format !== item.id" :severity="format === item.id ? 'primary' : 'secondary'"
                :aria-pressed="format === item.id" @click="format = item.id" />
              <Select v-model="tag" :options="tags" option-label="name" option-value="id" show-clear placeholder="所有標籤" aria-label="標籤篩選" />
            </div>
            <Button v-if="canUpload" label="＋ 上傳文件" @click="openUpload('single')" />
          </div>
          <DataTable :value="isMember ? rows : publicRows" :data-key="isMember ? 'id' : 'document_id'" :loading="loading"
            striped-rows :table-style="isMember ? 'min-width: 49rem' : undefined">
            <template #empty>{{ keywords ? "找不到符合條件的文件。" : (isMember ? "此分類與格式目前沒有文件。" : "目前沒有公開文章。") }}</template>
            <Column field="title" header="文件標題">
              <template #body="{ data }">
                <div class="document-title">
                  <RouterLink class="reader-link"
                    :to="isMember
                      ? { name: 'document-reader', params: { id: data.id } }
                      : { name: 'public-article', params: { id: data.document_id } }">{{ data.title }}</RouterLink>
                  <Tag v-if="isMember" :value="formatLabel(data.format)" :severity="data.format === 'html' ? 'info' : 'secondary'" />
                </div>
              </template>
            </Column>
            <Column v-if="isMember" field="category_name" header="分類">
              <template #body="{ data }">{{ data.category_name ?? '未分類' }}</template>
            </Column>
            <Column v-if="isMember" header="標籤">
              <template #body="{ data }">
                <div class="document-tags">
                  <Tag v-for="tag in data.tags" :key="tag.id" :value="tag.name" severity="secondary" />
                  <span v-if="!data.tags.length">—</span>
                </div>
              </template>
            </Column>
            <Column v-if="isMember" header="可見性">
              <template #body="{ data }">
                <Tag :value="data.is_public ? '公開' : '私人'"
                  :severity="data.is_public ? 'success' : 'secondary'" />
              </template>
            </Column>
            <Column v-if="isMember" header="版本">
              <template #body="{ data }">v{{ data.current_version.number }}</template>
            </Column>
            <Column v-if="isMember" field="updated_at" header="更新日期">
              <template #body="{ data }">{{ dateFormatter.format(new Date(data.updated_at)) }}</template>
            </Column>
            <Column v-if="isMember" header="操作">
              <template #body="{ data }">
                <div class="document-actions">
                  <Button as="a" :href="`/api/documents/${data.id}/download/`" label="下載" size="small" variant="text" />
                  <Button v-if="canUpload" label="管理文件" size="small" variant="text" @click="editMetadata(data)" />
                </div>
              </template>
            </Column>
          </DataTable>
          <footer v-if="isMember" class="library-count pagination">
            <span>共 {{ count }} 份文件</span>
            <Button v-if="page > 1" label="上一頁" size="small" text @click="page--" />
            <Button v-if="page * pageSize < count" label="下一頁" size="small" text @click="page++" />
          </footer>
          <nav v-else-if="isGuest && publicPages > 1" class="library-count pagination" aria-label="公開文章分頁">
            <Button label="上一頁" text :disabled="loading || page === 1" @click="page--" />
            <span>第 {{ page }} / {{ publicPages }} 頁</span>
            <Button label="下一頁" text :disabled="loading || page === publicPages" @click="page++" />
          </nav>
        </section>
      </main>
    </div>

    <Dialog v-model:visible="uploadOpen" :header="dialogTitle" modal :closable="!processing"
      :close-on-escape="!processing" :style="{ width: 'min(94vw, 42rem)' }">
      <div v-if="selected" class="version-target">
        <strong>{{ selected.title }}</strong>
        <span>v{{ selected.current_version.number }} · {{ formatLabel(selected.format) }}</span>
      </div>
      <div v-else class="upload-options">
        <Button label="單檔上傳" :variant="mode === 'single' ? undefined : 'outlined'" :disabled="processing" @click="changeMode('single')" />
        <Button label="批次上傳" :variant="mode === 'batch' ? undefined : 'outlined'" :disabled="processing" @click="changeMode('batch')" />
        <Select v-model="newCategory" :options="categoryOptions" option-label="name" option-value="id" placeholder="未分類" show-clear aria-label="新增文件的分類" :disabled="processing" />
        <MultiSelect v-model="uploadTags" :options="tags" option-label="name" option-value="id" placeholder="標籤" aria-label="標籤" :disabled="processing" />
      </div>

      <label v-if="selected" class="title-field">更新說明<InputText v-model="note" maxlength="500" :disabled="processing" /></label>
      <div class="dropzone" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="drop">
        <Button label="選擇檔案" outlined :disabled="processing" @click="chooser?.click()" />
        <input ref="chooser" type="file" accept=".md,.html" :multiple="mode === 'batch'" hidden @change="choose">
        <p>也可以拖曳檔案至此。支援 Markdown 和 HTML，每檔上限 {{ maxMB }} MB。</p>
        <small v-if="mode === 'batch'">最多 {{ maxBatch }} 個檔案，每個檔案都會建立一份新文件。</small>
      </div>
      <Message v-if="fileNotice" severity="warn" size="small">{{ fileNotice }}</Message>
      <ul v-if="uploads.length" class="upload-list" aria-label="檔案和處理結果">
        <li v-for="(item, index) in uploads" :key="index">
          <div class="upload-file">
            <strong>{{ item.file.name }}</strong>
            <small>{{ sizeLabel(item.file.size) }}</small>
          </div>
          <label v-if="mode === 'single' && item.result === 'ready'" class="title-field">
            文件標題
            <InputText v-model="item.title" maxlength="240" :disabled="processing" />
          </label>
          <progress v-if="processing && item.result === 'ready' && item.progress > 0" :value="item.progress" max="100" :aria-label="item.file.name" />
          <Message v-if="item.message" size="small"
            :severity="item.result === 'complete' ? 'success' : item.result === 'duplicate' ? 'warn' : 'error'">
            {{ item.message }}
          </Message>
          <label v-if="item.result === 'duplicate'" class="override">
            <input v-model="item.override" type="checkbox" :disabled="processing">
            仍要{{ mode === 'version' ? '建立新版本' : '新增文件' }}
          </label>
          <Button v-if="item.result !== 'complete'" label="移除" size="small" variant="text"
            :disabled="processing" @click="uploads.splice(index, 1)" />
        </li>
      </ul>
      <template #footer>
        <Button label="關閉" severity="secondary" variant="text" :disabled="processing" @click="uploadOpen = false" />
        <Button :label="mode === 'version' ? '建立新版本' : '開始上傳'" :loading="processing" :disabled="!ready" @click="saveUploads" />
      </template>
    </Dialog>
    <Dialog v-model:visible="taxonomyOpen" header="管理分類與標籤" modal :style="{ width: 'min(94vw, 32rem)' }">
      <form class="title-field" @submit.prevent="saveTaxonomy()">
        <label>類型</label>
        <Select v-model="taxonomyType" :options="[{ id: 'categories', name: '分類' }, { id: 'tags', name: '標籤' }]"
          option-label="name" option-value="id" aria-label="類型" @change="selectTaxonomy(null)" />
        <label>已有項目</label>
        <Select :model-value="taxonomyId" :options="taxonomyOptions" option-label="name" option-value="id" show-clear
          placeholder="選擇要編輯的項目，或留空新增" aria-label="已有項目" @update:model-value="selectTaxonomy" />
        <label for="taxonomy-name">名稱</label>
        <InputText id="taxonomy-name" v-model="taxonomyName" :maxlength="taxonomyType === 'categories' ? 120 : 60" required />
        <template v-if="taxonomyType === 'categories'">
          <label>上層分類</label>
          <Select v-model="taxonomyParent" :options="categoryOptions.filter(item => item.id !== taxonomyId)"
            option-label="name" option-value="id" show-clear placeholder="最上層" aria-label="上層分類" />
        </template>
        <Message v-if="submitError" severity="error">{{ submitError }}</Message>
        <div class="document-actions">
          <Button type="submit" :label="taxonomyId ? '儲存' : '新增'" :loading="working" />
          <Button v-if="taxonomyId" type="button" :label="removing ? '確認刪除' : '刪除'" severity="danger" outlined
            :disabled="working" @click="removing ? saveTaxonomy(true) : removing = true" />
        </div>
      </form>
    </Dialog>

    <PublicationDialog v-if="publication" :id="publication.id" :format="publication.format" :csrf="csrf"
      @close="publication = undefined" @changed="loadDocuments" />

    <Dialog :visible="Boolean(metadata)" header="管理文件" modal :style="{ width: 'min(94vw, 34rem)' }"
      @update:visible="value => { if (!value) metadata = undefined }">
      <form v-if="metadata" class="title-field" @submit.prevent="saveMetadata()">
        <label for="document-name">文件標題</label>
        <InputText id="document-name" v-model="metadataName" maxlength="240" required />
        <label>分類</label>
        <Select v-model="metadataCategory" :options="categoryOptions" option-label="name" option-value="id"
          show-clear placeholder="未分類" aria-label="分類" />
        <label>標籤</label>
        <MultiSelect v-model="metadataTags" :options="tags" option-label="name" option-value="id" aria-label="標籤" />
        <Message v-if="submitError" severity="error">{{ submitError }}</Message>
        <div class="document-actions">
          <Button type="submit" label="儲存" :loading="working" />
          <Button v-if="role === 'admin'" type="button" label="公開設定" outlined :disabled="working"
            @click="publication = metadata; metadata = undefined" />
          <Button type="button" label="新增版本" outlined :disabled="working" @click="openUpload('version', metadata); metadata = undefined" />
          <Button type="button" :label="removing ? '確認移入回收桶' : '移入回收桶'" severity="danger" outlined
            :disabled="working" @click="removing ? saveMetadata(true) : removing = true" />
        </div>
      </form>
    </Dialog>
  </div>
</template>

<style scoped>
.library { min-height: 100vh; background: #f5f7fb; color: #152b49; }
.library-header { padding: .95rem clamp(1rem, 3vw, 2.25rem); align-items: center; }
.library-header a { text-decoration: none; }
.library-layout { display: grid; grid-template-columns: 13rem minmax(0, 1fr); min-height: calc(100vh - 3.5rem); }
.library-search { display: flex; flex: 1 1 100%; gap: .5rem; }
.library-search input { flex: 1; min-width: 0; }
.library-sidebar { padding: 1.8rem .85rem; border-right: 1px solid #e0e7f0; background: #fbfcfe; }
.library-sidebar h2 { font-size: .875rem; margin: 0 .65rem .7rem; color: #475b77; }
.library-sidebar nav { display: grid; gap: .25rem; }
.library-sidebar button, .library-sidebar nav > span {
  padding: .65rem .8rem; border: 0; background: transparent; border-left: .2rem solid transparent;
  border-radius: .35rem; text-align: left; color: #263c5b; font: inherit;
}
.library-sidebar button { cursor: pointer; }
.library-sidebar .current { background: #e4edff; border-color: #2563eb; color: #1746a2; font-weight: 650; }
.library-sidebar button:hover { background: #eff4fd; }
.library-main { width: 100%; max-width: 89rem; box-sizing: border-box; margin: 0 auto; padding: 2rem clamp(1rem, 3vw, 2.5rem); }
.library-heading, .library-toolbar, .upload-file { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; }
.library-heading { margin-bottom: 1.4rem; }
.library-heading h1 { font-size: clamp(1.75rem, 3vw, 2.25rem); margin: 0 0 .35rem; }
.library-heading p, .library-count, .dropzone p, .dropzone small { color: #4c5e77; }
.library-heading p { margin: 0; }
.pagination, .library-filters, .document-title, .document-tags, .document-actions, .upload-options, .version-target, .override {
  display: flex; flex-wrap: wrap; gap: .5rem; align-items: center;
}
.pagination { justify-content: space-between; }
.library-panel { margin-top: 1rem; border: 1px solid #dfe6f0; border-radius: .75rem; background: white; overflow: hidden; }
.library-toolbar, .library-count { padding: 1rem 1.15rem; }
.library-count { font-size: .875rem; border-top: 1px solid #e3eaf2; }
.reader-link { overflow-wrap: anywhere; color: #1746a2; font-weight: 700; text-underline-offset: .18em; }
.document-actions { flex-wrap: nowrap; }
.dropzone {
  margin: 1rem 0; border: 1px dashed #82a5e8; border-radius: .6rem;
  background: #f5f8ff; text-align: center; padding: 1.45rem .75rem;
}
.dropzone.dragging { background: #e4edff; }
.dropzone p { margin: .75rem 0 0; }
.upload-list { padding: 0; margin: 1rem 0 0; list-style: none; max-height: 18rem; overflow-y: auto; }
.upload-list li { display: grid; gap: .5rem; padding: .7rem .15rem; border-bottom: 1px solid #e3eaf2; }
.upload-list li > button { justify-self: start; }
.upload-file strong { overflow-wrap: anywhere; }
.title-field { display: grid; gap: .35rem; }
@media (max-width: 720px) {
  .library-layout { grid-template-columns: 1fr; }
  .library-sidebar { border-right: 0; border-bottom: 1px solid #e0e7f0; padding: .65rem 1rem; }
  .library-sidebar h2 { display: none; }
  .library-sidebar nav { display: flex; overflow-x: auto; }
  .library-sidebar button, .library-sidebar nav > span { white-space: nowrap; }
  .library-main { padding-top: 1.2rem; }
}
</style>
