<script setup lang="ts">
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { api } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'
import type { DocumentDetails } from '../composables/useDocument'
import { formatLabel, longDateTime } from '../types'

type Heading = { id: string; text: string; level: number }

const props = defineProps<{ document: DocumentDetails; headings: Heading[]; editable: boolean }>()
const emit = defineEmits<{ jump: [id: string]; updated: [document: Partial<DocumentDetails>] }>()

const taxonomy = useTaxonomy()
const toast = useToast()
// Indent relative to the shallowest heading so a hidden leading H1 does not shift the whole list.
const topLevel = computed(() => Math.min(...props.headings.map(heading => heading.level), 6))
const category = ref<string | null>(null)
const tags = ref<string[]>([])
const saving = ref(false)

watch(() => props.document, document => {
  category.value = document.category
  tags.value = document.tags.map(tag => tag.id)
}, { immediate: true })

async function patch(payload: { category?: string | null; tags?: string[] }) {
  saving.value = true
  try {
    const saved = await api<DocumentDetails>(`/api/documents/${props.document.id}/`, 'PATCH', payload)
    emit('updated', { category: saved.category, category_name: saved.category_name, tags: saved.tags, updated_at: saved.updated_at })
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
      <dt>格式</dt>
      <dd>{{ formatLabel(document.format) }}<template v-if="document.current_version.size"> · {{ sizeLabel(document.current_version.size) }}</template></dd>
      <dt>最新版本</dt>
      <dd>v{{ document.current_version.number }} · {{ document.current_version.author ?? '系統' }}</dd>
      <dt>更新時間</dt>
      <dd><time :datetime="document.updated_at">{{ longDateTime(document.updated_at) }}</time></dd>
    </dl>

    <nav v-if="headings.length" class="toc" aria-label="本頁目錄">
      <span class="toc-title">本頁目錄</span>
      <a v-for="heading in headings" :key="heading.id" :href="`#${heading.id}`" class="toc-link"
        :style="{ paddingInlineStart: `${.75 + Math.max(0, heading.level - topLevel) * .75}rem` }"
        @click.prevent="emit('jump', heading.id)">{{ heading.text }}</a>
    </nav>
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
.toc { display: flex; flex-direction: column; gap: 2px; padding-top: var(--ui-space-4); border-top: 1px solid var(--ui-border); }
.toc-title { margin-bottom: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }
.toc-link {
  padding-block: .3125rem; border-left: 2px solid var(--ui-border); color: var(--ui-text-secondary);
  font-size: var(--ui-text-sm); text-decoration: none; overflow-wrap: anywhere;
}
.toc-link:hover { border-left-color: var(--ui-accent); color: var(--ui-accent); }
</style>
