<script setup lang="ts">
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { api, upload } from '../../api'
import { overLimit } from '../../fileLimits'
import { useSession } from '../../stores/session'
import { useTaxonomy } from '../../stores/taxonomy'
import type { DocumentDetails } from '../composables/useDocument'
import { formatLabel, longDateTime } from '../types'
import { GALLERY_LAYOUTS, LAYOUT_LABELS } from '../../gallery'

const props = defineProps<{ document: DocumentDetails; editable: boolean }>()
const emit = defineEmits<{ updated: [document: Partial<DocumentDetails>] }>()

const taxonomy = useTaxonomy()
const toast = useToast()
const session = useSession()
const presentations = [{ value: 'article', label: '文章' }, { value: 'gallery', label: '相簿' }]
const layouts = [{ value: '', label: '跟隨系統預設' }, ...GALLERY_LAYOUTS.map(value => ({ value, label: LAYOUT_LABELS[value] }))]
const category = ref<string | null>(null)
const tags = ref<string[]>([])
const saving = ref(false)

watch(() => props.document, document => {
  category.value = document.category
  tags.value = document.tags.map(tag => tag.id)
}, { immediate: true })

async function patch(payload: { category?: string | null; tags?: string[]; presentation?: string; gallery_layout?: string; cover_image?: string | null }) {
  saving.value = true
  try {
    const saved = await api<DocumentDetails>(`/api/documents/${props.document.id}/`, 'PATCH', payload)
    emit('updated', {
      category: saved.category, category_name: saved.category_name, tags: saved.tags, updated_at: saved.updated_at,
      presentation: saved.presentation, gallery_layout: saved.gallery_layout, cover_image: saved.cover_image,
    })
    toast.add({ severity: 'success', summary: '已更新文件資料', life: 2500 })
  } catch (cause) {
    category.value = props.document.category
    tags.value = props.document.tags.map(tag => tag.id)
    toast.add({ severity: 'error', summary: '無法更新', detail: cause instanceof Error ? cause.message : '', life: 5000 })
  } finally {
    saving.value = false
  }
}

function changeCategory(value: string | null) {
  category.value = value
  if (value !== props.document.category) void patch({ category: value })
}

function commitTags() {
  const before = props.document.tags.map(tag => tag.id).sort().join()
  if ([...tags.value].sort().join() !== before) void patch({ tags: tags.value })
}

function changePresentation(value: string) {
  if (value && value !== props.document.presentation) void patch({ presentation: value })
}
function changeLayout(value: string | null) {
  if ((value ?? '') !== props.document.gallery_layout) void patch({ gallery_layout: value ?? '' })
}

// ---- P22: cover picture ----------------------------------------------------------------------------
const picking = ref(false)
const pictures = ref<string[]>([])
const loadingPictures = ref(false)
const coverInput = ref<HTMLInputElement>()
const uploadingCover = ref(false)
const coverHint = computed(() => props.document.presentation === 'gallery'
  ? '未指定，卡片使用相簿的第一張圖片。'
  : '未設定，卡片顯示集合顏色的色帶。')

async function togglePicker() {
  picking.value = !picking.value
  if (!picking.value) return
  loadingPictures.value = true
  try {
    const sizes = await api<Record<string, [number, number]>>(`/api/documents/${props.document.id}/image-sizes/`)
    pictures.value = Object.keys(sizes)
  } catch {
    pictures.value = []
  } finally {
    loadingPictures.value = false
  }
}
function chooseCover(id: string | null) {
  picking.value = false
  if (id !== (props.document.cover_image?.id ?? null)) void patch({ cover_image: id })
}
function chooseFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) void uploadCover(file)
}

// Paste or drop a picture on the cover box (only there: the tab has other fields, and the page has its own uses for paste).
const dragging = ref(false)
function pictureOf(items?: DataTransferItemList | null, files?: FileList | null) {
  const fromFiles = Array.from(files ?? []).find(file => file.type.startsWith('image/'))
  if (fromFiles) return fromFiles
  const item = Array.from(items ?? []).find(entry => entry.kind === 'file' && entry.type.startsWith('image/'))
  return item?.getAsFile() ?? null
}
function pasteCover(event: ClipboardEvent) {
  if (!props.editable) return
  event.preventDefault()
  const file = pictureOf(event.clipboardData?.items, event.clipboardData?.files)
  if (file) void uploadCover(file)
  else toast.add({ severity: 'warn', summary: '剪貼簿裡沒有圖片', detail: '請複製圖片本身（例如截圖），而不是圖片網址。', life: 4000 })
}
function dropCover(event: DragEvent) {
  dragging.value = false
  if (!props.editable) return
  const file = pictureOf(event.dataTransfer?.items, event.dataTransfer?.files)
  if (file) void uploadCover(file)
  else toast.add({ severity: 'warn', summary: '請拖入圖片檔', life: 4000 })
}

async function uploadCover(file: File) {
  if (uploadingCover.value) return
  const tooBig = overLimit('image', file.size, session.limits)  // P23c: never send an oversized picture
  if (tooBig) {
    toast.add({ severity: 'error', summary: '無法上傳封面', detail: tooBig, life: 5000 })
    return
  }
  uploadingCover.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const image = await upload<{ id: string }>(`/api/documents/${props.document.id}/images/`, form)
    await patch({ cover_image: image.id })
  } catch (cause) {
    toast.add({ severity: 'error', summary: '無法上傳封面', detail: cause instanceof Error ? cause.message : '', life: 5000 })
  } finally {
    uploadingCover.value = false
  }
}

function sizeLabel(size?: number) {
  if (!size) return ''
  return size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`
}
</script>

<template>
  <div class="info">
    <dl class="fields">
      <dt><label for="info-category">集合</label></dt>
      <dd>
        <Select v-if="editable" input-id="info-category" :model-value="category" :options="taxonomy.categoryOptions"
          option-label="name" option-value="id" show-clear placeholder="未分類" filter size="small" :disabled="saving"
          fluid @update:model-value="changeCategory" />
        <span v-else>{{ taxonomy.pathLabel(document.category) }}</span>
      </dd>
      <dt><label for="info-tags">標籤</label></dt>
      <dd>
        <MultiSelect v-if="editable" v-model="tags" input-id="info-tags" :options="taxonomy.tags" option-label="name"
          option-value="id" placeholder="新增標籤" filter display="chip" size="small" :disabled="saving" fluid
          @hide="commitTags" />
        <span v-else class="tags">
          <span v-for="tag in document.tags" :key="tag.id" class="tag">{{ tag.name }}</span>
          <span v-if="!document.tags.length" class="muted">—</span>
        </span>
      </dd>
      <dt id="info-cover-label" class="top">封面</dt>
      <dd class="cover-field" aria-labelledby="info-cover-label">
        <div v-if="editable" class="cover-drop" :class="{ dragging, empty: !document.cover_image, busy: uploadingCover }" tabindex="0"
          role="group" :aria-label="`封面：${document.cover_image ? '已設定' : coverHint}按 Ctrl+V 貼上圖片，或把圖片拖到這裡。`"
          @paste="pasteCover" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="dropCover">
          <img v-if="document.cover_image" :src="document.cover_image.thumb" alt="目前的封面" class="cover-preview">
          <span v-else class="muted cover-hint">{{ coverHint }}</span>
          <span class="drop-hint" aria-hidden="true">{{ uploadingCover ? '上傳中…' : dragging ? '放開以設為封面' : 'Ctrl+V 貼上或拖入圖片' }}</span>
        </div>
        <template v-else>
          <img v-if="document.cover_image" :src="document.cover_image.thumb" alt="目前的封面" class="cover-preview">
          <span v-else class="muted cover-hint">{{ coverHint }}</span>
        </template>
        <div v-if="editable" class="cover-actions">
          <button v-if="document.format === 'md'" type="button" class="link-button" :aria-expanded="picking" :disabled="saving" @click="togglePicker">
            從文件中挑選
          </button>
          <button type="button" class="link-button" :disabled="saving || uploadingCover" @click="coverInput?.click()">
            {{ uploadingCover ? '上傳中…' : '上傳圖片' }}
          </button>
          <button v-if="document.cover_image" type="button" class="link-button danger" :disabled="saving" @click="chooseCover(null)">移除</button>
          <input ref="coverInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden @change="chooseFile">
        </div>
        <div v-if="picking" class="cover-picker" role="group" aria-label="挑選封面">
          <p v-if="loadingPictures" class="muted">載入圖片中…</p>
          <p v-else-if="!pictures.length" class="muted">這份文件還沒有圖片，可以在編輯器貼上，或直接上傳封面。</p>
          <button v-for="id in pictures" v-else :key="id" type="button" class="cover-choice" :class="{ on: document.cover_image?.id === id }"
            :aria-pressed="document.cover_image?.id === id" :aria-label="document.cover_image?.id === id ? '目前的封面' : '設為封面'" @click="chooseCover(id)">
            <img :src="`/api/images/${id}/thumb/`" alt="" loading="lazy">
          </button>
        </div>
      </dd>
      <template v-if="document.format === 'md'">
        <dt><label for="info-presentation">呈現方式</label></dt>
        <dd>
          <Select v-if="editable" input-id="info-presentation" :model-value="document.presentation" :options="presentations"
            option-label="label" option-value="value" size="small" :disabled="saving" fluid @update:model-value="changePresentation" />
          <span v-else>{{ document.presentation === 'gallery' ? '相簿' : '文章' }}</span>
        </dd>
        <template v-if="document.presentation === 'gallery'">
          <dt><label for="info-layout">相簿版面</label></dt>
          <dd>
            <Select v-if="editable" input-id="info-layout" :model-value="document.gallery_layout" :options="layouts"
              option-label="label" option-value="value" placeholder="跟隨系統預設" size="small" :disabled="saving" fluid
              @update:model-value="changeLayout" />
            <span v-else>{{ layouts.find(item => item.value === document.gallery_layout)?.label }}</span>
          </dd>
        </template>
      </template>
      <dt>格式</dt>
      <dd>{{ formatLabel(document.format) }}<template v-if="document.current_version.size"> · {{ sizeLabel(document.current_version.size) }}</template></dd>
      <dt>最新版本</dt>
      <dd>v{{ document.current_version.number }} · {{ document.current_version.author ?? '系統' }}</dd>
      <dt>更新時間</dt>
      <dd><time :datetime="document.updated_at">{{ longDateTime(document.updated_at) }}</time></dd>
    </dl>

  </div>
</template>

<style scoped>
.info { display: grid; gap: var(--ui-space-5); padding: var(--ui-space-4) var(--ui-space-4) var(--ui-space-6); }
.fields { display: grid; grid-template-columns: 5rem minmax(0, 1fr); gap: var(--ui-space-3) var(--ui-space-3); align-items: center; margin: 0; }
dt { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.tags { display: flex; flex-wrap: wrap; gap: var(--ui-space-1); }
.tag { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-pill); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-size: var(--ui-text-xs); font-weight: 500; }
.muted { color: var(--ui-text-muted); }
.fields dt.top { align-self: start; padding-top: var(--ui-space-1); }
.cover-field { display: grid; gap: var(--ui-space-2); }
.cover-preview { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: var(--ui-radius-md); border: 1px solid var(--ui-border); }
.cover-hint { font-size: var(--ui-text-sm); }
.cover-drop { position: relative; display: grid; border-radius: var(--ui-radius-md); outline: none; cursor: default; }
.cover-drop.empty { min-height: 4.5rem; padding: var(--ui-space-3); border: 1px dashed var(--ui-border-strong, var(--ui-border)); align-content: center; }
.drop-hint {
  display: none; position: absolute; inset: auto 0 0 0; padding: var(--ui-space-1) var(--ui-space-2); border-radius: 0 0 var(--ui-radius-md) var(--ui-radius-md);
  background: rgb(16 24 40 / .72); color: #fff; font-size: var(--ui-text-xs); text-align: center;
}
.cover-drop.empty .drop-hint { position: static; margin-top: var(--ui-space-2); padding: 0; background: none; color: var(--ui-text-muted); text-align: start; }
.cover-drop:focus-visible, .cover-drop:focus, .cover-drop.dragging { box-shadow: 0 0 0 2px var(--ui-accent); }
.cover-drop:focus .drop-hint, .cover-drop.dragging .drop-hint, .cover-drop.busy .drop-hint { display: block; }
.cover-drop.dragging { background: var(--ui-accent-soft, var(--ui-bg-muted)); }
.cover-actions { display: flex; flex-wrap: wrap; gap: var(--ui-space-3); }
.link-button { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-size: var(--ui-text-sm); font-weight: 600; cursor: pointer; }
.link-button:disabled { opacity: .5; cursor: default; }
.link-button.danger { color: var(--ui-danger); }
.cover-picker { display: grid; grid-template-columns: repeat(auto-fill, minmax(4.5rem, 1fr)); gap: var(--ui-space-2); }
.cover-picker p { grid-column: 1 / -1; margin: 0; font-size: var(--ui-text-sm); }
.cover-choice { padding: 0; aspect-ratio: 1; border: 2px solid transparent; border-radius: var(--ui-radius-sm); background: var(--ui-bg-muted); overflow: hidden; cursor: pointer; }
.cover-choice img { display: block; width: 100%; height: 100%; object-fit: cover; }
.cover-choice.on { border-color: var(--ui-accent); }
.cover-choice:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 1px; }
</style>
