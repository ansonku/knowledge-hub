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

type Mode = 'read' | 'edit' | 'split'
type Layout = 'standard' | 'wide' | 'full'
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
const layouts: { value: Layout; label: string }[] = [
  { value: 'standard', label: '標準' },
  { value: 'wide', label: '寬版' },
  { value: 'full', label: '全頁' },
]
const preferenceKey = (format: DocumentDetails['format']) => `knowledge-hub.${format}.reader-layout`
const previewUrl = ref('')
const htmlPreviewError = ref('')
const htmlPreviewLoading = ref(false)
const file = ref<DocumentDetails>()
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
const canEdit = computed(() => file.value?.format === 'md' && ['admin', 'editor'].includes(role.value))
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
const layout = ref<Layout>('standard')
const lastContainedLayout = ref<Exclude<Layout, 'full'>>('standard')
const article = ref<HTMLElement>()
const dateFormatter = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium' })
const categoryRoute = computed(() => file.value
  ? { path: '/library/', query: { category: file.value.category ?? 'uncategorized' } }
  : { path: '/library/' })
const downloadUrl = computed(() => file.value
  ? `/api/documents/${file.value.id}/download/?version=${file.value.current_version.id}`
  : '')
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

function restoreLayout(format: DocumentDetails['format']) {
  lastContainedLayout.value = 'standard'
  layout.value = format === 'html' ? 'full' : 'standard'
  try {
    const stored = localStorage.getItem(preferenceKey(format))
    if (stored === 'standard' || stored === 'wide' || stored === 'full') layout.value = stored
    if (layout.value !== 'full') lastContainedLayout.value = layout.value
  } catch {
    // Browser storage may be disabled.
  }
}

watch(layout, value => {
  if (value !== 'full') lastContainedLayout.value = value
  if (!file.value) return
  try {
    localStorage.setItem(preferenceKey(file.value.format), value)
  } catch {
    // Keep the current preference for this page.
  }
})

function toggleFullPage() {
  layout.value = layout.value === 'full' ? lastContainedLayout.value : 'full'
}

function jumpTo(id: string, updateAddress = true) {
  const target = article.value?.querySelector<HTMLElement>(`[id="${id}"]`)
  if (!target) return
  target.focus({ preventScroll: true })
  target.scrollIntoView({ block: 'start' })
  if (updateAddress) history.replaceState(history.state, '', `#${id}`)
}

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
      if (/^section-\d+$/.test(anchor)) jumpTo(anchor, false)
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
    const response = await fetch(`/api/documents/${document.id}/preview/`, {
      method: 'POST', cache: 'no-store', signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf_token },
      body: JSON.stringify({ version: document.current_version.id }),
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
onBeforeRouteUpdate((to, from) => to.params.id === from.params.id || canLeave())
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => {
  currentRequest?.abort()
  window.removeEventListener('beforeunload', beforeUnload)
})
watch(() => route.params.id, loadDocument, { immediate: true })
</script>

<template>
  <div class="reader">
    <header class="reader-header">
      <RouterLink to="/">Knowledge Hub</RouterLink>
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
      <template v-else-if="file">
        <div class="reading-toolbar">
          <div class="identity">
            <h1>{{ file.title }}</h1>
            <Tag :value="file.format === 'md' ? 'Markdown' : 'HTML'" severity="info" />
            <Tag :value="`v${file.current_version.number}`" severity="secondary" />
          </div>
          <div class="reader-actions">
            <Select v-if="mode === 'read'" v-model="layout" :options="layouts" option-label="label"
              option-value="value" aria-label="閱讀版面" />
            <Button v-if="mode === 'read'" :label="layout === 'full' ? '還原版面' : '最大化'"
              severity="secondary" outlined @click="toggleFullPage" />
            <Button as="a" :href="downloadUrl" label="下載原始檔" />
          </div>
        </div>

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
            <p class="version-date">版本日期 · {{ dateFormatter.format(new Date(file.current_version.created_at)) }}</p>
            <div ref="article"><MarkdownBody :rendered="rendered" /></div>
          </section>
          <aside v-if="layout === 'standard' && rendered.headings.length" class="reader-sidebar reader-toc">
            <span>本頁目錄</span>
            <nav aria-label="本頁目錄">
              <a v-for="heading in rendered.headings" :key="heading.id" :href="`#${heading.id}`"
                :style="{ paddingInlineStart: `${Math.max(0, heading.level - 1) * .5}rem` }"
                @click.prevent="jumpTo(heading.id)">{{ heading.text }}</a>
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

<style scoped>
.reader { min-height: 100vh; background: #f5f7fb; }
.reader-header { padding: 1rem clamp(1rem, 4vw, 3rem); }
.reader-header a { text-decoration: none; }
.reader-main { max-width: 96rem; box-sizing: border-box; margin: 0 auto; padding: 1.5rem clamp(1rem, 3vw, 2.5rem); }
.reader-main-full { max-width: none; }
.breadcrumbs, .identity, .reader-actions, .reading-toolbar, .reader-feedback {
  display: flex; align-items: center; flex-wrap: wrap; gap: .7rem;
}
.breadcrumbs a, .reader-sidebar a { color: #214d99; text-underline-offset: .18em; }
.breadcrumbs { font-size: .9rem; color: #52647c; }
.reading-toolbar { justify-content: space-between; gap: 1.25rem; margin: 1.1rem 0 1.5rem; }
.identity h1 { margin: 0; font-size: clamp(1.75rem, 3vw, 2.4rem); overflow-wrap: anywhere; }
.reader-feedback { margin-top: 1.5rem; }
.reading-layout { display: grid; gap: clamp(.8rem, 2vw, 1.5rem); align-items: start; }
.layout-standard { grid-template-columns: minmax(9rem, 13rem) minmax(0, 1fr) minmax(9rem, 13rem); }
.layout-wide { max-width: 66rem; margin-inline: auto; }
.reader-sidebar { position: sticky; top: 1rem; display: grid; gap: .65rem; background: #edf2fa; border-radius: .65rem; padding: 1rem; }
.reader-sidebar > span { color: #435976; font-size: .8rem; font-weight: 700; }
.reader-sidebar a { overflow-wrap: anywhere; font-size: .9rem; }
.reader-toc nav { display: grid; gap: .5rem; max-height: 65vh; overflow-y: auto; }
.reading-paper {
  grid-column: 1; min-width: 0; padding: clamp(1rem, 3.5vw, 2.75rem); border: 1px solid #dee6f1;
  border-radius: .75rem; background: white;
}
.layout-standard .reading-paper { grid-column: 2; }
.editor-modes, .editor-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: .65rem; margin: 0 0 1rem; }
.editor-toolbar input { flex: 1 1 16rem; min-width: 0; padding: .65rem; border: 1px solid #b9c7d9; border-radius: .4rem; font: inherit; }
.editor-panes { display: grid; gap: 1rem; }
.editor-split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.preview-paper { grid-column: auto; max-height: clamp(28rem, 65vh, 56rem); overflow: auto; }
.editor-notice { margin-bottom: 1rem; }
.html-layout.layout-standard { grid-template-columns: minmax(9rem, 13rem) minmax(0, 1fr); }
.html-preview { min-width: 0; display: grid; gap: 1rem; }
.html-preview-controls { display: flex; flex-wrap: wrap; gap: .65rem; }
.html-frame { width: 100%; min-height: 72vh; border: 1px solid #dee6f1; border-radius: .65rem; background: white; }
.version-date { margin: 0 0 1.5rem; color: #52647c; font-size: .85rem; }
:deep(.markdown-body) { color: #192e49; line-height: 1.75; overflow-wrap: anywhere; }
:deep(.markdown-body h1), :deep(.markdown-body h2), :deep(.markdown-body h3),
:deep(.markdown-body h4), :deep(.markdown-body h5), :deep(.markdown-body h6) { line-height: 1.25; scroll-margin-top: 1.25rem; }
:deep(.markdown-body a) { color: #1746a2; text-underline-offset: .18em; }
:deep(.markdown-body pre) { overflow-x: auto; padding: 1rem; border-radius: .45rem; background: #edf2fa; }
:deep(.markdown-body img) { max-width: 100%; height: auto; }
:deep(.markdown-body blockquote) { margin-inline: 0; padding-inline: 1rem; border-left: 3px solid #8ba8d2; }
:deep(.markdown-body table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
:deep(.markdown-body th), :deep(.markdown-body td) { border: 1px solid #dce5f0; padding: .4rem .7rem; }
@media (max-width: 850px) {
  .layout-standard, .html-layout.layout-standard { grid-template-columns: minmax(0, 1fr); }
  .layout-standard .reading-paper { grid-column: 1; }
  .reader-sidebar { position: static; }
  .editor-split { grid-template-columns: minmax(0, 1fr); }
  .reader-toc { grid-row: 2; }
}
</style>
