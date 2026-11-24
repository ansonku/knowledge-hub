<script setup lang="ts">
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '../../api'
import UiIcon from '../components/UiIcon.vue'
import { colorClass, type PublicCollection } from '../../site/public'

type Row = {
  document_id: string; title: string; published_at: string; path: PublicCollection[]
  published_version: number; latest_version: number; published_version_id: string; latest_version_id: string
  behind: number; total: number; spark: number[]; featured: boolean
}
type Overview = {
  days: number; total: number; daily: { day: string; count: number }[]
  articles: Row[]; lagging: number; idle: number; featured: string[]; featured_max: number
}

const route = useRoute()
const router = useRouter()
const ranges = [7, 30] as const
const days = computed(() => (route.query.days === '7' ? 7 : 30))
const data = ref<Overview>()
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api<Overview>(`/api/admin/public-overview/?days=${days.value}`)
  } catch (cause) {
    error.value = cause instanceof ApiError && cause.status === 403 ? '只有 Admin 可以查看公開站總覽。' : '無法讀取公開站總覽。'
  } finally {
    loading.value = false
  }
}
watch(days, load, { immediate: true })

const pick = (value: number) => void router.replace({ query: value === 30 ? {} : { days: String(value) } })

const peak = computed(() => Math.max(1, ...(data.value?.daily.map(item => item.count) ?? [1])))
const dayLabel = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' })
const lagging = computed(() => data.value?.articles.filter(item => item.behind) ?? [])
const viewed = computed(() => data.value?.articles.filter(item => item.total).length ?? 0)
const pathLabel = (row: Row) => row.path.map(item => item.name).join(' › ')
const leaf = (row: Row) => row.path[row.path.length - 1]
const sparkPeak = (row: Row) => Math.max(1, ...row.spark)
const sparkTotal = (row: Row) => row.spark.reduce((sum, value) => sum + value, 0)

// ---- Featured on the public home (P6b): the whole ordered list is saved on every change ------------
const toast = useToast()
const featured = ref<string[]>([])
const featuredMax = computed(() => data.value?.featured_max ?? 4)
const saving = ref(false)
watch(data, value => { featured.value = value?.featured ?? [] })
const byId = computed(() => new Map((data.value?.articles ?? []).map(row => [row.document_id, row])))
const featuredRows = computed(() => featured.value.map(id => byId.value.get(id)).filter((row): row is Row => Boolean(row)))

async function saveFeatured(next: string[], message: string) {
  if (saving.value) return
  saving.value = true
  const previous = featured.value
  featured.value = next
  try {
    const result = await api<{ results: { document_id: string }[] }>('/api/admin/featured/', 'PUT', { documents: next })
    featured.value = result.results.map(item => item.document_id)
    toast.add({ severity: 'success', summary: message, life: 2500 })
  } catch (cause) {
    featured.value = previous
    toast.add({ severity: 'error', summary: '無法更新首頁精選', detail: cause instanceof Error ? cause.message : undefined, life: 5000 })
  } finally {
    saving.value = false
  }
}
function toggleFeatured(row: Row) {
  if (featured.value.includes(row.document_id)) {
    void saveFeatured(featured.value.filter(id => id !== row.document_id), `已從首頁精選移除「${row.title}」`)
  } else if (featured.value.length >= featuredMax.value) {
    toast.add({ severity: 'warn', summary: `首頁精選最多 ${featuredMax.value} 篇`, detail: '請先移除一篇再加入。', life: 4000 })
  } else {
    void saveFeatured([...featured.value, row.document_id], `已加入首頁精選「${row.title}」`)
  }
}
function moveFeatured(index: number, step: -1 | 1) {
  const next = [...featured.value]
  const target = index + step
  if (target < 0 || target >= next.length) return
  ;[next[index], next[target]] = [next[target], next[index]]
  void saveFeatured(next, '已更新精選順序')
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <p class="eyebrow">管理</p>
        <h1>公開站總覽</h1>
        <p class="subtitle">對外文章的瀏覽情況與待處理事項。瀏覽數只記次數，不記訪客身分；數字僅供參考。</p>
      </div>
      <div class="range" role="group" aria-label="統計期間">
        <button v-for="value in ranges" :key="value" type="button" :aria-pressed="days === value" :class="{ on: days === value }"
          @click="pick(value)">最近 {{ value }} 天</button>
      </div>
    </header>

    <Message v-if="error" severity="error">{{ error }}</Message>
    <div v-else-if="!data" class="kpis"><Skeleton v-for="index in 3" :key="index" height="6rem" border-radius="12px" /></div>

    <template v-else>
      <dl class="kpis" :aria-busy="loading">
        <div class="kpi">
          <dt>{{ data.days }} 天公開瀏覽<span class="kpi-note">只計公開站訪客</span></dt>
          <dd>{{ data.total.toLocaleString() }}</dd>
        </div>
        <div class="kpi">
          <dt>公開文章<span class="kpi-note">{{ viewed }} 篇有瀏覽</span></dt>
          <dd>{{ data.articles.length }}</dd>
        </div>
        <div class="kpi">
          <dt>首頁精選<span class="kpi-note">最多 {{ featuredMax }} 篇</span></dt>
          <dd>{{ featured.length }} / {{ featuredMax }}</dd>
        </div>
        <div class="kpi">
          <dt>落後最新版<span class="kpi-note" :class="{ warn: data.lagging }">{{ data.lagging ? '需要重新發布' : '全部都是最新版' }}</span></dt>
          <dd>{{ data.lagging }}</dd>
        </div>
      </dl>

      <div class="split">
        <section class="card trend" aria-labelledby="trend-title">
          <div class="card-head">
            <h2 id="trend-title">全站每日公開瀏覽</h2>
            <span class="muted">尖峰 {{ peak }} 次／日</span>
          </div>
          <div class="bars" role="img" :aria-label="`最近 ${data.days} 天共 ${data.total} 次公開瀏覽，單日最多 ${peak} 次`">
            <span v-for="(item, index) in data.daily" :key="item.day" class="bar"
              :class="{ empty: !item.count, today: index === data.daily.length - 1 }"
              :style="{ height: `${Math.max(2, (item.count / peak) * 100)}%` }" :title="`${dayLabel(item.day)}：${item.count} 次`" />
          </div>
          <div class="axis"><span>{{ dayLabel(data.daily[0].day) }}</span><span>今天</span></div>
        </section>

        <div class="side">
        <section class="card todo" aria-labelledby="todo-title">
          <h2 id="todo-title">待處理</h2>
          <div v-for="row in lagging" :key="row.document_id" class="lag">
            <span class="lag-title"><UiIcon name="alert" :size="16" />{{ row.title }}</span>
            <span class="lag-text">公開 v{{ row.published_version }}，最新 v{{ row.latest_version }}（落後 {{ row.behind }} 版）</span>
            <span class="lag-actions">
              <RouterLink :to="{ name: 'app-compare', params: { id: row.document_id }, query: { from: row.published_version_id, to: row.latest_version_id } }"
                class="lag-button">比較 v{{ row.published_version }} 與 v{{ row.latest_version }}</RouterLink>
              <RouterLink :to="{ name: 'app-document', params: { id: row.document_id }, query: { panel: 'publish' } }" class="lag-button">
                前往發布 v{{ row.latest_version }}</RouterLink>
            </span>
          </div>
          <p v-if="!lagging.length" class="ok"><UiIcon name="check" :size="16" />所有公開文章都是最新版本。</p>
          <p v-if="data.idle" class="idle">{{ data.idle }} 篇公開文章在這段期間沒有任何瀏覽。</p>
        </section>

        <section class="card picks" aria-labelledby="picks-title">
          <div class="card-head">
            <h2 id="picks-title">首頁精選</h2>
            <a href="/articles/" target="_blank" rel="noopener" class="muted-link">在公開首頁查看</a>
          </div>
          <ol v-if="featuredRows.length" class="pick-list" :aria-busy="saving">
            <li v-for="(row, index) in featuredRows" :key="row.document_id" class="pick">
              <span class="rank" aria-hidden="true">{{ index + 1 }}</span>
              <span class="pick-title">{{ row.title }}</span>
              <button type="button" class="icon-button" :aria-label="`上移「${row.title}」`" :disabled="saving || index === 0"
                @click="moveFeatured(index, -1)"><UiIcon name="chevronDown" :size="16" class="up" /></button>
              <button type="button" class="icon-button" :aria-label="`下移「${row.title}」`" :disabled="saving || index === featuredRows.length - 1"
                @click="moveFeatured(index, 1)"><UiIcon name="chevronDown" :size="16" /></button>
              <button type="button" class="icon-button" :aria-label="`從精選移除「${row.title}」`" :disabled="saving"
                @click="toggleFeatured(row)"><UiIcon name="close" :size="16" /></button>
            </li>
          </ol>
          <p v-else class="note">還沒有精選文章。在下方表格點星號加入，最多 {{ featuredMax }} 篇。</p>
          <p class="note">依順序顯示在公開首頁「熱門文章」之後；熱門排行會略過精選文章。文章下架或移入回收桶時會自動移出。</p>
        </section>
        </div>
      </div>

      <section class="card table-card" aria-labelledby="articles-title">
        <div class="card-head">
          <h2 id="articles-title">公開文章（{{ data.articles.length }}）</h2>
          <span class="muted">依最近 {{ data.days }} 天的瀏覽數排序</span>
        </div>
        <p v-if="!data.articles.length" class="empty-note">目前沒有公開文章。</p>
        <div v-else class="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col" class="star-col"><span class="ui-visually-hidden">首頁精選</span></th>
                <th scope="col">文章</th>
                <th scope="col">公開版本</th>
                <th scope="col" class="num">瀏覽</th>
                <th scope="col" class="spark-col">最近 15 天</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data.articles" :key="row.document_id">
                <td class="star-col">
                  <button type="button" class="star" :class="{ on: featured.includes(row.document_id) }" :disabled="saving"
                    :aria-pressed="featured.includes(row.document_id)"
                    :aria-label="featured.includes(row.document_id) ? `從首頁精選移除「${row.title}」` : `加入首頁精選「${row.title}」`"
                    @click="toggleFeatured(row)">
                    <UiIcon name="star" :size="18" :filled="featured.includes(row.document_id)" />
                  </button>
                </td>
                <td>
                  <RouterLink :to="{ name: 'app-document', params: { id: row.document_id } }" class="title">{{ row.title }}</RouterLink>
                  <span v-if="row.path.length" class="tag" :class="colorClass(leaf(row))">{{ pathLabel(row) }}</span>
                  <span v-else class="tag ui-col-gray">未分類</span>
                </td>
                <td class="version">
                  v{{ row.published_version }}
                  <span v-if="row.behind" class="behind">落後 {{ row.behind }} 版</span>
                </td>
                <td class="num">{{ row.total.toLocaleString() }}</td>
                <td class="spark-col">
                  <span class="spark" role="img" :aria-label="`最近 15 天共 ${sparkTotal(row)} 次`">
                    <span v-for="(value, index) in row.spark" :key="index" :style="{ height: `${Math.max(8, (value / sparkPeak(row)) * 100)}%` }"
                      :class="{ zero: !value }" />
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
/* Same frame as the other admin pages: left aligned, up to 100rem. */
.page { box-sizing: border-box; max-width: 100rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-4); }
.page-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--ui-space-4); }
.eyebrow { margin: 0 0 var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
h2 { margin: 0; font-size: 1rem; }
.muted { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }

.range { display: inline-flex; gap: 2px; padding: 3px; border-radius: var(--ui-radius-md); background: var(--ui-bg-muted); }
.range button { height: 2rem; padding: 0 var(--ui-space-3); border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: var(--ui-text-muted); font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.range button.on { background: var(--ui-bg-surface); color: var(--ui-text); font-weight: 600; box-shadow: var(--ui-shadow-sm); }

/* Four figures: one row, or 2 × 2 on narrow screens. */
.kpis { margin: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--ui-space-3); }
@media (max-width: 900px) { .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.kpi { display: flex; flex-direction: column-reverse; gap: var(--ui-space-1); padding: var(--ui-space-4) var(--ui-space-5); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.kpi dt { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.kpi dd { margin: 0; font-size: 1.75rem; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; }
.kpi-note { display: block; margin-top: 2px; font-size: var(--ui-text-xs); }
.kpi-note.warn { color: var(--ui-lagging-text); }

.split { display: grid; grid-template-columns: minmax(0, 2fr) minmax(min(100%, 20rem), 1fr); gap: var(--ui-space-4); align-items: start; }
@media (max-width: 960px) { .split { grid-template-columns: minmax(0, 1fr); } }
.card { display: grid; align-content: start; gap: var(--ui-space-3); padding: var(--ui-space-5); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); min-width: 0; }
.side { display: grid; gap: var(--ui-space-4); align-content: start; min-width: 0; }
.muted-link { color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; }
.muted-link:hover { text-decoration: underline; }
.pick-list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--ui-space-2); }
.pick { display: flex; align-items: center; gap: var(--ui-space-2); padding: var(--ui-space-2) var(--ui-space-2) var(--ui-space-2) var(--ui-space-3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
.rank { flex: none; display: grid; place-items: center; width: 1.625rem; height: 1.625rem; border-radius: 50%; background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-size: var(--ui-text-xs); font-weight: 700; }
.pick-title { flex: 1; min-width: 0; font-weight: 600; font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.icon-button { flex: none; display: grid; place-items: center; width: 2rem; height: 2rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-bg-surface); color: var(--ui-text-secondary); cursor: pointer; }
.icon-button:hover:not(:disabled) { border-color: var(--ui-border-strong); color: var(--ui-text); }
.icon-button:disabled { opacity: .4; cursor: default; }
.up { transform: rotate(180deg); }
.note { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); line-height: 1.6; }
.star-col { width: 2.5rem; padding-right: 0 !important; }
.star { display: grid; place-items: center; width: 2rem; height: 2rem; border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.star:hover:not(:disabled) { background: var(--ui-bg-subtle); color: var(--ui-text); }
.star.on { color: #d99a00; }
.card-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--ui-space-2); }

.bars { display: flex; align-items: flex-end; gap: 3px; height: 11rem; padding-bottom: 4px; border-bottom: 1px solid var(--ui-border); }
.bar { flex: 1; min-width: 2px; border-radius: 3px 3px 0 0; background: var(--ui-accent); opacity: .45; }
.bar.today { opacity: 1; }
.bar.empty { background: var(--ui-border); opacity: 1; }
.axis { display: flex; justify-content: space-between; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }

.lag { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-3); border-radius: var(--ui-radius-md); background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.lag-title { display: flex; align-items: center; gap: var(--ui-space-2); font-weight: 600; overflow-wrap: anywhere; }
.lag-text { font-size: var(--ui-text-sm); }
.lag-actions { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); }
.lag-button { display: inline-flex; align-items: center; min-height: 2rem; padding: 0 var(--ui-space-3); border: 1px solid currentColor; border-radius: var(--ui-radius-sm); background: var(--ui-bg-surface); color: var(--ui-lagging-text); font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; }
.lag-button:hover { background: var(--ui-bg-subtle); }
.ok { margin: 0; display: flex; align-items: center; gap: var(--ui-space-2); color: var(--ui-public-text); font-size: var(--ui-text-sm); }
.idle { margin: 0; padding: var(--ui-space-3); border-radius: var(--ui-radius-md); background: var(--ui-bg-subtle); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); line-height: 1.6; }

.table-card { padding: 0; gap: 0; overflow: hidden; }
.table-card .card-head { padding: var(--ui-space-4) var(--ui-space-5); border-bottom: 1px solid var(--ui-border); }
.empty-note { margin: 0; padding: var(--ui-space-5); color: var(--ui-text-muted); }
.scroll { overflow-x: auto; }
table { width: 100%; min-width: 40rem; border-collapse: collapse; font-size: var(--ui-text-sm); }
th { padding: var(--ui-space-2) var(--ui-space-4); background: var(--ui-bg-subtle); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; text-align: left; }
td { padding: var(--ui-space-3) var(--ui-space-4); border-top: 1px solid var(--ui-border-subtle); vertical-align: middle; }
th:first-child, td:first-child { padding-left: var(--ui-space-5); }
th:last-child, td:last-child { padding-right: var(--ui-space-5); }
.title { display: block; color: var(--ui-text); font-weight: 600; text-decoration: none; overflow-wrap: anywhere; }
.title:hover { color: var(--ui-accent); }
.tag { display: inline-block; margin-top: var(--ui-space-1); padding: 1px var(--ui-space-2); border-radius: var(--ui-radius-sm); font-size: var(--ui-text-xs); font-weight: 600; }
.version { white-space: nowrap; font-variant-numeric: tabular-nums; }
.behind { margin-left: var(--ui-space-2); padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-pill); background: var(--ui-lagging-bg); color: var(--ui-lagging-text); font-size: var(--ui-text-xs); font-weight: 600; }
.num { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
.spark-col { width: 9rem; }
.spark { display: flex; align-items: flex-end; gap: 1px; height: 1.5rem; }
.spark span { flex: 1; border-radius: 1px; background: var(--ui-accent); opacity: .5; }
.spark span.zero { background: var(--ui-border); opacity: 1; }
/* Phones: drop the sparkline so title, version and views fit without scrolling. */
@media (max-width: 640px) {
  table { min-width: 0; }
  .spark-col { display: none; }
  .kpi { padding: var(--ui-space-3); }
  .kpi dd { font-size: 1.375rem; }
}
</style>
