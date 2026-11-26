<script setup lang="ts">
// P19: what the system looks like right now (read only). Settings are on 網站設定, maintenance on 維護與備份.
import Button from 'primevue/button'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useSession } from '../../stores/session'
import { useSite } from '../../stores/site'
import UiIcon, { type IconName } from '../components/UiIcon.vue'
import { longDateTime, shortDate } from '../types'
import { bytes, loadReport, type Report } from './system'

const site = useSite()
const session = useSession()
const report = ref<Report>()
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await loadReport()
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    loading.value = false
  }
}

const number = new Intl.NumberFormat('zh-TW')
const diskUsed = computed(() => {
  const disk = report.value?.storage.disk
  return disk ? (disk.total_bytes - disk.free_bytes) / disk.total_bytes : 0
})
const severity = (level: Report['warnings'][number]['level']) => level === 'danger' ? 'error' : level === 'warning' ? 'warn' : 'info'

const flags = computed(() => {
  const config = report.value?.config
  if (!config) return []
  return [
    { label: 'HTTPS', on: config.https, onText: '已使用 HTTPS 對外', offText: '本機 HTTP（開發環境）' },
    { label: 'SMTP 郵件', on: config.smtp, onText: '已設定，會實際寄出', offText: '未設定，郵件只寫入伺服器檔案' },
    { label: 'Google 登入', on: config.google_login, onText: '已設定', offText: '未設定' },
    { label: 'MFA 加密金鑰', on: config.mfa_key, onText: '已設定專用金鑰', offText: '未設定，由 Django 密鑰衍生' },
    { label: 'HTML 互動預覽', on: config.html_preview, onText: '已開啟（僅限本機）', offText: '已關閉' },
  ]
})

type Stat = { label: string; value: string; icon: IconName; to?: object }
const contentStats = computed<Stat[]>(() => {
  const content = report.value?.content
  if (!content) return []
  return [
    { label: '文件', value: number.format(content.documents), icon: 'files', to: { name: 'app-library' } },
    { label: '版本', value: number.format(content.versions), icon: 'history' },
    { label: '公開文章', value: number.format(content.published), icon: 'globe', to: { name: 'app-published' } },
    { label: '回收桶', value: number.format(content.trashed), icon: 'trash', to: { name: 'app-trash' } },
    { label: '集合', value: number.format(content.collections), icon: 'folder', to: { name: 'app-taxonomy' } },
    { label: '標籤', value: number.format(content.tags), icon: 'sliders', to: { name: 'app-taxonomy' } },
  ]
})

/** Where each warning is dealt with. */
const fixes: Record<string, { to: object; label: string }> = {
  pending_deletions: { to: { name: 'app-maintenance' }, label: '前往維護與備份' },
  unindexed: { to: { name: 'app-maintenance' }, label: '前往維護與備份' },
  missing_files: { to: { name: 'app-maintenance' }, label: '前往維護與備份' },
  single_admin: { to: { name: 'app-members' }, label: '前往成員管理' },
}

onMounted(() => {
  site.setTitle('系統狀態')
  if (!session.isAdmin) {
    loading.value = false
    error.value = '只有 Admin 可以查看系統狀態。'
    return
  }
  void load()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>系統狀態</h1>
        <p class="subtitle" aria-live="polite"><template v-if="report">更新於 <time :datetime="report.generated_at" :title="longDateTime(report.generated_at)">{{ shortDate(report.generated_at) }}</time> · </template>
          內容、儲存空間、成員與環境設定，只能查看。修改站名與公告請到<RouterLink :to="{ name: 'app-site-settings' }">網站設定</RouterLink>，執行維護請到<RouterLink :to="{ name: 'app-maintenance' }">維護與備份</RouterLink>。</p>
      </div>
      <Button v-if="session.isAdmin" outlined :loading="loading" class="refresh" @click="load">
        <UiIcon name="history" :size="16" /><span>重新整理</span>
      </Button>
    </header>

    <Message v-if="error" severity="error">{{ error }}</Message>
    <div v-else-if="loading && !report" class="grid"><Skeleton v-for="index in 4" :key="index" height="10rem" border-radius="12px" /></div>

    <template v-else-if="report">
      <section class="attention" aria-labelledby="attention-title">
        <h2 id="attention-title" class="ui-visually-hidden">需要注意</h2>
        <Message v-if="!report.warnings.length" severity="success">目前沒有需要處理的項目。</Message>
        <Message v-for="note in report.warnings" :key="note.key" :severity="severity(note.level)">
          {{ note.text }}<RouterLink v-if="fixes[note.key]" :to="fixes[note.key].to" class="fix-link">{{ fixes[note.key].label }}</RouterLink>
        </Message>
      </section>

      <div class="grid">
        <section id="content" class="card wide" aria-labelledby="content-title">
          <h2 id="content-title">內容</h2>
          <ul class="stats">
            <li v-for="stat in contentStats" :key="stat.label">
              <component :is="stat.to ? RouterLink : 'div'" :to="stat.to" class="stat" :class="{ link: stat.to }">
                <UiIcon :name="stat.icon" :size="16" />
                <span class="stat-value">{{ stat.value }}</span>
                <span class="stat-label">{{ stat.label }}</span>
              </component>
            </li>
          </ul>
        </section>
        <section id="storage" class="card" aria-labelledby="storage-title">
          <h2 id="storage-title">儲存空間</h2>
          <dl class="facts">
            <div><dt>文件版本檔案</dt><dd>{{ bytes(report.storage.versions_bytes) }}</dd></div>
            <div><dt>文件中的圖片（{{ report.content.images.toLocaleString() }} 張）</dt><dd>{{ bytes(report.storage.images_bytes) }}</dd></div>
            <div><dt>文件中的影片（{{ report.content.videos.toLocaleString() }} 支）</dt><dd>{{ bytes(report.storage.videos_bytes) }}</dd></div>
            <div><dt>資料庫</dt><dd>{{ bytes(report.storage.database_bytes) }}</dd></div>
          </dl>
          <div v-if="report.storage.disk" class="disk">
            <div class="disk-line">
              <span>磁碟</span>
              <span>剩餘 {{ bytes(report.storage.disk.free_bytes) }} / 共 {{ bytes(report.storage.disk.total_bytes) }}</span>
            </div>
            <div class="meter" role="meter" :aria-valuenow="Math.round(diskUsed * 100)" aria-valuemin="0" aria-valuemax="100" aria-label="磁碟使用率">
              <span :style="{ width: `${Math.round(diskUsed * 100)}%` }" :class="{ high: diskUsed > .9 }" />
            </div>
            <p class="note">已使用 {{ Math.round(diskUsed * 100) }}%。備份須同時包含 PostgreSQL 與文件檔案兩個資料卷。</p>
          </div>
          <p v-else class="note">無法讀取磁碟容量。</p>
        </section>
        <section id="members" class="card" aria-labelledby="members-title">
          <h2 id="members-title">成員</h2>
          <dl class="facts">
            <div><dt>使用中</dt><dd>{{ report.members.active }}</dd></div>
            <div><dt>待啟用</dt><dd>{{ report.members.pending }}</dd></div>
            <div><dt>已停用</dt><dd>{{ report.members.disabled }}</dd></div>
            <div><dt>Admin／Editor／Viewer</dt><dd>{{ report.members.by_role.admin }}／{{ report.members.by_role.editor }}／{{ report.members.by_role.viewer }}</dd></div>
            <div><dt>啟用雙因素驗證</dt><dd>{{ report.members.mfa_enabled }} / {{ report.members.total }}</dd></div>
          </dl>
          <RouterLink :to="{ name: 'app-members' }" class="more">管理成員 <UiIcon name="arrowRight" :size="14" /></RouterLink>
        </section>
        <section id="config" class="card" aria-labelledby="config-title">
          <h2 id="config-title">設定</h2>
          <ul class="flags">
            <li v-for="flag in flags" :key="flag.label" class="flag-row">
              <span class="flag" :class="{ on: flag.on }"><span class="dot" aria-hidden="true" />{{ flag.on ? '開啟' : '關閉' }}</span>
              <span class="flag-text"><strong>{{ flag.label }}</strong><span>{{ flag.on ? flag.onText : flag.offText }}</span></span>
            </li>
          </ul>
          <p class="note">上傳上限：每檔 {{ bytes(report.config.max_upload_bytes) }}，每批 {{ report.config.max_batch }} 檔。</p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped src="./systemPages.css"></style>
