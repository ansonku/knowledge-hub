<script setup lang="ts">
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Skeleton from 'primevue/skeleton'
import ToggleSwitch from 'primevue/toggleswitch'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, defineAsyncComponent, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import MarkdownBody from '../MarkdownBody.vue'
import { renderMarkdown } from '../markdown'
import { jumpToHeading } from '../reader-layout'
import { useSession } from '../stores/session'
import { useTheme } from '../stores/theme'
import { UNCATEGORIZED, useTaxonomy } from '../stores/taxonomy'
import MetadataDialog from './components/MetadataDialog.vue'
import UiIcon from './components/UiIcon.vue'
import UploadDialog from './components/UploadDialog.vue'
import { useDocument, type DocumentDetails, type PublicationStatus } from './composables/useDocument'
import InfoTab from './inspector/InfoTab.vue'
import ActivityTab from './inspector/ActivityTab.vue'
import PublishTab from './inspector/PublishTab.vue'
import VersionsTab from './inspector/VersionsTab.vue'
import { formatLabel, longDateTime, shortDate, type DocumentRow } from './types'

type Mode = 'read' | 'edit' | 'split'
type Tab = 'info' | 'versions' | 'activity' | 'publish'

const route = useRoute()
const router = useRouter()
const session = useSession()
const taxonomy = useTaxonomy()
const confirm = useConfirm()
const toast = useToast()
const theme = useTheme()

const documentId = computed(() => String(route.params.id))
const versionId = computed(() => typeof route.query.version === 'string' ? route.query.version : undefined)
const doc = useDocument(documentId, versionId)
const { file, historical, shownVersion, draft, dirty, loading, error, saving, saveError } = doc

const Monaco = defineAsyncComponent({
  loader: () => import('../MarkdownEditor.vue'),
  loadingComponent: () => h(ProgressSpinner, { 'aria-label': '正在載入編輯器', style: 'width: 2rem; height: 2rem' }),
  errorComponent: () => h(Message, { severity: 'error' }, () => '無法載入編輯器，請重新整理頁面。'),
})

// ---- Modes and rendering ---------------------------------------------------
const mode = ref<Mode>('read')
const note = ref('')
const canEdit = computed(() => session.canEdit && file.value?.format === 'md' && !historical.value)
const modes: { value: Mode; label: string }[] = [
  { value: 'read', label: '閱讀' }, { value: 'edit', label: '編輯' }, { value: 'split', label: '分割預覽' },
]
const rendered = computed(() => renderMarkdown(doc.source.value))
/** Many Markdown files open with an H1 equal to the document title; the page header already shows it. */
const leadingTitle = computed(() => {
  const first = rendered.value.headings[0]
  return Boolean(first && first.level === 1 && first.id === 'section-1' && first.text.trim() === file.value?.title.trim())
})
const tocHeadings = computed(() => leadingTitle.value ? rendered.value.headings.slice(1) : rendered.value.headings)
const previewSource = ref('')
const preview = computed(() => renderMarkdown(previewSource.value))
watch(draft, (value, _, onCleanup) => {
  const timer = setTimeout(() => { previewSource.value = value }, 170)
  onCleanup(() => clearTimeout(timer))
}, { immediate: true })
const article = ref<HTMLElement>()

watch([documentId, versionId], () => {
  mode.value = 'read'
  note.value = ''
  closePreview()
  previewError.value = ''
})
watch(() => [loading.value, file.value?.id] as const, ([busy]) => {
  if (busy) return
  document.title = file.value ? `${file.value.title} · Knowledge Hub` : 'Knowledge Hub'
  const anchor = window.location.hash.slice(1)
  if (/^section-\d+$/.test(anchor)) requestAnimationFrame(() => jumpToHeading(article.value, anchor, false))
})

function setMode(next: Mode) {
  mode.value = next
}
// Monaco has one global theme; follow the workspace appearance whenever an editor is on screen.
watch([() => theme.isDark, mode], ([dark, current]) => {
  if (current !== 'read') void import('../monaco').then(({ editor }) => editor.setTheme(dark ? 'vs-dark' : 'vs'))
}, { immediate: true })
// Editing needs the width: hide the inspector while editing, restore the saved preference afterwards.
watch(mode, (next, previous) => {
  if (next !== 'read' && previous === 'read') inspectorOpen.value = false
  else if (next === 'read' && previous !== 'read') inspectorOpen.value = !narrow.matches && storedInspector()
})

async function save() {
  const number = await doc.save(note.value)
  if (!number) return
  note.value = ''
  toast.add({ severity: 'success', summary: `已儲存為 v${number}`, life: 3000 })
  void loadPublication()
}

function discard() {
  confirm.require({
    header: '捨棄變更',
    message: '編輯區會回到目前版本的內容，未儲存的修改將遺失。',
    acceptProps: { label: '捨棄變更', severity: 'danger' },
    rejectProps: { label: '繼續編輯', severity: 'secondary', text: true },
    accept: () => { doc.discard(); mode.value = 'read' },
  })
}

// ---- HTML preview (sandboxed, short-lived URL) -------------------------------
const previewUrl = ref('')
const previewError = ref('')
const previewLoading = ref(false)
// Each request gets a number so a slow ticket for a previous document/version never replaces a newer one.
let previewRequest = 0
async function openPreview() {
  const request = ++previewRequest
  previewLoading.value = true
  previewError.value = ''
  previewUrl.value = ''
  try {
    const url = await doc.issuePreview()
    if (request === previewRequest) previewUrl.value = url
  } catch (cause) {
    if (request === previewRequest) previewError.value = cause instanceof Error ? cause.message : '目前無法開啟 HTML 預覽。'
  } finally {
    if (request === previewRequest) previewLoading.value = false
  }
}
function closePreview() {
  previewRequest++
  previewLoading.value = false
  previewUrl.value = ''
}

// Loading the preview lets the document fetch its external HTTPS resources, so each
// browser remembers whether to do that on open (default) or only after a click.
const autoPreviewKey = 'knowledge-hub.app.html-autopreview'
function storedAutoPreview() {
  try { return localStorage.getItem(autoPreviewKey) !== 'off' } catch { return true }
}
const autoPreview = ref(storedAutoPreview())
watch(autoPreview, on => {
  try { localStorage.setItem(autoPreviewKey, on ? 'on' : 'off') } catch { /* storage may be disabled */ }
  if (on && !previewUrl.value && !previewLoading.value) void maybeAutoPreview()
})
function maybeAutoPreview() {
  if (!autoPreview.value || loading.value || file.value?.format !== 'html' || !file.value.preview_available) return
  return openPreview()
}
watch(() => [loading.value, file.value?.id, shownVersion.value?.id] as const, ([busy]) => {
  if (!busy) void maybeAutoPreview()
})

// ---- Breadcrumb and header --------------------------------------------------
const crumbs = computed(() => file.value ? taxonomy.pathOf(file.value.category) : [])
const versionLine = computed(() => {
  const version = shownVersion.value
  if (!version) return ''
  return `${version.author ?? '系統'} · ${shortDate(version.created_at)}`
})

// ---- Publication status (admin only) ----------------------------------------
const publication = ref<PublicationStatus>()
const publicationError = ref('')
async function loadPublication() {
  publication.value = undefined
  publicationError.value = ''
  if (!session.isAdmin || !file.value) return
  try {
    publication.value = await api<PublicationStatus>(`/api/documents/${encodeURIComponent(file.value.id)}/publication/`)
  } catch (cause) {
    publicationError.value = cause instanceof Error ? cause.message : '無法讀取公開設定。'
  }
}
watch(() => file.value?.id, loadPublication)
// Admins get live status from the publication API; everyone else uses the detail fields.
const publishedNumber = computed(() => publication.value
  ? publication.value.publication?.version__number
  : file.value?.published_version ?? undefined)
const visibility = computed(() => {
  if (!file.value || (session.isAdmin && !publication.value)) return undefined
  const published = publishedNumber.value
  if (!published) return { kind: 'private', label: '私人' }
  const behind = (file.value?.current_version.number ?? published) - published
  return behind > 0
    ? { kind: 'lagging', label: `公開 v${published} · 落後 ${behind} 版` }
    : { kind: 'public', label: `公開 v${published}` }
})

// ---- Favourite and recent views ----------------------------------------------------
const favoriteBusy = ref(false)
async function toggleFavorite() {
  const current = file.value
  if (!current || favoriteBusy.value) return
  const next = !current.is_favorite
  favoriteBusy.value = true
  doc.applyMetadata({ is_favorite: next })
  try {
    await api(`/api/documents/${encodeURIComponent(current.id)}/favorite/`, next ? 'PUT' : 'DELETE')
    toast.add({ severity: 'success', summary: next ? '已加入收藏' : '已取消收藏', life: 2000 })
  } catch (cause) {
    doc.applyMetadata({ is_favorite: !next })
    toast.add({ severity: 'error', summary: '無法更新收藏', detail: cause instanceof Error ? cause.message : '', life: 4000 })
  } finally {
    favoriteBusy.value = false
  }
}
// Record the visit once per document load (private to the viewer).
watch(() => file.value?.id, id => {
  if (id) void api(`/api/documents/${encodeURIComponent(id)}/view/`, 'POST').catch(() => undefined)
})

// ---- Inspector -------------------------------------------------------------------
const inspectorKey = 'knowledge-hub.app.inspector'
const narrow = window.matchMedia('(max-width: 1100px)')
function storedInspector() {
  try { return localStorage.getItem(inspectorKey) !== 'closed' } catch { return true }
}
const inspectorOpen = ref(route.query.panel === 'versions' || (!narrow.matches && storedInspector()))
const tab = ref<Tab>(route.query.panel === 'versions' ? 'versions' : 'info')
const tabs = computed(() => [
  { value: 'info' as const, label: '資訊' },
  { value: 'versions' as const, label: '版本' },
  { value: 'activity' as const, label: '活動' },
  ...(session.isAdmin ? [{ value: 'publish' as const, label: '公開' }] : []),
])
function setInspector(open: boolean) {
  inspectorOpen.value = open
  if (!narrow.matches) {
    try { localStorage.setItem(inspectorKey, open ? 'open' : 'closed') } catch { /* storage may be disabled */ }
  }
}
function openTab(next: Tab) {
  tab.value = next
  setInspector(true)
}
function onNarrowChange(event: MediaQueryListEvent) {
  inspectorOpen.value = !event.matches && storedInspector()
}

function jump(id: string) {
  if (narrow.matches) inspectorOpen.value = false
  mode.value = 'read'
  requestAnimationFrame(() => jumpToHeading(article.value, id))
}

// ---- Actions menu -------------------------------------------------------------
const moreMenu = ref<InstanceType<typeof Menu>>()
const uploadOpen = ref(false)
const editing = ref<DocumentRow>()
const asRow = computed<DocumentRow | undefined>(() => file.value as DocumentRow | undefined)

const menuItems = computed<MenuItem[]>(() => {
  if (!file.value) return []
  const items: MenuItem[] = [{ label: historical.value ? `下載 v${historical.value.number}` : '下載原始檔', url: doc.downloadUrl.value }]
  if (session.canEdit) {
    items.push(
      { label: '編輯標題與標籤', command: () => { editing.value = asRow.value } },
      { label: '上傳新版本', command: () => { uploadOpen.value = true } },
    )
  }
  items.push({ label: '在舊版介面開啟', url: `/library/${file.value.id}/` })
  if (session.canEdit) items.push({ separator: true }, { label: '移入回收桶', class: 'danger-item', command: moveToTrash })
  return items
})

function moveToTrash() {
  const current = file.value
  if (!current) return
  confirm.require({
    header: '移入回收桶',
    message: `「${current.title}」與所有版本會移入回收桶${publishedNumber.value ? '，公開網址也會立即失效' : ''}。之後可從回收桶還原。`,
    acceptProps: { label: '移入回收桶', severity: 'danger' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      try {
        await api(`/api/documents/${encodeURIComponent(current.id)}/`, 'DELETE')
        doc.discard()
        toast.add({ severity: 'success', summary: '已移入回收桶', detail: current.title, life: 3000 })
        await router.push(current.category ? { name: 'app-collection', params: { id: current.category } } : { name: 'app-library' })
      } catch (cause) {
        toast.add({ severity: 'error', summary: '無法移入回收桶', detail: cause instanceof Error ? cause.message : '', life: 5000 })
      }
    },
  })
}

function onMetadataSaved(saved: DocumentRow) {
  editing.value = undefined
  doc.applyMetadata(saved as Partial<DocumentDetails>)
}

function onUploaded() {
  void doc.load()
  void loadPublication()
}

function onRestored() {
  void router.replace({ name: 'app-document', params: { id: documentId.value } })
  void doc.load()
  void loadPublication()
}

// ---- Leaving with unsaved changes ------------------------------------------------
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
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  narrow.addEventListener('change', onNarrowChange)
})
onBeforeUnmount(() => {
  doc.abort()
  window.removeEventListener('beforeunload', beforeUnload)
  narrow.removeEventListener('change', onNarrowChange)
})
</script>

<template>
  <div class="doc-page" :class="{ 'with-inspector': inspectorOpen && file }">
    <header class="topbar">
      <nav class="crumbs" aria-label="目前位置">
        <RouterLink :to="{ name: 'app-library' }">全部文件</RouterLink>
        <template v-if="file">
          <template v-for="item in crumbs" :key="item.id">
            <span aria-hidden="true">/</span>
            <RouterLink :to="{ name: 'app-collection', params: { id: item.id } }">{{ item.name }}</RouterLink>
          </template>
          <template v-if="!crumbs.length">
            <span aria-hidden="true">/</span>
            <RouterLink :to="{ name: 'app-collection', params: { id: UNCATEGORIZED } }">未分類</RouterLink>
          </template>
        </template>
      </nav>
      <div v-if="file" class="actions">
        <button type="button" class="icon-button star" :class="{ on: file.is_favorite }" :aria-pressed="Boolean(file.is_favorite)"
          :aria-label="file.is_favorite ? '取消收藏' : '加入收藏'" :disabled="favoriteBusy" @click="toggleFavorite">
          <UiIcon name="star" :size="18" :filled="file.is_favorite" />
        </button>
        <Button v-if="session.isAdmin" outlined severity="secondary" size="small" class="action-button" @click="openTab('publish')">
          <UiIcon name="globe" :size="16" /><span>公開設定</span>
        </Button>
        <Button v-if="canEdit && mode === 'read'" size="small" class="action-button" @click="setMode('split')">
          <UiIcon name="edit" :size="16" /><span>編輯</span>
        </Button>
        <button type="button" class="icon-button" aria-label="更多操作" aria-haspopup="menu" aria-controls="doc-menu"
          @click="moreMenu?.toggle($event)">
          <UiIcon name="more" :size="18" />
        </button>
        <button type="button" class="icon-button" :class="{ pressed: inspectorOpen }" aria-label="資訊面板"
          :aria-pressed="inspectorOpen" aria-controls="doc-inspector" @click="setInspector(!inspectorOpen)">
          <UiIcon name="panel" :size="18" />
        </button>
        <Menu id="doc-menu" ref="moreMenu" :model="menuItems" popup />
      </div>
    </header>

    <div class="layout">
      <section class="content" :class="{ wide: mode !== 'read' || file?.format === 'html' }" aria-label="文件內容">
        <div v-if="loading" class="skeleton" aria-busy="true">
          <Skeleton width="60%" height="2.25rem" />
          <Skeleton width="40%" />
          <Skeleton width="100%" height="1rem" class="gap" />
          <Skeleton width="95%" />
          <Skeleton width="88%" />
          <Skeleton width="92%" />
        </div>

        <div v-else-if="error" class="state">
          <UiIcon name="alert" :size="28" />
          <p class="state-title">{{ error }}</p>
          <div class="state-actions">
            <Button label="重新載入" outlined @click="doc.load()" />
            <Button label="回到文件清單" text @click="router.push({ name: 'app-library' })" />
          </div>
        </div>

        <template v-else-if="file && shownVersion">
          <div class="head">
            <Message v-if="historical" severity="info" class="banner">
              正在檢視舊版 v{{ historical.number }}（{{ longDateTime(historical.created_at) }}）。
              <RouterLink :to="{ name: 'app-document', params: { id: file.id } }">回到目前版本 v{{ file.current_version.number }}</RouterLink>
            </Message>
            <h1>{{ file.title }}</h1>
            <div class="meta">
              <span class="chip">{{ formatLabel(file.format) }}</span>
              <span class="chip">v{{ shownVersion.number }}</span>
              <button v-if="visibility" type="button" class="chip status" :class="visibility.kind" @click="openTab('publish')">
                <span class="dot" aria-hidden="true" />{{ visibility.label }}
              </button>
              <span class="byline">{{ versionLine }}</span>
            </div>
            <div v-if="canEdit" class="modes" role="group" aria-label="檢視模式">
              <button v-for="item in modes" :key="item.value" type="button" class="mode" :class="{ on: mode === item.value }"
                :aria-pressed="mode === item.value" :disabled="saving" @click="setMode(item.value)">{{ item.label }}</button>
            </div>
          </div>

          <!-- Markdown: read -->
          <div v-if="file.format === 'md' && mode === 'read'" ref="article" class="reading" :class="{ 'skip-title': leadingTitle }">
            <MarkdownBody :rendered="rendered" />
          </div>

          <!-- Markdown: edit / split -->
          <div v-else-if="file.format === 'md'" class="editor">
            <form class="editor-bar" @submit.prevent="save">
              <span class="draft-state" :class="{ dirty }" role="status">
                <span class="dot" aria-hidden="true" />{{ dirty ? '尚未儲存的變更' : '沒有變更' }}
              </span>
              <label for="version-note" class="ui-visually-hidden">更新說明</label>
              <InputText id="version-note" v-model="note" maxlength="500" placeholder="更新說明（選填）" size="small"
                class="note" :disabled="saving" />
              <Button v-if="dirty" type="button" label="捨棄變更" text severity="secondary" size="small" :disabled="saving" @click="discard" />
              <Button type="submit" :label="`儲存為 v${file.current_version.number + 1}`" size="small" :loading="saving"
                :disabled="!dirty || !draft.trim()" />
            </form>
            <Message v-if="saveError" severity="error" size="small" class="save-error">{{ saveError }}</Message>
            <div class="panes" :class="{ split: mode === 'split' }">
              <Monaco v-model="draft" :readonly="saving" />
              <div v-if="mode === 'split'" class="preview" aria-label="即時預覽">
                <span class="preview-label">即時預覽</span>
                <MarkdownBody :rendered="preview" />
              </div>
            </div>
          </div>

          <!-- HTML -->
          <div v-else class="html">
            <template v-if="file.preview_available">
              <Message severity="warn" size="small">
                HTML 預覽在隔離的沙箱中執行。相容模式可載入外部 HTTPS 資源，外部服務可能收到你的連線資訊。關閉「自動載入」後，需按下按鈕才會載入。
              </Message>
              <div class="html-actions">
                <Button :label="previewUrl ? '重新載入預覽' : '開啟 HTML 預覽'" size="small" :loading="previewLoading" @click="openPreview" />
                <Button v-if="previewUrl" label="關閉預覽" text size="small" @click="closePreview" />
                <span class="auto-preview">
                  <ToggleSwitch v-model="autoPreview" input-id="html-autopreview" />
                  <label for="html-autopreview">自動載入</label>
                </span>
                <a :href="doc.downloadUrl.value" class="download">下載原始檔</a>
              </div>
              <Message v-if="previewError" severity="error" size="small">{{ previewError }}</Message>
              <iframe v-if="previewUrl" :key="previewUrl" :src="previewUrl" title="HTML 文件沙箱預覽"
                sandbox="allow-scripts" referrerpolicy="no-referrer" class="html-frame" />
            </template>
            <Message v-else severity="info">這個環境不提供 HTML 預覽，請下載原始檔檢視。</Message>
          </div>
        </template>
      </section>

      <div v-if="inspectorOpen && file" class="scrim" aria-hidden="true" @click="setInspector(false)" />
      <aside v-if="inspectorOpen && file" id="doc-inspector" class="inspector" aria-label="文件資訊面板">
        <div class="tabs" role="tablist" aria-label="面板分頁">
          <button v-for="item in tabs" :id="`tab-${item.value}`" :key="item.value" type="button" role="tab" class="tab"
            :class="{ on: tab === item.value }" :aria-selected="tab === item.value" :aria-controls="`panel-${item.value}`"
            @click="tab = item.value">{{ item.label }}</button>
          <span class="tabs-spacer" />
          <button type="button" class="icon-button close" aria-label="關閉資訊面板" @click="setInspector(false)">
            <UiIcon name="close" :size="16" />
          </button>
        </div>
        <div :id="`panel-${tab}`" role="tabpanel" :aria-labelledby="`tab-${tab}`" class="panel">
          <InfoTab v-if="tab === 'info'" :document="file" :headings="file.format === 'md' ? tocHeadings : []"
            :editable="session.canEdit" @jump="jump" @updated="doc.applyMetadata" />
          <VersionsTab v-else-if="tab === 'versions'" :document="file" :shown-id="historical?.id" :can-restore="session.canEdit"
            :published-number="publishedNumber" @restored="onRestored" />
          <ActivityTab v-else-if="tab === 'activity'" :document-id="file.id" :revision="`${file.current_version.id}-${file.updated_at}`" />
          <PublishTab v-else :document="file" :status="publication" :error="publicationError"
            @changed="status => { publication = status }" />
        </div>
      </aside>
    </div>

    <UploadDialog v-if="asRow" v-model:visible="uploadOpen" :target="asRow" :max-bytes="session.limits.bytes" :max-batch="1"
      @uploaded="onUploaded" />
    <MetadataDialog :document="editing" @close="editing = undefined" @saved="onMetadataSaved" />
  </div>
</template>

<style scoped>
.doc-page { min-height: 100vh; display: flex; flex-direction: column; }
.topbar {
  position: sticky; top: 0; z-index: 10; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: var(--ui-space-2) var(--ui-space-4); min-height: var(--ui-topbar-height); padding: var(--ui-space-2) var(--ui-space-5);
  box-sizing: border-box; border-bottom: 1px solid var(--ui-border); background: var(--ui-bg-surface);
}
.crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: .375rem; min-width: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.crumbs a { color: inherit; text-decoration: none; }
.crumbs a:hover { color: var(--ui-accent); text-decoration: underline; }
.actions { display: flex; align-items: center; gap: var(--ui-space-2); }
.action-button { gap: var(--ui-space-2); }
.icon-button {
  display: grid; place-items: center; width: 2.25rem; height: 2.25rem; border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-secondary); cursor: pointer;
}
.icon-button:hover { background: var(--ui-bg-subtle); }
.icon-button.star { border-color: transparent; }
.icon-button.star.on { color: #d99a00; }
.icon-button.pressed { background: var(--ui-accent-soft); border-color: var(--ui-accent); color: var(--ui-accent-on-soft); }

.layout { flex: 1; display: flex; align-items: stretch; min-height: 0; }
.content { flex: 1; min-width: 0; padding: var(--ui-space-6) clamp(1rem, 4vw, 3.5rem) var(--ui-space-7); box-sizing: border-box; }
/* Markdown reads at a 48rem measure; HTML previews and the editor use a wider column, title included. */
.content > * { max-width: 48rem; margin-inline: auto; }
.content.wide > * { max-width: 72rem; }
.skeleton { display: grid; gap: var(--ui-space-3); }
.skeleton .gap { margin-top: var(--ui-space-5); }
.state { display: grid; justify-items: center; gap: var(--ui-space-3); padding: var(--ui-space-7) 0; color: var(--ui-text-muted); text-align: center; }
.state-title { margin: 0; color: var(--ui-text); font-weight: 600; font-size: var(--ui-text-lg); }
.state-actions { display: flex; gap: var(--ui-space-2); }

.head { margin-bottom: var(--ui-space-5); }
.banner { margin-bottom: var(--ui-space-4); }
.banner a { color: inherit; font-weight: 600; }
h1 { margin: 0 0 var(--ui-space-3); font-size: var(--ui-text-title); line-height: 1.25; font-weight: 700; letter-spacing: -.01em; overflow-wrap: anywhere; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.chip { display: inline-flex; align-items: center; gap: .375rem; padding: 2px var(--ui-space-2); border: 0; border-radius: var(--ui-radius-sm); background: var(--ui-bg-muted); color: var(--ui-text-secondary); font: inherit; font-size: var(--ui-text-sm); font-weight: 500; }
.chip.status { font-weight: 600; cursor: pointer; }
.chip .dot { width: 6px; height: 6px; border-radius: 50%; }
.chip.public { background: var(--ui-public-bg); color: var(--ui-public-text); }
.chip.public .dot { background: var(--ui-public-dot); }
.chip.lagging { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.chip.lagging .dot { background: var(--ui-lagging-dot); }
.chip.private { background: var(--ui-private-bg); color: var(--ui-private-text); }
.chip.private .dot { background: var(--ui-private-dot); }
.byline { margin-left: var(--ui-space-1); }
.modes { display: inline-flex; gap: 2px; margin-top: var(--ui-space-5); padding: 3px; border-radius: .5625rem; background: var(--ui-bg-muted); }
.mode { min-height: 1.875rem; padding: 0 .875rem; border: 0; border-radius: .4375rem; background: transparent; color: var(--ui-text-muted); font: inherit; font-size: var(--ui-text-sm); font-weight: 500; cursor: pointer; }
.mode.on { background: var(--ui-bg-surface); color: var(--ui-text); font-weight: 600; box-shadow: var(--ui-shadow-sm); }
.mode:disabled { cursor: default; }

/* Reading typography */
.reading, .preview { color: var(--ui-text-reading-color); font-size: var(--ui-text-reading); line-height: var(--ui-leading-reading); overflow-wrap: anywhere; }
.reading :deep(.markdown-body > div > *:first-child) { margin-top: 0; }
.reading.skip-title :deep(.markdown-body > div > h1:first-child) { display: none; }
.reading.skip-title :deep(.markdown-body > div > h1:first-child + *) { margin-top: 0; }
.reading :deep(h1), .reading :deep(h2), .reading :deep(h3), .reading :deep(h4),
.preview :deep(h1), .preview :deep(h2), .preview :deep(h3), .preview :deep(h4) {
  color: var(--ui-text); line-height: 1.35; scroll-margin-top: calc(var(--ui-topbar-height) + 1rem);
}
.reading :deep(h1) { font-size: 1.625rem; margin: 2.25rem 0 .75rem; }
.reading :deep(h2) { font-size: 1.375rem; margin: 2.25rem 0 .75rem; }
.reading :deep(h3) { font-size: 1.1875rem; margin: 1.75rem 0 .5rem; }
.reading :deep(h4) { font-size: 1.0625rem; margin: 1.5rem 0 .5rem; }
.reading :deep(p), .reading :deep(ul), .reading :deep(ol), .reading :deep(blockquote) { margin: 0 0 1.125rem; }
.reading :deep(a), .preview :deep(a) { color: var(--ui-accent); text-underline-offset: .18em; }
.reading :deep(:not(pre) > code), .preview :deep(:not(pre) > code) {
  padding: .125rem .375rem; border-radius: var(--ui-radius-sm); background: var(--ui-code-inline-bg); font-size: .875em;
}
.reading :deep(pre), .preview :deep(pre) {
  overflow-x: auto; margin: 0 0 1.25rem; padding: var(--ui-space-4) 1.125rem; border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-lg); background: var(--ui-bg-subtle); font-size: .8125rem; line-height: 1.7;
}
.reading :deep(blockquote), .preview :deep(blockquote) { padding: .25rem 1rem; border-left: 3px solid var(--ui-border-strong); color: var(--ui-text-secondary); }
.reading :deep(table), .preview :deep(table) { display: block; max-width: 100%; overflow-x: auto; margin: 0 0 1.25rem; border-collapse: collapse; font-size: .9375rem; }
.reading :deep(th), .reading :deep(td), .preview :deep(th), .preview :deep(td) { padding: .5rem .875rem; border: 1px solid var(--ui-border); text-align: left; }
.reading :deep(th), .preview :deep(th) { background: var(--ui-bg-subtle); font-weight: 600; }
.reading :deep(img), .preview :deep(img) { max-width: 100%; height: auto; border-radius: var(--ui-radius-md); }
.reading :deep(hr) { border: 0; border-top: 1px solid var(--ui-border); margin: 2rem 0; }

/* Editor */
.editor { display: grid; gap: var(--ui-space-3); }
.editor-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); padding: var(--ui-space-2) var(--ui-space-3);
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-subtle);
}
.draft-state { display: inline-flex; align-items: center; gap: .375rem; margin-right: auto; color: var(--ui-text-muted); font-size: var(--ui-text-sm); font-weight: 600; }
.draft-state .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ui-private-dot); }
.draft-state.dirty { color: var(--ui-lagging-text); }
.draft-state.dirty .dot { background: var(--ui-lagging-dot); }
.note { flex: 1 1 14rem; max-width: 24rem; }
.panes { display: grid; gap: var(--ui-space-3); }
.panes.split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.panes :deep(.editor-host) { border: 1px solid var(--ui-border); }
.preview {
  max-height: clamp(28rem, 65vh, 56rem); overflow: auto; padding: var(--ui-space-4) var(--ui-space-5);
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); box-sizing: border-box; font-size: 1rem;
}
.preview-label { display: block; margin-bottom: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }

/* HTML */
.html { display: grid; gap: var(--ui-space-3); }
.html-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); }
.auto-preview { display: inline-flex; align-items: center; gap: var(--ui-space-2); margin-left: var(--ui-space-2); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.auto-preview label { cursor: pointer; }
.download { margin-left: auto; color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; }
.html-frame { box-sizing: border-box; width: 100%; min-height: 72vh; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: #fff; }

/* Inspector */
.inspector {
  flex: none; width: var(--ui-inspector-width); box-sizing: border-box; border-left: 1px solid var(--ui-border);
  background: var(--ui-bg-panel); position: sticky; top: var(--ui-topbar-height); align-self: flex-start;
  height: calc(100vh - var(--ui-topbar-height)); overflow-y: auto;
}
.tabs { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: var(--ui-space-1); padding: var(--ui-space-2) var(--ui-space-3) 0; border-bottom: 1px solid var(--ui-border); background: var(--ui-bg-panel); }
.tab { min-height: 2.375rem; padding: 0 .625rem; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--ui-text-muted); font: inherit; font-weight: 500; cursor: pointer; }
.tab:hover { color: var(--ui-text); }
.tab.on { border-bottom-color: var(--ui-accent); color: var(--ui-accent-on-soft); font-weight: 600; }
.tabs-spacer { flex: 1; }
.close { width: 2rem; height: 2rem; border: 0; background: transparent; margin-bottom: var(--ui-space-1); }
.scrim { display: none; }

@media (max-width: 1100px) {
  .inspector {
    position: fixed; z-index: 45; top: 0; right: 0; height: 100%; width: min(90vw, 22rem);
    box-shadow: var(--ui-shadow-lg);
  }
  .scrim { display: block; position: fixed; z-index: 44; inset: 0; background: rgb(16 24 40 / .35); }
  .panes.split { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 900px) {
  .topbar { position: static; padding-inline: var(--ui-space-4); }
}
</style>
