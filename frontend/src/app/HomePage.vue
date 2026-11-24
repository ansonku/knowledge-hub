<script setup lang="ts">
import Button from 'primevue/button'
import Skeleton from 'primevue/skeleton'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { useSession } from '../stores/session'
import { useTaxonomy } from '../stores/taxonomy'
import { useWorkspace } from '../stores/workspace'
import { activityDetail, activityVerb, initialOf, type ActivityItem, type ActivityPage } from './activity'
import UiIcon from './components/UiIcon.vue'
import { longDateTime, shortDate, type DocumentRow } from './types'

const emit = defineEmits<{ upload: [] }>()
const session = useSession()
const taxonomy = useTaxonomy()
const workspace = useWorkspace()

const today = new Intl.DateTimeFormat('zh-TW', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
const greeting = computed(() => {
  const hour = new Date().getHours()
  const name = session.account?.display_name || session.account?.username || ''
  const part = hour < 5 ? '晚安' : hour < 11 ? '早安' : hour < 18 ? '午安' : '晚安'
  return `${part}，${name}`
})

// ---- Continue reading ------------------------------------------------------
const recent = ref<DocumentRow[]>([])
const recentLoading = ref(true)

// ---- Team activity -----------------------------------------------------------
type Scope = 'all' | 'mine' | 'publish'
const scopes: { value: Scope; label: string }[] = [{ value: 'all', label: '全部' }, { value: 'mine', label: '我的' }, { value: 'publish', label: '發布' }]
const scope = ref<Scope>('all')
const activity = ref<ActivityItem[]>([])
const activityPage = ref(1)
const hasMore = ref(false)
const activityLoading = ref(true)
const activityError = ref('')
let activityRequest = 0

async function loadActivity(reset = true) {
  const current = ++activityRequest
  activityLoading.value = true
  activityError.value = ''
  if (reset) activityPage.value = 1
  try {
    const data = await api<ActivityPage>(`/api/activity/?scope=${scope.value}&page=${activityPage.value}`)
    if (current !== activityRequest) return
    activity.value = reset ? data.results : [...activity.value, ...data.results]
    hasMore.value = data.has_more
  } catch (cause) {
    if (current === activityRequest) activityError.value = cause instanceof Error ? cause.message : '無法載入活動。'
  } finally {
    if (current === activityRequest) activityLoading.value = false
  }
}
watch(scope, () => loadActivity())

const roots = computed(() => taxonomy.tree.filter(node => node.depth === 0))
const markOf = (name: string) => Array.from(name)[0]?.toUpperCase() ?? '?'

onMounted(async () => {
  document.title = 'Knowledge Hub'
  void workspace.refresh()
  void loadActivity()
  try {
    recent.value = (await api<{ results: DocumentRow[] }>('/api/me/recent/?limit=4')).results
  } catch {
    recent.value = []
  } finally {
    recentLoading.value = false
  }
})
</script>

<template>
  <div class="home">
    <header class="head">
      <div>
        <p class="date">{{ today }}</p>
        <h1>{{ greeting }}</h1>
      </div>
      <Button v-if="session.canEdit" class="upload" @click="emit('upload')">
        <UiIcon name="upload" :size="16" /><span>上傳文件</span>
      </Button>
    </header>

    <section aria-labelledby="continue-heading" class="section">
      <div class="section-head">
        <h2 id="continue-heading">繼續閱讀</h2>
        <RouterLink v-if="recent.length" :to="{ name: 'app-recent' }" class="more">全部最近閱讀</RouterLink>
      </div>
      <div v-if="recentLoading" class="cards">
        <Skeleton v-for="index in 4" :key="index" height="7.5rem" border-radius="12px" />
      </div>
      <div v-else-if="recent.length" class="cards">
        <RouterLink v-for="doc in recent" :key="doc.id" :to="{ name: 'app-document', params: { id: doc.id } }" class="card">
          <span class="card-top">
            <span class="format" :class="doc.format">{{ doc.format === 'html' ? 'HTML' : 'MD' }}</span>
            <UiIcon v-if="doc.is_favorite" name="star" filled :size="15" class="star" />
          </span>
          <span class="card-title">{{ doc.title }}</span>
          <span class="card-meta">{{ taxonomy.pathLabel(doc.category) }}</span>
        </RouterLink>
      </div>
      <div v-else class="placeholder">
        <UiIcon name="clock" :size="20" />
        <span>你開啟過的文件會出現在這裡。</span>
        <RouterLink :to="{ name: 'app-library' }">瀏覽全部文件</RouterLink>
      </div>
    </section>

    <div class="columns">
      <section aria-labelledby="feed-heading" class="panel feed">
        <div class="panel-head">
          <h2 id="feed-heading">團隊最近更新</h2>
          <div class="segments" role="group" aria-label="篩選更新">
            <button v-for="item in scopes" :key="item.value" type="button" class="segment" :class="{ on: scope === item.value }"
              :aria-pressed="scope === item.value" @click="scope = item.value">{{ item.label }}</button>
          </div>
        </div>
        <p v-if="activityError" class="feed-error">{{ activityError }} <button type="button" class="link" @click="loadActivity()">重試</button></p>
        <ol v-else class="events" :aria-busy="activityLoading">
          <li v-for="item in activity" :key="item.id" class="event">
            <span class="avatar" aria-hidden="true">{{ initialOf(item.actor) }}</span>
            <div class="event-body">
              <p class="event-line">
                <strong>{{ item.actor ?? '系統' }}</strong>
                {{ activityVerb(item) }}
                <RouterLink :to="{ name: 'app-document', params: { id: item.document.id } }">{{ item.document.title }}</RouterLink>
              </p>
              <p v-if="activityDetail(item)" class="event-detail">{{ activityDetail(item) }}</p>
            </div>
            <time class="event-time" :datetime="item.created_at" :title="longDateTime(item.created_at)">{{ shortDate(item.created_at) }}</time>
          </li>
          <template v-if="activityLoading && !activity.length">
            <li v-for="index in 5" :key="`s${index}`" class="event"><Skeleton width="100%" height="2.5rem" /></li>
          </template>
          <li v-if="!activityLoading && !activity.length" class="feed-empty">
            {{ scope === 'mine' ? '你最近還沒有更新文件。' : scope === 'publish' ? '還沒有發布紀錄。' : '還沒有任何活動。' }}
          </li>
        </ol>
        <div v-if="hasMore" class="feed-more">
          <Button label="載入更多" text size="small" :loading="activityLoading" @click="activityPage++; loadActivity(false)" />
        </div>
      </section>

      <div class="side">
        <section v-if="workspace.lagging || (session.canEdit && workspace.trash) || workspace.uncategorized" aria-labelledby="attention-heading" class="panel">
          <div class="panel-head"><h2 id="attention-heading">需要注意</h2></div>
          <div class="notices">
            <RouterLink v-if="workspace.lagging" :to="{ name: 'app-published', query: { visibility: 'lagging' } }" class="notice warn">
              <UiIcon name="alert" :size="18" />
              <span><strong>{{ workspace.lagging }} 篇公開文章落後內部版本</strong><small>訪客讀到的仍是舊版，可檢視後發布新版本。</small></span>
            </RouterLink>
            <RouterLink v-if="workspace.uncategorized" :to="{ name: 'app-collection', params: { id: 'uncategorized' } }" class="notice">
              <UiIcon name="folder" :size="18" />
              <span><strong>{{ workspace.uncategorized }} 份文件尚未分類</strong><small>放進集合後比較容易找到。</small></span>
            </RouterLink>
            <RouterLink v-if="session.canEdit && workspace.trash" :to="{ name: 'app-trash' }" class="notice">
              <UiIcon name="trash" :size="18" />
              <span><strong>回收桶有 {{ workspace.trash }} 份文件</strong><small>可以還原，或由 Admin 永久刪除。</small></span>
            </RouterLink>
          </div>
        </section>

        <section aria-labelledby="collections-heading" class="panel">
          <div class="panel-head"><h2 id="collections-heading">集合</h2></div>
          <div v-if="roots.length" class="collections">
            <RouterLink v-for="node in roots" :key="node.id" :to="{ name: 'app-collection', params: { id: node.id } }" class="collection">
              <span class="ui-col-mark col-mark" :class="`ui-col-${node.color || 'gray'}`" aria-hidden="true">{{ markOf(node.name) }}</span>
              <span class="col-text">
                <span class="col-name">{{ node.name }}</span>
                <span v-if="node.description" class="col-desc">{{ node.description }}</span>
              </span>
              <span class="col-count">{{ taxonomy.totalOf(node.id) }}</span>
            </RouterLink>
          </div>
          <p v-else class="muted-line">還沒有集合。<template v-if="session.canEdit">從側欄的「＋」建立第一個集合。</template></p>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Grows with wide screens (keeping ~5rem of margin each side) between 76rem and 90rem. */
.home { box-sizing: border-box; max-width: clamp(76rem, calc(100vw - var(--ui-sidebar-width) - 10rem), 90rem); margin-inline: auto; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-6); }
.head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--ui-space-4); }
.date { margin: 0 0 var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); font-weight: 700; letter-spacing: -.01em; }
h2 { margin: 0; font-size: .9375rem; font-weight: 600; }
.upload { gap: var(--ui-space-2); }
.section { display: grid; gap: var(--ui-space-3); }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-3); }
.more { color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; }
.more:hover { text-decoration: underline; }
/* At most four columns; auto-fit drops empty tracks so however many recent documents there are fill the row. */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(max(13rem, calc((100% - 3 * var(--ui-space-3)) / 4)), 1fr)); gap: var(--ui-space-3); }
.card {
  display: flex; flex-direction: column; gap: var(--ui-space-2); min-height: 7.5rem; padding: var(--ui-space-4);
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface);
  color: var(--ui-text); text-decoration: none; box-sizing: border-box; transition: border-color .15s, box-shadow .15s;
}
.card:hover { border-color: var(--ui-border-strong); box-shadow: var(--ui-shadow-sm); }
.card-top { display: flex; align-items: center; justify-content: space-between; }
.format { display: grid; place-items: center; min-width: 2.25rem; height: 1.75rem; padding: 0 .25rem; box-sizing: border-box; border-radius: var(--ui-radius-sm); font-size: .65625rem; font-weight: 700; }
.format.md { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); }
.format.html { background: var(--ui-format-html-bg); color: var(--ui-format-html-text); }
.star { color: #d99a00; }
.card-title { font-weight: 600; line-height: 1.4; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-meta { margin-top: auto; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.placeholder { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2) var(--ui-space-3); padding: var(--ui-space-5); border: 1px dashed var(--ui-border-strong); border-radius: var(--ui-radius-lg); color: var(--ui-text-muted); }
.placeholder a { color: var(--ui-accent); font-weight: 600; }

.columns { display: flex; flex-wrap: wrap; align-items: flex-start; gap: var(--ui-space-5); }
.feed { flex: 999 1 28rem; min-width: 0; }
.side { flex: 1 1 18rem; min-width: 0; display: grid; gap: var(--ui-space-4); }
.panel { border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); overflow: hidden; }
.panel-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-space-2); padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border); }
.segments { display: inline-flex; gap: 2px; padding: 3px; border-radius: var(--ui-radius-md); background: var(--ui-bg-muted); }
.segment { min-height: 1.75rem; padding: 0 .75rem; border: 0; border-radius: .375rem; background: transparent; color: var(--ui-text-muted); font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.segment.on { background: var(--ui-bg-surface); color: var(--ui-text); font-weight: 600; box-shadow: var(--ui-shadow-sm); }
.events { list-style: none; margin: 0; padding: 0; }
.event { display: flex; gap: var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
.event:last-child { border-bottom: 0; }
.avatar { flex: none; display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: 50%; background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); font-size: var(--ui-text-sm); font-weight: 600; }
.event-body { flex: 1; min-width: 0; display: grid; gap: var(--ui-space-1); }
.event-line { margin: 0; color: var(--ui-text-secondary); line-height: 1.5; overflow-wrap: anywhere; }
.event-line strong { color: var(--ui-text); font-weight: 600; }
.event-line a { color: var(--ui-accent); font-weight: 600; text-decoration: none; }
.event-line a:hover { text-decoration: underline; }
.event-detail { margin: 0; padding-left: var(--ui-space-3); border-left: 2px solid var(--ui-border); color: var(--ui-text-muted); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.event-time { flex: none; color: var(--ui-text-muted); font-size: var(--ui-text-xs); white-space: nowrap; }
.feed-empty, .feed-error { margin: 0; padding: var(--ui-space-6) var(--ui-space-4); color: var(--ui-text-muted); text-align: center; list-style: none; }
.feed-more { display: flex; justify-content: center; padding: var(--ui-space-2); border-top: 1px solid var(--ui-border-subtle); }
.link { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; cursor: pointer; }
.notices { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-3); }
.notice { display: flex; gap: var(--ui-space-3); padding: var(--ui-space-3); border-radius: var(--ui-radius-md); background: var(--ui-bg-subtle); color: var(--ui-text-secondary); text-decoration: none; }
.notice:hover { background: var(--ui-bg-muted); }
.notice span { display: grid; gap: 2px; }
.notice strong { color: var(--ui-text); font-weight: 600; }
.notice small { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.notice.warn { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.notice.warn strong, .notice.warn small { color: var(--ui-lagging-text); }
.collections { display: grid; padding: var(--ui-space-2); }
.collection { display: flex; align-items: center; gap: var(--ui-space-3); padding: var(--ui-space-2); border-radius: var(--ui-radius-md); color: var(--ui-text); text-decoration: none; }
.collection:hover { background: var(--ui-bg-subtle); }
.col-mark { width: 1.75rem; height: 1.75rem; font-size: var(--ui-text-sm); }
.col-text { flex: 1; min-width: 0; display: grid; }
.col-name { font-weight: 600; }
.col-desc { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; color: var(--ui-text-muted); font-size: var(--ui-text-xs); line-height: 1.45; }
.col-count { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.muted-line { margin: 0; padding: var(--ui-space-4); color: var(--ui-text-muted); }
/* On narrow screens show what needs attention before the long activity feed. */
@media (max-width: 900px) {
  .side { order: -1; }
}
/* On wide screens give the side column room for collection descriptions; the feed keeps a readable measure. */
@media (min-width: 1600px) {
  .side { flex-basis: 22rem; }
}
@media (max-width: 640px) {
  .upload { width: 100%; justify-content: center; }
  .event { flex-wrap: wrap; }
  .event-time { margin-left: 2.75rem; }
}
</style>
