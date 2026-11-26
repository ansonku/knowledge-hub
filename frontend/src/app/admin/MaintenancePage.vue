<script setup lang="ts">
// P19: maintenance on demand and its last result; backups (M7a) and scheduled runs (M7b) will join here.
import Button from 'primevue/button'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../../api'
import { useSession } from '../../stores/session'
import { useSite } from '../../stores/site'
import UiIcon from '../components/UiIcon.vue'
import { longDateTime, shortDate } from '../types'
import { maintenanceLines } from './maintenance'
import { bytes, loadReport, type Report } from './system'

const site = useSite()
const session = useSession()
const toast = useToast()
const report = ref<Report>()
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
    report.value = await loadReport()
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  site.setTitle('維護與備份')
  if (!session.isAdmin) {
    loading.value = false
    error.value = '只有 Admin 可以執行維護。'
    return
  }
  void load()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>維護與備份</h1>
        <p class="subtitle" aria-live="polite">重試檔案清理、補建搜尋索引、清理未使用的圖片與影片，以及檢查檔案和資料庫是否一致。備份之後也會放在這裡。</p>
      </div>
      <Button v-if="session.isAdmin" outlined :loading="loading" class="refresh" @click="load">
        <UiIcon name="history" :size="16" /><span>重新整理</span>
      </Button>
    </header>

    <Message v-if="error" severity="error">{{ error }}</Message>
    <div v-else-if="loading && !report" class="grid"><Skeleton height="14rem" border-radius="12px" /></div>
    <div v-else-if="report" class="grid">
        <section id="jobs" class="card wide" aria-labelledby="jobs-title">
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
    </div>
  </div>
</template>

<style scoped src="./systemPages.css"></style>
