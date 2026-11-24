<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Select from 'primevue/select'
import { computed, defineAsyncComponent, h, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '../api'
import { useTheme } from '../stores/theme'
import UiIcon from './components/UiIcon.vue'
import { versionSource, type DocumentDetails, type VersionInfo } from './composables/useDocument'
import { longDateTime } from './types'
import { useSite } from '../stores/site'

const site = useSite()
type History = { current: string; count: number; page_size: number; results: VersionInfo[] }

const DiffEditor = defineAsyncComponent({
  loader: () => import('../VersionDiff.vue'),
  loadingComponent: () => h(ProgressSpinner, { 'aria-label': '正在載入差異檢視', style: 'width: 2rem; height: 2rem' }),
  errorComponent: () => h(Message, { severity: 'error' }, () => '無法載入差異檢視。'),
})

const route = useRoute()
const theme = useTheme()
watch(() => theme.isDark, dark => {
  void import('../monaco').then(({ editor }) => editor.setTheme(dark ? 'vs-dark' : 'vs'))
}, { immediate: true })
const router = useRouter()
const documentId = computed(() => String(route.params.id))
const fromId = computed(() => typeof route.query.from === 'string' ? route.query.from : '')
const toId = computed(() => typeof route.query.to === 'string' ? route.query.to : '')
const base = computed(() => `/api/documents/${encodeURIComponent(documentId.value)}/`)

const file = ref<DocumentDetails>()
const versions = ref<VersionInfo[]>([])
const texts = ref<{ original: string; modified: string }>()
const loading = ref(true)
const error = ref('')
let controller: AbortController | undefined

const older = computed(() => versions.value.find(version => version.id === fromId.value))
const newer = computed(() => versions.value.find(version => version.id === toId.value))
const options = computed(() => versions.value.map(version => ({ id: version.id, label: `v${version.number} · ${version.note || versionSource(version)}` })))

async function loadMeta() {
  const [details, history] = await Promise.all([
    api<DocumentDetails>(base.value),
    api<History>(`${base.value}versions/?page=1`),
  ])
  file.value = details
  const known = new Map(history.results.map(version => [version.id, version]))
  // Selected versions may be older than the first page of history.
  for (const id of [fromId.value, toId.value]) {
    if (id && !known.has(id)) {
      const version = await api<VersionInfo>(`${base.value}versions/${encodeURIComponent(id)}/`).catch(cause => {
        throw cause instanceof ApiError && cause.status === 404 ? new Error('找不到要比較的版本，可能已被 Admin 刪除。') : cause
      })
      known.set(id, version)
    }
  }
  versions.value = [...known.values()].sort((a, b) => b.number - a.number)
  site.setTitle(`比較版本 · ${details.title}`)
}

async function load() {
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = ''
  texts.value = undefined
  try {
    await loadMeta()
    if (!older.value || !newer.value) throw new Error('請選擇兩個要比較的版本。')
    const [original, modified] = await Promise.all([older.value, newer.value].map(async version => {
      const response = await fetch(`${base.value}versions/${version.id}/download/`, { cache: 'no-store', signal: request.signal })
      if (!response.ok) throw new Error(`無法讀取 v${version.number} 的原始檔。`)
      return response.text()
    }))
    if (!request.signal.aborted) texts.value = { original, modified }
  } catch (cause) {
    if (!request.signal.aborted) error.value = cause instanceof Error ? cause.message : '無法比較版本。'
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}

function choose(key: 'from' | 'to', id: string) {
  void router.replace({ query: { ...route.query, [key]: id } })
}

function swap() {
  void router.replace({ query: { ...route.query, from: toId.value, to: fromId.value } })
}

watch([documentId, fromId, toId], load, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div class="compare-page">
    <header class="topbar">
      <RouterLink :to="{ name: 'app-document', params: { id: documentId } }" class="back">
        <UiIcon name="chevronLeft" :size="16" /><span>{{ file?.title ?? '回到文件' }}</span>
      </RouterLink>
    </header>
    <div class="body">
      <h1>比較版本</h1>
      <div class="pickers">
        <div class="picker">
          <label for="compare-from">舊版本</label>
          <Select input-id="compare-from" :model-value="fromId" :options="options" option-label="label" option-value="id"
            :disabled="loading && !versions.length" fluid @update:model-value="id => choose('from', id)" />
          <span v-if="older" class="when">{{ older.author ?? '系統' }} · {{ longDateTime(older.created_at) }}</span>
        </div>
        <Button text rounded aria-label="交換兩個版本" class="swap" @click="swap">
          <template #icon><UiIcon name="swap" :size="18" /></template>
        </Button>
        <div class="picker">
          <label for="compare-to">新版本</label>
          <Select input-id="compare-to" :model-value="toId" :options="options" option-label="label" option-value="id"
            :disabled="loading && !versions.length" fluid @update:model-value="id => choose('to', id)" />
          <span v-if="newer" class="when">{{ newer.author ?? '系統' }} · {{ longDateTime(newer.created_at) }}</span>
        </div>
      </div>

      <Message v-if="error" severity="error">{{ error }}</Message>
      <div v-else-if="loading" class="loading" role="status"><ProgressSpinner style="width: 2rem; height: 2rem" aria-label="正在讀取版本內容" /></div>
      <div v-else-if="texts && file" class="diff">
        <div class="legend"><span>v{{ older?.number }}</span><span>v{{ newer?.number }}</span></div>
        <DiffEditor :key="`${fromId}-${toId}`" :original="texts.original" :modified="texts.modified" :format="file.format" compact />
      </div>
    </div>
  </div>
</template>

<style scoped>
.topbar { display: flex; align-items: center; min-height: var(--ui-topbar-height); padding: 0 var(--ui-space-5); border-bottom: 1px solid var(--ui-border); box-sizing: border-box; }
.back { display: inline-flex; align-items: center; gap: var(--ui-space-1); min-width: 0; color: var(--ui-text-secondary); font-weight: 500; text-decoration: none; }
.back span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.back:hover { color: var(--ui-accent); }
.body { display: grid; gap: var(--ui-space-4); padding: var(--ui-space-5) var(--ui-gutter) var(--ui-space-7); }
h1 { margin: 0; font-size: 1.5rem; line-height: var(--ui-leading-tight); }
.pickers { display: flex; flex-wrap: wrap; align-items: flex-start; gap: var(--ui-space-3); }
.picker { flex: 1 1 16rem; display: grid; gap: var(--ui-space-1); min-width: 0; }
.picker label { font-weight: 600; }
.when { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.swap { margin-top: 1.5rem; }
.loading { display: grid; place-items: center; padding: var(--ui-space-7); }
.diff { border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); overflow: hidden; }
.legend { display: grid; grid-template-columns: 1fr 1fr; padding: var(--ui-space-2) var(--ui-space-4); border-bottom: 1px solid var(--ui-border); background: var(--ui-bg-subtle); color: var(--ui-text-muted); font-size: var(--ui-text-sm); font-weight: 600; }
</style>
