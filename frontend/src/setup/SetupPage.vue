<script setup lang="ts">
// P24: the first-run setup wizard (mockup v8): brand panel with the step timeline on the left, one card on the
// right. Steps: welcome → licence and developer → (setup code, only past the hour) → admin → site → checks.
// Finishing signs the new admin in and opens the management centre.
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { errorMessage } from '../api'
import { useTheme } from '../stores/theme'
import {
  complete, isApiError, loadStatus, passwordRules, sizeText, strength, verify,
  type About, type AdminForm, type Checks, type SiteForm,
} from './setup'

type StepId = 'welcome' | 'license' | 'code' | 'admin' | 'site' | 'checks'
const STEP_INFO: Record<StepId, { name: string; hint: string }> = {
  welcome: { name: '歡迎', hint: '這套系統能做什麼' },
  license: { name: '授權與開發者', hint: '開發者資訊與條款' },
  code: { name: '設定碼', hint: '超過時限才需要' },
  admin: { name: '管理員', hint: '第一位 Admin 帳號' },
  site: { name: '網站', hint: '名稱、介紹與空間' },
  checks: { name: '系統檢查', hint: '部署設定狀態' },
}

const detachTheme = useTheme().attach()  // follow the visitor's light/dark setting like every other layout
const loading = ref(true)
const loadError = ref('')
const about = ref<About>()
const checks = ref<Checks>()
const codeFile = ref('')
const secondsLeft = ref(0)
const codeRequired = ref(false)
const permitted = ref(false)
const current = ref<StepId>('welcome')
const busy = ref(false)
const stepError = ref('')
const agreed = ref(false)
const code = ref<string[]>(Array(12).fill(''))
const admin = reactive<AdminForm>({ display_name: '', username: '', email: '', password: '' })
const confirm = ref('')
const reveal = ref(false)
const site = reactive<{ name: string; tagline: string; limit: string }>({ name: '', tagline: '', limit: '' })
const siteSkipped = ref(false)
const openFix = ref<Record<string, boolean>>({})
const heading = ref<HTMLElement>()
let timer: number | undefined

const needsCode = computed(() => codeRequired.value && !permitted.value)
const usedCode = ref(false)  // keeps the code step in the timeline, ticked, once it was passed
const steps = computed<StepId[]>(() => (['welcome', 'license', 'code', 'admin', 'site', 'checks'] as StepId[])
  .filter(id => id !== 'code' || needsCode.value || usedCode.value || current.value === 'code'))
const index = computed(() => steps.value.indexOf(current.value))
const minutesText = computed(() => `${Math.floor(secondsLeft.value / 60)} 分 ${String(secondsLeft.value % 60).padStart(2, '0')} 秒`)
const showWindow = computed(() => !permitted.value && ['welcome', 'license', 'code', 'admin'].includes(current.value))

async function refresh() {
  try {
    const status = await loadStatus()
    if (!status.required) {
      window.location.replace('/app/')
      return
    }
    about.value = status.about
    checks.value = status.checks
    codeFile.value = status.code_file
    secondsLeft.value = status.window_seconds
    codeRequired.value = status.code_required
    permitted.value = status.permitted
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : '無法載入設定狀態。'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  document.title = 'Knowledge Hub · 首次設定'
  await refresh()
  timer = window.setInterval(() => {
    if (secondsLeft.value > 0) secondsLeft.value--
    if (secondsLeft.value === 0 && !permitted.value) codeRequired.value = true
  }, 1000)
})
onBeforeUnmount(() => { window.clearInterval(timer); detachTheme() })

watch(current, async () => {
  stepError.value = ''
  await nextTick()
  heading.value?.focus()
})

// ---- Per-step readiness --------------------------------------------------------------------------
const rules = computed(() => passwordRules(admin, confirm.value))
const level = computed(() => strength(admin.password))
const adminReady = computed(() => admin.display_name.trim().length > 0 && /^[\w.@+-]{3,}$/.test(admin.username)
  && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(admin.email) && rules.value.every(([, met]) => met))
const codeText = computed(() => code.value.join(''))
const ready = computed(() => {
  switch (current.value) {
    case 'license': return agreed.value
    case 'code': return codeText.value.length === 12
    case 'admin': return adminReady.value
    default: return true
  }
})
const ctaLabel = computed(() => ({
  welcome: '下一步', license: '同意並繼續', code: '驗證並繼續', admin: '下一步', site: '儲存並繼續', checks: '完成設定，進入管理中心',
} as Record<StepId, string>)[current.value])

// ---- Moving on -----------------------------------------------------------------------------------
function go(step: StepId) { current.value = step }
function back() {
  const previous = steps.value[index.value - 1]
  if (previous) go(previous === 'code' && permitted.value ? 'license' : previous)  // a passed code needs no second entry
}

async function next() {
  if (!ready.value || busy.value) return
  stepError.value = ''
  busy.value = true
  try {
    if (current.value === 'welcome') go('license')
    else if (current.value === 'license') await afterLicense()
    else if (current.value === 'code') await submitCode()
    else if (current.value === 'admin') go('site')
    else if (current.value === 'site') { siteSkipped.value = false; go('checks') }
    else if (current.value === 'checks') await finish()
  } finally {
    busy.value = false
  }
}

async function afterLicense() {
  if (permitted.value) return go('admin')
  if (needsCode.value) return go('code')
  try {
    await verify()
    permitted.value = true
    go('admin')
  } catch {
    // The hour ran out meanwhile: the server now wants the code.
    await refresh()
    codeRequired.value = true
    go('code')
  }
}

async function submitCode() {
  try {
    await verify(codeText.value)
    usedCode.value = true
    permitted.value = true
    go('admin')
  } catch (cause) {
    stepError.value = isApiError(cause) ? (errorMessage(cause.body) || cause.message) : '無法驗證設定碼，請稍後再試。'
  }
}

async function finish() {
  if (!about.value) return
  const siteForm: SiteForm | null = siteSkipped.value ? null : {
    name: site.name.trim(), tagline: site.tagline.trim(), storage_limit_gb: site.limit ? Number(site.limit) : null,
  }
  if (siteForm && !siteForm.name) delete (siteForm as Partial<SiteForm>).name
  try {
    const result = await complete(about.value.terms_version, { ...admin, display_name: admin.display_name.trim() }, siteForm)
    window.location.assign(result.next)  // a full load: the session and CSRF token change with the sign-in
  } catch (cause) {
    if (!isApiError(cause)) { stepError.value = '無法完成設定，請稍後再試。'; return }
    const body = (cause.body ?? {}) as Record<string, unknown>
    if (cause.status === 410) { window.location.replace('/app/'); return }
    if (cause.status === 403) {
      // The 30-minute permit ran out: start again from the licence (and the code, past the hour).
      permitted.value = false
      await refresh()
      go('license')
      stepError.value = '設定許可已過期，請重新確認條款後繼續。'
      return
    }
    if ('terms_version' in body) {
      agreed.value = false
      await refresh()
      go('license')
      stepError.value = '條款已更新，請重新閱讀後再同意。'
      return
    }
    go('admin')
    await nextTick()
    stepError.value = errorMessage(body) || cause.message
  }
}

function skipSite() {
  siteSkipped.value = true
  go('checks')
}

// ---- Setup code boxes ----------------------------------------------------------------------------
const boxes = ref<HTMLInputElement[]>([])
function onCodeInput(i: number, event: Event) {
  const input = event.target as HTMLInputElement
  const value = input.value.replace(/[^a-z0-9]/gi, '').slice(-1).toUpperCase()
  code.value[i] = value
  input.value = value
  if (value && i < 11) boxes.value[i + 1]?.focus()
}
function onCodeKey(i: number, event: KeyboardEvent) {
  if (event.key === 'Backspace' && !code.value[i] && i > 0) {
    event.preventDefault()
    code.value[i - 1] = ''
    boxes.value[i - 1]?.focus()
  }
}
function onCodePaste(event: ClipboardEvent) {
  const text = (event.clipboardData?.getData('text') ?? '').replace(/[^a-z0-9]/gi, '').toUpperCase().slice(0, 12)
  if (!text) return
  event.preventDefault()
  text.split('').forEach((char, k) => { code.value[k] = char })
  boxes.value[Math.min(11, text.length)]?.focus()
}
const copied = ref(false)
const command = computed(() => `docker compose exec backend cat ${codeFile.value}`)
function copyCommand() {
  navigator.clipboard?.writeText(command.value).then(() => { copied.value = true; window.setTimeout(() => { copied.value = false }, 2000) }, () => {})
}

// ---- System checks -------------------------------------------------------------------------------
type CheckRow = { key: string; ok: boolean; title: string; text: string; fix?: string }
const checkRows = computed<CheckRow[]>(() => {
  const c = checks.value
  if (!c) return []
  const disk = c.disk
  const diskOk = !!disk && disk.free_bytes > disk.total_bytes * 0.1
  return [
    { key: 'https', ok: c.https, title: 'HTTPS', text: c.https ? c.origin : `未使用 HTTPS：${c.origin}`,
      fix: '對外開放前，在 <code>.env</code> 把 <code>PUBLIC_ORIGIN</code> 設成 <code>https://</code> 開頭的正式網址（經過 Cloudflare Tunnel 時就是你的網域），再重新啟動服務。' },
    { key: 'storage', ok: c.database && c.storage_writable, title: '資料庫與檔案',
      text: c.storage_writable ? 'PostgreSQL 連線正常，文件資料夾可以寫入' : '文件資料夾無法寫入',
      fix: '確認文件資料卷已掛載，且擁有者是容器中的 hub 使用者（uid 999）。' },
    { key: 'disk', ok: diskOk, title: '磁碟空間', text: disk ? `剩餘 ${sizeText(disk.free_bytes)}，共 ${sizeText(disk.total_bytes)}` : '無法讀取磁碟容量',
      fix: '剩餘空間不到 10%：清理主機上的其他檔案，或把文件資料卷移到較大的磁碟。' },
    { key: 'smtp', ok: c.smtp, title: '郵件（SMTP）', text: c.smtp ? '已設定，邀請與密碼重設信會實際寄出' : '未設定：邀請與密碼重設信不會寄出',
      fix: '在 <code>.env</code> 設定 <code>SMTP_HOST</code>、<code>SMTP_PORT</code>、<code>SMTP_USERNAME</code>、<code>SMTP_PASSWORD</code>、<code>SMTP_FROM_EMAIL</code>，再重新啟動服務。' },
    { key: 'google', ok: c.google_login, title: 'Google 登入', text: c.google_login ? '已設定' : '未設定：成員只能用 Email 與密碼登入',
      fix: '設定 <code>GOOGLE_CLIENT_ID</code> 與 <code>GOOGLE_CLIENT_SECRET</code>，並在 Google 允許回呼網址 <code>/accounts/google/login/callback/</code>。' },
    { key: 'mfa', ok: c.mfa_key, title: 'MFA 加密金鑰', text: c.mfa_key ? '已設定專用金鑰' : '未設定：目前由網站密鑰衍生',
      fix: '設定一組獨立的 <code>MFA_ENCRYPTION_KEY</code>，之後更換網站密鑰時雙因素驗證不受影響。' },
  ]
})
const readyCount = computed(() => checkRows.value.filter(row => row.ok).length)

const initials = computed(() => (about.value?.developer.name ?? '').replace(/[^a-z]/gi, '').slice(0, 2).toUpperCase() || 'KH')
const githubLabel = computed(() => about.value?.developer.github.replace(/^https?:\/\//, '') ?? '')
const FEATURES = [
  ['doc', '文件與版本', '上傳或直接撰寫 Markdown，每次儲存都保留版本，可比較與還原。'],
  ['shield', '安全的 HTML 閱讀', '互動式 HTML 在隔離沙箱中顯示，不影響網站本身。'],
  ['image', '圖片、相簿與影片', '貼上即上傳，相簿與燈箱播放，影片直接嵌入文章。'],
  ['search', '搜尋與文件連結', '全文搜尋並標示關鍵字，失效連結會自動檢查。'],
  ['globe', '公開站', '挑選文章發布給訪客，成員另有內部閱讀入口。'],
  ['users', '角色與稽核', 'Admin、Editor、Viewer 三種角色，重要操作都有紀錄。'],
] as const
const ICONS: Record<string, string> = {
  doc: '<path d="M5 4h9l5 5v11H5z"/><path d="M14 4v5h5"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.5 3.3-5.5 6.5-5.5s5.9 2 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.9.8 3.2 2.6 3.5 5.2"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  warn: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.01"/>',
  circle: '<circle cx="12" cy="12" r="8"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  code: '<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  heart: '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
  cup: '<path d="M5 8h11v6a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5z"/><path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16"/><path d="M8 3.5c0 1 1 1 1 2M11.5 3.5c0 1 1 1 1 2"/>',
  star: '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
}
const svg = (name: string, size = 18) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`
const STRENGTH = ['', '太弱', '普通', '不錯', '很強']
</script>

<template>
  <div class="setup">
    <aside class="panel" aria-label="Knowledge Hub">
      <div class="brand">
        <span class="logo" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h9l5 5v11H5z" /><path d="M14 4v5h5" /><path d="M8.5 13h7M8.5 16.5h5" /></svg></span>
        <div><div class="brand-name">Knowledge Hub</div><div class="brand-sub">首次設定</div></div>
      </div>
      <span v-if="!loading && index >= 0" class="mobile-step">{{ index + 1 }}／{{ steps.length }} · {{ STEP_INFO[current].name }}</span>
      <div class="pitch">
        <h2>把團隊的技術知識，放在一個找得到、改得動、留得住的地方。</h2>
        <p>大約三分鐘完成設定。</p>
      </div>
      <ol class="timeline">
        <li v-for="(id, i) in steps" :key="id" :class="{ done: i < index, current: i === index }" :aria-current="i === index ? 'step' : undefined">
          <span class="dot"><span v-if="i < index" v-html="svg('check', 13)" /><template v-else>{{ i + 1 }}</template></span>
          <span class="step-name">{{ STEP_INFO[id].name }}<span class="step-hint">{{ STEP_INFO[id].hint }}</span></span>
        </li>
      </ol>
      <div v-if="about" class="support">
        <strong>喜歡這個專案嗎？</strong>
        <span>Knowledge Hub 是開源專案，你的支持能讓它持續更新。</span>
        <div class="support-actions">
          <a v-if="about.support.github_sponsors" class="panel-btn heart" :href="about.support.github_sponsors" target="_blank" rel="noopener"><span v-html="svg('heart', 15)" />Sponsors</a>
          <span v-else class="panel-btn heart soon" aria-disabled="true"><span v-html="svg('heart', 15)" />Sponsors<em>即將開放</em></span>
          <a v-if="about.support.buy_me_a_coffee" class="panel-btn coffee" :href="about.support.buy_me_a_coffee" target="_blank" rel="noopener"><span v-html="svg('cup', 15)" />請我喝杯咖啡</a>
          <span v-else class="panel-btn coffee soon" aria-disabled="true"><span v-html="svg('cup', 15)" />請我喝杯咖啡<em>即將開放</em></span>
          <a class="panel-btn" :href="about.developer.github" target="_blank" rel="noopener"><span v-html="svg('star', 15)" />GitHub</a>
        </div>
      </div>
      <div v-if="about" class="panel-foot"><span>v{{ about.version }} · © {{ about.copyright }}</span><span>{{ about.developer.email }}</span></div>
    </aside>

    <main class="main">
      <div class="column">
        <p v-if="loading" class="loading" role="status">載入中…</p>
        <div v-else-if="loadError" class="card"><div class="card-body"><h1>無法載入設定</h1><p class="sub">{{ loadError }}</p></div></div>
        <template v-else-if="about">
          <div class="progress">
            <div class="progress-text"><span>步驟 {{ index + 1 }}／{{ steps.length }}</span><span>{{ STEP_INFO[current].name }}</span></div>
            <div class="bars" :style="{ gridTemplateColumns: `repeat(${steps.length}, 1fr)` }" aria-hidden="true">
              <span v-for="(id, i) in steps" :key="id" :class="{ on: i <= index }" />
            </div>
          </div>

          <section class="card" :aria-labelledby="`step-${current}`">
            <form class="card-body" @submit.prevent="next">
              <!-- Window: within the hour no code is needed; past it the code step appears. -->
              <div v-if="showWindow && !needsCode" class="window" :class="{ low: secondsLeft < 600 }" role="status">
                <span class="clock" v-html="svg('clock', 17)" />
                <div><strong>首次設定開放中：剩 {{ minutesText }}</strong><br><span>在時限內開始設定即可，不需要設定碼。</span></div>
              </div>
              <div v-else-if="showWindow && needsCode" class="window expired" role="status">
                <span class="clock" v-html="svg('clock', 17)" />
                <div><strong>首次設定的一小時時限已過</strong><br><span>為了安全，需要輸入設定碼；也可以重新啟動服務，再在一小時內完成設定。</span></div>
              </div>

              <!-- Welcome -->
              <template v-if="current === 'welcome'">
                <div class="head"><h1 :id="`step-${current}`" ref="heading" tabindex="-1">歡迎使用 Knowledge Hub</h1>
                  <p class="sub">團隊的技術知識庫。接下來幾分鐘，我們會完成授權確認、建立管理員與基本設定。</p></div>
                <ul class="features">
                  <li v-for="[icon, title, text] in FEATURES" :key="title"><span class="ficon" v-html="svg(icon)" /><div><strong>{{ title }}</strong><span>{{ text }}</span></div></li>
                </ul>
              </template>

              <!-- Licence and developer -->
              <template v-else-if="current === 'license'">
                <div class="head"><h1 :id="`step-${current}`" ref="heading" tabindex="-1">授權與開發者</h1>
                  <p class="sub">請確認開發者資訊並閱讀授權條款。這些內容之後也可以在管理中心的「關於」頁查看。</p></div>
                <div class="dev">
                  <div class="avatar" aria-hidden="true">{{ initials }}</div>
                  <div>
                    <div class="dev-name">{{ about.developer.name }}</div>
                    <div class="dev-role">開發與維護 Knowledge Hub</div>
                    <div class="dev-links">
                      <span><span v-html="svg('mail', 15)" />{{ about.developer.email }}</span>
                      <span><span v-html="svg('code', 15)" /><a :href="about.developer.github" target="_blank" rel="noopener">{{ githubLabel }}</a></span>
                    </div>
                    <div class="badges">
                      <span class="badge">版本 <b>v{{ about.version }}</b></span>
                      <span class="badge">授權 <b>{{ about.license || '待定' }}</b></span>
                      <span class="badge">© <b>{{ about.copyright }}</b></span>
                    </div>
                    <div class="support-row">
                      <a v-if="about.support.github_sponsors" class="support-btn heart" :href="about.support.github_sponsors" target="_blank" rel="noopener"><span v-html="svg('heart', 15)" />GitHub Sponsors</a>
                      <span v-else class="support-btn heart soon" aria-disabled="true"><span v-html="svg('heart', 15)" />GitHub Sponsors<em>即將開放</em></span>
                      <a v-if="about.support.buy_me_a_coffee" class="support-btn coffee" :href="about.support.buy_me_a_coffee" target="_blank" rel="noopener"><span v-html="svg('cup', 15)" />請我喝杯咖啡</a>
                      <span v-else class="support-btn coffee soon" aria-disabled="true"><span v-html="svg('cup', 15)" />請我喝杯咖啡<em>即將開放</em></span>
                      <a class="support-btn" :href="about.developer.github" target="_blank" rel="noopener"><span v-html="svg('star', 15)" />在 GitHub 加星號</a>
                    </div>
                  </div>
                </div>
                <div class="license">
                  <div class="license-head"><strong>使用說明與授權條款</strong><span>條款版本 {{ about.terms_version }}</span></div>
                  <div class="license-body" tabindex="0" aria-label="使用說明與授權條款全文">
                    <template v-for="part in about.terms" :key="part.title"><h4>{{ part.title }}</h4><p>{{ part.body }}</p></template>
                  </div>
                  <label class="agree"><input v-model="agreed" type="checkbox" id="setup-agree"><span>我已閱讀並同意使用說明與授權條款</span></label>
                </div>
              </template>

              <!-- Setup code -->
              <template v-else-if="current === 'code'">
                <div class="head"><h1 :id="`step-${current}`" ref="heading" tabindex="-1">輸入設定碼</h1>
                  <p class="sub">確認你是這台主機的部署者。設定碼在服務啟動時產生，只有能登入主機的人看得到。</p></div>
                <div class="field"><span class="label">在主機的專案資料夾執行</span>
                  <div class="cmd"><code>{{ command }}</code><button type="button" class="copy" @click="copyCommand">{{ copied ? '已複製' : '複製' }}</button></div></div>
                <div class="field"><span id="code-label" class="label">設定碼</span>
                  <div class="code-boxes" role="group" aria-labelledby="code-label" @paste="onCodePaste">
                    <template v-for="group in 3" :key="group">
                      <span v-if="group > 1" class="sep" aria-hidden="true">–</span>
                      <div class="code-group">
                        <input v-for="k in 4" :key="k" :ref="el => { if (el) boxes[(group - 1) * 4 + k - 1] = el as HTMLInputElement }"
                          type="text" maxlength="1" autocomplete="one-time-code" autocapitalize="characters" spellcheck="false"
                          :aria-label="`設定碼第 ${(group - 1) * 4 + k} 碼`" :value="code[(group - 1) * 4 + k - 1]"
                          @input="onCodeInput((group - 1) * 4 + k - 1, $event)" @keydown="onCodeKey((group - 1) * 4 + k - 1, $event)">
                      </div>
                    </template>
                  </div>
                  <span class="help">可以一次貼上整組設定碼，大小寫與連字號都不影響。</span></div>
              </template>

              <!-- Admin -->
              <template v-else-if="current === 'admin'">
                <div class="head"><h1 :id="`step-${current}`" ref="heading" tabindex="-1">建立管理員帳號</h1>
                  <p class="sub">這個帳號管理成員、內容與系統設定。其他成員之後由你邀請。</p></div>
                <div class="section"><div class="section-title"><strong>基本資料</strong><span>顯示在稽核紀錄、文件作者與成員清單。</span></div>
                  <div class="fields">
                    <div class="pair">
                      <div class="field"><label for="setup-name">顯示名稱</label><input id="setup-name" v-model="admin.display_name" type="text" autocomplete="name" maxlength="150" placeholder="Taiwan"></div>
                      <div class="field"><label for="setup-username">帳號</label><input id="setup-username" v-model="admin.username" type="text" autocomplete="username" maxlength="150" placeholder="hub.tw" spellcheck="false"></div>
                    </div>
                    <div class="field"><label for="setup-email">Email</label><input id="setup-email" v-model="admin.email" type="email" autocomplete="email" maxlength="254" placeholder="you@example.com"><span class="help">用來登入與接收通知。</span></div>
                  </div></div>
                <div class="section"><div class="section-title"><strong>密碼</strong><span>之後可以在個人設定加上雙因素驗證。</span></div>
                  <div class="fields">
                    <div class="pair">
                      <div class="field"><label for="setup-password">密碼</label>
                        <div class="input-wrap"><input id="setup-password" v-model="admin.password" :type="reveal ? 'text' : 'password'" class="has-reveal" autocomplete="new-password">
                          <button type="button" class="reveal" :aria-pressed="reveal" @click="reveal = !reveal">{{ reveal ? '隱藏' : '顯示' }}</button></div></div>
                      <div class="field"><label for="setup-confirm">再輸入一次</label><input id="setup-confirm" v-model="confirm" :type="reveal ? 'text' : 'password'" autocomplete="new-password"></div>
                    </div>
                    <div class="meter-row"><div class="meter" :data-level="level" aria-hidden="true"><span /><span /><span /><span /></div>
                      <span class="meter-text">{{ level ? `強度：${STRENGTH[level]}` : '密碼強度' }}</span></div>
                    <ul class="rules" aria-live="polite">
                      <li v-for="[text, met] in rules" :key="text" :class="{ met }"><span v-html="svg(met ? 'check' : 'circle', 14)" />{{ text }}</li>
                    </ul>
                  </div></div>
              </template>

              <!-- Site -->
              <template v-else-if="current === 'site'">
                <div class="head"><h1 :id="`step-${current}`" ref="heading" tabindex="-1">網站基本設定</h1>
                  <p class="sub">顯示在公開站、閱讀入口與登入頁。這一步可以略過，之後隨時修改。</p></div>
                <div class="section"><div class="section-title"><strong>網站資訊</strong><span>訪客與成員看到的名稱和介紹。</span></div>
                  <div class="fields">
                    <div class="field"><label for="setup-site-name">網站名稱</label><input id="setup-site-name" v-model="site.name" type="text" maxlength="60" placeholder="Knowledge Hub"></div>
                    <div class="field"><label for="setup-tagline">一句話介紹</label><textarea id="setup-tagline" v-model="site.tagline" maxlength="160" placeholder="團隊成員撰寫並審核後公開的技術規範、操作指南與參考文件。" /></div>
                  </div></div>
                <div class="section"><div class="section-title"><strong>儲存空間</strong><span>資料庫、所有版本、圖片與影片的總和。</span></div>
                  <div class="fields"><div class="field"><label for="setup-limit">上限</label>
                    <div class="input-wrap narrow"><input id="setup-limit" v-model="site.limit" type="number" min="1" step="1" class="has-reveal" placeholder="不限制"><span class="unit">GB</span></div>
                    <span v-if="checks?.disk" class="help">這台主機的磁碟剩餘 {{ sizeText(checks.disk.free_bytes) }}。</span></div></div></div>
              </template>

              <!-- Checks -->
              <template v-else-if="current === 'checks'">
                <div class="head"><h1 :id="`step-${current}`" ref="heading" tabindex="-1">系統檢查</h1>
                  <p class="sub">{{ readyCount }} 項已就緒<template v-if="readyCount < checkRows.length">，{{ checkRows.length - readyCount }} 項建議之後補上</template>。未設定的項目不影響完成設定。</p></div>
                <ul class="checklist">
                  <li v-for="row in checkRows" :key="row.key">
                    <div class="check-row">
                      <span class="state" :class="row.ok ? 'ok' : 'warn'" v-html="svg(row.ok ? 'check' : 'warn', 15)" />
                      <div><strong>{{ row.title }}</strong><span>{{ row.text }}</span></div>
                      <button v-if="!row.ok && row.fix" type="button" class="textbtn" :aria-expanded="!!openFix[row.key]"
                        @click="openFix[row.key] = !openFix[row.key]">{{ openFix[row.key] ? '收起' : '如何設定' }}</button>
                    </div>
                    <!-- Fixed text written in this file, never from the server. -->
                    <div v-if="!row.ok && row.fix && openFix[row.key]" class="fix" v-html="row.fix" />
                  </li>
                </ul>
              </template>

              <p v-if="stepError" class="error" role="alert">{{ stepError }}</p>
              <button type="submit" hidden tabindex="-1" aria-hidden="true" />
            </form>
            <div class="card-foot">
              <button v-if="index > 0" type="button" class="linkish" :disabled="busy" @click="back">← 上一步</button>
              <span class="spacer" />
              <button v-if="current === 'site'" type="button" class="linkish" :disabled="busy" @click="skipSite">略過</button>
              <button type="button" class="btn primary" :disabled="!ready || busy" @click="next">{{ busy ? '處理中…' : ctaLabel }}</button>
            </div>
          </section>
        </template>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* The brand panel keeps its deep blue in both themes; everything else follows the app tokens. */
.setup { --panel: #0f1f4d; --panel-ink: #e8edff; --panel-dim: #9fb0dc;
  min-height: 100vh; min-height: 100dvh; display: grid; grid-template-columns: minmax(18rem, 23rem) minmax(0, 1fr);
  background: var(--ui-bg-shell, var(--ui-bg-subtle)); color: var(--ui-text); font-family: var(--ui-font-sans); }
.panel { position: relative; overflow: hidden; background: var(--panel); color: var(--panel-ink); padding: 36px 32px 28px; display: flex; flex-direction: column; gap: 30px; }
.panel::before { content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image: linear-gradient(to right, rgb(255 255 255 / .045) 1px, transparent 1px), linear-gradient(to bottom, rgb(255 255 255 / .045) 1px, transparent 1px);
  background-size: 28px 28px; mask-image: linear-gradient(160deg, #000 10%, transparent 75%); }
.panel::after { content: ""; position: absolute; width: 420px; height: 420px; right: -180px; bottom: -160px; border-radius: 50%; background: radial-gradient(circle, rgb(124 157 255 / .28), transparent 65%); pointer-events: none; }
.panel > * { position: relative; }
.brand { display: flex; align-items: center; gap: 12px; }
.logo { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: linear-gradient(145deg, #4f7bff, #1e4fd8); box-shadow: inset 0 0 0 1px rgb(255 255 255 / .18); flex: none; }
.brand-name { font-weight: 700; font-size: 1.05rem; }
.brand-sub { font-size: .78rem; color: var(--panel-dim); }
.pitch h2 { margin: 0 0 8px; font-size: 1.3rem; line-height: 1.4; font-weight: 700; text-wrap: balance; }
.pitch p { margin: 0; color: var(--panel-dim); font-size: .9rem; }
.timeline { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.timeline li { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 12px; position: relative; padding-bottom: 14px; }
.timeline li:not(:last-child)::before { content: ""; position: absolute; left: 12px; top: 26px; bottom: 0; width: 2px; background: rgb(255 255 255 / .12); }
.timeline li.done:not(:last-child)::before { background: rgb(124 157 255 / .55); }
.dot { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: .74rem; font-weight: 700; border: 1.5px solid rgb(255 255 255 / .22); color: var(--panel-dim); background: var(--panel); font-variant-numeric: tabular-nums; }
.timeline .done .dot { background: #4f7bff; border-color: #4f7bff; color: #fff; }
.timeline .current .dot { border-color: #9cb4ff; color: #fff; box-shadow: 0 0 0 4px rgb(124 157 255 / .22); }
.step-name { font-weight: 600; font-size: .9rem; line-height: 26px; color: var(--panel-dim); }
.step-hint { display: block; font-weight: 400; font-size: .78rem; line-height: 1.4; color: rgb(159 176 220 / .75); }
.timeline .current .step-name, .timeline .done .step-name { color: var(--panel-ink); }
.support { display: grid; gap: 6px; padding: 14px 16px; border-radius: 14px; background: rgb(255 255 255 / .06); border: 1px solid rgb(255 255 255 / .1); font-size: .8rem; color: var(--panel-dim); }
.support strong { color: var(--panel-ink); font-size: .88rem; }
.support-actions { display: flex; gap: 8px; margin-top: 4px; flex-wrap: wrap; }
.panel-btn { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: 9px; font-size: .8rem; font-weight: 600; text-decoration: none; color: var(--panel-ink); background: rgb(255 255 255 / .08); border: 1px solid rgb(255 255 255 / .14); }
.panel-btn:hover:not(.soon) { background: rgb(255 255 255 / .14); }
.panel-btn.heart :deep(svg) { color: #ff8fa3; }
.panel-btn.coffee :deep(svg), .support-btn.coffee :deep(svg) { color: #e2a63b; }
.panel-foot { margin-top: auto; display: grid; gap: 4px; font-size: .76rem; color: var(--panel-dim); }
.soon { cursor: default; opacity: .75; }
.soon em { font-style: normal; font-size: .68rem; font-weight: 600; padding: 0 6px; margin-left: 2px; border-radius: 999px; background: rgb(255 255 255 / .12); }
.mobile-step { display: none; }

.main { display: flex; flex-direction: column; min-width: 0; padding: 20px 24px 40px; }
.column { width: 100%; max-width: 680px; margin: auto; display: grid; gap: 16px; padding-block: 24px; }
.loading { color: var(--ui-text-muted); text-align: center; }
.progress { display: grid; gap: 10px; padding-inline: 4px; }
.progress-text { display: flex; justify-content: space-between; font-size: .78rem; color: var(--ui-text-muted); font-weight: 500; font-variant-numeric: tabular-nums; }
.bars { display: grid; gap: 6px; }
.bars span { height: 4px; border-radius: 4px; background: var(--ui-border); transition: background .25s; }
.bars span.on { background: var(--ui-accent); }
.card { background: var(--ui-bg-surface); border: 1px solid var(--ui-border); border-radius: 18px; box-shadow: var(--ui-shadow-lg); overflow: hidden; }
.card-body { padding: 30px 32px; display: grid; gap: 22px; }
.card-foot { padding: 16px 32px; border-top: 1px solid var(--ui-border-subtle); background: var(--ui-bg-subtle); display: flex; align-items: center; gap: 12px; }
.card-foot .spacer { flex: 1; }
.head { display: grid; gap: 6px; }
h1 { margin: 0; font-size: 1.6rem; line-height: 1.25; font-weight: 700; letter-spacing: -.02em; text-wrap: balance; }
h1:focus { outline: none; }
.sub { margin: 0; color: var(--ui-text-secondary); font-size: .95rem; max-width: 60ch; }
.error { margin: 0; padding: 10px 12px; border-radius: 10px; background: var(--ui-danger-bg); border: 1px solid var(--ui-danger-border); color: var(--ui-danger); font-size: .86rem; font-weight: 600; }

.window { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 10px; align-items: center; padding: 10px 12px; border-radius: 12px; background: var(--ui-accent-soft); font-size: .84rem; }
.window.low, .window.expired { background: var(--ui-lagging-bg); }
.clock { width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; background: var(--ui-bg-surface); color: var(--ui-accent); }
.window.low .clock, .window.expired .clock { color: var(--ui-lagging-text); }
.window strong { font-variant-numeric: tabular-nums; }
.window span { color: var(--ui-text-secondary); }

.features { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 20px; margin: 0; padding: 0; list-style: none; }
.features li { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 12px; align-items: start; }
.ficon { width: 36px; height: 36px; border-radius: 10px; background: var(--ui-accent-soft); color: var(--ui-accent); display: grid; place-items: center; }
.features strong { display: block; font-size: .92rem; }
.features span { color: var(--ui-text-secondary); font-size: .84rem; }

.dev { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 18px; align-items: center; padding: 20px; border: 1px solid var(--ui-border); border-radius: 16px; background: linear-gradient(135deg, var(--ui-accent-soft), transparent 70%); }
.avatar { width: 64px; height: 64px; border-radius: 18px; display: grid; place-items: center; background: linear-gradient(145deg, #4f7bff, #1e4fd8); color: #fff; font-weight: 700; font-size: 1.3rem; }
.dev-name { font-size: 1.1rem; font-weight: 700; }
.dev-role { color: var(--ui-text-muted); font-size: .82rem; }
.dev-links { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 8px; font-size: .84rem; }
.dev-links > span { display: inline-flex; align-items: center; gap: 6px; color: var(--ui-text-secondary); min-width: 0; overflow-wrap: anywhere; }
.dev-links a { color: var(--ui-accent); text-decoration: none; }
.dev-links a:hover { text-decoration: underline; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; font-size: .76rem; font-weight: 600; background: var(--ui-bg-surface); border: 1px solid var(--ui-border); color: var(--ui-text-secondary); }
.badge b { color: var(--ui-text); }
.support-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.support-btn { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: 9px; border: 1px solid var(--ui-border); background: var(--ui-bg-surface); color: var(--ui-text); font-size: .8rem; font-weight: 600; text-decoration: none; }
.support-btn:hover:not(.soon) { border-color: var(--ui-accent); }
.support-btn.heart :deep(svg) { color: #e0436b; }
.support-btn.soon em { background: var(--ui-bg-muted); color: var(--ui-text-muted); }
.license { border: 1px solid var(--ui-border); border-radius: 14px; overflow: hidden; }
.license-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--ui-border-subtle); }
.license-head strong { font-size: .92rem; }
.license-head span { color: var(--ui-text-muted); font-size: .78rem; }
.license-body { max-height: 240px; overflow: auto; padding: 16px; background: var(--ui-bg-subtle); display: grid; gap: 8px; font-size: .86rem; color: var(--ui-text-secondary); line-height: 1.75; }
.license-body h4 { margin: 4px 0 0; font-size: .86rem; color: var(--ui-text); }
.license-body p { margin: 0; white-space: pre-line; }
.agree { display: flex; gap: 10px; align-items: flex-start; cursor: pointer; font-size: .92rem; font-weight: 500; padding: 12px 16px; border-top: 1px solid var(--ui-border-subtle); }
.agree input { margin-top: 3px; width: 17px; height: 17px; accent-color: var(--ui-accent); flex: none; }

.section { display: grid; grid-template-columns: 11rem minmax(0, 1fr); gap: 20px; padding-top: 20px; border-top: 1px solid var(--ui-border-subtle); }
.head + .section, .window + .head + .section { padding-top: 0; border-top: 0; }
.section-title strong { display: block; font-size: .92rem; }
.section-title span { color: var(--ui-text-muted); font-size: .8rem; line-height: 1.5; }
.fields { display: grid; gap: 14px; min-width: 0; }
.pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.field { display: grid; gap: 6px; min-width: 0; }
.field > label, .label { font-weight: 600; font-size: .84rem; }
.help { color: var(--ui-text-muted); font-size: .78rem; }
.input-wrap { position: relative; }
.input-wrap.narrow { max-width: 14rem; }
input[type=text], input[type=email], input[type=password], input[type=number], textarea {
  width: 100%; height: 42px; padding: 0 12px; border: 1px solid var(--ui-border); border-radius: 10px; background: var(--ui-bg-surface); color: var(--ui-text);
  font: inherit; font-size: .92rem; transition: border-color .15s, box-shadow .15s; }
textarea { height: auto; min-height: 84px; padding: 10px 12px; resize: vertical; line-height: 1.55; }
input:focus, textarea:focus { outline: none; border-color: var(--ui-accent); box-shadow: 0 0 0 3px var(--ui-focus-ring, var(--ui-accent-soft)); }
.has-reveal { padding-right: 64px !important; }
.reveal, .unit { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); height: 30px; padding: 0 10px; border: 0; border-radius: 7px; background: none; color: var(--ui-text-muted); font: inherit; font-size: .78rem; font-weight: 600; }
.reveal { cursor: pointer; }
.unit { display: grid; place-items: center; pointer-events: none; }
.reveal:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.meter-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; }
.meter { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.meter span { height: 4px; border-radius: 4px; background: var(--ui-border); transition: background .2s; }
.meter[data-level="1"] span:nth-child(-n+1) { background: var(--ui-danger); }
.meter[data-level="2"] span:nth-child(-n+2) { background: var(--ui-lagging-dot, #d97706); }
.meter[data-level="3"] span:nth-child(-n+3) { background: var(--ui-accent); }
.meter[data-level="4"] span { background: var(--ui-public-dot, #16a34a); }
.meter-text { font-size: .76rem; color: var(--ui-text-muted); white-space: nowrap; }
.rules { list-style: none; margin: 0; padding: 12px 14px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 14px; font-size: .79rem; border-radius: 10px; background: var(--ui-bg-subtle); border: 1px solid var(--ui-border-subtle); }
.rules li { display: flex; gap: 6px; align-items: center; color: var(--ui-text-muted); }
.rules li.met { color: var(--ui-public-text, #15803d); }

.cmd { display: flex; align-items: center; gap: 8px; padding: 10px 10px 10px 14px; border-radius: 10px; background: var(--ui-code-bg); font-family: var(--ui-font-mono); font-size: .8rem; overflow-x: auto; }
.cmd code { flex: 1; white-space: nowrap; color: var(--ui-code-text, var(--ui-text)); }
.copy { flex: none; height: 28px; padding: 0 10px; border-radius: 7px; border: 1px solid var(--ui-border); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; font-size: .76rem; font-weight: 600; cursor: pointer; }
.code-boxes { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.code-group { display: flex; gap: 6px; }
.code-boxes input { width: 40px; height: 50px; padding: 0; text-align: center; font-family: var(--ui-font-mono); font-size: 1.15rem; font-weight: 600; text-transform: uppercase; }
.sep { color: var(--ui-text-muted); }

.checklist { list-style: none; margin: 0; padding: 0; border: 1px solid var(--ui-border); border-radius: 14px; overflow: hidden; }
.checklist li + li { border-top: 1px solid var(--ui-border-subtle); }
.check-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 12px 14px; }
.state { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; }
.state.ok { background: var(--ui-public-bg); color: var(--ui-public-text); }
.state.warn { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.check-row strong { display: block; font-size: .9rem; }
.check-row span { color: var(--ui-text-secondary); font-size: .8rem; overflow-wrap: anywhere; }
.textbtn { border: 0; background: none; color: var(--ui-accent); font: inherit; font-size: .8rem; font-weight: 600; cursor: pointer; padding: 4px 6px; border-radius: 6px; }
.fix { padding: 0 14px 12px 54px; color: var(--ui-text-secondary); font-size: .8rem; }
.fix :deep(code) { font-family: var(--ui-font-mono); font-size: .78rem; background: var(--ui-code-inline-bg, var(--ui-bg-muted)); padding: 1px 5px; border-radius: 5px; }

.btn { height: 42px; padding: 0 20px; border-radius: 10px; border: 1px solid var(--ui-border); background: var(--ui-bg-surface); color: var(--ui-text); font: inherit; font-size: .92rem; font-weight: 600; cursor: pointer; }
.btn.primary { background: var(--ui-accent); border-color: var(--ui-accent); color: var(--ui-text-inverse, #fff); }
.btn.primary:hover:not(:disabled) { background: var(--ui-accent-hover, var(--ui-accent)); }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.linkish { border: 0; background: none; padding: 4px 2px; color: var(--ui-text-secondary); font: inherit; font-size: .88rem; font-weight: 500; cursor: pointer; border-radius: 6px; }
.linkish:hover:not(:disabled) { color: var(--ui-text); }
button:focus-visible, a:focus-visible, .license-body:focus-visible, .agree input:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
@media (prefers-reduced-motion: no-preference) { .card { animation: rise .22s ease-out; } @keyframes rise { from { opacity: 0; transform: translateY(6px); } } }

@media (max-width: 860px) {
  .setup { grid-template-columns: minmax(0, 1fr); }
  .panel { padding: 16px; flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; }
  .pitch, .timeline, .support, .panel-foot { display: none; }
  .mobile-step { display: block; font-size: .8rem; color: var(--panel-dim); text-align: right; }
  .main { padding: 12px 16px 32px; }
  h1 { font-size: 1.4rem; }
}
@media (max-width: 640px) {
  .section { grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .features { grid-template-columns: minmax(0, 1fr); }
  .dev { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 560px) {
  .card-body { padding: 22px 18px; }
  .card-foot { padding: 14px 18px; }
  .pair, .rules { grid-template-columns: minmax(0, 1fr); }
  .code-boxes input { width: 32px; height: 44px; }
}
</style>
