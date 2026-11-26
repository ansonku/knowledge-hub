<script setup lang="ts">
// P13a: documents linking here (current versions only), and the documents this one links to with their state.
import Skeleton from 'primevue/skeleton'
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import UiIcon from '../components/UiIcon.vue'
import { shortDate } from '../types'

type Linked = { id: string; title: string; format: string; category: string | null; category_name: string | null; updated_at: string }
type Target = { id: string; status: 'ok' | 'trashed' | 'missing'; title?: string; category_name?: string | null }
const props = defineProps<{ documentId: string; revision: string }>()

const incoming = ref<Linked[]>([])
const outgoing = ref<Target[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<{ incoming: Linked[]; outgoing: Target[] }>(`/api/documents/${encodeURIComponent(props.documentId)}/links/`)
    incoming.value = data.incoming
    outgoing.value = data.outgoing
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法載入連結。'
  } finally {
    loading.value = false
  }
}
watch(() => [props.documentId, props.revision], load, { immediate: true })

const broken = (target: Target) => target.status === 'trashed' ? '已移入回收桶' : '文件不存在'
</script>

<template>
  <div class="links">
    <p v-if="error" class="error">{{ error }} <button type="button" class="retry" @click="load">重試</button></p>
    <template v-else>
      <section aria-labelledby="links-in">
        <h3 id="links-in">連到這裡的文件 <span v-if="!loading" class="count">{{ incoming.length }}</span></h3>
        <div v-if="loading" class="skeleton"><Skeleton height="2.5rem" /><Skeleton height="2.5rem" /></div>
        <ul v-else-if="incoming.length" class="list">
          <li v-for="item in incoming" :key="item.id">
            <RouterLink :to="{ name: 'app-document', params: { id: item.id } }" class="item">
              <UiIcon name="files" :size="15" />
              <span class="text">
                <span class="title">{{ item.title }}</span>
                <span class="meta">{{ item.category_name ?? '未分類' }} · {{ shortDate(item.updated_at) }}</span>
              </span>
            </RouterLink>
          </li>
        </ul>
        <p v-else class="empty">還沒有文件連到這裡。</p>
      </section>
      <section aria-labelledby="links-out">
        <h3 id="links-out">這份文件連到 <span v-if="!loading" class="count">{{ outgoing.length }}</span></h3>
        <div v-if="loading" class="skeleton"><Skeleton height="2.5rem" /></div>
        <ul v-else-if="outgoing.length" class="list">
          <li v-for="target in outgoing" :key="target.id">
            <RouterLink v-if="target.status === 'ok'" :to="{ name: 'app-document', params: { id: target.id } }" class="item">
              <UiIcon name="link" :size="15" />
              <span class="text">
                <span class="title">{{ target.title }}</span>
                <span class="meta">{{ target.category_name ?? '未分類' }}</span>
              </span>
            </RouterLink>
            <div v-else class="item broken">
              <UiIcon name="alert" :size="15" />
              <span class="text">
                <span class="title">{{ target.title ?? '（無法顯示標題）' }}</span>
                <span class="meta">{{ broken(target) }}，連結已失效</span>
              </span>
            </div>
          </li>
        </ul>
        <p v-else class="empty">目前版本沒有連到其他文件。編輯時輸入 <kbd>[[</kbd> 可以搜尋並插入文件連結。</p>
      </section>
      <p class="note">只計算各文件目前版本中的連結。</p>
    </template>
  </div>
</template>

<style scoped>
.links { display: grid; gap: var(--ui-space-5); padding: var(--ui-space-4) var(--ui-space-4) var(--ui-space-6); }
h3 { display: flex; align-items: center; gap: var(--ui-space-2); margin: 0 0 var(--ui-space-2); font-size: var(--ui-text-sm); }
.count { padding: 0 var(--ui-space-2); border-radius: var(--ui-radius-pill); background: var(--ui-bg-subtle); color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.item { display: flex; gap: var(--ui-space-2); align-items: flex-start; padding: var(--ui-space-2); border-radius: var(--ui-radius-md); color: var(--ui-text); text-decoration: none; }
a.item:hover { background: var(--ui-bg-subtle); }
.item .ui-icon { flex: none; margin-top: 3px; color: var(--ui-text-muted); }
.text { display: grid; min-width: 0; }
.title { overflow-wrap: anywhere; font-weight: 500; }
.meta { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.broken .title { text-decoration: line-through; color: var(--ui-text-muted); }
.broken .meta, .broken .ui-icon { color: var(--ui-lagging-text); }
.empty, .note { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); line-height: 1.6; }
.note { font-size: var(--ui-text-xs); }
.skeleton { display: grid; gap: var(--ui-space-2); }
.error { margin: 0; color: var(--ui-danger); }
.retry { border: 0; background: none; color: var(--ui-accent); cursor: pointer; font: inherit; }
kbd { padding: 0 4px; border: 1px solid var(--ui-border); border-radius: 4px; font-size: .75rem; }
</style>
