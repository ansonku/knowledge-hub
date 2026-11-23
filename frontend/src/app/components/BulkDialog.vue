<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { api } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'

export type BulkAction = 'move' | 'add_tags' | 'remove_tags'

const props = defineProps<{ action?: BulkAction; ids: string[] }>()
const emit = defineEmits<{ close: []; done: [] }>()

const taxonomy = useTaxonomy()
const toast = useToast()
const category = ref<string | null>(null)
const tags = ref<string[]>([])
const working = ref(false)
const error = ref('')

const header = computed(() => ({ move: '移動到集合', add_tags: '加上標籤', remove_tags: '移除標籤' })[props.action ?? 'move'])
const ready = computed(() => props.action === 'move' || tags.value.length > 0)

watch(() => props.action, () => {
  category.value = null
  tags.value = []
  error.value = ''
})

async function apply() {
  if (!props.action || !ready.value || working.value) return
  working.value = true
  error.value = ''
  try {
    const payload = props.action === 'move' ? { category: category.value } : { tags: tags.value }
    const result = await api<{ count: number }>('/api/documents/bulk/', 'POST', { ids: props.ids, action: props.action, ...payload })
    toast.add({ severity: 'success', summary: `${header.value}：已更新 ${result.count} 份文件`, life: 3000 })
    emit('done')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法完成批次操作。'
  } finally {
    working.value = false
  }
}
</script>

<template>
  <Dialog :visible="Boolean(action)" :header="header" modal :closable="!working" :style="{ width: 'min(94vw, 28rem)' }"
    @update:visible="open => { if (!open && !working) emit('close') }">
    <form v-if="action" class="form" @submit.prevent="apply">
      <p class="lead">已選 {{ ids.length }} 份文件。</p>
      <div v-if="action === 'move'" class="field">
        <label for="bulk-category">目標集合</label>
        <Select input-id="bulk-category" v-model="category" :options="taxonomy.categoryOptions" option-label="name"
          option-value="id" show-clear placeholder="未分類" filter fluid />
      </div>
      <div v-else class="field">
        <label for="bulk-tags">標籤</label>
        <MultiSelect input-id="bulk-tags" v-model="tags" :options="taxonomy.tags" option-label="name" option-value="id"
          placeholder="選擇標籤" filter display="chip" fluid />
      </div>
      <Message v-if="error" severity="error" size="small">{{ error }}</Message>
      <div class="actions">
        <Button type="button" label="取消" text severity="secondary" :disabled="working" @click="emit('close')" />
        <Button type="submit" label="套用" :loading="working" :disabled="!ready" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.form, .field { display: grid; gap: var(--ui-space-2); }
.form { gap: var(--ui-space-4); }
.lead { margin: 0; color: var(--ui-text-muted); }
.field label { font-weight: 600; }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
</style>
