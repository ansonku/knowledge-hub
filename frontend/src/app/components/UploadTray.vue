<script setup lang="ts">
import ProgressBar from 'primevue/progressbar'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useTaxonomy } from '../../stores/taxonomy'
import { useUploads } from '../../stores/uploads'
import OrganizeDialog, { type OrganizeTarget } from './OrganizeDialog.vue'
import UiIcon from './UiIcon.vue'

const uploads = useUploads()
const taxonomy = useTaxonomy()
const collapsed = ref(false)

const title = computed(() => {
  const total = uploads.items.length
  if (uploads.active.length) return `上傳中 · ${uploads.finished} / ${total} 完成`
  if (uploads.needsAttention) return '上傳完成，部分檔案需要處理'
  return `已上傳 ${uploads.finished} 份文件`
})

// ---- Collection and tags for the whole batch, once nothing is uploading any more ----
const LIMIT = 100
const organizing = ref(false)
const batch = computed<OrganizeTarget[]>(() =>
  uploads.created.map(item => ({ id: item.documentId!, title: item.title ?? item.file.name })))
function onOrganized(category: string | null | undefined) {
  if (category !== undefined) uploads.moved(category)
}

function sizeLabel(size: number) {
  return size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`
}
</script>

<template>
  <section v-if="uploads.open && uploads.items.length" class="tray" aria-label="上傳進度">
    <header class="head">
      <span class="title" role="status" aria-live="polite">{{ title }}</span>
      <button type="button" class="icon" :aria-label="collapsed ? '展開上傳清單' : '收合上傳清單'" :aria-expanded="!collapsed"
        @click="collapsed = !collapsed">
        <UiIcon name="chevronDown" :size="16" :class="{ flipped: collapsed }" />
      </button>
      <button type="button" class="icon" aria-label="關閉上傳匣" :disabled="uploads.active.length > 0" @click="uploads.clear()">
        <UiIcon name="close" :size="16" />
      </button>
    </header>
    <ul v-if="!collapsed" class="list">
      <li v-for="item in uploads.items" :key="item.id" class="item">
        <div class="row">
          <span class="name" :title="item.file.name">{{ item.file.name }}</span>
          <span v-if="item.state === 'complete'" class="ok"><UiIcon name="check" :size="14" />{{ item.message }}</span>
          <span v-else-if="item.state === 'uploading'" class="muted">{{ item.progress }}%</span>
          <span v-else-if="item.state === 'queued'" class="muted">等待中</span>
          <span v-else-if="item.state === 'skipped'" class="muted">已略過</span>
          <span v-else class="muted">{{ sizeLabel(item.file.size) }}</span>
        </div>
        <span class="target">{{ taxonomy.pathLabel(item.category) }}</span>
        <ProgressBar v-if="item.state === 'uploading'" :value="item.progress" :show-value="false" class="bar"
          :aria-label="`${item.file.name} 上傳進度`" />
        <p v-if="item.state === 'failed'" class="error">{{ item.message }}</p>
        <div v-if="item.state === 'duplicate'" class="duplicate">
          <span>{{ item.message }}</span>
          <span class="actions">
            <button type="button" class="small" @click="uploads.skip(item)">略過</button>
            <button type="button" class="small" @click="uploads.retry(item, true)">仍要新增</button>
          </span>
        </div>
        <RouterLink v-if="item.state === 'complete' && item.documentId" :to="{ name: 'app-document', params: { id: item.documentId } }"
          class="open">開啟文件</RouterLink>
      </li>
    </ul>
    <footer v-if="!uploads.active.length && batch.length" class="foot">
      <button type="button" class="organize" :disabled="batch.length > LIMIT" @click="organizing = true">
        設定集合與標籤（{{ batch.length }} 份）
      </button>
      <p v-if="batch.length > LIMIT" class="error">一次最多 {{ LIMIT }} 份，請到「全部文件」用批次修改。</p>
    </footer>
    <OrganizeDialog v-model:visible="organizing" :documents="batch" @done="onOrganized" />
  </section>
</template>

<style scoped>
.tray {
  position: fixed; z-index: 1000; right: var(--ui-space-5); bottom: var(--ui-space-5); width: min(22rem, calc(100vw - 2rem));
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface);
  box-shadow: var(--ui-shadow-lg); overflow: hidden; font-size: var(--ui-text-md);
}
.head { display: flex; align-items: center; gap: var(--ui-space-1); padding: var(--ui-space-2) var(--ui-space-2) var(--ui-space-2) var(--ui-space-4); background: var(--ui-bg-inverse); color: var(--ui-text-inverse); }
.title { flex: 1; font-weight: 600; font-size: var(--ui-text-sm); }
.icon { display: grid; place-items: center; width: 2rem; height: 2rem; border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: inherit; cursor: pointer; }
.icon:disabled { opacity: .4; cursor: default; }
.flipped { transform: rotate(180deg); }
.list { list-style: none; margin: 0; padding: var(--ui-space-1) 0; max-height: 18rem; overflow-y: auto; }
.item { display: grid; gap: var(--ui-space-1); padding: var(--ui-space-2) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
.item:last-child { border-bottom: 0; }
.row { display: flex; align-items: center; gap: var(--ui-space-2); }
.name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ui-text); font-weight: 500; }
.target { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.muted { color: var(--ui-text-muted); font-size: var(--ui-text-xs); white-space: nowrap; }
.ok { display: inline-flex; align-items: center; gap: 4px; color: var(--ui-public-text); font-size: var(--ui-text-xs); font-weight: 600; white-space: nowrap; }
.bar { height: 4px; }
.error { margin: 0; color: var(--ui-danger); font-size: var(--ui-text-xs); }
.duplicate { display: grid; gap: var(--ui-space-1); color: var(--ui-lagging-text); font-size: var(--ui-text-xs); }
.actions { display: flex; gap: var(--ui-space-2); }
.small { min-height: 1.75rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-sm); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; font-size: var(--ui-text-xs); cursor: pointer; }
.open { color: var(--ui-accent); font-size: var(--ui-text-xs); font-weight: 600; }
.foot { display: grid; gap: var(--ui-space-1); padding: var(--ui-space-3) var(--ui-space-4); border-top: 1px solid var(--ui-border); background: var(--ui-bg-subtle); }
.organize {
  min-height: 2.25rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-accent); border-radius: var(--ui-radius-md);
  background: var(--ui-bg-surface); color: var(--ui-accent); font: inherit; font-size: var(--ui-text-sm); font-weight: 600; cursor: pointer;
}
.organize:hover:not(:disabled) { background: var(--ui-accent-soft); }
.organize:disabled { opacity: .5; cursor: default; }
</style>
