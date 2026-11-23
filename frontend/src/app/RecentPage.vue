<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { useTaxonomy } from '../stores/taxonomy'
import UiIcon from './components/UiIcon.vue'
import { longDateTime, shortDate, visibilityOf, type DocumentRow } from './types'

type RecentRow = DocumentRow & { viewed_at: string }

const taxonomy = useTaxonomy()
const rows = ref<RecentRow[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = (await api<{ results: RecentRow[] }>('/api/me/recent/?limit=50')).results
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法載入最近閱讀。'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  document.title = '最近閱讀 · Knowledge Hub'
  void load()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <h1>最近閱讀</h1>
      <p class="subtitle">只有你看得到這份清單，最多保留最近 50 份文件。</p>
    </header>
    <Message v-if="error" severity="error">{{ error }} <Button label="重試" text size="small" @click="load" /></Message>
    <ol v-else class="list" :aria-busy="loading">
      <template v-if="loading">
        <li v-for="index in 6" :key="index" class="row"><Skeleton width="100%" height="2.75rem" /></li>
      </template>
      <li v-for="row in rows" v-else :key="row.id" class="row">
        <span class="format" :class="row.format">{{ row.format === 'html' ? 'HTML' : 'MD' }}</span>
        <div class="text">
          <RouterLink :to="{ name: 'app-document', params: { id: row.id } }" class="title">{{ row.title }}</RouterLink>
          <span class="meta">{{ taxonomy.pathLabel(row.category) }} · v{{ row.current_version.number }} · {{ visibilityOf(row).label }}</span>
        </div>
        <UiIcon v-if="row.is_favorite" name="star" filled :size="15" class="star" />
        <time class="when" :datetime="row.viewed_at" :title="longDateTime(row.viewed_at)">{{ shortDate(row.viewed_at) }}</time>
      </li>
    </ol>
    <div v-if="!loading && !error && !rows.length" class="empty">
      <UiIcon name="clock" :size="28" />
      <p class="empty-title">還沒有閱讀紀錄</p>
      <p>開啟任何文件後，就會出現在這裡。</p>
      <RouterLink :to="{ name: 'app-library' }" class="empty-link">瀏覽全部文件</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 60rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); }
.head { margin-bottom: var(--ui-space-5); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.list { list-style: none; margin: 0; padding: 0; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.list:empty { display: none; }
.row { display: flex; align-items: center; gap: var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
.row:last-child { border-bottom: 0; }
.format { flex: none; display: grid; place-items: center; min-width: 2.25rem; height: 2rem; padding: 0 .25rem; box-sizing: border-box; border-radius: var(--ui-radius-md); font-size: .65625rem; font-weight: 700; }
.format.md { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); }
.format.html { background: var(--ui-format-html-bg); color: var(--ui-format-html-text); }
.text { flex: 1; min-width: 0; display: grid; gap: 2px; }
.title { color: var(--ui-text); font-weight: 600; text-decoration: none; overflow-wrap: anywhere; }
.title:hover { color: var(--ui-accent); text-decoration: underline; }
.meta { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.star { color: #d99a00; }
.when { flex: none; color: var(--ui-text-muted); font-size: var(--ui-text-sm); white-space: nowrap; }
.empty { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-7) var(--ui-space-4); border: 1px dashed var(--ui-border-strong); border-radius: var(--ui-radius-lg); color: var(--ui-text-muted); text-align: center; }
.empty p { margin: 0; }
.empty-title { color: var(--ui-text); font-weight: 600; font-size: var(--ui-text-lg); }
.empty-link { color: var(--ui-accent); font-weight: 600; }
</style>
