<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Drawer from 'primevue/drawer'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../../api'
import { useSession } from '../../stores/session'
import { useTaxonomy, type CategoryNode } from '../../stores/taxonomy'
import { useWorkspace } from '../../stores/workspace'
import UiIcon from '../components/UiIcon.vue'
import type { CollectionColor, TagItem } from '../types'
import { useSite } from '../../stores/site'

const site = useSite()
const route = useRoute()
const router = useRouter()
const session = useSession()
const taxonomy = useTaxonomy()
const workspace = useWorkspace()
const confirm = useConfirm()
const toast = useToast()

const markOf = (name: string) => Array.from(name)[0]?.toUpperCase() ?? '?'
const failure = (cause: unknown, fallback: string) => cause instanceof Error && cause.message ? cause.message : fallback
async function refresh() {
  await taxonomy.load()
  void workspace.refresh(true)
}

// ---- Collections ------------------------------------------------------------------------------
const colors: { value: CollectionColor; label: string }[] = [
  { value: 'blue', label: '藍' }, { value: 'teal', label: '藍綠' }, { value: 'green', label: '綠' }, { value: 'amber', label: '琥珀' },
  { value: 'orange', label: '橘' }, { value: 'red', label: '紅' }, { value: 'purple', label: '紫' }, { value: 'gray', label: '灰' },
]
const editorOpen = ref(false)
const editingId = ref<string | null>(null)
const form = ref({ name: '', parent: null as string | null, description: '', color: '' as CollectionColor | '' })
const formError = ref('')
const saving = ref(false)

function openCollection(node?: CategoryNode, parent: string | null = null) {
  editingId.value = node?.id ?? null
  form.value = node
    ? { name: node.name, parent: node.parent, description: node.description ?? '', color: node.color ?? '' }
    : { name: '', parent, description: '', color: '' }
  formError.value = ''
  editorOpen.value = true
}
/** A collection cannot move under itself or its own descendants. */
const parentOptions = computed(() => {
  const id = editingId.value
  const blocked = new Set<string>()
  if (id) for (const node of taxonomy.tree) if (taxonomy.pathOf(node.id).some(item => item.id === id)) blocked.add(node.id)
  return taxonomy.categoryOptions.filter(option => !blocked.has(option.id))
})
async function saveCollection() {
  if (saving.value || !form.value.name.trim()) return
  saving.value = true
  formError.value = ''
  const payload = { name: form.value.name.trim(), parent: form.value.parent, description: form.value.description.trim(), color: form.value.color }
  try {
    await api(`/api/categories/${editingId.value ? `${editingId.value}/` : ''}`, editingId.value ? 'PATCH' : 'POST', payload)
    await refresh()
    toast.add({ severity: 'success', summary: editingId.value ? '已更新集合' : '已新增集合', detail: payload.name, life: 2500 })
    editorOpen.value = false
  } catch (cause) {
    formError.value = failure(cause, '無法儲存集合。')
  } finally {
    saving.value = false
  }
}
const deleteBlocker = (node: CategoryNode) =>
  node.hasChildren ? '先移走或刪除子集合' : (node.document_count ?? 0) > 0 ? '先把文件移到其他集合' : ''
function removeCollection(node: CategoryNode) {
  confirm.require({
    header: '刪除集合',
    message: `確定刪除「${node.name}」？`,
    acceptProps: { label: '刪除', severity: 'danger' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      try {
        await api(`/api/categories/${node.id}/`, 'DELETE')
        await refresh()
        toast.add({ severity: 'success', summary: '已刪除集合', detail: node.name, life: 2500 })
      } catch (cause) {
        toast.add({ severity: 'error', summary: '無法刪除集合', detail: failure(cause, ''), life: 5000 })
      }
    },
  })
}

// ---- Tags -----------------------------------------------------------------------------------------
const tagFilter = ref('')
const tags = computed(() => {
  const keyword = tagFilter.value.trim().toLowerCase()
  return keyword ? taxonomy.tags.filter(tag => tag.name.toLowerCase().includes(keyword)) : taxonomy.tags
})
const newTag = ref('')
const tagError = ref('')
async function addTag() {
  const name = newTag.value.trim()
  if (!name) return
  tagError.value = ''
  try {
    await api('/api/tags/', 'POST', { name })
    await refresh()
    newTag.value = ''
    toast.add({ severity: 'success', summary: '已新增標籤', detail: name, life: 2500 })
  } catch (cause) {
    tagError.value = failure(cause, '無法新增標籤。')
  }
}
const renaming = ref<string | null>(null)
const renameText = ref('')
async function startRename(tag: TagItem) {
  renaming.value = tag.id
  renameText.value = tag.name
  await nextTick()
  document.getElementById(`rename-${tag.id}`)?.focus()
}
async function saveRename(tag: TagItem) {
  const name = renameText.value.trim()
  if (!name || name === tag.name) { renaming.value = null; return }
  try {
    await api(`/api/tags/${tag.id}/`, 'PATCH', { name })
    await refresh()
    renaming.value = null
    toast.add({ severity: 'success', summary: '已重新命名標籤', detail: `${tag.name} → ${name}`, life: 2500 })
  } catch (cause) {
    toast.add({ severity: 'error', summary: '無法重新命名', detail: failure(cause, ''), life: 5000 })
  }
}
function removeTag(tag: TagItem) {
  const count = tag.document_count ?? 0
  confirm.require({
    header: '刪除標籤',
    message: count ? `「${tag.name}」會從 ${count} 份文件上移除。` : `確定刪除「${tag.name}」？`,
    acceptProps: { label: '刪除', severity: 'danger' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      try {
        await api(`/api/tags/${tag.id}/`, 'DELETE')
        selected.value = selected.value.filter(id => id !== tag.id)
        await refresh()
        toast.add({ severity: 'success', summary: '已刪除標籤', detail: tag.name, life: 2500 })
      } catch (cause) {
        toast.add({ severity: 'error', summary: '無法刪除標籤', detail: failure(cause, ''), life: 5000 })
      }
    },
  })
}

// ---- Merge (Admin) ---------------------------------------------------------------------------------------
const selected = ref<string[]>([])
const mergeOpen = ref(false)
const mergeTarget = ref<string | null>(null)
const merging = ref(false)
const mergeError = ref('')
function toggleTag(id: string) {
  selected.value = selected.value.includes(id) ? selected.value.filter(item => item !== id) : [...selected.value, id]
}
const tagName = (id: string) => taxonomy.tags.find(tag => tag.id === id)?.name ?? ''
const mergeSources = computed(() => selected.value.filter(id => id !== mergeTarget.value))
const mergeAffects = computed(() => mergeSources.value.reduce((sum, id) => sum + (taxonomy.tags.find(tag => tag.id === id)?.document_count ?? 0), 0))
function openMerge() {
  // Default target: the most used of the selected tags.
  const ranked = [...selected.value].sort((a, b) =>
    (taxonomy.tags.find(tag => tag.id === b)?.document_count ?? 0) - (taxonomy.tags.find(tag => tag.id === a)?.document_count ?? 0))
  mergeTarget.value = ranked[0] ?? null
  mergeError.value = ''
  mergeOpen.value = true
}
async function merge() {
  if (!mergeTarget.value || !mergeSources.value.length || merging.value) return
  merging.value = true
  mergeError.value = ''
  try {
    const result = await api<{ merged: number; documents: number }>('/api/tags/merge/', 'POST', { sources: mergeSources.value, target: mergeTarget.value })
    const target = tagName(mergeTarget.value)
    selected.value = []
    mergeOpen.value = false
    await refresh()
    toast.add({ severity: 'success', summary: `已合併 ${result.merged} 個標籤到「${target}」`, detail: `更新了 ${result.documents} 份文件`, life: 4000 })
  } catch (cause) {
    mergeError.value = failure(cause, '無法合併標籤。')
  } finally {
    merging.value = false
  }
}

onMounted(() => {
  site.setTitle('集合與標籤')
  if (route.query.new === 'collection' && session.canEdit) {
    openCollection()
    void router.replace({ query: {} })
  }
})
watch(() => route.query.new, value => {
  if (value === 'collection' && session.canEdit) {
    openCollection()
    void router.replace({ query: {} })
  }
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <p class="eyebrow">管理</p>
      <h1>集合與標籤</h1>
      <p class="subtitle">集合是文件的資料夾，每份文件屬於一個集合；標籤可以跨集合標記文件。</p>
    </header>

    <Message v-if="!session.canEdit" severity="error">集合與標籤只開放給 Editor 與 Admin 管理。</Message>

    <div v-else class="columns">
      <!-- Collections -->
      <section class="card" aria-labelledby="collections-title">
        <div class="card-head">
          <div>
            <h2 id="collections-title">集合</h2>
            <p class="card-sub">{{ taxonomy.categories.length }} 個集合</p>
          </div>
          <Button size="small" @click="openCollection()"><UiIcon name="plus" :size="15" /><span>新增集合</span></Button>
        </div>
        <ul v-if="taxonomy.tree.length" class="tree">
          <li v-for="node in taxonomy.tree" :key="node.id" class="node" :style="{ '--depth': node.depth }">
            <span class="ui-col-mark mark" :class="`ui-col-${node.color || 'gray'}`" aria-hidden="true">{{ markOf(node.name) }}</span>
            <div class="node-text">
              <RouterLink :to="{ name: 'app-collection', params: { id: node.id } }" class="node-name">{{ node.name }}</RouterLink>
              <span v-if="node.description" class="node-desc">{{ node.description }}</span>
            </div>
            <span class="count" :title="`直接收錄 ${node.document_count ?? 0} 份，含子集合共 ${taxonomy.totalOf(node.id)} 份`">
              {{ taxonomy.totalOf(node.id) }} 份
            </span>
            <div class="row-actions">
              <button type="button" class="icon-button" :aria-label="`在「${node.name}」下新增子集合`" title="新增子集合" @click="openCollection(undefined, node.id)">
                <UiIcon name="plus" :size="16" />
              </button>
              <button type="button" class="icon-button" :aria-label="`編輯「${node.name}」`" title="編輯" @click="openCollection(node)">
                <UiIcon name="edit" :size="16" />
              </button>
              <button type="button" class="icon-button danger" :aria-label="`刪除「${node.name}」`"
                :title="deleteBlocker(node) || '刪除'" :disabled="Boolean(deleteBlocker(node))" @click="removeCollection(node)">
                <UiIcon name="trash" :size="16" />
              </button>
            </div>
          </li>
        </ul>
        <p v-else class="empty">還沒有集合。</p>
      </section>

      <!-- Tags -->
      <section class="card" aria-labelledby="tags-title">
        <div class="card-head">
          <div>
            <h2 id="tags-title">標籤</h2>
            <p class="card-sub">{{ taxonomy.tags.length }} 個標籤</p>
          </div>
        </div>
        <div class="tag-tools">
          <label class="filter">
            <span class="ui-visually-hidden">篩選標籤</span>
            <UiIcon name="search" :size="15" />
            <input v-model="tagFilter" type="search" placeholder="篩選標籤" maxlength="60">
          </label>
          <form class="add-tag" @submit.prevent="addTag">
            <label for="new-tag" class="ui-visually-hidden">新標籤名稱</label>
            <InputText id="new-tag" v-model="newTag" maxlength="60" placeholder="新標籤名稱" size="small" />
            <Button type="submit" label="新增" size="small" outlined :disabled="!newTag.trim()" />
          </form>
        </div>
        <Message v-if="tagError" severity="error" size="small" class="tag-error">{{ tagError }}</Message>

        <div v-if="session.isAdmin && selected.length" class="merge-bar" role="toolbar" aria-label="合併標籤">
          <span>已選 {{ selected.length }} 個標籤</span>
          <button type="button" class="bar-button" @click="openMerge">合併…</button>
          <button type="button" class="bar-button ghost" @click="selected = []">取消選取</button>
        </div>

        <ul v-if="tags.length" class="tags">
          <li v-for="tag in tags" :key="tag.id" class="tag-row" :class="{ selected: selected.includes(tag.id) }">
            <input v-if="session.isAdmin" type="checkbox" class="check" :checked="selected.includes(tag.id)"
              :aria-label="`選取「${tag.name}」以合併`" @change="toggleTag(tag.id)">
            <form v-if="renaming === tag.id" class="rename" @submit.prevent="saveRename(tag)">
              <label :for="`rename-${tag.id}`" class="ui-visually-hidden">新名稱</label>
              <InputText :id="`rename-${tag.id}`" v-model="renameText" maxlength="60" size="small" @keydown.esc="renaming = null" />
              <Button type="submit" label="儲存" size="small" />
              <Button type="button" label="取消" size="small" text severity="secondary" @click="renaming = null" />
            </form>
            <template v-else>
              <span class="tag-name">{{ tag.name }}</span>
              <RouterLink v-if="tag.document_count" :to="{ name: 'app-library', query: { tag: tag.id } }" class="count link">{{ tag.document_count }} 份</RouterLink>
              <span v-else class="count">未使用</span>
              <div class="row-actions">
                <button type="button" class="icon-button" :aria-label="`重新命名「${tag.name}」`" title="重新命名" @click="startRename(tag)">
                  <UiIcon name="edit" :size="16" />
                </button>
                <button type="button" class="icon-button danger" :aria-label="`刪除「${tag.name}」`" title="刪除" @click="removeTag(tag)">
                  <UiIcon name="trash" :size="16" />
                </button>
              </div>
            </template>
          </li>
        </ul>
        <p v-else class="empty">{{ tagFilter ? '沒有符合的標籤。' : '還沒有標籤。' }}</p>
        <p v-if="session.isAdmin" class="hint">勾選兩個以上意思相同的標籤，可以合併成一個。</p>
      </section>
    </div>

    <Drawer v-model:visible="editorOpen" position="right" :header="editingId ? '編輯集合' : '新增集合'" :style="{ width: 'min(100vw, 26rem)' }">
      <form class="collection-form" @submit.prevent="saveCollection">
        <div class="field">
          <label for="collection-name">名稱</label>
          <InputText id="collection-name" v-model="form.name" maxlength="120" required />
        </div>
        <div class="field">
          <label for="collection-parent">上層集合</label>
          <Select v-model="form.parent" input-id="collection-parent" :options="parentOptions" option-label="name" option-value="id"
            show-clear placeholder="最上層" />
        </div>
        <div class="field">
          <label for="collection-desc">說明 <span class="optional">選填</span></label>
          <Textarea id="collection-desc" v-model="form.description" maxlength="1000" rows="3" auto-resize
            placeholder="這個集合收錄哪些文件？會顯示在集合頁與首頁。" />
        </div>
        <fieldset class="field colors">
          <legend>色標</legend>
          <label v-for="item in colors" :key="item.value" class="swatch" :class="[`ui-col-${item.value}`, { on: form.color === item.value }]">
            <input v-model="form.color" type="radio" name="collection-color" :value="item.value" class="ui-visually-hidden">
            <span aria-hidden="true">{{ markOf(form.name || '集') }}</span>
            <span class="ui-visually-hidden">{{ item.label }}</span>
          </label>
        </fieldset>
        <Message v-if="formError" severity="error" size="small">{{ formError }}</Message>
        <div class="actions">
          <Button type="button" label="取消" text severity="secondary" @click="editorOpen = false" />
          <Button type="submit" :label="editingId ? '儲存' : '新增集合'" :loading="saving" :disabled="!form.name.trim()" />
        </div>
      </form>
    </Drawer>

    <Dialog v-model:visible="mergeOpen" header="合併標籤" modal :style="{ width: 'min(94vw, 30rem)' }" :closable="!merging">
      <div class="merge">
        <div class="field">
          <label for="merge-target">保留的標籤</label>
          <Select v-model="mergeTarget" input-id="merge-target" :options="taxonomy.tags" option-label="name" option-value="id" filter />
        </div>
        <p v-if="mergeSources.length" class="merge-summary">
          會把 <strong>{{ mergeSources.map(tagName).join('、') }}</strong> 合併到 <strong>{{ tagName(mergeTarget ?? '') }}</strong>，
          約 {{ mergeAffects }} 份文件會改用保留的標籤（回收桶裡的文件也會一併更新），被合併的標籤會刪除。每份受影響的文件都會留下一筆活動紀錄。
        </p>
        <p v-else class="merge-summary">請至少保留一個與「保留的標籤」不同的已選標籤。</p>
        <Message v-if="mergeError" severity="error" size="small">{{ mergeError }}</Message>
        <div class="actions">
          <Button type="button" label="取消" text severity="secondary" :disabled="merging" @click="mergeOpen = false" />
          <Button type="button" label="合併" severity="danger" :loading="merging" :disabled="!mergeSources.length || !mergeTarget" @click="merge" />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 90rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-5); }
.eyebrow { margin: 0 0 var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.columns { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: var(--ui-space-5); align-items: start; }
.card { border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); overflow: hidden; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-3); padding: var(--ui-space-4) var(--ui-space-5); border-bottom: 1px solid var(--ui-border-subtle); }
.card-head .p-button { gap: var(--ui-space-1); }
h2 { margin: 0; font-size: 1rem; }
.card-sub { margin: 2px 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.tree, .tags { list-style: none; margin: 0; padding: var(--ui-space-2) 0; }
.node { display: flex; align-items: center; gap: var(--ui-space-3); padding: var(--ui-space-2) var(--ui-space-4) var(--ui-space-2) calc(var(--ui-space-5) + var(--depth) * 1.5rem); }
.node:hover, .tag-row:hover { background: var(--ui-bg-subtle); }
.mark { width: 1.75rem; height: 1.75rem; font-size: .8125rem; }
.node-text { flex: 1; min-width: 0; display: grid; gap: 1px; }
.node-name { color: var(--ui-text); font-weight: 600; text-decoration: none; overflow-wrap: anywhere; }
.node-name:hover { color: var(--ui-accent); text-decoration: underline; }
.node-desc { color: var(--ui-text-muted); font-size: var(--ui-text-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.count { flex: none; color: var(--ui-text-muted); font-size: var(--ui-text-sm); white-space: nowrap; }
.count.link { color: var(--ui-accent); text-decoration: none; }
.count.link:hover { text-decoration: underline; }
.row-actions { flex: none; display: flex; gap: 2px; }
.icon-button { display: grid; place-items: center; width: 2rem; height: 2rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.icon-button:hover:not(:disabled) { background: var(--ui-bg-muted); color: var(--ui-text); }
.icon-button.danger:hover:not(:disabled) { color: var(--ui-danger); }
.icon-button:disabled { opacity: .35; cursor: default; }
.tag-tools { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); padding: var(--ui-space-3) var(--ui-space-5) 0; }
.filter { flex: 1 1 10rem; display: flex; align-items: center; gap: var(--ui-space-2); min-height: 2.25rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); color: var(--ui-text-muted); box-sizing: border-box; }
.filter:focus-within { border-color: var(--ui-accent); box-shadow: var(--ui-focus-ring); }
.filter input { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; color: var(--ui-text); font: inherit; }
.filter input:focus-visible { box-shadow: none; }
.add-tag { flex: 1 1 12rem; display: flex; gap: var(--ui-space-2); }
.add-tag .p-inputtext { flex: 1; min-width: 0; }
.tag-error { margin: var(--ui-space-2) var(--ui-space-5) 0; }
.merge-bar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); margin: var(--ui-space-3) var(--ui-space-5) 0; padding: var(--ui-space-2) var(--ui-space-2) var(--ui-space-2) var(--ui-space-4); border-radius: var(--ui-radius-lg); background: var(--ui-bg-inverse); color: var(--ui-text-inverse); font-size: var(--ui-text-sm); font-weight: 600; }
.bar-button { min-height: 2rem; padding: 0 var(--ui-space-3); border: 0; border-radius: var(--ui-radius-md); background: rgb(255 255 255 / .14); color: inherit; font: inherit; cursor: pointer; }
.hub-dark .bar-button { background: rgb(16 24 40 / .1); }
.bar-button.ghost { margin-left: auto; background: transparent; }
.tag-row { display: flex; align-items: center; gap: var(--ui-space-3); min-height: 2.75rem; padding: var(--ui-space-1) var(--ui-space-4) var(--ui-space-1) var(--ui-space-5); }
.tag-row.selected { background: var(--ui-accent-soft); }
.check { width: 1rem; height: 1rem; margin: 0; accent-color: var(--ui-accent); }
.tag-name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.rename { flex: 1; display: flex; flex-wrap: wrap; gap: var(--ui-space-2); }
.rename .p-inputtext { flex: 1 1 8rem; min-width: 0; }
.empty, .hint { margin: 0; padding: var(--ui-space-4) var(--ui-space-5); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.hint { padding-top: 0; font-size: var(--ui-text-xs); }
.collection-form, .merge { display: grid; gap: var(--ui-space-4); }
.field { display: grid; gap: var(--ui-space-2); }
.field > label, legend { font-weight: 600; }
.optional { color: var(--ui-text-muted); font-weight: 400; font-size: var(--ui-text-sm); }
.colors { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); margin: 0; padding: 0; border: 0; }
.colors legend { width: 100%; margin-bottom: var(--ui-space-2); padding: 0; }
.swatch { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border-radius: var(--ui-radius-md); border: 2px solid transparent; font-weight: 700; cursor: pointer; }
.swatch.on { border-color: var(--ui-text); }
.swatch:has(input:focus-visible) { box-shadow: var(--ui-focus-ring); }
.merge-summary { margin: 0; color: var(--ui-text-secondary); line-height: 1.7; }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
@media (max-width: 1100px) {
  .columns { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 560px) {
  .node { padding-left: calc(var(--ui-space-4) + var(--depth) * 1rem); padding-right: var(--ui-space-2); }
  .node-desc { display: none; }
  .tag-row { padding-left: var(--ui-space-4); padding-right: var(--ui-space-2); }
}
</style>
