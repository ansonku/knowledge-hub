<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import ProgressBar from 'primevue/progressbar'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { ApiError, upload } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'
import { formatLabel, type DocumentRow, type Format } from '../types'
import UiIcon from './UiIcon.vue'

const visible = defineModel<boolean>('visible', { required: true })
const props = defineProps<{
  /** When set, the dialog adds a new version to this document instead of creating documents. */
  target?: DocumentRow
  defaultCategory?: string | null
  maxBytes: number
  maxBatch: number
}>()
const emit = defineEmits<{ uploaded: [count: number] }>()

type Item = {
  file: File
  title: string
  state: 'ready' | 'invalid' | 'duplicate' | 'uploading' | 'complete'
  message: string
  progress: number
  force: boolean
}

const taxonomy = useTaxonomy()
const toast = useToast()
const items = ref<Item[]>([])
const category = ref<string | null>(null)
const tags = ref<string[]>([])
const note = ref('')
const notice = ref('')
const dragging = ref(false)
const processing = ref(false)
const chooser = ref<HTMLInputElement>()

const isVersion = computed(() => Boolean(props.target))
const limit = computed(() => isVersion.value ? 1 : props.maxBatch)
const maxMB = computed(() => Math.round(props.maxBytes / (1024 * 1024)))
const pending = computed(() => items.value.filter(item => item.state === 'ready' || (item.state === 'duplicate' && item.force)))
const header = computed(() => isVersion.value ? '新增版本' : '上傳文件')
const submitLabel = computed(() => {
  if (isVersion.value) return '建立新版本'
  return pending.value.length > 1 ? `上傳 ${pending.value.length} 份文件` : '上傳'
})

watch(visible, open => {
  if (!open) return
  items.value = []
  category.value = props.defaultCategory && taxonomy.byId(props.defaultCategory) ? props.defaultCategory : null
  tags.value = []
  note.value = ''
  notice.value = ''
})

function formatOf(name: string): Format | undefined {
  if (/\.html$/i.test(name)) return 'html'
  if (/\.md$/i.test(name)) return 'md'
}

function sizeLabel(size: number) {
  return size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`
}

function addFiles(files: FileList | null | undefined) {
  if (!files?.length || processing.value) return
  notice.value = ''
  const kept = isVersion.value ? [] : items.value.filter(item => item.state !== 'complete')
  const room = limit.value - kept.length
  if (files.length > room) notice.value = `一次最多 ${limit.value} 個檔案，已略過多出的部分。`
  const added = Array.from(files).slice(0, Math.max(0, room)).map<Item>(file => {
    const format = formatOf(file.name)
    let message = ''
    if (!format) message = '只支援 .md 或 .html 檔案。'
    else if (props.target && format !== props.target.format) message = `新版本必須維持 ${formatLabel(props.target.format)} 格式。`
    else if (!file.size) message = '空白檔案無法上傳。'
    else if (file.size > props.maxBytes) message = `超過每檔 ${maxMB.value} MB 上限。`
    return { file, title: file.name.replace(/\.[^.]+$/, ''), state: message ? 'invalid' : 'ready', message, progress: 0, force: false }
  })
  items.value = [...kept, ...added]
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
  if (processing.value || !pending.value.length) return
  processing.value = true
  const single = pending.value.length === 1
  let complete = 0
  try {
    for (const item of pending.value) {
      const data = new FormData()
      data.append('file', item.file)
      if (item.force) data.append('force', 'true')
      if (props.target) data.append('note', note.value.trim())
      else {
        if (single && item.title.trim()) data.append('title', item.title.trim())
        if (category.value) data.append('category', category.value)
        for (const id of tags.value) data.append('tags', id)
      }
      item.state = 'uploading'
      item.progress = 0
      try {
        const url = props.target ? `/api/documents/${props.target.id}/versions/` : '/api/documents/'
        const saved = await upload<DocumentRow>(url, data, percent => { item.progress = percent })
        item.state = 'complete'
        item.message = props.target ? `已建立 v${saved.current_version.number}` : '已新增 · v1'
        complete++
      } catch (cause) {
        const duplicate = cause instanceof ApiError && cause.status === 409
        item.state = duplicate ? 'duplicate' : 'invalid'
        item.force = false
        item.message = cause instanceof Error ? cause.message : '上傳失敗。'
      }
    }
  } finally {
    processing.value = false
  }
  if (!complete) return
  emit('uploaded', complete)
  toast.add({
    severity: 'success',
    summary: props.target ? '已建立新版本' : `已上傳 ${complete} 份文件`,
    life: 3000,
  })
  if (items.value.every(item => item.state === 'complete')) visible.value = false
}
</script>

<template>
  <Dialog v-model:visible="visible" :header="header" modal :closable="!processing" :close-on-escape="!processing"
    :style="{ width: 'min(94vw, 40rem)' }">
    <div class="upload">
      <div v-if="target" class="target">
        <span class="target-title">{{ target.title }}</span>
        <span class="target-meta">目前 v{{ target.current_version.number }} · {{ formatLabel(target.format) }}</span>
      </div>
      <div v-else class="fields">
        <div class="field">
          <label for="upload-category">集合</label>
          <Select input-id="upload-category" v-model="category" :options="taxonomy.categoryOptions" option-label="name"
            option-value="id" show-clear placeholder="未分類" filter :disabled="processing" />
        </div>
        <div class="field">
          <label for="upload-tags">標籤</label>
          <MultiSelect input-id="upload-tags" v-model="tags" :options="taxonomy.tags" option-label="name" option-value="id"
            placeholder="選擇標籤" filter display="chip" :disabled="processing" />
        </div>
      </div>
      <div v-if="target" class="field">
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
        <small>
          Markdown 或 HTML，每檔上限 {{ maxMB }} MB<template v-if="!target">，一次最多 {{ maxBatch }} 個；每個檔案會建立一份新文件</template>。
        </small>
        <input ref="chooser" type="file" accept=".md,.html" :multiple="!target" hidden @change="choose">
      </div>
      <Message v-if="notice" severity="warn" size="small">{{ notice }}</Message>

      <ul v-if="items.length" class="items" aria-label="選擇的檔案">
        <li v-for="(item, index) in items" :key="`${item.file.name}-${index}`" class="item">
          <div class="item-row">
            <span class="item-name">{{ item.file.name }}</span>
            <span class="item-size">{{ sizeLabel(item.file.size) }}</span>
            <span v-if="item.state === 'complete'" class="item-ok"><UiIcon name="check" :size="15" />{{ item.message }}</span>
            <Button v-else-if="!processing" type="button" text rounded size="small" severity="secondary"
              :aria-label="`移除 ${item.file.name}`" @click="items.splice(index, 1)">
              <template #icon><UiIcon name="close" :size="15" /></template>
            </Button>
          </div>
          <div v-if="!target && items.length === 1 && item.state === 'ready'" class="field">
            <label :for="`upload-title-${index}`">文件標題</label>
            <InputText :id="`upload-title-${index}`" v-model="item.title" maxlength="240" :disabled="processing" />
          </div>
          <ProgressBar v-if="item.state === 'uploading'" :value="item.progress" :show-value="false" class="progress"
            :aria-label="`${item.file.name} 上傳進度`" />
          <p v-if="item.state === 'invalid'" class="item-error">{{ item.message }}</p>
          <div v-if="item.state === 'duplicate'" class="item-duplicate">
            <span>{{ item.message }}</span>
            <label><input v-model="item.force" type="checkbox" :disabled="processing">仍要{{ target ? '建立新版本' : '新增' }}</label>
          </div>
        </li>
      </ul>
    </div>
    <template #footer>
      <Button label="關閉" severity="secondary" text :disabled="processing" @click="visible = false" />
      <Button :label="submitLabel" :loading="processing" :disabled="!pending.length" @click="start" />
    </template>
  </Dialog>
</template>

<style scoped>
.upload { display: grid; gap: var(--ui-space-4); }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: var(--ui-space-3); }
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
.items { list-style: none; margin: 0; padding: 0; max-height: 18rem; overflow-y: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
.item { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
.item:last-child { border-bottom: 0; }
.item-row { display: flex; align-items: center; gap: var(--ui-space-3); min-height: 2rem; }
.item-name { flex: 1; min-width: 0; overflow-wrap: anywhere; font-weight: 500; }
.item-size { color: var(--ui-text-muted); font-size: var(--ui-text-sm); white-space: nowrap; }
.item-ok { display: inline-flex; align-items: center; gap: 4px; color: var(--ui-public-text); font-weight: 600; font-size: var(--ui-text-sm); white-space: nowrap; }
.item-error { margin: 0; color: var(--ui-danger); font-size: var(--ui-text-sm); }
.item-duplicate { display: grid; gap: var(--ui-space-1); color: var(--ui-lagging-text); font-size: var(--ui-text-sm); }
.item-duplicate label { display: inline-flex; align-items: center; gap: var(--ui-space-2); color: var(--ui-text-secondary); }
.progress { height: 4px; }
</style>
