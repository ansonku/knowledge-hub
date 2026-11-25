<script setup lang="ts">
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import ToggleSwitch from 'primevue/toggleswitch'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../../api'
import { useSession } from '../../stores/session'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import UiIcon, { type IconName } from '../components/UiIcon.vue'
import { longDateTime, shortDate } from '../types'
import { maintenanceLines, type MaintenanceRun } from './maintenance'
import { SPEED_FACTORS, useSite, type GallerySettings, type NoticeLevel, type NoticeSettings } from '../../stores/site'
import { GALLERY_LAYOUTS, LAYOUT_LABELS } from '../../gallery'

const site = useSite()
type Report = {
  generated_at: string
  content: { documents: number; trashed: number; versions: number; published: number; collections: number; tags: number; images: number; videos: number }
  storage: { versions_bytes: number; images_bytes: number; videos_bytes: number; database_bytes: number | null; disk: { total_bytes: number; free_bytes: number } | null }
  members: {
    total: number; active: number; pending: number; disabled: number
    by_role: { admin: number; editor: number; viewer: number }; active_admins: number; mfa_enabled: number
  }
  jobs: {
    pending_deletions: number; oldest_pending_deletion: string | null; unindexed_documents: number
    unused_images: number; unused_images_bytes: number
    unused_videos: number; unused_videos_bytes: number
  }
  config: { https: boolean; google_login: boolean; smtp: boolean; mfa_key: boolean; html_preview: boolean; max_upload_bytes: number; max_batch: number }
  warnings: { level: 'info' | 'warning' | 'danger'; key: string; text: string }[]
  maintenance: MaintenanceRun | null
}

const session = useSession()
const report = ref<Report>()
const toast = useToast()

// ---- Site settings (name and tagline) -----------------------------------------------------------
const siteForm = ref({ name: site.name, tagline: site.tagline })
const siteSaving = ref(false)
// Follow the loaded settings until the admin starts editing.
const siteTouched = ref(false)
watch(() => [site.name, site.tagline] as const, ([name, tagline]) => { if (!siteTouched.value) siteForm.value = { name, tagline } })
const siteError = ref('')
const siteDirty = computed(() => siteForm.value.name.trim() !== site.name || siteForm.value.tagline.trim() !== site.tagline)
async function saveSite() {
  if (!siteDirty.value || siteSaving.value || !siteForm.value.name.trim()) return
  siteSaving.value = true
  siteError.value = ''
  try {
    await site.save({ name: siteForm.value.name.trim(), tagline: siteForm.value.tagline.trim() })
    siteForm.value = { name: site.name, tagline: site.tagline }
    siteTouched.value = false
    toast.add({ severity: 'success', summary: '已更新站台設定', life: 2500 })
  } catch (cause) {
    siteError.value = cause instanceof Error && cause.message ? cause.message : '無法儲存站台設定。'
  } finally {
    siteSaving.value = false
  }
}

// ---- Announcement banner (P6c) -------------------------------------------------------------------
const levels: { value: NoticeLevel; label: string }[] = [
  { value: 'info', label: '資訊' }, { value: 'warning', label: '提醒' }, { value: 'urgent', label: '重要' },
]
type NoticeForm = Omit<NoticeSettings, 'starts_at' | 'ends_at'> & { starts_at: string; ends_at: string }
const blankNotice: NoticeForm = { enabled: false, text: '', link: '', level: 'info', starts_at: '', ends_at: '' }
/** ISO time ⇄ the value of <input type="datetime-local"> in this browser's time zone. */
function toLocal(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  const pad = (number: number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
const fromLocal = (value: string) => (value ? new Date(value).toISOString() : null)
const formFrom = (settings?: NoticeSettings): NoticeForm => settings
  ? { ...settings, starts_at: toLocal(settings.starts_at), ends_at: toLocal(settings.ends_at) }
  : { ...blankNotice }
const noticeForm = ref<NoticeForm>(formFrom(site.noticeSettings))
const noticeTouched = ref(false)
watch(() => site.noticeSettings, settings => { if (!noticeTouched.value) noticeForm.value = formFrom(settings) })
const noticeSaving = ref(false)
const noticeError = ref('')
const noticeDirty = computed(() => JSON.stringify(noticeForm.value) !== JSON.stringify(formFrom(site.noticeSettings)))
/** What visitors see right now, from the saved settings. */
const noticeState = computed(() => {
  const saved = site.noticeSettings
  if (!saved?.enabled || !saved.text) return { label: '未顯示', tone: '' }
  const now = Date.now()
  if (saved.starts_at && new Date(saved.starts_at).getTime() > now) return { label: '已排程', tone: 'scheduled' }
  if (saved.ends_at && new Date(saved.ends_at).getTime() <= now) return { label: '已到期', tone: '' }
  return { label: '顯示中', tone: 'on' }
})
async function saveNotice() {
  if (noticeSaving.value) return
  noticeSaving.value = true
  noticeError.value = ''
  try {
    const form = noticeForm.value
    await site.saveNotice({ ...form, text: form.text.trim(), link: form.link.trim(), starts_at: fromLocal(form.starts_at), ends_at: fromLocal(form.ends_at) })
    noticeTouched.value = false
    noticeForm.value = formFrom(site.noticeSettings)
    toast.add({ severity: 'success', summary: '已更新公告', life: 2500 })
  } catch (cause) {
    noticeError.value = cause instanceof Error && cause.message ? cause.message : '無法儲存公告。'
  } finally {
    noticeSaving.value = false
  }
}
function pickLevel(level: NoticeLevel) {
  noticeForm.value.level = level
  noticeTouched.value = true
}
function resetNotice() {
  noticeTouched.value = false
  noticeForm.value = formFrom(site.noticeSettings)
  noticeError.value = ''
}

// ---- Lightbox and galleries (P11d) -------------------------------------------------------------
const effects: { value: GallerySettings['effect']; label: string }[] = [
  { value: 'center', label: '背景先出、圖片從中間浮現' }, { value: 'zoom', label: '從縮圖放大' }, { value: 'fade', label: '淡入' },
]
const speeds: { value: GallerySettings['speed']; label: string }[] = [
  { value: 'fast', label: '快' }, { value: 'normal', label: '標準' }, { value: 'slow', label: '慢' },
]
const layoutChoices = GALLERY_LAYOUTS.map(value => ({ value, label: LAYOUT_LABELS[value] }))
const galleryForm = ref<GallerySettings>({ ...site.gallery })
const galleryTouched = ref(false)
watch(() => site.gallery, settings => { if (!galleryTouched.value) galleryForm.value = { ...settings } })
const galleryDirty = computed(() => JSON.stringify(galleryForm.value) !== JSON.stringify(site.gallery))
const gallerySaving = ref(false)
const galleryError = ref('')
function pickGallery<K extends keyof GallerySettings>(key: K, value: GallerySettings[K]) {
  galleryForm.value = { ...galleryForm.value, [key]: value }
  galleryTouched.value = true
}
async function saveGallery() {
  if (gallerySaving.value) return
  gallerySaving.value = true
  galleryError.value = ''
  try {
    await site.saveGallery(galleryForm.value)
    galleryTouched.value = false
    galleryForm.value = { ...site.gallery }
    toast.add({ severity: 'success', summary: '已更新相簿與燈箱設定', life: 2500 })
  } catch (cause) {
    galleryError.value = cause instanceof Error && cause.message ? cause.message : '無法儲存設定。'
  } finally {
    gallerySaving.value = false
  }
}
function resetGallery() {
  galleryTouched.value = false
  galleryForm.value = { ...site.gallery }
  galleryError.value = ''
}
// Preview: sample pictures drawn here, opened with the settings on the form (saved or not).
const samples = ref<{ src: string; alt: string }[]>([])
function drawSamples() {
  const shapes: [number, number, number, string][] = [[1600, 1000, 215, '範例 1'], [900, 1300, 25, '範例 2'], [1800, 900, 150, '範例 3'], [1200, 1200, 275, '範例 4']]
  samples.value = shapes.map(([width, height, hue, label]) => {
    const canvas = Object.assign(document.createElement('canvas'), { width, height })
    const context = canvas.getContext('2d')
    if (context) {
      const gradient = context.createLinearGradient(0, 0, width, height)
      gradient.addColorStop(0, `hsl(${hue} 60% 52%)`)
      gradient.addColorStop(1, `hsl(${hue + 40} 55% 32%)`)
      context.fillStyle = gradient
      context.fillRect(0, 0, width, height)
      context.fillStyle = 'rgb(255 255 255 / .9)'
      context.font = `600 ${Math.round(Math.min(width, height) / 7)}px sans-serif`
      context.fillText(label, width * .08, height * .9)
    }
    return { src: canvas.toDataURL('image/jpeg', .85), alt: label }
  })
}
const sampleStrip = ref<HTMLElement>()
async function previewLightbox(index: number) {
  const images = Array.from(sampleStrip.value?.querySelectorAll('img') ?? [])
  if (!images[index]) return
  const { openLightbox } = await import('../../lightbox')
  const form = galleryForm.value
  void openLightbox(images, index, {
    download: false, look: { effect: form.effect, speed: SPEED_FACTORS[form.speed], backdrop: form.backdrop / 100 },
  })
}

const loading = ref(true)
const error = ref('')

// ---- Maintenance on demand -----------------------------------------------------
const confirm = useConfirm()
const maintaining = ref(false)
const lastRun = computed(() => report.value?.maintenance ?? null)
const lastLines = computed(() => lastRun.value ? maintenanceLines(lastRun.value.results) : [])
function confirmMaintenance() {
  confirm.require({
    header: '立即執行維護',
    message: '會依序執行：重試未完成的檔案清理、補建缺少的搜尋索引、刪除超過 24 小時且沒有任何版本使用的圖片與影片，'
      + '以及檢查檔案和資料庫是否一致（只檢查，不移動檔案）。執行期間會短暫暫停儲存版本和上傳圖片、影片。',
    acceptProps: { label: '執行' },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: () => { void runMaintenance() },
  })
}
async function runMaintenance() {
  maintaining.value = true
  try {
    await api('/api/admin/system/maintenance/', 'POST')
    await load()
    const alert = lastLines.value.some(line => line.alert)
    toast.add({ severity: alert ? 'warn' : 'success', summary: alert ? '維護完成，有項目需要處理' : '維護完成', life: 4000 })
  } catch (cause) {
    const busy = cause instanceof ApiError && cause.status === 409
    toast.add({ severity: busy ? 'warn' : 'error', summary: busy ? cause.message : '維護執行失敗，請稍後再試。', life: 5000 })
  } finally {
    maintaining.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await api<Report>('/api/admin/system/')
  } catch (cause) {
    error.value = cause instanceof ApiError && cause.status === 403 ? '只有 Admin 可以查看系統狀態。' : '無法載入系統狀態。'
  } finally {
    loading.value = false
  }
}

const units = ['B', 'KB', 'MB', 'GB', 'TB']
function bytes(value: number | null | undefined) {
  if (value == null) return '—'
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++ }
  return `${size >= 100 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`
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

onMounted(() => {
  drawSamples()
  site.setTitle('系統狀態')
  if (!session.isAdmin) {
    loading.value = false
    error.value = '只有 Admin 可以查看系統狀態。'
    return
  }
  void site.refresh()  // the stored announcement (Admins only) may predate this sign-in
  void load()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <p class="eyebrow">管理</p>
        <h1>系統狀態</h1>
        <p class="subtitle" aria-live="polite">
          <template v-if="report">更新於 <time :datetime="report.generated_at" :title="longDateTime(report.generated_at)">{{ shortDate(report.generated_at) }}</time> · </template>
          儲存空間、內容與成員統計、背景工作與設定。只顯示數量與是否啟用，不含設定值。
        </p>
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
        <Message v-for="note in report.warnings" :key="note.key" :severity="severity(note.level)">{{ note.text }}</Message>
      </section>

      <div class="grid">
        <section class="card wide" aria-labelledby="content-title">
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

        <section class="card" aria-labelledby="site-title">
          <h2 id="site-title">站台設定</h2>
          <form class="site-form" @submit.prevent="saveSite" @input="siteTouched = true">
            <div class="field">
              <label for="site-name">站名</label>
              <InputText id="site-name" v-model="siteForm.name" maxlength="60" required />
            </div>
            <div class="field">
              <label for="site-tagline">介紹 <span class="optional">選填</span></label>
              <InputText id="site-tagline" v-model="siteForm.tagline" maxlength="160" placeholder="一句話說明這個知識庫收錄什麼" />
            </div>
            <p class="note">顯示在公開站首頁、頁首與頁尾、工作區側欄、瀏覽器分頁標題，以及分享連結的預覽。</p>
            <Message v-if="siteError" severity="error" size="small">{{ siteError }}</Message>
            <Button type="submit" label="儲存" size="small" class="save" :loading="siteSaving" :disabled="!siteDirty || !siteForm.name.trim()" />
          </form>
        </section>

        <section class="card" aria-labelledby="storage-title">
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

        <section class="card" aria-labelledby="members-title">
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

        <section class="card" aria-labelledby="jobs-title">
          <h2 id="jobs-title">背景工作</h2>
          <dl class="facts">
            <div>
              <dt>待完成的檔案清理</dt>
              <dd :class="{ alert: report.jobs.pending_deletions }">{{ report.jobs.pending_deletions }}</dd>
            </div>
            <div v-if="report.jobs.oldest_pending_deletion">
              <dt>最舊的一筆</dt>
              <dd><time :datetime="report.jobs.oldest_pending_deletion" :title="longDateTime(report.jobs.oldest_pending_deletion)">{{ shortDate(report.jobs.oldest_pending_deletion) }}</time></dd>
            </div>
            <div>
              <dt>尚未建立搜尋索引的文件</dt>
              <dd :class="{ alert: report.jobs.unindexed_documents }">{{ report.jobs.unindexed_documents }}</dd>
            </div>
            <div>
              <dt>待清理的未使用圖片</dt>
              <dd>{{ report.jobs.unused_images }}<template v-if="report.jobs.unused_images">（{{ bytes(report.jobs.unused_images_bytes) }}）</template></dd>
            </div>
            <div>
              <dt>待清理的未使用影片</dt>
              <dd>{{ report.jobs.unused_videos }}<template v-if="report.jobs.unused_videos">（{{ bytes(report.jobs.unused_videos_bytes) }}）</template></dd>
            </div>
          </dl>
          <p class="note">沒有任何版本使用、且超過 24 小時的圖片與影片會自動刪除：服務啟動時一次，之後有人上傳圖片或影片時最多每小時一次。</p>
          <div class="maintenance">
            <div class="maintenance-head">
              <p class="note">
                <template v-if="lastRun">
                  上次手動維護：<time :datetime="lastRun.at" :title="longDateTime(lastRun.at)">{{ shortDate(lastRun.at) }}</time>
                  <template v-if="lastRun.actor">・{{ lastRun.actor }}</template>
                </template>
                <template v-else>還沒有手動執行過維護。</template>
              </p>
              <Button label="立即執行維護" size="small" outlined :loading="maintaining" @click="confirmMaintenance" />
            </div>
            <dl v-if="lastLines.length" class="facts results" aria-label="上次維護結果">
              <div v-for="line in lastLines" :key="line.label">
                <dt>{{ line.label }}</dt><dd :class="{ alert: line.alert }">{{ line.value }}</dd>
              </div>
            </dl>
          </div>
          <p class="note">維護也會檢查檔案和資料庫是否一致，但只顯示數量。要知道是哪些檔案，或把多出的檔案移到隔離區，請在主機上執行 <code>check_document_storage</code>。</p>
        </section>

        <section class="card" aria-labelledby="config-title">
          <h2 id="config-title">設定</h2>
          <ul class="flags">
            <li v-for="flag in flags" :key="flag.label" class="flag-row">
              <span class="flag" :class="{ on: flag.on }"><span class="dot" aria-hidden="true" />{{ flag.on ? '開啟' : '關閉' }}</span>
              <span class="flag-text"><strong>{{ flag.label }}</strong><span>{{ flag.on ? flag.onText : flag.offText }}</span></span>
            </li>
          </ul>
          <p class="note">上傳上限：每檔 {{ bytes(report.config.max_upload_bytes) }}，每批 {{ report.config.max_batch }} 檔。</p>
        </section>

        <section class="card" aria-labelledby="gallery-title">
          <h2 id="gallery-title">相簿與燈箱</h2>
          <form class="site-form" @submit.prevent="saveGallery">
            <fieldset class="field levels">
              <legend>燈箱效果</legend>
              <div class="level-buttons">
                <button v-for="item in effects" :key="item.value" type="button" class="level" :class="{ on: galleryForm.effect === item.value }"
                  :aria-pressed="galleryForm.effect === item.value" @click="pickGallery('effect', item.value)">{{ item.label }}</button>
              </div>
            </fieldset>
            <fieldset class="field levels">
              <legend>動畫速度</legend>
              <div class="level-buttons">
                <button v-for="item in speeds" :key="item.value" type="button" class="level" :class="{ on: galleryForm.speed === item.value }"
                  :aria-pressed="galleryForm.speed === item.value" @click="pickGallery('speed', item.value)">{{ item.label }}</button>
              </div>
            </fieldset>
            <div class="field">
              <label for="gallery-backdrop">背景暗度 <span class="optional">{{ (galleryForm.backdrop / 100).toFixed(2) }}</span></label>
              <input id="gallery-backdrop" type="range" min="60" max="100" step="1" class="range" :value="galleryForm.backdrop"
                @input="pickGallery('backdrop', Number(($event.target as HTMLInputElement).value))">
            </div>
            <fieldset class="field levels">
              <legend>預設相簿版面</legend>
              <div class="level-buttons">
                <button v-for="item in layoutChoices" :key="item.value" type="button" class="level" :class="{ on: galleryForm.layout === item.value }"
                  :aria-pressed="galleryForm.layout === item.value" @click="pickGallery('layout', item.value)">{{ item.label }}</button>
              </div>
            </fieldset>
            <label class="switch-row">
              <ToggleSwitch :model-value="galleryForm.member_download" input-id="gallery-download"
                @update:model-value="pickGallery('member_download', $event)" />
              <span>成員可在燈箱下載原圖</span>
            </label>
            <div class="field">
              <span class="field-label">預覽 <span class="optional">點縮圖，以上方（尚未儲存的）設定開啟燈箱</span></span>
              <div ref="sampleStrip" class="samples">
                <button v-for="(sample, index) in samples" :key="sample.alt" type="button" class="sample" :aria-label="`預覽：${sample.alt}`"
                  @click="previewLightbox(index)"><img :src="sample.src" :alt="sample.alt"></button>
              </div>
            </div>
            <p class="note">套用到工作區、閱讀入口與公開站的所有圖片。「預設相簿版面」用於沒有寫明版面的 <code>:::gallery</code> 與相簿模式的文件。訪客一律沒有下載按鈕；作業系統開啟「減少動態效果」的人不會看到動畫。</p>
            <Message v-if="galleryError" severity="error" size="small">{{ galleryError }}</Message>
            <div class="form-actions">
              <Button type="submit" label="儲存" size="small" :loading="gallerySaving" :disabled="!galleryDirty" />
              <Button type="button" label="還原" size="small" text severity="secondary" :disabled="!galleryDirty || gallerySaving" @click="resetGallery" />
            </div>
          </form>
        </section>

        <section class="card" aria-labelledby="notice-title">
          <div class="card-title-row">
            <h2 id="notice-title">公告橫幅</h2>
            <span class="notice-state" :class="noticeState.tone">{{ noticeState.label }}</span>
          </div>
          <form class="site-form" @submit.prevent="saveNotice" @input="noticeTouched = true">
            <label class="switch-row">
              <ToggleSwitch v-model="noticeForm.enabled" input-id="notice-enabled" />
              <span>開啟公告</span>
            </label>
            <div class="field">
              <label for="notice-text">內容 <span class="optional">{{ noticeForm.text.length }} / 120</span></label>
              <InputText id="notice-text" v-model="noticeForm.text" maxlength="120" placeholder="例如：11/30（日）20:00–22:00 系統維護" />
            </div>
            <div class="field">
              <label for="notice-link">連結 <span class="optional">選填</span></label>
              <InputText id="notice-link" v-model="noticeForm.link" maxlength="300" placeholder="https://… 或 /articles/…" />
            </div>
            <fieldset class="field levels">
              <legend>類型</legend>
              <div class="level-buttons">
                <button v-for="level in levels" :key="level.value" type="button" class="level" :class="[level.value, { on: noticeForm.level === level.value }]"
                  :aria-pressed="noticeForm.level === level.value" @click="pickLevel(level.value)">{{ level.label }}</button>
              </div>
            </fieldset>
            <div class="when">
              <div class="field">
                <label for="notice-start">開始 <span class="optional">選填</span></label>
                <input id="notice-start" v-model="noticeForm.starts_at" type="datetime-local" class="time-input">
              </div>
              <div class="field">
                <label for="notice-end">結束 <span class="optional">選填</span></label>
                <input id="notice-end" v-model="noticeForm.ends_at" type="datetime-local" class="time-input">
              </div>
            </div>
            <p class="note">顯示在公開站、閱讀入口、工作區與登入等頁面。只支援純文字；結束時間到了會自動隱藏，訪客也可以自行關閉。修改內容後，已關閉的人會再看到一次。</p>
            <div v-if="noticeForm.text.trim()" class="preview" :class="noticeForm.level" aria-hidden="true">
              <UiIcon :name="noticeForm.level === 'info' ? 'info' : 'alert'" :size="16" />
              <span>{{ noticeForm.text.trim() }}<span v-if="noticeForm.link.trim()" class="preview-link"> 查看詳情</span></span>
            </div>
            <Message v-if="noticeError" severity="error" size="small">{{ noticeError }}</Message>
            <div class="form-actions">
              <Button type="submit" label="儲存" size="small" :loading="noticeSaving" :disabled="!noticeDirty || (noticeForm.enabled && !noticeForm.text.trim())" />
              <Button type="button" label="還原" size="small" text severity="secondary" :disabled="!noticeDirty || noticeSaving" @click="resetNotice" />
            </div>
          </form>
        </section>
      </div>
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
.refresh { gap: var(--ui-space-2); }
.attention { display: grid; gap: var(--ui-space-2); }
.attention :deep(code), .note code { font-size: .8125rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr)); gap: var(--ui-space-4); align-items: start; }
.card { display: grid; gap: var(--ui-space-4); padding: var(--ui-space-5); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.card.wide { grid-column: 1 / -1; }
h2 { margin: 0; font-size: 1rem; }
/* Six figures: one row of six when there is room, otherwise even rows (3 × 2, 2 × 3). */
.stats { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(max(8.5rem, calc((100% - 5 * var(--ui-space-3)) / 6)), 1fr)); gap: var(--ui-space-3); }
.stat { display: grid; grid-template-columns: auto 1fr; grid-template-areas: "icon value" "icon label"; column-gap: var(--ui-space-3); align-items: center; padding: var(--ui-space-3) var(--ui-space-4); border: 1px solid var(--ui-border-subtle); border-radius: var(--ui-radius-md); background: var(--ui-bg-subtle); color: var(--ui-text-muted); text-decoration: none; }
.stat .ui-icon { grid-area: icon; }
.stat.link:hover { border-color: var(--ui-border-strong); }
.stat-value { grid-area: value; color: var(--ui-text); font-size: 1.375rem; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; }
.stat-label { grid-area: label; font-size: var(--ui-text-sm); }
.facts { margin: 0; display: grid; gap: var(--ui-space-2); }
.facts div { display: flex; justify-content: space-between; gap: var(--ui-space-3); padding-bottom: var(--ui-space-2); border-bottom: 1px solid var(--ui-border-subtle); }
.facts div:last-child { border-bottom: 0; padding-bottom: 0; }
.facts dt { color: var(--ui-text-secondary); }
.facts dd { margin: 0; color: var(--ui-text); font-weight: 600; font-variant-numeric: tabular-nums; text-align: right; }
.facts dd.alert { color: var(--ui-lagging-text); }
.disk { display: grid; gap: var(--ui-space-2); }
.disk-line { display: flex; justify-content: space-between; gap: var(--ui-space-3); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.meter { height: .5rem; border-radius: var(--ui-radius-pill); background: var(--ui-bg-muted); overflow: hidden; }
.meter span { display: block; height: 100%; border-radius: inherit; background: var(--ui-accent); }
.meter span.high { background: var(--ui-danger); }
.note { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); line-height: 1.6; }
.maintenance { display: grid; gap: var(--ui-space-3); padding-top: var(--ui-space-3); border-top: 1px solid var(--ui-border); }
.maintenance-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-space-2); }
.results { font-size: var(--ui-text-sm); }
.more { display: inline-flex; align-items: center; gap: var(--ui-space-1); justify-self: start; color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; }
.more:hover { text-decoration: underline; }
.flags { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--ui-space-3); }
.flag-row { display: flex; align-items: flex-start; gap: var(--ui-space-3); }
.flag { flex: none; display: inline-flex; align-items: center; gap: .375rem; min-width: 3.5rem; padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-private-bg); color: var(--ui-private-text); font-size: var(--ui-text-xs); font-weight: 600; }
.flag .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ui-private-dot); }
.flag.on { background: var(--ui-public-bg); color: var(--ui-public-text); }
.flag.on .dot { background: var(--ui-public-dot); }
.flag-text { display: grid; gap: 1px; }
.flag-text span { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.site-form { display: grid; gap: var(--ui-space-3); }
.field { display: grid; gap: var(--ui-space-1); }
.field label { font-weight: 600; font-size: var(--ui-text-sm); }
.optional { color: var(--ui-text-muted); font-weight: 400; }
.save { justify-self: start; }
.card-title-row { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-3); }
.notice-state { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-pill); background: var(--ui-private-bg); color: var(--ui-private-text); font-size: var(--ui-text-xs); font-weight: 600; }
.notice-state.on { background: var(--ui-public-bg); color: var(--ui-public-text); }
.notice-state.scheduled { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.switch-row { display: flex; align-items: center; gap: var(--ui-space-3); font-weight: 600; font-size: var(--ui-text-sm); cursor: pointer; }
.levels { margin: 0; padding: 0; border: 0; }
.field-label { font-weight: 600; font-size: var(--ui-text-sm); }
/* Choices without a notice level (相簿與燈箱): the chosen one in the accent colour. */
.level.on:not(.info, .warning, .urgent) { border-color: var(--ui-accent); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.range { width: 100%; accent-color: var(--ui-accent); }
.samples { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); }
.sample { width: 5.5rem; height: 3.75rem; padding: 0; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); overflow: hidden; background: var(--ui-bg-subtle); cursor: zoom-in; }
.sample img { display: block; width: 100%; height: 100%; object-fit: cover; }
.levels legend { padding: 0 0 var(--ui-space-1); font-weight: 600; font-size: var(--ui-text-sm); }
.level-buttons { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); }
.level { height: 2rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-sm); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; font-size: var(--ui-text-sm); font-weight: 600; cursor: pointer; }
.level.on.info { background: var(--ui-accent-soft); border-color: var(--ui-accent); color: var(--ui-accent-on-soft); }
.level.on.warning { background: var(--ui-lagging-bg); border-color: var(--ui-lagging-border); color: var(--ui-lagging-text); }
.level.on.urgent { background: var(--ui-danger-bg); border-color: var(--ui-danger-border); color: var(--ui-danger); }
.when { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr)); gap: var(--ui-space-3); }
.time-input { box-sizing: border-box; width: 100%; height: 2.5rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text); font: inherit; font-size: var(--ui-text-sm); color-scheme: inherit; }
.time-input:focus-visible { outline: none; border-color: var(--ui-accent); box-shadow: var(--ui-focus-ring); }
.preview { display: flex; align-items: center; gap: var(--ui-space-2); padding: var(--ui-space-2) var(--ui-space-3); border-radius: var(--ui-radius-md); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.preview.info { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.preview.warning { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.preview.urgent { background: var(--ui-danger-bg); color: var(--ui-danger); }
.preview-link { font-weight: 600; text-decoration: underline; }
.form-actions { display: flex; gap: var(--ui-space-2); }
</style>
