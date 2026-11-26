<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import Select from 'primevue/select'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../../api'
import type { DocumentDetails, PublicationStatus } from '../composables/useDocument'

const props = defineProps<{ document: DocumentDetails; status?: PublicationStatus; error?: string }>()
const emit = defineEmits<{ changed: [status: PublicationStatus | undefined] }>()

const confirm = useConfirm()
const toast = useToast()
const router = useRouter()
const version = ref<string>()
const busy = ref(false)
const actionError = ref('')

const endpoint = computed(() => `/api/documents/${encodeURIComponent(props.document.id)}/publication/`)
const published = computed(() => props.status?.publication)
const latest = computed(() => props.status?.versions[0])
const behind = computed(() => published.value && latest.value ? latest.value.number - published.value.version__number : 0)
const publishedVersion = computed(() => props.status?.versions.find(item => item.number === published.value?.version__number))
const chosen = computed(() => props.status?.versions.find(item => item.id === version.value))
const options = computed(() => (props.status?.versions ?? []).map(item => ({
  id: item.id,
  label: `v${item.number}${item.number === latest.value?.number ? '（最新）' : ''}${item.number === published.value?.version__number ? '（目前公開）' : ''}`,
})))
const publicUrl = computed(() => `${window.location.origin}/articles/${props.document.id}/`)

// ---- Public views over the last 30 days (counts only; see documents/popularity.py) ----------------
type Trend = { days: number; total: number; daily: { day: string; count: number }[] }
const trend = ref<Trend>()
const peak = computed(() => Math.max(1, ...(trend.value?.daily.map(item => item.count) ?? [1])))
async function loadTrend() {
  if (!published.value) { trend.value = undefined; return }
  try {
    trend.value = await api<Trend>(`/api/documents/${encodeURIComponent(props.document.id)}/public-views/`)
  } catch {
    trend.value = undefined
  }
}
watch(() => [props.document.id, published.value?.version__number], loadTrend, { immediate: true })
const dayLabel = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' })

watch(() => props.status, status => { version.value = status?.versions[0]?.id }, { immediate: true })

function publish() {
  const target = chosen.value
  if (!target || !props.status) return
  confirm.require({
    header: `發布 v${target.number}`,
    message: `訪客會在公開網址讀到「${props.status.title}」v${target.number}。之後的內部更新不會自動公開。`,
    acceptProps: { label: `發布 v${target.number}` },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      busy.value = true
      actionError.value = ''
      try {
        const next = await api<PublicationStatus>(endpoint.value, 'POST', { version: target.id, title: props.status?.title })
        emit('changed', next)
        toast.add({ severity: 'success', summary: `已發布 v${target.number}`, life: 3000 })
      } catch (cause) {
        actionError.value = cause instanceof Error ? cause.message : '無法發布。'
      } finally {
        busy.value = false
      }
    },
  })
}

function withdraw() {
  confirm.require({
    header: '下架公開文章',
    message: '公開網址會立即失效，訪客將無法再讀到這篇文章。',
    acceptProps: { label: '下架', severity: 'danger' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: async () => {
      busy.value = true
      actionError.value = ''
      try {
        await api(endpoint.value, 'DELETE')
        if (props.status) emit('changed', { ...props.status, publication: null })
        toast.add({ severity: 'success', summary: '已下架', life: 3000 })
      } catch (cause) {
        actionError.value = cause instanceof Error ? cause.message : '無法下架。'
      } finally {
        busy.value = false
      }
    },
  })
}

async function copyUrl() {
  try {
    await navigator.clipboard.writeText(publicUrl.value)
    toast.add({ severity: 'success', summary: '已複製公開網址', life: 2000 })
  } catch {
    toast.add({ severity: 'warn', summary: '無法存取剪貼簿', detail: publicUrl.value, life: 6000 })
  }
}

function comparePublished() {
  if (!publishedVersion.value || !latest.value) return
  void router.push({ name: 'app-compare', params: { id: props.document.id }, query: { from: publishedVersion.value.id, to: latest.value.id } })
}
</script>

<template>
  <div class="publish">
    <Message v-if="error" severity="error" size="small">{{ error }}</Message>
    <p v-else-if="!status" class="muted" role="status">正在讀取發布狀態…</p>
    <template v-else>
      <div v-if="published && behind > 0" class="card lagging">
        <strong>公開版本落後 {{ behind }} 版</strong>
        <span>訪客目前讀到 v{{ published.version__number }}，v{{ published.version__number + 1 }} 之後的更新只在成員文件庫內可見。</span>
      </div>
      <div v-else-if="published" class="card public">
        <strong>公開中 · 已是最新版本</strong>
        <span>訪客讀到的是 v{{ published.version__number }}。</span>
      </div>
      <div v-else class="card private">
        <strong>私人</strong>
        <span>只有登入的成員可以閱讀。發布後訪客可從公開站搜尋與閱讀。</span>
      </div>

      <dl v-if="published" class="fields">
        <dt>公開標題</dt><dd>{{ published.title }}</dd>
        <dt>公開版本</dt><dd>v{{ published.version__number }}</dd>
        <dt>公開網址</dt>
        <dd class="url">
          <RouterLink :to="{ name: 'public-article', params: { id: document.id } }" target="_blank" rel="noopener">開啟公開頁</RouterLink>
          <button type="button" class="link" @click="copyUrl">複製網址</button>
        </dd>
      </dl>

      <section v-if="published && trend" class="views" aria-labelledby="views-title">
        <div class="views-head">
          <span id="views-title" class="views-title">公開瀏覽</span>
          <span class="views-total">最近 {{ trend.days }} 天 <strong>{{ trend.total }}</strong> 次</span>
        </div>
        <div class="bars" role="img" :aria-label="`最近 ${trend.days} 天共 ${trend.total} 次公開瀏覽`">
          <span v-for="item in trend.daily" :key="item.day" class="bar" :style="{ height: `${Math.max(2, (item.count / peak) * 100)}%` }"
            :class="{ empty: !item.count }" :title="`${dayLabel(item.day)}：${item.count} 次`" />
        </div>
        <p class="views-note">同一個瀏覽器一天只算一次，不記錄訪客身分；數字僅供參考。</p>
      </section>

      <div class="field">
        <label for="publish-version">要發布的版本</label>
        <Select input-id="publish-version" v-model="version" :options="options" option-label="label" option-value="id"
          :disabled="busy" fluid size="small" />
        <RouterLink v-if="version" :to="{ name: 'app-document', params: { id: document.id }, query: version === latest?.id ? {} : { version } }"
          class="review">先檢視這個版本</RouterLink>
      </div>
      <Message v-if="actionError" severity="error" size="small">{{ actionError }}</Message>
      <div class="buttons">
        <Button v-if="published && behind > 0" label="比較公開版與最新版" outlined size="small" :disabled="busy" @click="comparePublished" />
        <Button :label="chosen ? `發布 v${chosen.number}…` : '發布…'" size="small" :loading="busy"
          :disabled="!chosen || chosen.number === published?.version__number" @click="publish" />
      </div>
      <div v-if="published" class="danger">
        <span>下架後公開網址立即失效</span>
        <Button label="下架…" severity="danger" outlined size="small" :disabled="busy" @click="withdraw" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.publish { display: grid; gap: var(--ui-space-4); padding: var(--ui-space-4) var(--ui-space-4) var(--ui-space-6); }
.muted { margin: 0; color: var(--ui-text-muted); }
.card { display: grid; gap: var(--ui-space-1); padding: var(--ui-space-3) var(--ui-space-4); border-radius: var(--ui-radius-md); line-height: 1.55; }
.card span { font-size: var(--ui-text-sm); }
.card.lagging { background: var(--ui-lagging-bg); border: 1px solid var(--ui-lagging-border); color: var(--ui-lagging-text); }
.card.public { background: var(--ui-public-bg); color: var(--ui-public-text); }
.card.private { background: var(--ui-private-bg); color: var(--ui-private-text); }
.fields { display: grid; grid-template-columns: 5rem minmax(0, 1fr); gap: var(--ui-space-2) var(--ui-space-3); margin: 0; }
dt { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
dd { margin: 0; overflow-wrap: anywhere; }
.url { display: flex; flex-wrap: wrap; gap: var(--ui-space-3); }
.url a, .review, .link { color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; }
.link { padding: 0; border: 0; background: none; font-family: inherit; cursor: pointer; }
.field { display: grid; gap: var(--ui-space-2); }
.field label { font-weight: 600; }
.buttons { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); }
.buttons > * { flex: 1 1 auto; }
.danger { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-3); padding-top: var(--ui-space-4); border-top: 1px solid var(--ui-border); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.views { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
.views-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--ui-space-2); }
.views-title { font-weight: 600; font-size: var(--ui-text-sm); }
.views-total { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.views-total strong { color: var(--ui-text); font-size: var(--ui-text-md); }
.bars { display: flex; align-items: flex-end; gap: 2px; height: 3rem; }
.bar { flex: 1; min-width: 2px; border-radius: 2px 2px 0 0; background: var(--ui-accent); opacity: .85; }
.bar.empty { background: var(--ui-border); opacity: 1; }
.views-note { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
</style>
