<script setup lang="ts">
// P19: settings Admins change — site name and tagline, the announcement banner, lightbox and galleries.
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ToggleSwitch from 'primevue/toggleswitch'
import { useToast } from 'primevue/usetoast'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useConfirm } from 'primevue/useconfirm'
import { useSession } from '../../stores/session'
import UiIcon from '../components/UiIcon.vue'
import { SPEED_FACTORS, useSite, type GallerySettings, type NoticeLevel, type NoticeSettings } from '../../stores/site'
import { GALLERY_LAYOUTS, LAYOUT_LABELS } from '../../gallery'

const site = useSite()
const session = useSession()
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
const intervals: GallerySettings['interval'][] = [3, 5, 8, 12]
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
    download: false,
    look: { effect: form.effect, speed: SPEED_FACTORS[form.speed], backdrop: form.backdrop / 100, respectReducedMotion: form.respect_reduced_motion,
      interval: form.interval },
  })
}

// ---- P19 (E2＋): unsaved changes ask before leaving ----------------------------------------------
const confirm = useConfirm()
const unsaved = computed(() => (siteTouched.value && siteDirty.value) || (noticeTouched.value && noticeDirty.value) || (galleryTouched.value && galleryDirty.value))
onBeforeRouteLeave(() => {
  if (!unsaved.value) return true
  return new Promise<boolean>(resolve => {
    confirm.require({
      header: '有尚未儲存的變更',
      message: '網站設定有修改還沒儲存。離開這一頁會放棄這些變更。',
      acceptProps: { label: '不儲存並離開', severity: 'danger' },
      rejectProps: { label: '留在這一頁', severity: 'secondary', outlined: true },
      accept: () => resolve(true),
      reject: () => resolve(false),
      onHide: () => resolve(false),
    })
  })
})
function warnOnUnload(event: BeforeUnloadEvent) {
  if (unsaved.value) event.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', warnOnUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', warnOnUnload))

onMounted(() => {
  drawSamples()
  site.setTitle('網站設定')
  if (session.isAdmin) void site.refresh()  // the stored announcement (Admins only) may predate this sign-in
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>網站設定</h1>
        <p class="subtitle" aria-live="polite">站名與介紹、公告橫幅、相簿與燈箱。會影響工作區、閱讀入口與公開站。</p>
      </div>
    </header>

    <Message v-if="!session.isAdmin" severity="error">只有 Admin 可以修改網站設定。</Message>
    <div v-else class="grid">
        <section id="site" class="card" aria-labelledby="site-title">
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
        <section id="notice" class="card" aria-labelledby="notice-title">
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
        <section id="gallery" class="card" aria-labelledby="gallery-title">
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
            <fieldset class="field levels">
              <legend>自動播放間隔</legend>
              <div class="level-buttons">
                <button v-for="seconds in intervals" :key="seconds" type="button" class="level" :class="{ on: galleryForm.interval === seconds }"
                  :aria-pressed="galleryForm.interval === seconds" @click="pickGallery('interval', seconds)">{{ seconds }} 秒</button>
              </div>
              <p class="note">燈箱的「播放」按鈕每隔這麼久換到下一張，播到最後一張自動暫停。</p>
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
              <label class="switch-row">
                <ToggleSwitch :model-value="galleryForm.respect_reduced_motion" input-id="gallery-reduced-motion"
                  @update:model-value="pickGallery('respect_reduced_motion', $event)" />
                <span>配合瀏覽器的「減少動態效果」</span>
              </label>
              <p class="note">開啟時，瀏覽器要求減少動態效果的人不會看到動畫（無障礙建議）。虛擬機或遠端桌面上的瀏覽器常會誤報這個設定；成員多半在這類環境時，可以關閉，讓所有人都看到動畫。</p>
            </div>
            <div class="field">
              <span class="field-label">預覽 <span class="optional">點縮圖，以上方（尚未儲存的）設定開啟燈箱</span></span>
              <div ref="sampleStrip" class="samples">
                <button v-for="(sample, index) in samples" :key="sample.alt" type="button" class="sample" :aria-label="`預覽：${sample.alt}`"
                  @click="previewLightbox(index)"><img :src="sample.src" :alt="sample.alt"></button>
              </div>
            </div>
            <p class="note">套用到工作區、閱讀入口與公開站的所有圖片。「預設相簿版面」用於沒有寫明版面的 <code>:::gallery</code> 與相簿模式的文件。訪客一律沒有下載按鈕。</p>
            <Message v-if="galleryError" severity="error" size="small">{{ galleryError }}</Message>
            <div class="form-actions">
              <Button type="submit" label="儲存" size="small" :loading="gallerySaving" :disabled="!galleryDirty" />
              <Button type="button" label="還原" size="small" text severity="secondary" :disabled="!galleryDirty || gallerySaving" @click="resetGallery" />
            </div>
          </form>
        </section>
    </div>
  </div>
</template>

<style scoped src="./systemPages.css"></style>
