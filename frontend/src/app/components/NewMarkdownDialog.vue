<script setup lang="ts">
// Create a Markdown document without uploading a file: v1 holds just the title, then the editor opens.
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'
import type { DocumentRow } from '../types'

const visible = defineModel<boolean>('visible', { required: true })
const props = defineProps<{ defaultCategory: string | null }>()

const taxonomy = useTaxonomy()
const toast = useToast()
const router = useRouter()
const title = ref('')
const category = ref<string | null>(null)
const tags = ref<string[]>([])
const error = ref('')
const working = ref(false)

watch(visible, open => {
  if (!open) return
  title.value = ''
  category.value = props.defaultCategory && taxonomy.byId(props.defaultCategory) ? props.defaultCategory : null
  tags.value = []
  error.value = ''
  void nextTick(() => document.getElementById('new-markdown-title')?.focus())
})

async function create() {
  if (!title.value.trim() || working.value) return
  working.value = true
  error.value = ''
  try {
    const created = await api<DocumentRow>('/api/documents/new/', 'POST',
      { title: title.value.trim(), category: category.value, tags: tags.value })
    toast.add({ severity: 'success', summary: '已建立文件', detail: '直接開始撰寫，儲存後成為 v2。', life: 3000 })
    window.dispatchEvent(new CustomEvent('hub:documents-changed'))
    visible.value = false
    void router.push({ name: 'app-document', params: { id: created.id }, query: { mode: 'split' } })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法建立文件。'
  } finally {
    working.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" header="新增 Markdown 文件" modal :closable="!working" :style="{ width: 'min(94vw, 32rem)' }">
    <form class="new-markdown" @submit.prevent="create">
      <div class="field">
        <label for="new-markdown-title">標題</label>
        <InputText id="new-markdown-title" v-model="title" maxlength="240" required :disabled="working" autocomplete="off" />
      </div>
      <div class="field">
        <label for="new-markdown-category">集合</label>
        <Select v-model="category" input-id="new-markdown-category" :options="taxonomy.categoryOptions" option-label="name"
          option-value="id" show-clear placeholder="未分類" filter :disabled="working" />
      </div>
      <div class="field">
        <label for="new-markdown-tags">標籤 <span class="optional">選填</span></label>
        <MultiSelect v-model="tags" input-id="new-markdown-tags" :options="taxonomy.tags" option-label="name" option-value="id"
          placeholder="選擇標籤" filter display="chip" :disabled="working" />
      </div>
      <p class="hint">建立後會直接打開編輯器。v1 只有標題，第一次儲存後成為 v2。</p>
      <Message v-if="error" severity="error" size="small">{{ error }}</Message>
      <div class="actions">
        <Button type="button" label="取消" severity="secondary" text :disabled="working" @click="visible = false" />
        <Button type="submit" label="建立" :loading="working" :disabled="!title.trim()" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.new-markdown { display: grid; gap: var(--ui-space-4); }
.field { display: grid; gap: var(--ui-space-2); }
.field label { font-weight: 600; }
.optional { color: var(--ui-text-muted); font-weight: 400; font-size: var(--ui-text-sm); }
.hint { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
</style>
