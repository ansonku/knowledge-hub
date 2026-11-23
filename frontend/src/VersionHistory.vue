<script setup lang="ts">
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { computed, defineAsyncComponent, h, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

type Version = {
  id: string
  number: number
  filename: string
  note: string
  source: string
  author: string | null
  created_at: string
  restored_from_number: number | null
}
type Details = { id: string; title: string; format: 'md' | 'html' }
type History = { current: string; count: number; page_size: number; results: Version[] }

const route = useRoute()
const documentId = computed(() => encodeURIComponent(String(route.params.id)))
const endpoint = computed(() => `/api/documents/${documentId.value}/`)
const details = ref<Details>()
const history = ref<History>()
const page = ref(1)
const role = ref('')
const csrf = ref('')
const loading = ref(true)
const error = ref('')
const notice = ref('')
const selected = ref<Version[]>([])
const compareOpen = ref(false)
const comparing = ref(false)
const compareError = ref('')
const comparison = ref<{ original: string; modified: string; older: number; newer: number }>()
const restoring = ref<Version>()
const restoreNote = ref('')
const restoreError = ref('')
const saving = ref(false)
const canRestore = computed(() => role.value === 'admin' || role.value === 'editor')
const dateTime = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short' })
const DiffEditor = defineAsyncComponent({
  loader: () => import('./VersionDiff.vue'),
  loadingComponent: () => h(ProgressSpinner, { 'aria-label': '正在載入差異編輯器' }),
  errorComponent: () => h(Message, { severity: 'error' }, () => '無法載入差異編輯器。'),
})
let loadingRequest: AbortController | undefined
let comparisonRequest: AbortController | undefined

function href(version: Version) {
  return `${endpoint.value}versions/${version.id}/download/`
}

function reader(version?: Version) {
  return { name: 'document-reader', params: { id: route.params.id }, query: version ? { version: version.id } : {} }
}

function sourceLabel(version: Version) {
  if (version.source === 'restore') return `還原自 v${version.restored_from_number}`
  return version.source === 'markdown_edit' ? 'Markdown 編輯' : '上傳'
}

async function load() {
  loadingRequest?.abort()
  const request = new AbortController()
  loadingRequest = request
  loading.value = true
  error.value = ''
  try {
    const options = { cache: 'no-store', signal: request.signal } as const
    const [document, versions, account] = await Promise.all([
      fetch(endpoint.value, options),
      fetch(`${endpoint.value}versions/?page=${page.value}`, options),
      fetch('/api/auth/me', options),
    ])
    if (account.status === 403) {
      window.location.assign(`/accounts/login/?next=${encodeURIComponent(route.fullPath)}`)
      return
    }
    if (document.status === 404) throw new Error('找不到這份文件。')
    if (!document.ok || !versions.ok || !account.ok) throw new Error('無法載入版本歷史，請再試一次。')
    const [doc, list, user] = await Promise.all([document.json(), versions.json(), account.json()])
    if (request.signal.aborted) return
    details.value = doc
    history.value = list
    role.value = user.role
    csrf.value = user.csrf_token
  } catch (failure) {
    if (!request.signal.aborted) error.value = failure instanceof Error ? failure.message : '無法載入版本歷史。'
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}

watch(documentId, () => {
  selected.value = []
  page.value = 1
  notice.value = ''
  compareOpen.value = false
  restoring.value = undefined
  void load()
}, { immediate: true })
watch(page, load)

function toggle(version: Version) {
  const index = selected.value.findIndex(item => item.id === version.id)
  if (index >= 0) selected.value.splice(index, 1)
  else if (selected.value.length < 2) selected.value.push(version)
}

async function compare() {
  if (selected.value.length !== 2) return
  const [older, newer] = [...selected.value].sort((a, b) => a.number - b.number)
  compareOpen.value = true
  comparing.value = true
  compareError.value = ''
  comparison.value = undefined
  comparisonRequest?.abort()
  const request = new AbortController()
  comparisonRequest = request
  try {
    const texts = await Promise.all([older, newer].map(async version => {
      const response = await fetch(href(version), { cache: 'no-store', signal: request.signal })
      if (!response.ok) throw new Error(`無法讀取 v${version.number} 的原始檔。`)
      return response.text()
    }))
    if (!request.signal.aborted) comparison.value = { original: texts[0], modified: texts[1], older: older.number, newer: newer.number }
  } catch (failure) {
    if (!request.signal.aborted) compareError.value = failure instanceof Error ? failure.message : '無法比較版本。'
  } finally {
    if (!request.signal.aborted) comparing.value = false
  }
}

watch(compareOpen, open => { if (!open) comparisonRequest?.abort() })

function requestRestore(version: Version) {
  restoring.value = version
  restoreNote.value = ''
  restoreError.value = ''
}

async function restore() {
  if (!restoring.value || !history.value || saving.value) return
  saving.value = true
  restoreError.value = ''
  const candidate = restoring.value
  try {
    const response = await fetch(`${endpoint.value}versions/${candidate.id}/restore/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf.value },
      body: JSON.stringify({ base_version: history.value.current, note: restoreNote.value }),
    })
    const result = await response.json().catch(() => null)
    if (response.status === 409) {
      await load()
      throw new Error('目前版本已變更。清單已更新，請確認後再還原。')
    }
    if (!response.ok) throw new Error(result?.detail || '無法還原版本。')
    notice.value = `已從 v${candidate.number} 還原，並建立 v${result.current_version.number}。`
    restoring.value = undefined
    selected.value = []
    if (page.value !== 1) page.value = 1
    else await load()
  } catch (failure) {
    restoreError.value = failure instanceof Error ? failure.message : '無法還原版本。'
  } finally {
    saving.value = false
  }
}

onBeforeUnmount(() => {
  loadingRequest?.abort()
  comparisonRequest?.abort()
})
</script>

<template>
  <header>
    <RouterLink to="/" class="site-brand">Knowledge Hub</RouterLink>
    <RouterLink to="/library/">知識總覽</RouterLink>
  </header>
  <main class="history-page">
    <RouterLink :to="reader()">返回文件</RouterLink>
    <div class="history-toolbar">
      <div>
        <h1>版本歷史</h1>
        <p v-if="details">{{ details.title }}</p>
      </div>
      <div class="history-actions">
        <span>已選 {{ selected.length }} 個版本</span>
        <Button label="比較版本" :disabled="selected.length !== 2" @click="compare" />
      </div>
    </div>
    <Message v-if="notice" severity="success">{{ notice }}</Message>
    <ProgressSpinner v-if="loading" aria-label="正在載入版本" />
    <Message v-else-if="error" severity="error">{{ error }}</Message>
    <template v-else-if="history">
      <ol class="version-list" aria-label="版本列表">
        <li v-for="version in history.results" :key="version.id" class="version-card">
          <div class="version-info">
            <div class="version-title">
              <Checkbox :model-value="selected.some(item => item.id === version.id)" binary
                :aria-label="`選取 v${version.number} 進行比較`"
                :disabled="selected.length >= 2 && !selected.some(item => item.id === version.id)"
                @update:model-value="toggle(version)" />
              <RouterLink :to="reader(version)">v{{ version.number }}</RouterLink>
              <Tag v-if="version.id === history.current" value="目前版本" />
              <Tag :value="sourceLabel(version)" severity="secondary" />
            </div>
            <p>{{ version.author ?? '系統' }} · {{ dateTime.format(new Date(version.created_at)) }}</p>
            <p v-if="version.note" class="version-note">{{ version.note }}</p>
          </div>
          <div class="history-actions">
            <Button as="a" :href="href(version)" label="下載" text />
            <Button v-if="canRestore && version.id !== history.current" label="還原" outlined @click="requestRestore(version)" />
          </div>
        </li>
      </ol>
      <nav class="history-actions" aria-label="版本分頁">
        <Button v-if="page > 1" label="上一頁" text @click="page--" />
        <span>共 {{ history.count }} 個版本</span>
        <Button v-if="page * history.page_size < history.count" label="下一頁" text @click="page++" />
      </nav>
    </template>
    <Dialog v-model:visible="compareOpen" header="版本差異" modal :style="{ width: 'min(95vw, 96rem)' }">
      <ProgressSpinner v-if="comparing" aria-label="正在讀取版本內容" />
      <Message v-else-if="compareError" severity="error">{{ compareError }}</Message>
      <template v-else-if="comparison && details">
        <p>v{{ comparison.older }} → v{{ comparison.newer }}</p>
        <DiffEditor :original="comparison.original" :modified="comparison.modified" :format="details.format" />
      </template>
    </Dialog>
    <Dialog :visible="!!restoring" header="確認還原版本" modal :closable="!saving" :close-on-escape="!saving"
      :style="{ width: 'min(94vw, 35rem)' }" @update:visible="value => { if (!value && !saving) restoring = undefined }">
      <form v-if="restoring" class="restore-form" @submit.prevent="restore">
        <p>將 v{{ restoring.number }} 的內容儲存為新的目前版本。既有版本會保留。</p>
        <label for="restore-note">更新說明</label>
        <Textarea id="restore-note" v-model="restoreNote" maxlength="500" :disabled="saving" rows="3" />
        <Message v-if="restoreError" severity="error">{{ restoreError }}</Message>
        <Button type="submit" label="確認還原" :loading="saving" />
      </form>
    </Dialog>
  </main>
</template>

<style scoped>
.history-page { max-width: 65rem; }
.history-toolbar, .version-card, .history-actions, .version-title { display: flex; align-items: center; flex-wrap: wrap; gap: .75rem; }
.history-toolbar, .version-card { justify-content: space-between; }
.history-toolbar { margin: 1rem 0 1.5rem; }
.history-toolbar h1, .history-toolbar p { margin: .2rem 0; }
.version-list { display: grid; gap: .75rem; padding: 0; list-style: none; }
.version-card { padding: 1rem; border: 1px solid #dee6f1; border-radius: .65rem; background: white; }
.version-title a { color: #1746a2; font-weight: 700; text-underline-offset: .18em; }
.version-info p { margin: .55rem 0 0; color: #52647c; }
.version-info .version-note { white-space: pre-wrap; overflow-wrap: anywhere; color: #152b49; }
.version-info { min-width: 0; }
.restore-form { display: grid; gap: .75rem; }
.restore-form button { justify-self: end; }
</style>
