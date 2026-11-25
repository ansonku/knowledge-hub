<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Skeleton from 'primevue/skeleton'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { api, ApiError } from '../../api'
import { useSession } from '../../stores/session'
import { activityDetail, activityVerb, type ActivityItem } from '../activity'
import UiIcon, { type IconName } from '../components/UiIcon.vue'
import { longDateTime, shortDate } from '../types'
import { auditLabel, roleLabels, type MemberListing, type MemberRow } from './members'
import { maintenanceSummary, type MaintenanceResults } from './maintenance'
import { gallerySummary } from './gallerySettings'
import { useSite } from '../../stores/site'

const site = useSite()
type Category = 'account' | 'signin' | 'document' | 'publish' | 'trash' | 'deletion'
type Person = { id: string; name: string } | null
type AuditRow = {
  id: string
  category: Category
  action: string
  created_at: string
  actor: Person
  member: Person
  document: { id: string; title: string; deleted: boolean } | null
  version_number: number | null
  detail: Record<string, unknown>
}
type AuditPage = { page: number; has_more: boolean; results: AuditRow[] }

const route = useRoute()
const router = useRouter()
const session = useSession()

const categories: { value: Category; label: string; icon: IconName }[] = [
  { value: 'account', label: '帳號管理', icon: 'users' },
  { value: 'signin', label: '登入', icon: 'logout' },
  { value: 'document', label: '文件', icon: 'files' },
  { value: 'publish', label: '發布', icon: 'globe' },
  { value: 'trash', label: '回收桶', icon: 'trash' },
  { value: 'deletion', label: '永久刪除', icon: 'alert' },
]
const iconOf = (category: Category) => categories.find(item => item.value === category)?.icon ?? 'history'
const labelOf = (category: Category) => categories.find(item => item.value === category)?.label ?? category

// ---- Filters (kept in the URL) ---------------------------------------------------------------------
const queryText = (key: string) => typeof route.query[key] === 'string' ? route.query[key] as string : ''
const category = computed(() => queryText('category') as Category | '')
const actor = computed(() => queryText('actor'))
const member = computed(() => queryText('member'))
const from = computed(() => queryText('from'))
const to = computed(() => queryText('to'))
/** Sign-ins flood the unfiltered view, so they are opt-in there (`?signins=1`). */
const signins = computed(() => queryText('signins') === '1')
function setQuery(patch: Record<string, string | undefined>) {
  const query: LocationQueryRaw = { ...route.query, ...patch }
  for (const key of Object.keys(query)) if (!query[key]) delete query[key]
  void router.replace({ query })
}
const hasFilters = computed(() => Boolean(category.value || actor.value || member.value || from.value || to.value || signins.value))

/** Local calendar days → ISO instants: [from 00:00, the day after `to` 00:00). */
function dayStart(value: string, plusDays = 0) {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day + plusDays).toISOString()
}

// ---- Members for the actor filter and labels --------------------------------------------------------------
const members = ref<MemberRow[]>([])
async function loadMembers() {
  const all: MemberRow[] = []
  for (let page = 1; page <= 20; page++) {
    const data = await api<MemberListing>(`/api/users/?page=${page}`)
    all.push(...data.results)
    if (page >= data.page_count) break
  }
  members.value = all
}
const memberOptions = computed(() => members.value.map(item => ({ id: item.id, name: `${item.display_name || item.username}（${item.username}）` })))
const memberName = computed(() => {
  const found = members.value.find(item => item.id === member.value)
  return found ? found.display_name || found.username : '指定成員'
})

// ---- Feed ----------------------------------------------------------------------------------------------------
const rows = ref<AuditRow[]>([])
const page = ref(1)
const hasMore = ref(false)
const loading = ref(true)
const error = ref('')
let request = 0
async function load(reset = true) {
  const current = ++request
  loading.value = true
  error.value = ''
  if (reset) page.value = 1
  const params = new URLSearchParams({ page: String(page.value) })
  if (category.value) params.set('category', category.value)
  if (actor.value) params.set('actor', actor.value)
  if (member.value) params.set('member', member.value)
  if (from.value) params.set('since', dayStart(from.value))
  if (to.value) params.set('until', dayStart(to.value, 1))
  if (!signins.value) params.set('signins', 'false')
  try {
    const data = await api<AuditPage>(`/api/admin/audit/?${params}`)
    if (current !== request) return
    rows.value = reset ? data.results : [...rows.value, ...data.results]
    hasMore.value = data.has_more
  } catch (cause) {
    if (current !== request) return
    error.value = cause instanceof ApiError && cause.status === 403 ? '只有 Admin 可以查看稽核紀錄。'
      : cause instanceof ApiError && cause.status === 400 ? '篩選條件不正確，請清除後再試。' : '無法載入稽核紀錄。'
  } finally {
    if (current === request) loading.value = false
  }
}
function more() {
  page.value++
  void load(false)
}
watch([category, actor, member, from, to, signins], () => { void load() })

// ---- Presentation ----------------------------------------------------------------------------------------------
function asActivity(row: AuditRow) {
  return { action: row.action, version_number: row.version_number, detail: row.detail } as unknown as ActivityItem
}
function verb(row: AuditRow) {
  if (row.category === 'deletion' && row.action !== 'version_deleted') return '永久刪除了文件'
  if (row.category === 'account' || row.category === 'signin') return auditLabel(row.action)
  return activityVerb(asActivity(row))
}
function detailLine(row: AuditRow) {
  const detail = row.detail
  if (row.category === 'deletion' && row.action !== 'version_deleted') return `共 ${detail.version_count ?? '?'} 個版本`
  if (row.category === 'account' || row.category === 'signin') {
    if (detail.maintenance) return maintenanceSummary(detail.maintenance as MaintenanceResults)
    if (detail.gallery) return gallerySummary(detail.gallery as Record<string, { from: unknown; to: unknown }>)
    const parts: string[] = []
    if (detail.old_role && detail.role) parts.push(`${roleLabels[detail.old_role as 'viewer'] ?? detail.old_role} → ${roleLabels[detail.role as 'viewer'] ?? detail.role}`)
    else if (detail.role) parts.push(`角色 ${roleLabels[detail.role as 'viewer'] ?? detail.role}`)
    if (detail.reason) parts.push(`理由：${detail.reason}`)
    if (detail.identity_verified) parts.push('已核對身分')
    return parts.join('；')
  }
  return activityDetail(asActivity(row))
}
/** Account events about the actor themself (login, profile changes) need no separate target. */
const selfEvent = (row: AuditRow) => row.member && row.actor && row.member.id === row.actor.id

onMounted(async () => {
  site.setTitle('稽核紀錄')
  if (!session.isAdmin) {
    loading.value = false
    error.value = '只有 Admin 可以查看稽核紀錄。'
    return
  }
  void loadMembers().catch(() => { /* the feed still works without the actor list */ })
  await load()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <p class="eyebrow">管理</p>
      <h1>稽核紀錄</h1>
      <p class="subtitle" aria-live="polite">
        {{ loading && !rows.length ? '正在載入…' : `已顯示 ${rows.length} 筆${hasMore ? '，還有更早的紀錄' : ''}` }} ·
        依時間由新到舊排列，登入與登出預設不顯示。紀錄只能查看，無法修改或刪除。
      </p>
    </header>

    <Message v-if="!session.isAdmin" severity="error">只有 Admin 可以查看稽核紀錄。</Message>
    <template v-else>
      <div class="toolbar" role="search">
        <Select :model-value="category || null" :options="categories" option-label="label" option-value="value" show-clear
          placeholder="所有類型" aria-label="依類型篩選" class="facet" @update:model-value="value => setQuery({ category: value ?? '' })" />
        <Select :model-value="actor || null" :options="memberOptions" option-label="name" option-value="id" show-clear filter
          placeholder="所有操作者" aria-label="依操作者篩選" class="facet wide" @update:model-value="value => setQuery({ actor: value ?? '' })" />
        <label class="date">
          <span class="ui-visually-hidden">起始日期</span>
          <input type="date" :value="from" :max="to || undefined" aria-label="起始日期"
            @change="setQuery({ from: ($event.target as HTMLInputElement).value })">
        </label>
        <span class="dash" aria-hidden="true">–</span>
        <label class="date">
          <span class="ui-visually-hidden">結束日期</span>
          <input type="date" :value="to" :min="from || undefined" aria-label="結束日期"
            @change="setQuery({ to: ($event.target as HTMLInputElement).value })">
        </label>
        <label v-if="!category" class="toggle">
          <input type="checkbox" :checked="signins" @change="setQuery({ signins: ($event.target as HTMLInputElement).checked ? '1' : '' })">
          <span>包含登入與登出</span>
        </label>
        <Button v-if="hasFilters" label="清除篩選" text severity="secondary"
          @click="setQuery({ category: '', actor: '', member: '', from: '', to: '', signins: '' })" />
      </div>
      <p v-if="member" class="member-filter">
        只顯示與 <strong>{{ memberName }}</strong> 帳號有關的紀錄
        <button type="button" class="link" @click="setQuery({ member: '' })">顯示全部</button>
      </p>

      <Message v-if="error" severity="error">{{ error }} <Button label="重試" text size="small" @click="load()" /></Message>
      <div v-else class="table-wrap" role="region" aria-label="稽核紀錄" tabindex="0">
        <table class="table" :aria-busy="loading">
          <thead>
            <tr>
              <th scope="col" class="col-time">時間</th>
              <th scope="col" class="col-kind">類型</th>
              <th scope="col" class="col-actor">操作者</th>
              <th scope="col">內容</th>
              <th scope="col" class="col-detail">細節</th>
            </tr>
          </thead>
          <tbody v-if="loading && !rows.length">
            <tr v-for="index in 8" :key="index"><td colspan="5"><Skeleton width="70%" /></td></tr>
          </tbody>
          <tbody v-else :class="{ stale: loading }">
            <tr v-for="row in rows" :key="row.id" class="event" :class="row.category">
              <td class="cell-time">
                <time :datetime="row.created_at" :title="longDateTime(row.created_at)">{{ shortDate(row.created_at) }}</time>
              </td>
              <td class="cell-kind">
                <span class="kind" :class="row.category"><UiIcon :name="iconOf(row.category)" :size="13" />{{ labelOf(row.category) }}</span>
              </td>
              <td class="cell-actor">
                <RouterLink v-if="row.actor" :to="{ name: 'app-member', params: { id: row.actor.id } }" class="who">{{ row.actor.name }}</RouterLink>
                <span v-else class="who system">系統</span>
              </td>
              <td class="cell-what">
                {{ verb(row) }}
                <RouterLink v-if="row.member && !selfEvent(row)" :to="{ name: 'app-member', params: { id: row.member.id } }" class="target">{{ row.member.name }}</RouterLink>
                <template v-if="row.document">
                  <RouterLink v-if="!row.document.deleted" :to="{ name: 'app-document', params: { id: row.document.id } }" class="target">{{ row.document.title }}</RouterLink>
                  <span v-else class="target gone">{{ row.document.title }}</span>
                </template>
              </td>
              <td class="cell-detail" :class="{ none: !detailLine(row) }">{{ detailLine(row) || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!loading && !rows.length" class="empty">
          <UiIcon name="history" :size="28" />
          <p>{{ hasFilters ? '沒有符合條件的紀錄。' : '還沒有任何紀錄。' }}</p>
        </div>
      </div>
      <Button v-if="hasMore && !error" label="載入更早的紀錄" outlined :loading="loading" class="more" @click="more" />
    </template>
  </div>
</template>

<style scoped>
/* Same frame as the other list pages (members, library, trash): left aligned, up to 100rem. */
.page { box-sizing: border-box; max-width: 100rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-4); }
.eyebrow { margin: 0 0 var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); }
.facet { min-width: 9.5rem; min-height: 2.5rem; align-items: center; }
.facet.wide { min-width: 14rem; }
.date input {
  box-sizing: border-box; min-height: 2.5rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text); font: inherit; color-scheme: inherit;
}
.date input:focus-visible { border-color: var(--ui-accent); box-shadow: var(--ui-focus-ring); outline: none; }
.dash { color: var(--ui-text-muted); }
.toggle { display: inline-flex; align-items: center; gap: var(--ui-space-2); margin-left: var(--ui-space-2); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); cursor: pointer; }
.toggle input { width: 1rem; height: 1rem; margin: 0; accent-color: var(--ui-accent); }
.member-filter { margin: 0; padding: var(--ui-space-2) var(--ui-space-3); border-radius: var(--ui-radius-md); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-size: var(--ui-text-sm); }
.link { margin-left: var(--ui-space-2); padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; cursor: pointer; }

.table-wrap { position: relative; overflow-x: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.table { width: 100%; border-collapse: collapse; }
.table th { padding: .625rem var(--ui-space-3); background: var(--ui-bg-subtle); border-bottom: 1px solid var(--ui-border); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; text-align: left; white-space: nowrap; }
.table th:first-child, .table td:first-child { padding-left: var(--ui-space-4); }
.table td { padding: var(--ui-space-3); border-bottom: 1px solid var(--ui-border-subtle); color: var(--ui-text-secondary); vertical-align: top; line-height: 1.55; }
.table tbody tr:last-child td { border-bottom: 0; }
.table tbody tr:hover td { background: var(--ui-bg-subtle); }
.stale { opacity: .6; }
.col-time { width: 8rem; } .col-kind { width: 7.5rem; } .col-actor { width: 10rem; } .col-detail { width: 30%; }
.cell-time { white-space: nowrap; color: var(--ui-text-muted); }
.kind { display: inline-flex; align-items: center; gap: .3rem; padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-bg-muted); color: var(--ui-text-secondary); font-size: var(--ui-text-xs); font-weight: 600; white-space: nowrap; }
.kind.account { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.kind.publish { background: var(--ui-public-bg); color: var(--ui-public-text); }
.kind.trash { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.kind.deletion { background: var(--ui-danger-bg); color: var(--ui-danger); }
.who { color: var(--ui-text); font-weight: 600; text-decoration: none; overflow-wrap: anywhere; }
a.who:hover, a.target:hover { color: var(--ui-accent); text-decoration: underline; }
.who.system { color: var(--ui-text-muted); font-weight: 400; }
.cell-what { overflow-wrap: anywhere; }
.target { margin-left: .25rem; color: var(--ui-accent); font-weight: 600; text-decoration: none; }
.target.gone { color: var(--ui-text); text-decoration: line-through; text-decoration-color: var(--ui-text-muted); }
.cell-detail { color: var(--ui-text-muted); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.empty { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-7) var(--ui-space-4); color: var(--ui-text-muted); }
.empty p { margin: 0; }
.more { justify-self: center; }

/* Below tablet width each row becomes a card, like the other list pages. */
@media (max-width: 860px) {
  .table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .table, .table tbody { display: block; }
  .table tbody tr {
    display: grid; grid-template-columns: auto 1fr auto; grid-template-areas: "kind actor time" "what what what" "detail detail detail";
    gap: var(--ui-space-1) var(--ui-space-2); align-items: center; padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle);
  }
  .table tbody tr:last-child { border-bottom: 0; }
  .table td, .table td:first-child { padding: 0; border: 0; }
  .table tbody tr:hover td { background: transparent; }
  .cell-kind { grid-area: kind; }
  .cell-actor { grid-area: actor; min-width: 0; }
  .cell-time { grid-area: time; font-size: var(--ui-text-sm); }
  .cell-what { grid-area: what; }
  .cell-detail { grid-area: detail; }
  .cell-detail.none { display: none; }
  .facet, .facet.wide { flex: 1 1 10rem; min-width: 0; }
  .toggle { margin-left: 0; }
}
</style>
