<script setup lang="ts">
// Set the collection and add tags for a finished upload batch, in one request (bulk action "organize").
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'

export type OrganizeTarget = { id: string; title: string }

const props = defineProps<{ documents: OrganizeTarget[] }>()
const visible = defineModel<boolean>('visible', { required: true })
/** `category` is undefined when collections were left as they were, null for "uncategorised". */
const emit = defineEmits<{ done: [category: string | null | undefined] }>()

const KEEP = 'keep', NONE = 'none'
const SHOWN = 5
const taxonomy = useTaxonomy()
const toast = useToast()
const category = ref(KEEP)
const tags = ref<string[]>([])
const error = ref('')
const working = ref(false)

const categoryOptions = computed(() => [
  { id: KEEP, name: '維持目前的集合' }, { id: NONE, name: '未分類' }, ...taxonomy.categoryOptions,
])
const shown = computed(() => props.documents.slice(0, SHOWN))
const more = computed(() => Math.max(0, props.documents.length - SHOWN))
const changed = computed(() => category.value !== KEEP || tags.value.length > 0)

watch(visible, open => {
  if (!open) return
  category.value = KEEP
  tags.value = []
  error.value = ''
})

async function apply() {
  if (!changed.value || working.value) return
  working.value = true
  error.value = ''
  const chosen = category.value === KEEP ? undefined : category.value === NONE ? null : category.value
  try {
    await api('/api/documents/bulk/', 'POST', {
      ids: props.documents.map(document => document.id), action: 'organize', tags: tags.value,
      ...(chosen === undefined ? {} : { category: chosen }),
    })
    toast.add({ severity: 'success', summary: `已更新 ${props.documents.length} 份文件`, life: 3000 })
    window.dispatchEvent(new CustomEvent('hub:documents-changed'))
    emit('done', chosen)
    visible.value = false
  } catch (cause) {
    const missing = cause instanceof ApiError ? (cause.body as { missing?: string[] } | undefined)?.missing : undefined
    error.value = missing?.length
      ? `有 ${missing.length} 份文件已被刪除或移入回收桶，所以這次沒有更新任何文件。請到「全部文件」用批次修改。`
      : cause instanceof Error ? cause.message : '無法更新，請稍後再試。'
  } finally {
    working.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" header="設定集合與標籤" modal :closable="!working" :style="{ width: 'min(94vw, 32rem)' }">
    <form class="organize" @submit.prevent="apply">
      <div class="batch">
        <p class="lead">套用到這次上傳的 {{ documents.length }} 份文件：</p>
        <ul class="titles">
          <li v-for="document in shown" :key="document.id">{{ document.title }}</li>
          <li v-if="more" class="more">等 {{ more }} 份</li>
        </ul>
      </div>
      <div class="field">
        <label for="organize-category">集合</label>
        <Select v-model="category" input-id="organize-category" :options="categoryOptions" option-label="name"
          option-value="id" filter :disabled="working" />
      </div>
      <div class="field">
        <label for="organize-tags">加上標籤</label>
        <MultiSelect v-model="tags" input-id="organize-tags" :options="taxonomy.tags" option-label="name" option-value="id"
          placeholder="選擇標籤" filter display="chip" :disabled="working" />
        <p class="hint">只會加上標籤，不會移除文件原有的標籤。要建立新標籤，請到
          <RouterLink :to="{ name: 'app-taxonomy' }" @click="visible = false">集合與標籤</RouterLink>。</p>
      </div>
      <Message v-if="error" severity="error" size="small">{{ error }}</Message>
      <div class="actions">
        <Button type="button" label="取消" severity="secondary" text :disabled="working" @click="visible = false" />
        <Button type="submit" label="套用" :loading="working" :disabled="!changed" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.organize { display: grid; gap: var(--ui-space-4); }
.batch { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-3) var(--ui-space-4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-bg-subtle); }
.lead { margin: 0; color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.titles { margin: 0; padding-left: 1.25rem; display: grid; gap: 2px; overflow-wrap: anywhere; }
.titles .more { list-style: none; margin-left: -1.25rem; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.field { display: grid; gap: var(--ui-space-2); }
.field label { font-weight: 600; }
.hint { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.hint a { color: var(--ui-accent); }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
</style>
