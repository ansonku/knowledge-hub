<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, defineAsyncComponent, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import MarkdownBody from './MarkdownBody.vue'
import { renderMarkdown } from './markdown'
import { jumpToHeading, layouts, useReaderLayout } from './reader-layout'

type Mode = 'read' | 'edit' | 'split'
type Category = { id: string; name: string; parent: string | null }
type DocumentDetails = {
  id: string
  category: string | null
  category_name: string | null
  title: string
  format: 'md' | 'html'
  preview_available?: boolean
  current_version: { id: string; number: number; created_at: string; filename: string }
}

const route = useRoute()
const previewUrl = ref('')
const htmlPreviewError = ref('')
const htmlPreviewLoading = ref(false)
const file = ref<DocumentDetails>()
const historicalVersion = ref<DocumentDetails['current_version']>()
const shownVersion = computed(() => historicalVersion.value ?? file.value?.current_version)
const source = ref('')
const draft = ref('')
const previewSource = ref('')
const mode = ref<Mode>('read')
const role = ref('')
const csrf = ref('')
const saving = ref(false)
const editorError = ref('')
const savedMessage = ref('')
const note = ref('')
const canEdit = computed(() => !historicalVersion.value && file.value?.format === 'md' && ['admin', 'editor'].includes(role.value))
const dirty = computed(() => draft.value !== source.value)
const Monaco = defineAsyncComponent({
  loader: () => import('./MarkdownEditor.vue'),
  loadingComponent: () => h(ProgressSpinner, { 'aria-label': '正在載入編輯器' }),
  errorComponent: () => h(Message, { severity: 'error' }, () => '無法載入編輯器，請重新整理頁面。'),
})
const modes: { value: Mode; label: string }[] = [
  { value: 'read', label: '閱讀' }, { value: 'edit', label: '編輯' }, { value: 'split', label: '分割預覽' },
]
const categoryList = ref<Category[]>([])
const loading = ref(true)
const error = ref('')
const { layout, restoreLayout, toggleFullPage } = useReaderLayout(computed(() => file.value?.format))
const article = ref<HTMLElement>()
const dateFormatter = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium' })
const categoryRoute = computed(() => file.value
  ? { path: '/library/', query: { category: file.value.category ?? 'uncategorized' } }
  : { path: '/library/' })
const downloadUrl = computed(() => {
  if (!file.value) return ''
  const endpoint = `/api/documents/${file.value.id}/`
  return historicalVersion.value
    ? `${endpoint}versions/${historicalVersion.value.id}/download/`
    : `${endpoint}download/?version=${file.value.current_version.id}`
})
const categoryPath = computed(() => {
  const byId = new Map(categoryList.value.map(category => [category.id, category]))
  const result: Category[] = []
  let id = file.value?.category
  while (id && !result.some(category => category.id === id)) {
    const category = byId.get(id)
    if (!category) break
    result.unshift(category)
    id = category.parent
  }
  return result
})

const preview = computed(() => renderMarkdown(previewSource.value))
const rendered = computed(() => renderMarkdown(source.value))
watch(draft, (value, _, onCleanup) => {
  const refresh = setTimeout(() => { previewSource.value = value }, 170)
  onCleanup(() => clearTimeout(refresh))
})

function redirectToLogin() {
  const next = encodeURIComponent(route.fullPath.split('#')[0])
  window.location.assign(`/accounts/login/?next=${next}`)
}

let currentRequest: AbortController | undefined
async function loadDocument() {
  currentRequest?.abort()
  const request = new AbortController()
  currentRequest = request
  loading.value = true
  error.value = ''
  file.value = undefined
  historicalVersion.value = undefined
  source.value = ''
  draft.value = ''
  mode.value = 'read'
  editorError.value = ''
  savedMessage.value = ''
  note.value = ''
  previewUrl.value = ''
  htmlPreviewError.value = ''
  htmlPreviewLoading.value = false
  categoryList.value = []
  try {
    const id = encodeURIComponent(String(route.params.id))
    const response = await fetch(`/api/documents/${id}/`, { cache: 'no-store', signal: request.signal })
    if (response.status === 403) return redirectToLogin()
    if (!response.ok) throw new Error(response.status === 404 ? '找不到這份文件。' : '無法載入文件。')
    if (request.signal.aborted) return
    const details = await response.json() as DocumentDetails
    if (request.signal.aborted) return
    const version = route.query.version
    if (typeof version === 'string') {
      const history = await fetch(`/api/documents/${id}/versions/${encodeURIComponent(version)}/`, {
        cache: 'no-store', signal: request.signal,
      })
      if (history.status === 403) return redirectToLogin()
      if (!history.ok) throw new Error('找不到指定的文件版本。')
      const selected = await history.json() as DocumentDetails['current_version']
      if (request.signal.aborted) return
      if (selected.id !== details.current_version.id) historicalVersion.value = selected
    }
    file.value = details
    restoreLayout(details.format)
    if (details.format !== 'md') return
    const [download, categories, session] = await Promise.all([
      fetch(downloadUrl.value, { cache: 'no-store', signal: request.signal }),
      fetch('/api/categories/', { cache: 'no-store', signal: request.signal }).catch(() => null),
      fetch('/api/auth/me', { cache: 'no-store', signal: request.signal }).catch(() => null),
    ])
    if (download.status === 403) return redirectToLogin()
    if (download.status === 409) throw new Error('文件已有新版本，請重新載入。')
    if (!download.ok) throw new Error('無法讀取 Markdown 原始檔。')
    const text = await download.text()
    const available: Category[] = categories?.ok ? await categories.json().catch(() => []) : []
    const account = session?.ok ? await session.json().catch(() => null) : null
    if (request.signal.aborted) return
    source.value = draft.value = previewSource.value = text
    role.value = account?.role ?? ''
    csrf.value = account?.csrf_token ?? ''
    categoryList.value = available
  } catch (failure) {
    if (!request.signal.aborted) error.value = failure instanceof Error ? failure.message : '無法載入文件。'
  } finally {
    if (!request.signal.aborted) {
      loading.value = false
      await nextTick()
      const anchor = window.location.hash.slice(1)
      if (/^section-\d+$/.test(anchor)) jumpToHeading(article.value, anchor, false)
    }
  }
}

async function startHtmlPreview() {
  const document = file.value
  const signal = currentRequest?.signal
  if (!document?.preview_available || htmlPreviewLoading.value) return
  htmlPreviewLoading.value = true
  previewUrl.value = ''
  htmlPreviewError.value = ''
  try {
    const account = await fetch('/api/auth/me', { cache: 'no-store', signal })
    if (!account.ok) throw new Error('登入狀態已失效，請重新登入。')
    const { csrf_token } = await account.json()
    const endpoint = `/api/documents/${document.id}/`
    const previewPath = historicalVersion.value ? `versions/${historicalVersion.value.id}/preview/` : 'preview/'
    const response = await fetch(endpoint + previewPath, {
      method: 'POST', cache: 'no-store', signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf_token },
      body: JSON.stringify({ version: shownVersion.value?.id }),
    })
    if (response.status === 409) throw new Error('文件已有新版本，請重新載入頁面。')
    if (!response.ok) throw new Error('目前無法開啟 HTML 預覽。')
    const { url } = await response.json()
    if (typeof url !== 'string' || !/^\/preview\/[A-Za-z0-9_-]{43}\/$/.test(url)) {
      throw new Error('預覽連結無效。')
    }
    if (!signal?.aborted) previewUrl.value = url
  } catch (failure) {
    if (!signal?.aborted) htmlPreviewError.value = failure instanceof Error ? failure.message : '目前無法開啟 HTML 預覽。'
  } finally {
    if (!signal?.aborted) htmlPreviewLoading.value = false
  }
}

async function saveDraft() {
  if (!file.value || !dirty.value || !canEdit.value || saving.value) return
  saving.value = true
  editorError.value = ''
  savedMessage.value = ''
  const text = draft.value
  const form = new FormData()
  form.append('file', new Blob([text], { type: 'text/markdown;charset=utf-8' }), file.value.current_version.filename)
  form.append('base_version', file.value.current_version.id)
  form.append('note', note.value)
  try {
    const response = await fetch(`/api/documents/${file.value.id}/markdown/`, {
      method: 'POST', headers: { 'X-CSRFToken': csrf.value }, body: form,
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = body?.detail ?? body?.file?.[0]
      throw new Error(detail || '無法儲存新版本，草稿仍保留在編輯區。')
    }
    file.value = body as DocumentDetails
    source.value = text
    note.value = ''
    savedMessage.value = `已儲存 v${file.value.current_version.number}。`
  } catch (failure) {
    editorError.value = failure instanceof Error ? failure.message : '無法儲存新版本。'
  } finally {
    saving.value = false
  }
}

function canLeave() {
  return !saving.value && (!dirty.value || window.confirm('離開會捨棄未儲存的草稿，要繼續嗎？'))
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value || saving.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate((to, from) => (to.params.id === from.params.id && to.query.version === from.query.version) || canLeave())
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => {
  currentRequest?.abort()
  window.removeEventListener('beforeunload', beforeUnload)
})
watch([() => route.params.id, () => route.query.version], loadDocument, { immediate: true })
</script>

<template>
  <div class="reader">
    <header class="reader-header">
      <RouterLink to="/" class="site-brand">Knowledge Hub</RouterLink>
      <RouterLink to="/library/">知識總覽</RouterLink>
    </header>
    <main class="reader-main" :class="{ 'reader-main-full': layout === 'full' }">
      <nav class="breadcrumbs" aria-label="目前位置">
        <RouterLink to="/library/">知識總覽</RouterLink>
        <template v-if="file?.category_name">
          <span aria-hidden="true">/</span>
          <RouterLink :to="categoryRoute">{{ file.category_name }}</RouterLink>
        </template>
      </nav>

      <div v-if="loading" class="reader-feedback"><ProgressSpinner aria-label="正在載入文件" /></div>
      <div v-else-if="error" class="reader-feedback">
        <Message severity="error">{{ error }}</Message>
        <Button label="重新載入" outlined @click="loadDocument" />
      </div>
      <template v-else-if="file && shownVersion">
        <div class="reading-toolbar">
          <div class="identity">
            <h1>{{ file.title }}</h1>
            <Tag :value="file.format === 'md' ? 'Markdown' : 'HTML'" severity="info" />
            <Tag :value="`v${shownVersion.number}`" severity="secondary" />
          </div>
          <div class="reader-actions">
            <Select v-if="mode === 'read'" v-model="layout" :options="layouts" option-label="label"
              option-value="value" aria-label="閱讀版面" />
            <Button v-if="mode === 'read'" :label="layout === 'full' ? '還原版面' : '最大化'"
              severity="secondary" outlined @click="toggleFullPage" />
            <RouterLink :to="{ name: 'version-history', params: { id: file.id } }">版本歷史</RouterLink>
            <Button as="a" :href="downloadUrl" label="下載原始檔" />
          </div>
        </div>

        <Message v-if="historicalVersion" severity="info" class="editor-notice">
          正在查看舊版 v{{ historicalVersion.number }}。
          <RouterLink :to="{ name: 'document-reader', params: { id: file.id } }">回到目前版本</RouterLink>
        </Message>
        <nav v-if="canEdit" class="editor-modes" aria-label="Markdown 模式">
          <Button v-for="choice in modes" :key="choice.value" :label="choice.label" :outlined="mode !== choice.value"
            :aria-pressed="mode === choice.value" :disabled="saving" @click="mode = choice.value" />
          <span v-if="dirty" role="status">尚未儲存</span>
        </nav>
        <Message v-if="savedMessage" severity="success" class="editor-notice">{{ savedMessage }}</Message>
        <div v-if="file.format === 'md' && mode === 'read'" class="reading-layout" :class="`layout-${layout}`">
          <aside v-if="layout === 'standard'" class="reader-sidebar" aria-label="分類導覽">
            <span>分類</span>
            <RouterLink to="/library/">全部文件</RouterLink>
            <RouterLink v-for="category in categoryPath" :key="category.id"
              :to="{ path: '/library/', query: { category: category.id } }">{{ category.name }}</RouterLink>
            <RouterLink v-if="!categoryPath.length" :to="categoryRoute">{{ file.category_name ?? '未分類' }}</RouterLink>
          </aside>
          <section class="reading-paper" aria-label="文章內容">
            <p class="version-date">版本日期 · {{ dateFormatter.format(new Date(shownVersion.created_at)) }}</p>
            <div ref="article"><MarkdownBody :rendered="rendered" /></div>
          </section>
          <aside v-if="layout === 'standard' && rendered.headings.length" class="reader-sidebar reader-toc">
            <span>本頁目錄</span>
            <nav aria-label="本頁目錄">
              <a v-for="heading in rendered.headings" :key="heading.id" :href="`#${heading.id}`"
                :style="{ paddingInlineStart: `${Math.max(0, heading.level - 1) * .5}rem` }"
                @click.prevent="jumpToHeading(article, heading.id)">{{ heading.text }}</a>
            </nav>
          </aside>
        </div>
        <section v-else-if="canEdit" aria-label="Markdown 編輯">
          <form class="editor-toolbar" @submit.prevent="saveDraft">
            <label for="version-note">更新說明</label>
            <input id="version-note" v-model="note" maxlength="500" :disabled="saving">
            <Button type="submit" label="儲存為新版本" :disabled="!dirty || !draft.trim()" :loading="saving" />
          </form>
          <Message v-if="editorError" severity="error" class="editor-notice">{{ editorError }}</Message>
          <div class="editor-panes" :class="{ 'editor-split': mode === 'split' }">
            <Monaco v-model="draft" :readonly="saving" />
            <div v-if="mode === 'split'" class="reading-paper preview-paper" aria-label="即時預覽">
              <MarkdownBody :rendered="preview" />
            </div>
          </div>
        </section>
        <div v-else-if="file.preview_available" class="html-layout reading-layout" :class="`layout-${layout}`">
          <aside v-if="layout === 'standard'" class="reader-sidebar" aria-label="分類導覽">
            <span>分類</span>
            <RouterLink to="/library/">全部文件</RouterLink>
            <RouterLink :to="categoryRoute">{{ file.category_name ?? '未分類' }}</RouterLink>
          </aside>
          <section class="html-preview" aria-label="HTML 預覽">
            <Message severity="warn" size="small">
              相容模式可載入外部 HTTPS 資源，外部服務可能收到你的連線資訊或追蹤預覽活動。
            </Message>
            <div class="html-preview-controls">
              <Button :label="previewUrl ? '重新載入預覽' : '開啟 HTML 預覽'" :loading="htmlPreviewLoading"
                @click="startHtmlPreview" />
              <Button v-if="previewUrl" label="關閉預覽" text @click="previewUrl = ''" />
            </div>
            <Message v-if="htmlPreviewError" severity="error">{{ htmlPreviewError }}</Message>
            <iframe v-if="previewUrl" :key="previewUrl" :src="previewUrl" title="HTML 文件沙箱預覽"
              sandbox="allow-scripts" referrerpolicy="no-referrer" class="html-frame" />
          </section>
        </div>
        <Message v-else severity="info">這個環境提供 HTML 原始檔下載。</Message>
      </template>
    </main>
  </div>
</template>

<style scoped src="./reader.css"></style>

<style scoped>
.editor-modes, .editor-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: .65rem; margin: 0 0 1rem; }
.editor-toolbar input { flex: 1 1 16rem; min-width: 0; padding: .65rem; border: 1px solid #b9c7d9; border-radius: .4rem; font: inherit; }
.editor-panes { display: grid; gap: 1rem; }
.editor-split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.preview-paper { grid-column: auto; max-height: clamp(28rem, 65vh, 56rem); overflow: auto; }
.editor-notice { margin-bottom: 1rem; }
@media (max-width: 850px) {
  .editor-split { grid-template-columns: minmax(0, 1fr); }
}
</style>
