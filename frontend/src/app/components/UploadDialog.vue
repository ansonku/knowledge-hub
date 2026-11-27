<script setup lang="ts">
// Adds a new version to one document. New documents use the upload tray (stores/uploads.ts) instead,
// and get their collection and tags afterwards from the tray's "設定集合與標籤".
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import ProgressBar from 'primevue/progressbar'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { ApiError, upload } from '../../api'
import { documentKind, limitOf, overLimit, sizeLabel } from '../../fileLimits'
import { useSession } from '../../stores/session'
import { formatLabel, type DocumentRow, type Format } from '../types'
import UiIcon from './UiIcon.vue'

const visible = defineModel<boolean>('visible', { required: true })
const props = defineProps<{ target: DocumentRow }>()
const emit = defineEmits<{ uploaded: [count: number] }>()

type Item = {
  file: File
  state: 'ready' | 'invalid' | 'duplicate' | 'uploading' | 'complete'
  message: string
  progress: number
  force: boolean
}

const toast = useToast()
const item = ref<Item>()
const note = ref('')
const dragging = ref(false)
const processing = ref(false)
const chooser = ref<HTMLInputElement>()

const session = useSession()
const maxBytes = computed(() => limitOf(documentKind(props.target.format), session.limits))
const ready = computed(() => item.value?.state === 'ready' || (item.value?.state === 'duplicate' && item.value.force))

watch(visible, open => {
  if (!open) return
  item.value = undefined
  note.value = ''
})

function formatOf(name: string): Format | undefined {
  if (/\.html$/i.test(name)) return 'html'
  if (/\.md$/i.test(name)) return 'md'
}

function addFiles(files: FileList | null | undefined) {
  const file = files?.[0]
  if (!file || processing.value) return
  const format = formatOf(file.name)
  let message = ''
  if (!format) message = '只支援 .md 或 .html 檔案。'
  else if (format !== props.target.format) message = `新版本必須維持 ${formatLabel(props.target.format)} 格式。`
  else if (!file.size) message = '空白檔案無法上傳。'
  else message = overLimit(documentKind(props.target.format), file.size, session.limits)
  item.value = { file, state: message ? 'invalid' : 'ready', message, progress: 0, force: false }
}

function choose(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(input.files)
  input.value = ''
}

function drop(event: DragEvent) {
  dragging.value = false
  addFiles(event.dataTransfer?.files)
}

async function start() {
  const current = item.value
  if (processing.value || !current || !ready.value) return
  processing.value = true
  const data = new FormData()
  data.append('file', current.file)
  if (current.force) data.append('force', 'true')
  data.append('note', note.value.trim())
  current.state = 'uploading'
  current.progress = 0
  try {
    const saved = await upload<DocumentRow>(`/api/documents/${props.target.id}/versions/`, data, percent => { current.progress = percent })
    current.state = 'complete'
    current.message = `已建立 v${saved.current_version.number}`
    emit('uploaded', 1)
    toast.add({ severity: 'success', summary: '已建立新版本', life: 3000 })
    visible.value = false
  } catch (cause) {
    current.state = cause instanceof ApiError && cause.status === 409 ? 'duplicate' : 'invalid'
    current.force = false
    current.message = cause instanceof Error ? cause.message : '上傳失敗。'
  } finally {
    processing.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" header="新增版本" modal :closable="!processing" :close-on-escape="!processing"
    :style="{ width: 'min(94vw, 40rem)' }">
    <div class="upload">
      <div class="target">
        <span class="target-title">{{ target.title }}</span>
        <span class="target-meta">目前 v{{ target.current_version.number }} · {{ formatLabel(target.format) }}</span>
      </div>
      <div class="field">
        <label for="upload-note">更新說明</label>
        <InputText id="upload-note" v-model="note" maxlength="500" :disabled="processing" placeholder="這個版本改了什麼" />
      </div>

      <div class="dropzone" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false"
        @drop.prevent="drop">
        <UiIcon name="upload" :size="22" />
        <p>
          將檔案拖曳到這裡，或
          <button type="button" class="link-button" :disabled="processing" @click="chooser?.click()">選擇檔案</button>
        </p>
        <small>{{ formatLabel(target.format) }} 檔案，上限 {{ sizeLabel(maxBytes) }}。</small>
        <input ref="chooser" type="file" accept=".md,.html" hidden @change="choose">
      </div>

      <div v-if="item" class="item" aria-label="選擇的檔案">
        <div class="item-row">
          <span class="item-name">{{ item.file.name }}</span>
          <span class="item-size">{{ sizeLabel(item.file.size) }}</span>
          <span v-if="item.state === 'complete'" class="item-ok"><UiIcon name="check" :size="15" />{{ item.message }}</span>
          <Button v-else-if="!processing" type="button" text rounded size="small" severity="secondary"
            :aria-label="`移除 ${item.file.name}`" @click="item = undefined">
            <template #icon><UiIcon name="close" :size="15" /></template>
          </Button>
        </div>
        <ProgressBar v-if="item.state === 'uploading'" :value="item.progress" :show-value="false" class="progress"
          :aria-label="`${item.file.name} 上傳進度`" />
        <p v-if="item.state === 'invalid'" class="item-error">{{ item.message }}</p>
        <div v-if="item.state === 'duplicate'" class="item-duplicate">
          <span>{{ item.message }}</span>
          <label><input v-model="item.force" type="checkbox" :disabled="processing">仍要建立新版本</label>
        </div>
      </div>
    </div>
    <template #footer>
      <Button label="關閉" severity="secondary" text :disabled="processing" @click="visible = false" />
      <Button label="建立新版本" :loading="processing" :disabled="!ready" @click="start" />
    </template>
  </Dialog>
</template>

<style scoped>
.upload { display: grid; gap: var(--ui-space-4); }
.field { display: grid; gap: var(--ui-space-2); }
.field label { font-weight: 600; }
.target { display: grid; gap: 2px; padding: var(--ui-space-3) var(--ui-space-4); border-radius: var(--ui-radius-md); background: var(--ui-bg-subtle); border: 1px solid var(--ui-border); }
.target-title { font-weight: 600; overflow-wrap: anywhere; }
.target-meta { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.dropzone {
  display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-6) var(--ui-space-4);
  border: 1.5px dashed var(--ui-border-strong); border-radius: var(--ui-radius-lg); background: var(--ui-bg-subtle);
  color: var(--ui-text-muted); text-align: center;
}
.dropzone.dragging { border-color: var(--ui-accent); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.dropzone p { margin: 0; color: var(--ui-text-secondary); }
.dropzone small { font-size: var(--ui-text-sm); }
.link-button { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; cursor: pointer; text-decoration: underline; text-underline-offset: .18em; }
.item { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-3) var(--ui-space-4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
.item-row { display: flex; align-items: center; gap: var(--ui-space-3); min-height: 2rem; }
.item-name { flex: 1; min-width: 0; overflow-wrap: anywhere; font-weight: 500; }
.item-size { color: var(--ui-text-muted); font-size: var(--ui-text-sm); white-space: nowrap; }
.item-ok { display: inline-flex; align-items: center; gap: 4px; color: var(--ui-public-text); font-weight: 600; font-size: var(--ui-text-sm); white-space: nowrap; }
.item-error { margin: 0; color: var(--ui-danger); font-size: var(--ui-text-sm); }
.item-duplicate { display: grid; gap: var(--ui-space-1); color: var(--ui-lagging-text); font-size: var(--ui-text-sm); }
.item-duplicate label { display: inline-flex; align-items: center; gap: var(--ui-space-2); color: var(--ui-text-secondary); }
.progress { height: 4px; }
</style>
