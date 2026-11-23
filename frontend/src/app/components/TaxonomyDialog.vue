<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import Select from 'primevue/select'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { api } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'

const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ changed: [] }>()

const taxonomy = useTaxonomy()
const confirm = useConfirm()
const toast = useToast()

type Kind = 'categories' | 'tags'
const kinds: { value: Kind; label: string }[] = [{ value: 'categories', label: '集合' }, { value: 'tags', label: '標籤' }]
const kind = ref<Kind>('categories')
const selectedId = ref<string | null>(null)
const name = ref('')
const parent = ref<string | null>(null)
const error = ref('')
const working = ref(false)

const items = computed(() => kind.value === 'categories' ? taxonomy.categoryOptions : taxonomy.tags)
const parentOptions = computed(() => {
  // A category cannot move under itself or its own descendants.
  const blocked = new Set<string>()
  if (selectedId.value) {
    blocked.add(selectedId.value)
    for (const node of taxonomy.tree) if (taxonomy.pathOf(node.id).some(item => item.id === selectedId.value)) blocked.add(node.id)
  }
  return taxonomy.categoryOptions.filter(option => !blocked.has(option.id))
})
const noun = computed(() => kind.value === 'categories' ? '集合' : '標籤')

function select(id: string | null) {
  selectedId.value = id
  const category = kind.value === 'categories' ? taxonomy.byId(id) : undefined
  name.value = category?.name ?? taxonomy.tags.find(tag => tag.id === id)?.name ?? ''
  parent.value = category?.parent ?? null
  error.value = ''
}

watch(kind, () => select(null))
watch(visible, open => { if (open) select(null) })

async function save() {
  if (working.value || !name.value.trim()) return
  working.value = true
  error.value = ''
  try {
    const endpoint = `/api/${kind.value}/${selectedId.value ? `${selectedId.value}/` : ''}`
    const payload = kind.value === 'categories' ? { name: name.value.trim(), parent: parent.value } : { name: name.value.trim() }
    await api(endpoint, selectedId.value ? 'PATCH' : 'POST', payload)
    await taxonomy.load()
    toast.add({ severity: 'success', summary: selectedId.value ? `已更新${noun.value}` : `已新增${noun.value}`, life: 3000 })
    emit('changed')
    select(null)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法儲存。'
  } finally {
    working.value = false
  }
}

function remove() {
  const id = selectedId.value
  if (!id) return
  confirm.require({
    header: `刪除${noun.value}`,
    message: kind.value === 'categories'
      ? `確定刪除「${name.value}」？仍有文件或子集合的集合無法刪除，請先移走其中的內容。`
      : `刪除「${name.value}」後，文件上的這個標籤會一併移除。`,
    acceptProps: { label: '刪除', severity: 'danger' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      working.value = true
      error.value = ''
      try {
        await api(`/api/${kind.value}/${id}/`, 'DELETE')
        await taxonomy.load()
        toast.add({ severity: 'success', summary: `已刪除${noun.value}`, life: 3000 })
        emit('changed')
        select(null)
      } catch (cause) {
        error.value = cause instanceof Error ? cause.message : '無法刪除。'
      } finally {
        working.value = false
      }
    },
  })
}
</script>

<template>
  <Dialog v-model:visible="visible" header="管理集合與標籤" modal :style="{ width: 'min(94vw, 32rem)' }">
    <form class="taxonomy-form" @submit.prevent="save">
      <SelectButton v-model="kind" :options="kinds" option-label="label" option-value="value" :allow-empty="false" aria-label="類型" />
      <div class="field">
        <label for="taxonomy-item">要編輯的{{ noun }}</label>
        <Select input-id="taxonomy-item" :model-value="selectedId" :options="items" option-label="name" option-value="id"
          show-clear :placeholder="`留空以新增${noun}`" filter @update:model-value="select" />
      </div>
      <div class="field">
        <label for="taxonomy-name">名稱</label>
        <InputText id="taxonomy-name" v-model="name" :maxlength="kind === 'categories' ? 120 : 60" required />
      </div>
      <div v-if="kind === 'categories'" class="field">
        <label for="taxonomy-parent">上層集合</label>
        <Select input-id="taxonomy-parent" v-model="parent" :options="parentOptions" option-label="name" option-value="id"
          show-clear placeholder="最上層" />
      </div>
      <Message v-if="error" severity="error" size="small">{{ error }}</Message>
      <div class="actions">
        <Button v-if="selectedId" type="button" label="刪除" severity="danger" text :disabled="working" @click="remove" />
        <span class="spacer" />
        <Button type="submit" :label="selectedId ? '儲存' : `新增${noun}`" :loading="working" :disabled="!name.trim()" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.taxonomy-form, .field { display: grid; gap: var(--ui-space-2); }
.taxonomy-form { gap: var(--ui-space-4); }
.field label { font-weight: 600; font-size: var(--ui-text-md); }
.actions { display: flex; align-items: center; gap: var(--ui-space-2); }
.spacer { flex: 1; }
</style>
