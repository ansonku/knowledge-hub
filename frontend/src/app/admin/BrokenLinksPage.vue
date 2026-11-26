<script setup lang="ts">
// P18b: links in current versions that no longer work, and media kept only by old versions (Editors and Admins).
import Button from 'primevue/button'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import { useSession } from '../../stores/session'
import { useSite } from '../../stores/site'
import UiIcon, { type IconName } from '../components/UiIcon.vue'

type Kind = 'document' | 'image' | 'video' | 'public'
type Issue = {
  kind: Kind; severity: 'broken' | 'warning'; reason: string; target: string; text: string; line: number | null
  owner?: { id: string; title: string }; published_version?: number
}
type Row = { id: string; title: string; category_name: string | null; version: number; issues: Issue[] }
type OldMedia = { kind: 'image' | 'video'; id: string; size: number; versions: number[]; document: { id: string; title: string } }
type Report = {
  summary: { checked: number; documents: number; broken: number; warnings: number }
  documents: Row[]
  storage: { old_versions: OldMedia[]; old_versions_bytes: number; unused: { images: number; videos: number; bytes: number } }
}

const session = useSession()
const site = useSite()
site.setTitle('失效連結')
const report = ref<Report>()
const loading = ref(true)
const error = ref('')
const checkedAt = ref<Date>()
const severity = ref<'all' | 'broken' | 'warning'>('all')
const kind = ref<'all' | Kind>('all')

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await api<Report>('/api/admin/broken-links/')
    checkedAt.value = new Date()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法檢查連結。'
  } finally {
    loading.value = false
  }
}
onMounted(() => { if (session.canEdit) void load() })

const KINDS: { value: 'all' | Kind; label: string }[] = [
  { value: 'all', label: '全部類型' }, { value: 'document', label: '文件連結' }, { value: 'image', label: '圖片' },
  { value: 'video', label: '影片' }, { value: 'public', label: '公開文章' },
]
const ICONS: Record<Kind, IconName> = { document: 'link', image: 'image', video: 'video', public: 'globe' }
const KIND_LABELS: Record<Kind, string> = { document: '文件連結', image: '圖片', video: '影片', public: '公開文章' }
const rows = computed(() => (report.value?.documents ?? []).map(row => ({
  ...row,
  issues: row.issues.filter(item => (severity.value === 'all' || item.severity === severity.value) && (kind.value === 'all' || item.kind === kind.value)),
})).filter(row => row.issues.length))
const filtered = computed(() => severity.value !== 'all' || kind.value !== 'all')

const size = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
const time = (date?: Date) => date?.toLocaleTimeString('zh-Hant', { hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>失效連結</h1>
      <p class="subtitle">檢查每份 Markdown 文件目前版本中，連到本站文件、圖片與影片的連結。外部網址與 HTML 文件不檢查，也不會自動修改任何內容。</p>
    </header>

    <Message v-if="!session.canEdit" severity="error">失效連結只開放給 Editor 與 Admin。</Message>
    <template v-else>
      <div v-if="loading && !report" class="skeleton"><Skeleton height="5rem" /><Skeleton height="12rem" /></div>
      <Message v-else-if="error" severity="error">{{ error }} <button type="button" class="link" @click="load">重試</button></Message>
      <template v-else-if="report">
        <section class="summary" aria-label="檢查結果">
          <div class="stat" :class="{ bad: report.summary.broken }"><strong>{{ report.summary.broken }}</strong><span>處失效</span></div>
          <div class="stat" :class="{ warn: report.summary.warnings }"><strong>{{ report.summary.warnings }}</strong><span>處提醒</span></div>
          <div class="stat"><strong>{{ report.summary.documents }}</strong><span>份文件有問題</span></div>
          <div class="stat muted"><strong>{{ report.summary.checked }}</strong><span>份文件已檢查</span></div>
          <div class="recheck">
            <span v-if="checkedAt" class="checked-at">{{ time(checkedAt) }} 檢查</span>
            <Button size="small" outlined :loading="loading" @click="load"><UiIcon name="refresh" :size="15" /><span>重新檢查</span></Button>
          </div>
        </section>

        <div class="filters" role="group" aria-label="篩選">
          <div class="segments" role="radiogroup" aria-label="嚴重程度">
            <button v-for="item in [{ value: 'all', label: '全部' }, { value: 'broken', label: '失效' }, { value: 'warning', label: '提醒' }] as const"
              :key="item.value" type="button" role="radio" class="segment" :aria-checked="severity === item.value"
              @click="severity = item.value">{{ item.label }}</button>
          </div>
          <select v-model="kind" class="kind" aria-label="類型">
            <option v-for="item in KINDS" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </div>

        <section v-if="rows.length" class="documents" aria-label="有問題的文件">
          <article v-for="row in rows" :key="row.id" class="doc">
            <header class="doc-head">
              <RouterLink :to="{ name: 'app-document', params: { id: row.id } }" class="doc-title">{{ row.title }}</RouterLink>
              <span class="doc-meta">{{ row.category_name ?? '未分類' }} · v{{ row.version }}</span>
            </header>
            <ul class="issues">
              <li v-for="(item, index) in row.issues" :key="index" class="issue" :class="item.severity">
                <span class="issue-icon" :title="KIND_LABELS[item.kind]"><UiIcon :name="ICONS[item.kind]" :size="16" /></span>
                <div class="issue-text">
                  <span class="badge" :class="item.severity">{{ item.severity === 'broken' ? '失效' : '提醒' }}</span>
                  <span class="reason">{{ item.reason }}</span>
                  <code class="link-text">{{ item.text }}</code>
                  <span class="where">
                    <template v-if="item.line">第 {{ item.line }} 行</template>
                    <template v-else-if="item.published_version">公開版本 v{{ item.published_version }}（與目前版本不同）</template>
                    <RouterLink v-if="item.owner" :to="{ name: 'app-document', params: { id: item.owner.id } }" class="owner">開啟「{{ item.owner.title }}」</RouterLink>
                  </span>
                </div>
                <RouterLink v-if="item.line" :to="{ name: 'app-document', params: { id: row.id }, query: { mode: 'split', line: item.line } }" class="fix">
                  <UiIcon name="edit" :size="15" />編輯第 {{ item.line }} 行
                </RouterLink>
                <RouterLink v-else-if="item.kind === 'public'" :to="{ name: 'app-document', params: { id: row.id }, query: { panel: 'publish' } }" class="fix">
                  <UiIcon name="globe" :size="15" />發布管理
                </RouterLink>
              </li>
            </ul>
          </article>
        </section>
        <div v-else class="empty">
          <UiIcon name="check" :size="26" />
          <p>{{ filtered ? '沒有符合篩選條件的問題。' : '沒有發現失效連結。' }}</p>
        </div>

        <section class="storage" aria-labelledby="storage-title">
          <h2 id="storage-title">儲存空間</h2>
          <p class="storage-note">以下只是資訊，不影響閱讀，也不會自動刪除。</p>
          <h3>只有舊版本用到的圖片與影片
            <span class="count">{{ report.storage.old_versions.length }} 個 · {{ size(report.storage.old_versions_bytes) }}</span></h3>
          <p class="storage-note">目前版本已經沒有用到，但舊版本還在，所以不會被自動清理。要釋放空間，可以由 Admin 在「版本」分頁刪除那些舊版本。</p>
          <table v-if="report.storage.old_versions.length" class="media">
            <thead><tr><th>文件</th><th>類型</th><th>用到的版本</th><th class="num">大小</th><th /></tr></thead>
            <tbody>
              <tr v-for="item in report.storage.old_versions" :key="item.id">
                <td><RouterLink :to="{ name: 'app-document', params: { id: item.document.id } }">{{ item.document.title }}</RouterLink></td>
                <td>{{ item.kind === 'image' ? '圖片' : '影片' }}</td>
                <td>{{ item.versions.map(number => `v${number}`).join('、') }}</td>
                <td class="num">{{ size(item.size) }}</td>
                <td><RouterLink :to="{ name: 'app-document', params: { id: item.document.id }, query: { panel: 'versions' } }">版本歷史</RouterLink></td>
              </tr>
            </tbody>
          </table>
          <p v-else class="none">沒有。</p>
          <h3>沒有任何版本用到的圖片與影片</h3>
          <p class="storage-note">
            圖片 {{ report.storage.unused.images }} 張、影片 {{ report.storage.unused.videos }} 支，共 {{ size(report.storage.unused.bytes) }}。
            通常是貼上後沒有儲存；上傳 24 小時後會自動清理。
          </p>
          <p class="storage-note">硬碟與資料庫對不上的檔案，請看<RouterLink v-if="session.isAdmin" :to="{ name: 'app-maintenance' }">維護與備份</RouterLink><template v-else>維護與備份（Admin）</template>的「一致性檢查」。</p>
        </section>
      </template>
    </template>
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 72rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-5); }
.eyebrow { margin: 0 0 var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-2) 0 0; color: var(--ui-text-secondary); line-height: 1.6; }
.skeleton { display: grid; gap: var(--ui-space-3); }
.link { border: 0; background: none; color: var(--ui-accent); cursor: pointer; font: inherit; }
.summary { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-3); }
.stat { display: grid; min-width: 7rem; padding: var(--ui-space-3) var(--ui-space-4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.stat strong { font-size: 1.5rem; font-variant-numeric: tabular-nums; }
.stat span { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.stat.bad strong { color: var(--ui-danger); }
.stat.warn strong { color: var(--ui-lagging-text); }
.stat.muted strong { color: var(--ui-text-secondary); }
.recheck { display: flex; align-items: center; gap: var(--ui-space-3); margin-left: auto; }
.recheck .p-button { gap: var(--ui-space-1); }
.checked-at { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-3); }
.segments { display: inline-flex; gap: 2px; padding: 3px; border-radius: .5625rem; background: var(--ui-bg-muted); }
.segment { padding: .35rem .8rem; border: 0; border-radius: .4rem; background: transparent; color: var(--ui-text-secondary); font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.segment[aria-checked="true"] { background: var(--ui-bg-surface); color: var(--ui-text); font-weight: 600; box-shadow: 0 1px 2px rgb(16 24 40 / .08); }
.kind { padding: .4rem .6rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text); font: inherit; font-size: var(--ui-text-sm); }
.documents { display: grid; gap: var(--ui-space-3); }
.doc { border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); overflow: hidden; }
.doc-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--ui-space-2) var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
.doc-title { color: var(--ui-text); font-weight: 600; text-decoration: none; }
.doc-title:hover { color: var(--ui-accent); }
.doc-meta { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.issues { list-style: none; margin: 0; padding: 0; }
.issue { display: flex; align-items: flex-start; gap: var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-4); }
.issue + .issue { border-top: 1px solid var(--ui-border-subtle); }
.issue-icon { flex: none; display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: var(--ui-radius-md); }
.issue.broken .issue-icon { background: var(--ui-danger-bg); color: var(--ui-danger); }
.issue.warning .issue-icon { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.issue-text { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--ui-space-1) var(--ui-space-2); }
.badge { padding: 0 var(--ui-space-2); border-radius: var(--ui-radius-pill); font-size: var(--ui-text-xs); font-weight: 600; }
.badge.broken { background: var(--ui-danger-bg); color: var(--ui-danger); }
.badge.warning { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.reason { color: var(--ui-text); overflow-wrap: anywhere; }
.link-text { flex-basis: 100%; color: var(--ui-text-secondary); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.where { flex-basis: 100%; display: flex; flex-wrap: wrap; gap: var(--ui-space-3); color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.owner { color: var(--ui-accent); }
.fix { flex: none; display: inline-flex; align-items: center; gap: var(--ui-space-1); padding: .3rem .65rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md);
  color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; white-space: nowrap; }
.fix:hover { background: var(--ui-accent-soft); }
.empty { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-6); border: 1px dashed var(--ui-border); border-radius: var(--ui-radius-lg); color: var(--ui-success, #16a34a); }
.empty p { margin: 0; color: var(--ui-text-secondary); }
.storage { display: grid; gap: var(--ui-space-2); padding: var(--ui-space-4) var(--ui-space-5); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.storage h2 { margin: 0; font-size: 1rem; }
.storage h3 { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); align-items: baseline; margin: var(--ui-space-3) 0 0; font-size: var(--ui-text-sm); }
.count { color: var(--ui-text-muted); font-weight: 400; }
.storage-note, .none { margin: 0; color: var(--ui-text-secondary); font-size: var(--ui-text-sm); line-height: 1.6; }
.media { width: 100%; border-collapse: collapse; font-size: var(--ui-text-sm); }
.media th, .media td { padding: .45rem .5rem; border-bottom: 1px solid var(--ui-border-subtle); text-align: left; }
.media th { color: var(--ui-text-muted); font-weight: 600; }
.media .num { text-align: right; font-variant-numeric: tabular-nums; }
@media (max-width: 640px) {
  .issue { flex-wrap: wrap; }
  .fix { margin-left: calc(2rem + var(--ui-space-3)); }
  .recheck { margin-left: 0; }
  .media { display: block; overflow-x: auto; }
}
</style>
