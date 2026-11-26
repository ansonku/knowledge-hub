<script setup lang="ts">
// P15: create or edit a collection in a dialog over the current page. A new collection starts under the
// collection being viewed; once created, its page opens and the sidebar marks it (unless asked to stay).
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { useTaxonomy } from '../../stores/taxonomy'
import { useWorkspace } from '../../stores/workspace'
import { closeCollectionEditor, collectionEditor } from '../collectionEditor'
import type { Category, CollectionColor } from '../types'

const taxonomy = useTaxonomy()
const workspace = useWorkspace()
const toast = useToast()
const router = useRouter()
const colors: { value: CollectionColor; label: string }[] = [
  { value: 'blue', label: '藍' }, { value: 'teal', label: '藍綠' }, { value: 'green', label: '綠' }, { value: 'amber', label: '琥珀' },
  { value: 'orange', label: '橘' }, { value: 'red', label: '紅' }, { value: 'purple', label: '紫' }, { value: 'gray', label: '灰' },
]
const request = computed(() => collectionEditor.request)
const editing = computed(() => request.value?.mode === 'edit' ? taxonomy.byId(request.value.id) : undefined)
const name = ref('')
const parent = ref<string | null>(null)
const description = ref('')
const color = ref<CollectionColor | ''>('')
const working = ref(false)
const error = ref('')
const nameInput = ref<{ $el: HTMLInputElement }>()

watch(request, next => {
  if (!next) return
  const current = next.mode === 'edit' ? taxonomy.byId(next.id) : undefined
  name.value = current?.name ?? ''
  parent.value = next.mode === 'create' ? next.parent : current?.parent ?? null
  description.value = current?.description ?? ''
  color.value = current?.color ?? ''
  error.value = ''
}, { immediate: true })

/** A collection cannot move under itself or its own descendants. */
const parentOptions = computed(() => {
  const id = editing.value?.id
  if (!id) return taxonomy.categoryOptions
  const blocked = new Set(taxonomy.tree.filter(node => taxonomy.pathOf(node.id).some(item => item.id === id)).map(node => node.id))
  return taxonomy.categoryOptions.filter(option => !blocked.has(option.id))
})
const where = computed(() => parent.value ? `建立在「${taxonomy.pathLabel(parent.value)}」底下。` : '建立在最上層。')

function focusName() {
  void nextTick(() => nameInput.value?.$el.focus())
}
function close() {
  if (!working.value) closeCollectionEditor()
}
async function save() {
  const current = request.value
  if (!current || working.value || !name.value.trim()) return
  working.value = true
  error.value = ''
  const payload = { name: name.value.trim(), parent: parent.value, description: description.value.trim(), color: color.value }
  try {
    const saved = current.mode === 'edit'
      ? await api<Category>(`/api/categories/${current.id}/`, 'PATCH', payload)
      : await api<Category>('/api/categories/', 'POST', payload)
    // Reload first, so the sidebar and the collection page already know the new collection.
    await taxonomy.load()
    void workspace.refresh(true)
    if (current.mode === 'create') {
      collectionEditor.created = saved.id
      if (!current.stay) void router.push({ name: 'app-collection', params: { id: saved.id } })
    }
    toast.add({ severity: 'success', summary: current.mode === 'edit' ? '已更新集合' : '已新增集合', detail: payload.name, life: 2500 })
    closeCollectionEditor()
  } catch (cause) {
    error.value = cause instanceof Error && cause.message ? cause.message : '無法儲存集合。'
  } finally {
    working.value = false
  }
}
</script>

<template>
  <Dialog :visible="Boolean(request)" :header="request?.mode === 'edit' ? '編輯集合' : '新增集合'" modal :closable="!working"
    :style="{ width: 'min(94vw, 30rem)' }" @show="focusName" @update:visible="open => { if (!open) close() }">
    <form v-if="request" class="form" @submit.prevent="save">
      <div class="field">
        <label for="collection-name">名稱</label>
        <InputText id="collection-name" ref="nameInput" v-model="name" maxlength="120" required autocomplete="off" autofocus />
      </div>
      <div class="field">
        <label for="collection-parent">上層集合</label>
        <Select v-model="parent" input-id="collection-parent" :options="parentOptions" option-label="name" option-value="id"
          show-clear filter placeholder="最上層" />
        <span v-if="request.mode === 'create'" class="hint">{{ where }}</span>
      </div>
      <div class="field">
        <label for="collection-desc">說明 <span class="optional">選填</span></label>
        <Textarea id="collection-desc" v-model="description" maxlength="1000" rows="3" auto-resize
          placeholder="這個集合收錄哪些文件？會顯示在集合頁與首頁。" />
      </div>
      <fieldset class="field colors">
        <legend>色標</legend>
        <label v-for="item in colors" :key="item.value" class="swatch" :class="[`ui-col-${item.value}`, { on: color === item.value }]">
          <input v-model="color" type="radio" name="collection-color" :value="item.value" class="ui-visually-hidden">
          <span aria-hidden="true">{{ Array.from(name || '集')[0].toUpperCase() }}</span>
          <span class="ui-visually-hidden">{{ item.label }}</span>
        </label>
      </fieldset>
      <Message v-if="error" severity="error" size="small">{{ error }}</Message>
      <div class="actions">
        <Button type="button" label="取消" text severity="secondary" :disabled="working" @click="close" />
        <Button type="submit" :label="request.mode === 'edit' ? '儲存' : '新增集合'" :loading="working" :disabled="!name.trim()" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.form { display: grid; gap: var(--ui-space-4); }
.field { display: grid; gap: var(--ui-space-2); }
.field > label, legend { font-weight: 600; }
.optional { color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 500; }
.hint { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.colors { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); margin: 0; padding: 0; border: 0; }
.colors legend { width: 100%; margin-bottom: var(--ui-space-2); padding: 0; }
.swatch { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border-radius: var(--ui-radius-md); border: 2px solid transparent; font-weight: 700; cursor: pointer; }
.swatch.on { border-color: var(--ui-text); }
.swatch:has(input:focus-visible) { box-shadow: var(--ui-focus-ring); }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
</style>
