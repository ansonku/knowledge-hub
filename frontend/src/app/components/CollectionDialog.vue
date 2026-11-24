<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { ref, watch } from 'vue'
import { api } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'
import type { Category, CollectionColor } from '../types'

const props = defineProps<{ collection?: Category }>()
const emit = defineEmits<{ close: [] }>()

const taxonomy = useTaxonomy()
const toast = useToast()
const colors: { value: CollectionColor; label: string }[] = [
  { value: 'blue', label: '藍' }, { value: 'teal', label: '藍綠' }, { value: 'green', label: '綠' }, { value: 'amber', label: '琥珀' },
  { value: 'orange', label: '橘' }, { value: 'red', label: '紅' }, { value: 'purple', label: '紫' }, { value: 'gray', label: '灰' },
]
const name = ref('')
const description = ref('')
const color = ref<CollectionColor | ''>('')
const working = ref(false)
const error = ref('')

watch(() => props.collection, collection => {
  if (!collection) return
  name.value = collection.name
  description.value = collection.description ?? ''
  color.value = collection.color ?? ''
  error.value = ''
}, { immediate: true })

async function save() {
  if (!props.collection || working.value || !name.value.trim()) return
  working.value = true
  error.value = ''
  try {
    await api(`/api/categories/${props.collection.id}/`, 'PATCH', { name: name.value.trim(), description: description.value.trim(), color: color.value })
    await taxonomy.load()
    toast.add({ severity: 'success', summary: '已更新集合', life: 2500 })
    emit('close')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法儲存。'
  } finally {
    working.value = false
  }
}
</script>

<template>
  <Dialog :visible="Boolean(collection)" header="編輯集合" modal :closable="!working" :style="{ width: 'min(94vw, 30rem)' }"
    @update:visible="open => { if (!open && !working) emit('close') }">
    <form v-if="collection" class="form" @submit.prevent="save">
      <div class="field">
        <label for="collection-name">名稱</label>
        <InputText id="collection-name" v-model="name" maxlength="120" required />
      </div>
      <div class="field">
        <label for="collection-description">說明</label>
        <Textarea id="collection-description" v-model="description" maxlength="1000" rows="3" auto-resize
          placeholder="這個集合收錄哪些文件？會顯示在集合頁與首頁。" />
      </div>
      <fieldset class="field colors">
        <legend>色標</legend>
        <label v-for="item in colors" :key="item.value" class="swatch" :class="[`ui-col-${item.value}`, { on: color === item.value }]">
          <input v-model="color" type="radio" name="collection-color" :value="item.value" class="ui-visually-hidden">
          <span aria-hidden="true">{{ Array.from(name || '集')[0] }}</span>
          <span class="ui-visually-hidden">{{ item.label }}</span>
        </label>
      </fieldset>
      <Message v-if="error" severity="error" size="small">{{ error }}</Message>
      <div class="actions">
        <Button type="button" label="取消" text severity="secondary" :disabled="working" @click="emit('close')" />
        <Button type="submit" label="儲存" :loading="working" :disabled="!name.trim()" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.form { display: grid; gap: var(--ui-space-4); }
.field { display: grid; gap: var(--ui-space-2); }
.field > label, legend { font-weight: 600; }
.colors { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); margin: 0; padding: 0; border: 0; }
.colors legend { width: 100%; margin-bottom: var(--ui-space-2); padding: 0; }
.swatch { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border-radius: var(--ui-radius-md); border: 2px solid transparent; font-weight: 700; cursor: pointer; }
.swatch.on { border-color: var(--ui-text); }
.swatch:has(input:focus-visible) { box-shadow: var(--ui-focus-ring); }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
</style>
