<script setup lang="ts">
// P23: storage usage against the limit, what counts towards it, and the limit itself (系統狀態 › 儲存空間).
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import Skeleton from 'primevue/skeleton'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAttention } from '../../stores/attention'
import { bytes } from './system'

type Storage = {
  limit: number | null; used: number; share: number | null; level: 'notice' | 'warning' | 'full' | null
  parts: Record<'database' | 'versions_current' | 'versions_old' | 'images' | 'videos' | 'trash', number>
  disk: { total_bytes: number; free_bytes: number } | null; min_free_bytes: number
}

const emit = defineEmits<{ changed: [] }>()
const toast = useToast()
const attention = useAttention()
const GB = 1024 ** 3

const data = ref<Storage>()
const error = ref('')
const limitGb = ref<number | null>(null)
const saving = ref(false)

async function load() {
  try {
    data.value = await api<Storage>('/api/admin/storage/')
    limitGb.value = data.value.limit ? Math.round(data.value.limit / GB * 10) / 10 : null
    error.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法載入儲存空間。'
  }
}
onMounted(load)

const LABELS: [keyof Storage['parts'], string][] = [
  ['database', '資料庫'], ['versions_current', '文件（目前版本）'], ['versions_old', '文件（舊版本）'],
  ['images', '圖片'], ['videos', '影片'], ['trash', '回收桶'],
]
const parts = computed(() => data.value
  ? LABELS.map(([key, label]) => ({ key, label, size: data.value!.parts[key], share: data.value!.used ? data.value!.parts[key] / data.value!.used : 0 }))
  : [])
const percent = computed(() => data.value?.share == null ? 0 : Math.round(data.value.share * 100))
const tone = computed(() => data.value?.level === 'full' || data.value?.level === 'warning' ? 'danger' : data.value?.level === 'notice' ? 'warn' : '')
const diskUsed = computed(() => data.value?.disk ? (data.value.disk.total_bytes - data.value.disk.free_bytes) / data.value.disk.total_bytes : 0)

const savedGb = computed(() => data.value?.limit ? Math.round(data.value.limit / GB * 10) / 10 : null)
const dirty = computed(() => (limitGb.value ?? null) !== savedGb.value)
const belowUsage = computed(() => limitGb.value != null && data.value != null && limitGb.value * GB < data.value.used)

async function save(value: number | null) {
  saving.value = true
  try {
    data.value = await api<Storage>('/api/admin/storage/', 'PUT', { limit: value == null ? null : Math.round(value * GB) })
    limitGb.value = data.value.limit ? Math.round(data.value.limit / GB * 10) / 10 : null
    toast.add({ severity: 'success', summary: value == null ? '已取消儲存空間上限' : `儲存空間上限已設為 ${value} GB`, life: 2500 })
    emit('changed')
    void attention.load(true)
  } catch (cause) {
    toast.add({ severity: 'error', summary: '無法儲存', detail: cause instanceof Error ? cause.message : '', life: 5000 })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section id="storage" class="card" aria-labelledby="storage-title">
    <h2 id="storage-title">儲存空間</h2>
    <p v-if="error" class="note">{{ error }}</p>
    <Skeleton v-else-if="!data" height="9rem" />
    <template v-else>
      <div class="usage">
        <div class="usage-line">
          <strong>已用 {{ bytes(data.used) }}</strong>
          <span v-if="data.limit">上限 {{ bytes(data.limit) }}（{{ percent }}%）</span>
          <span v-else>未設定上限</span>
        </div>
        <div v-if="data.limit" class="meter" role="meter" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100"
          aria-label="儲存空間使用率">
          <span :style="{ width: `${Math.min(100, percent)}%` }" :class="tone" />
        </div>
        <p v-if="data.level === 'full'" class="level danger" role="status">已達上限，新的上傳會被拒絕。</p>
        <p v-else-if="data.level === 'warning'" class="level danger" role="status">已用超過 90%，接近上限。</p>
        <p v-else-if="data.level === 'notice'" class="level warn" role="status">已用超過 80%。</p>
      </div>

      <table class="parts">
        <caption class="sr-only">各類檔案的用量</caption>
        <tbody>
          <tr v-for="part in parts" :key="part.key">
            <th scope="row">{{ part.label }}</th>
            <td class="bar" aria-hidden="true"><span :style="{ width: `${Math.max(part.size ? 2 : 0, Math.round(part.share * 100))}%` }" /></td>
            <td class="size">{{ bytes(part.size) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="note">上限計算資料庫、文件的所有版本、圖片、影片，以及回收桶中還沒永久刪除的文件；不含縮圖與備份。要釋出空間，可以清空回收桶，或刪除不需要的舊版本與影片。</p>

      <form class="limit" @submit.prevent="save(limitGb ?? null)">
        <label for="storage-limit">儲存空間上限</label>
        <div class="limit-row">
          <InputNumber v-model="limitGb" input-id="storage-limit" :min="1" :max="1000000" :use-grouping="false" :max-fraction-digits="1" suffix=" GB"
            placeholder="不限制" size="small" :disabled="saving" />
          <Button type="submit" label="儲存" size="small" :disabled="!dirty || saving" :loading="saving" />
          <Button v-if="savedGb != null" type="button" label="不限制" size="small" severity="secondary" text :disabled="saving" @click="save(null)" />
        </div>
        <p v-if="belowUsage" class="level warn" role="status">目前用量已超過這個上限，儲存後所有新的上傳都會被拒絕。</p>
        <p class="note">超過上限時拒絕上傳文件、新版本、圖片與影片；在編輯器儲存 Markdown 文字不受影響。最小 1 GB，留空表示不限制。</p>
      </form>

      <div v-if="data.disk" class="disk">
        <div class="disk-line">
          <span>磁碟</span>
          <span>剩餘 {{ bytes(data.disk.free_bytes) }} / 共 {{ bytes(data.disk.total_bytes) }}</span>
        </div>
        <div class="meter" role="meter" :aria-valuenow="Math.round(diskUsed * 100)" aria-valuemin="0" aria-valuemax="100" aria-label="磁碟使用率">
          <span :style="{ width: `${Math.round(diskUsed * 100)}%` }" :class="{ danger: diskUsed > .9 }" />
        </div>
        <p class="note">已使用 {{ Math.round(diskUsed * 100) }}%。不論有沒有設定上限，上傳後磁碟至少要剩 {{ bytes(data.min_free_bytes) }}。</p>
      </div>
    </template>
  </section>
</template>

<style scoped src="./systemPages.css"></style>
<style scoped>
.usage { display: grid; gap: var(--ui-space-2); }
.usage-line { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--ui-space-2); font-variant-numeric: tabular-nums; }
.usage-line span { color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.meter span.warn { background: var(--ui-lagging-text, #b54708); }
.meter span.danger { background: var(--ui-danger); }
.level { margin: 0; font-size: var(--ui-text-sm); font-weight: 600; }
.level.warn { color: var(--ui-lagging-text, #b54708); }
.level.danger { color: var(--ui-danger); }
.parts { width: 100%; border-collapse: collapse; font-size: var(--ui-text-sm); }
.parts th { padding: var(--ui-space-1) 0; color: var(--ui-text-secondary); font-weight: 400; text-align: left; white-space: nowrap; }
.parts td { padding: var(--ui-space-1) 0; }
.parts .bar { width: 40%; padding: 0 var(--ui-space-3); }
.parts .bar span { display: block; height: .375rem; border-radius: var(--ui-radius-pill); background: var(--ui-accent); opacity: .7; }
.parts .size { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.limit { display: grid; gap: var(--ui-space-2); padding-top: var(--ui-space-3); border-top: 1px solid var(--ui-border); }
.limit label { font-weight: 600; font-size: var(--ui-text-sm); }
.limit-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); }
.limit-row :deep(input) { width: 9rem; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
