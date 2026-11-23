<script setup lang="ts">
import Button from 'primevue/button'
import Skeleton from 'primevue/skeleton'
import { ref, watch } from 'vue'
import { api } from '../../api'
import { activityDetail, activityVerb, initialOf, type ActivityItem, type ActivityPage } from '../activity'
import { longDateTime, shortDate } from '../types'

const props = defineProps<{ documentId: string; revision: string }>()

const items = ref<ActivityItem[]>([])
const page = ref(1)
const hasMore = ref(false)
const loading = ref(true)
const error = ref('')

async function load(reset = true) {
  loading.value = true
  error.value = ''
  if (reset) page.value = 1
  try {
    const data = await api<ActivityPage>(`/api/documents/${encodeURIComponent(props.documentId)}/activity/?page=${page.value}`)
    items.value = reset ? data.results : [...items.value, ...data.results]
    hasMore.value = data.has_more
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法載入活動。'
  } finally {
    loading.value = false
  }
}

// Reload when the document or its current version / metadata changes.
watch(() => [props.documentId, props.revision], () => load(), { immediate: true })
</script>

<template>
  <div class="activity">
    <p v-if="error" class="error">{{ error }} <button type="button" class="link" @click="load()">重試</button></p>
    <ol v-else class="events" aria-label="文件活動" :aria-busy="loading">
      <li v-for="item in items" :key="item.id" class="event">
        <span class="avatar" aria-hidden="true">{{ initialOf(item.actor) }}</span>
        <div class="body">
          <p class="line"><strong>{{ item.actor ?? '系統' }}</strong> {{ activityVerb(item) }}</p>
          <p v-if="activityDetail(item)" class="detail">{{ activityDetail(item) }}</p>
          <time :datetime="item.created_at" :title="longDateTime(item.created_at)">{{ shortDate(item.created_at) }}</time>
        </div>
      </li>
      <template v-if="loading && !items.length">
        <li v-for="index in 4" :key="`s${index}`" class="event"><Skeleton width="100%" height="2.5rem" /></li>
      </template>
      <li v-if="!loading && !items.length" class="empty">還沒有活動紀錄。</li>
    </ol>
    <Button v-if="hasMore" label="載入更早的活動" text size="small" fluid :loading="loading" @click="page++; load(false)" />
  </div>
</template>

<style scoped>
.activity { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-4) var(--ui-space-4) var(--ui-space-6); }
.events { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--ui-space-4); }
.event { display: flex; gap: var(--ui-space-3); }
.avatar { flex: none; display: grid; place-items: center; width: 1.75rem; height: 1.75rem; border-radius: 50%; background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); font-size: var(--ui-text-xs); font-weight: 600; }
.body { min-width: 0; display: grid; gap: 2px; }
.line { margin: 0; color: var(--ui-text-secondary); line-height: 1.5; }
.line strong { color: var(--ui-text); font-weight: 600; }
.detail { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
time { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.empty, .error { margin: 0; color: var(--ui-text-muted); }
.link { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; cursor: pointer; }
</style>
