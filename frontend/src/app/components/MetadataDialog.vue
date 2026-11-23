<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { ref, watch } from 'vue'
import { api } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'
import type { DocumentRow } from '../types'

const props = defineProps<{ document?: DocumentRow }>()
const emit = defineEmits<{ close: []; saved: [document: DocumentRow] }>()

const taxonomy = useTaxonomy()
const toast = useToast()
const title = ref('')
const category = ref<string | null>(null)
const tags = ref<string[]>([])
const error = ref('')
const working = ref(false)

watch(() => props.document, document => {
  if (!document) return
  title.value = document.title
  category.value = document.category
  tags.value = document.tags.map(tag => tag.id)
  error.value = ''
}, { immediate: true })

async function save() {
  if (!props.document || working.value) return
  working.value = true
  error.value = ''
  try {
    const saved = await api<DocumentRow>(`/api/documents/${props.document.id}/`, 'PATCH',
      { title: title.value.trim(), category: category.value, tags: tags.value })
    toast.add({ severity: 'success', summary: '已更新文件資料', life: 3000 })
    emit('saved', saved)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法儲存。'
  } finally {
    working.value = false
  }
}
</script>

<template>
  <Dialog :visible="Boolean(document)" header="編輯文件資料" modal :closable="!working" :style="{ width: 'min(94vw, 34rem)' }"
    @update:visible="open => { if (!open && !working) emit('close') }">
    <form v-if="document" class="metadata-form" @submit.prevent="save">
      <div class="field">
        <label for="metadata-title">標題</label>
        <InputText id="metadata-title" v-model="title" maxlength="240" required />
      </div>
      <div class="field">
        <label for="metadata-category">集合</label>
        <Select input-id="metadata-category" v-model="category" :options="taxonomy.categoryOptions" option-label="name"
          option-value="id" show-clear placeholder="未分類" filter />
      </div>
      <div class="field">
        <label for="metadata-tags">標籤</label>
        <MultiSelect input-id="metadata-tags" v-model="tags" :options="taxonomy.tags" option-label="name" option-value="id"
          placeholder="選擇標籤" filter display="chip" />
      </div>
      <Message v-if="error" severity="error" size="small">{{ error }}</Message>
      <div class="actions">
        <Button type="button" label="取消" severity="secondary" text :disabled="working" @click="emit('close')" />
        <Button type="submit" label="儲存" :loading="working" :disabled="!title.trim()" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.metadata-form { display: grid; gap: var(--ui-space-4); }
.field { display: grid; gap: var(--ui-space-2); }
.field label { font-weight: 600; }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
</style>
