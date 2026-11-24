<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import InputText from 'primevue/inputtext'
import Skeleton from 'primevue/skeleton'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api, ApiError } from '../../api'
import { versionSource, type DocumentDetails, type VersionInfo } from '../composables/useDocument'
import { longDateTime, shortDate } from '../types'

type DeletedVersion = { number: number; deleted_at: string; deleted_by: string | null; reason: string }
type History = { current: string; count: number; page_size: number; results: VersionInfo[]; deleted: DeletedVersion[] }
type Entry = { kind: 'version'; number: number; version: VersionInfo } | { kind: 'deleted'; number: number; deleted: DeletedVersion }

const props = defineProps<{
  document: DocumentDetails; shownId?: string; canRestore: boolean; publishedNumber?: number
  /** Admins can permanently delete versions other than the current and the published one. */
  canDelete?: boolean
}>()
const emit = defineEmits<{ restored: [] }>()

const router = useRouter()
const toast = useToast()
const versions = ref<VersionInfo[]>([])
const deletedVersions = ref<DeletedVersion[]>([])
const current = ref('')
const count = ref(0)
const page = ref(1)
const loading = ref(true)
const error = ref('')
const selected = ref<string[]>([])
const restoring = ref<VersionInfo>()
const restoreNote = ref('')
const restoreError = ref('')
const saving = ref(false)

const base = computed(() => `/api/documents/${encodeURIComponent(props.document.id)}/`)
const hasMore = computed(() => versions.value.length < count.value)
/** Versions and the places of deleted ones, newest first; deleted ones only within the loaded range. */
const entries = computed<Entry[]>(() => {
  const oldest = hasMore.value ? Math.min(...versions.value.map(version => version.number)) : 0
  return [
    ...versions.value.map(version => ({ kind: 'version' as const, number: version.number, version })),
    ...deletedVersions.value.filter(item => item.number > oldest).map(deleted => ({ kind: 'deleted' as const, number: deleted.number, deleted })),
  ].sort((a, b) => b.number - a.number)
})
const pair = computed(() => versions.value.filter(version => selected.value.includes(version.id)).sort((a, b) => a.number - b.number))

async function load(reset = true) {
  loading.value = true
  error.value = ''
  if (reset) page.value = 1
  try {
    const data = await api<History>(`${base.value}versions/?page=${page.value}`)
    versions.value = reset ? data.results : [...versions.value, ...data.results]
    deletedVersions.value = data.deleted ?? []
    current.value = data.current
    count.value = data.count
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法載入版本。'
  } finally {
    loading.value = false
  }
}

function more() {
  page.value++
  void load(false)
}

watch(() => [props.document.id, props.document.current_version.id], () => {
  selected.value = []
  void load()
}, { immediate: true })

function toggle(id: string) {
  if (selected.value.includes(id)) selected.value = selected.value.filter(item => item !== id)
  else selected.value = [...selected.value, id].slice(-2)
}

function compare() {
  const [older, newer] = pair.value
  if (!older || !newer) return
  void router.push({ name: 'app-compare', params: { id: props.document.id }, query: { from: older.id, to: newer.id } })
}

function requestRestore(version: VersionInfo) {
  restoring.value = version
  restoreNote.value = `還原自 v${version.number}`
  restoreError.value = ''
}

// ---- Permanent deletion (Admin) -------------------------------------------------
const deleting = ref<VersionInfo>()
const typed = ref('')
const deleteReason = ref('')
const deleteError = ref('')
const blocked = computed(() => {
  const version = deleting.value
  if (!version) return ''
  if (version.id === current.value) return '這是目前版本，不能刪除。如果要刪除，請先用其他版本「還原為新版本」，再回來刪除這個版本。'
  if (version.number === props.publishedNumber) return '這是公開中的版本，不能刪除。請先在「公開」分頁改發布其他版本，或下架文章。'
  return ''
})
const confirmed = computed(() => Boolean(deleting.value) && typed.value.trim().toLowerCase() === `v${deleting.value?.number}`)

function requestDelete(version: VersionInfo) {
  deleting.value = version
  typed.value = ''
  deleteReason.value = ''
  deleteError.value = ''
}

async function remove() {
  const victim = deleting.value
  if (!victim || !confirmed.value || saving.value) return
  saving.value = true
  deleteError.value = ''
  try {
    await api(`${base.value}versions/${victim.id}/delete/`, 'POST', { number: victim.number, reason: deleteReason.value.trim() })
    toast.add({ severity: 'success', summary: `已永久刪除 v${victim.number}`, life: 4000 })
    deleting.value = undefined
    selected.value = selected.value.filter(id => id !== victim.id)
    // If the deleted version was on screen, go back to the current one.
    if (props.shownId === victim.id) void router.replace({ name: 'app-document', params: { id: props.document.id }, query: { panel: 'versions' } })
    await load()
  } catch (cause) {
    deleteError.value = cause instanceof Error ? cause.message : '無法刪除版本。'
  } finally {
    saving.value = false
  }
}

async function restore() {
  const candidate = restoring.value
  if (!candidate || saving.value) return
  saving.value = true
  restoreError.value = ''
  try {
    const result = await api<DocumentDetails>(`${base.value}versions/${candidate.id}/restore/`, 'POST',
      { base_version: current.value, note: restoreNote.value.trim() })
    toast.add({ severity: 'success', summary: `已從 v${candidate.number} 還原`, detail: `建立了 v${result.current_version.number}`, life: 4000 })
    restoring.value = undefined
    emit('restored')
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 409) {
      await load()
      restoreError.value = '目前版本已變更，清單已更新，請確認後再還原。'
    } else {
      restoreError.value = cause instanceof Error ? cause.message : '無法還原版本。'
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="versions">
    <div class="compare">
      <Button v-if="pair.length === 2" :label="`比較 v${pair[0].number} → v${pair[1].number}`" size="small" fluid @click="compare" />
      <p v-else class="hint">勾選兩個版本以比較差異</p>
    </div>

    <Message v-if="error" severity="error" size="small">
      {{ error }} <Button label="重試" text size="small" @click="load()" />
    </Message>

    <ol class="timeline" aria-label="版本時間軸">
      <template v-for="entry in entries" :key="`${entry.kind}-${entry.number}`">
        <li v-if="entry.kind === 'deleted'" class="entry deleted">
          <span class="check-space" aria-hidden="true" />
          <div class="body">
            <div class="head">
              <span class="number gone">v{{ entry.number }}</span>
              <span class="badge removed">已刪除</span>
              <time class="when" :datetime="entry.deleted.deleted_at" :title="longDateTime(entry.deleted.deleted_at)">{{ shortDate(entry.deleted.deleted_at) }}</time>
            </div>
            <p class="meta">{{ entry.deleted.deleted_by ?? '系統' }} 永久刪除<template v-if="entry.deleted.reason">・{{ entry.deleted.reason }}</template></p>
          </div>
        </li>
        <li v-else class="entry" :class="{ shown: entry.version.id === (shownId ?? current) }">
          <input :id="`version-${entry.version.id}`" type="checkbox" class="check" :checked="selected.includes(entry.version.id)"
            :aria-label="`選取 v${entry.version.number} 進行比較`" @change="toggle(entry.version.id)">
          <div class="body">
            <div class="head">
              <RouterLink :to="{ name: 'app-document', params: { id: document.id }, query: entry.version.id === current ? {} : { version: entry.version.id } }"
                class="number" :aria-current="entry.version.id === (shownId ?? current) ? 'true' : undefined">v{{ entry.version.number }}</RouterLink>
              <span v-if="entry.version.id === current" class="badge current">目前版本</span>
              <span v-if="entry.version.number === publishedNumber" class="badge published">公開中</span>
              <time class="when" :datetime="entry.version.created_at" :title="longDateTime(entry.version.created_at)">{{ shortDate(entry.version.created_at) }}</time>
            </div>
            <p v-if="entry.version.note" class="note">{{ entry.version.note }}</p>
            <p class="meta">{{ entry.version.author ?? '系統' }} · {{ versionSource(entry.version) }}</p>
            <div class="row-actions">
              <a :href="`${base}versions/${entry.version.id}/download/`" class="action">下載</a>
              <button v-if="canRestore && entry.version.id !== current" type="button" class="action" @click="requestRestore(entry.version)">還原為新版本</button>
              <button v-if="canDelete" type="button" class="action danger" @click="requestDelete(entry.version)">刪除</button>
            </div>
          </div>
        </li>
      </template>
      <template v-if="loading">
        <li v-for="index in 3" :key="`s${index}`" class="entry"><Skeleton width="100%" height="3.5rem" /></li>
      </template>
    </ol>
    <Button v-if="hasMore && !loading" label="載入更早的版本" text size="small" fluid @click="more" />

    <Dialog :visible="Boolean(deleting)" :header="deleting ? `永久刪除 v${deleting.number}` : ''" modal :closable="!saving"
      :close-on-escape="!saving" :style="{ width: 'min(94vw, 30rem)' }" @update:visible="open => { if (!open && !saving) deleting = undefined }">
      <div v-if="deleting && blocked" class="restore">
        <Message severity="warn" size="small">{{ blocked }}</Message>
        <div class="restore-actions"><Button type="button" label="知道了" @click="deleting = undefined" /></div>
      </div>
      <form v-else-if="deleting" class="restore" @submit.prevent="remove">
        <p>v{{ deleting.number }} 的內容和檔案會被永久刪除，<strong>無法復原</strong>。</p>
        <ul class="consequences">
          <li>版本號不會重新編排，歷史裡會顯示「v{{ deleting.number }} 已刪除」。</li>
          <li>只有這個版本用到的圖片，會在 24 小時後自動清除。</li>
          <li>已經做過的備份裡仍然保有這個版本。</li>
        </ul>
        <label for="delete-reason">原因 <span class="optional">選填</span></label>
        <InputText id="delete-reason" v-model="deleteReason" maxlength="200" :disabled="saving" placeholder="例如：上傳錯檔案" />
        <label for="delete-confirm">輸入 <code>v{{ deleting.number }}</code> 確認</label>
        <InputText id="delete-confirm" v-model="typed" :disabled="saving" autocomplete="off" />
        <Message v-if="deleteError" severity="error" size="small">{{ deleteError }}</Message>
        <div class="restore-actions">
          <Button type="button" label="取消" text severity="secondary" :disabled="saving" @click="deleting = undefined" />
          <Button type="submit" :label="`永久刪除 v${deleting.number}`" severity="danger" :loading="saving" :disabled="!confirmed" />
        </div>
      </form>
    </Dialog>

    <Dialog :visible="Boolean(restoring)" header="還原版本" modal :closable="!saving" :close-on-escape="!saving"
      :style="{ width: 'min(94vw, 30rem)' }" @update:visible="open => { if (!open && !saving) restoring = undefined }">
      <form v-if="restoring" class="restore" @submit.prevent="restore">
        <p>v{{ restoring.number }} 的內容會儲存為新的目前版本，既有的版本都會保留。</p>
        <label for="restore-note">更新說明</label>
        <Textarea id="restore-note" v-model="restoreNote" maxlength="500" rows="3" :disabled="saving" auto-resize />
        <Message v-if="restoreError" severity="error" size="small">{{ restoreError }}</Message>
        <div class="restore-actions">
          <Button type="button" label="取消" text severity="secondary" :disabled="saving" @click="restoring = undefined" />
          <Button type="submit" label="還原" :loading="saving" />
        </div>
      </form>
    </Dialog>
  </div>
</template>

<style scoped>
.versions { display: grid; gap: var(--ui-space-3); padding: var(--ui-space-4) var(--ui-space-4) var(--ui-space-6); }
.hint { margin: 0; padding: var(--ui-space-2) var(--ui-space-3); border-radius: var(--ui-radius-md); background: var(--ui-bg-muted); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.timeline { list-style: none; margin: 0; padding: 0; }
.entry { display: flex; gap: var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-2); border-bottom: 1px solid var(--ui-border-subtle); border-radius: var(--ui-radius-sm); }
.entry.shown { background: var(--ui-accent-soft); }
.check { flex: none; width: 1rem; height: 1rem; margin: .1875rem 0 0; accent-color: var(--ui-accent); }
.body { flex: 1; min-width: 0; display: grid; gap: .1875rem; }
.head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); }
.number { color: var(--ui-text); font-weight: 600; text-decoration: none; }
.number:hover { color: var(--ui-accent); text-decoration: underline; }
.badge { padding: 1px var(--ui-space-2); border-radius: var(--ui-radius-pill); font-size: .71875rem; font-weight: 600; }
.badge.current { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); }
.badge.published { background: var(--ui-public-bg); color: var(--ui-public-text); }
.when { margin-left: auto; color: var(--ui-text-muted); font-size: var(--ui-text-xs); white-space: nowrap; }
.note { margin: 0; color: var(--ui-text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
.meta { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.row-actions { display: flex; gap: var(--ui-space-3); margin-top: 2px; }
.action { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-size: var(--ui-text-xs); font-weight: 600; text-decoration: none; cursor: pointer; }
.action:hover { text-decoration: underline; }
.action.danger { margin-left: auto; color: var(--ui-danger); }
.entry.deleted .body { opacity: .8; }
.check-space { flex: none; width: 1rem; }
.number.gone { color: var(--ui-text-muted); text-decoration: line-through; }
.badge.removed { background: var(--ui-danger-bg); color: var(--ui-danger); }
.consequences { margin: 0; padding-left: 1.25rem; display: grid; gap: var(--ui-space-1); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.optional { color: var(--ui-text-muted); font-weight: 400; font-size: var(--ui-text-sm); }
.restore { display: grid; gap: var(--ui-space-3); }
.restore p { margin: 0; }
.restore label { font-weight: 600; }
.restore-actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
</style>
