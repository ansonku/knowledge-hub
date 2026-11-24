<script setup lang="ts">
import { useSite } from '../../stores/site'
import Button from 'primevue/button'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import Textarea from 'primevue/textarea'
import { useConfirm } from 'primevue/useconfirm'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError } from '../../api'
import { useSession, type Role } from '../../stores/session'
import UiIcon from '../components/UiIcon.vue'
import { longDateTime, shortDate } from '../types'
import {
  auditLabel, formFor, initialOf, memberName, roleHints, roleLabels, statusLabels, statusOf,
  type MemberDetail, type Notice,
} from './members'

const site = useSite()
type Tab = 'profile' | 'security' | 'activity'
const route = useRoute()
const session = useSession()
const confirm = useConfirm()

const id = computed(() => String(route.params.id))
const detail = ref<MemberDetail>()
const loading = ref(true)
const error = ref('')
const notices = ref<Notice[]>([])
const tab = ref<Tab>('profile')
const tabs: { value: Tab; label: string }[] = [
  { value: 'profile', label: '資料' }, { value: 'security', label: '安全' }, { value: 'activity', label: '活動' },
]

async function load() {
  loading.value = true
  error.value = ''
  if (!session.isAdmin) {
    loading.value = false
    error.value = '只有 Admin 可以管理成員。'
    return
  }
  try {
    const data = await api<MemberDetail>(`/api/users/${encodeURIComponent(id.value)}/`)
    detail.value = data
    notices.value = data.notices
    newRole.value = data.account.role
    site.setTitle(`${memberName(data.account)} · 成員`)
  } catch (cause) {
    detail.value = undefined
    error.value = cause instanceof ApiError && cause.status === 404 ? '找不到這位成員。'
      : cause instanceof ApiError && cause.status === 403 ? '只有 Admin 可以管理成員。' : '無法載入成員資料。'
  } finally {
    loading.value = false
    await nextTick()
  }
}
watch(id, load, { immediate: true })

const account = computed(() => detail.value?.account)
const formUrl = computed(() => formFor(id.value))
const csrf = computed(() => detail.value?.csrf_token ?? '')
const status = computed(() => account.value ? statusOf(account.value) : 'active')
const isSelf = computed(() => Boolean(account.value?.is_self))
const roles: Role[] = ['admin', 'editor', 'viewer']

// ---- Actions: each is a native POST to the Django endpoint (CSRF, re-auth, audit) -------------
const newRole = ref<Role>('viewer')
const mfaReason = ref('')
const mfaVerified = ref(false)

function confirmSubmit(event: Event, header: string, message: string, label: string, danger = false) {
  const form = event.target as HTMLFormElement
  confirm.require({
    header, message,
    acceptProps: { label, severity: danger ? 'danger' : undefined },
    rejectProps: { label: '取消', severity: 'secondary', text: true },
    accept: () => form.submit(),
  })
}
</script>

<template>
  <div class="page">
    <RouterLink :to="{ name: 'app-members' }" class="back"><UiIcon name="chevronLeft" :size="16" />成員</RouterLink>

    <div v-if="loading && !detail" class="loading"><Skeleton width="40%" height="2.5rem" /><Skeleton height="10rem" /></div>
    <Message v-else-if="error" severity="error">{{ error }}</Message>

    <template v-else-if="account && detail">
      <header class="head">
        <span class="avatar" aria-hidden="true">{{ initialOf(memberName(account)) }}</span>
        <div class="head-text">
          <h1>{{ memberName(account) }}<span v-if="isSelf" class="you">（你）</span></h1>
          <p class="sub">{{ account.username }} · {{ account.email }}</p>
          <div class="badges">
            <span class="role" :class="account.role">{{ roleLabels[account.role] }}</span>
            <span class="status" :class="status"><span class="dot" aria-hidden="true" />{{ statusLabels[status] }}</span>
          </div>
        </div>
      </header>

      <div v-if="notices.length" class="notices">
        <Message v-for="(notice, index) in notices" :key="index" :severity="notice.warning ? 'error' : 'success'" closable
          @close="notices.splice(index, 1)">{{ notice.text }}</Message>
      </div>

      <div class="tabs" role="tablist" aria-label="成員資料分頁">
        <button v-for="item in tabs" :id="`member-tab-${item.value}`" :key="item.value" type="button" role="tab" class="tab"
          :class="{ on: tab === item.value }" :aria-selected="tab === item.value" aria-controls="member-panel" @click="tab = item.value">
          {{ item.label }}
        </button>
      </div>

      <section id="member-panel" role="tabpanel" :aria-labelledby="`member-tab-${tab}`" class="panel">
        <!-- Profile -->
        <template v-if="tab === 'profile'">
          <dl class="facts">
            <div><dt>帳號名稱</dt><dd>{{ account.username }}</dd></div>
            <div><dt>電子郵件</dt><dd>{{ account.email }}</dd></div>
            <div><dt>顯示名稱</dt><dd>{{ account.display_name || '—' }}</dd></div>
            <div><dt>建立時間</dt><dd>{{ longDateTime(account.date_joined) }}</dd></div>
            <div><dt>最後登入</dt><dd>{{ account.last_login ? longDateTime(account.last_login) : '從未登入' }}</dd></div>
          </dl>
          <form :action="formUrl" method="post" class="block"
            @submit.prevent="confirmSubmit($event, '變更角色', `要把 ${memberName(account)} 的角色改為 ${roleLabels[newRole]} 嗎？對方會收到通知信。`, '變更角色')">
            <input type="hidden" name="csrfmiddlewaretoken" :value="csrf">
            <input type="hidden" name="action" value="role">
            <fieldset class="roles" :disabled="isSelf">
              <legend>角色</legend>
              <label v-for="option in roles" :key="option" class="role-option" :class="{ on: newRole === option }">
                <input v-model="newRole" type="radio" name="role" :value="option" class="ui-visually-hidden">
                <span class="role-name">{{ roleLabels[option] }}</span>
                <span class="role-hint">{{ roleHints[option] }}</span>
              </label>
            </fieldset>
            <p v-if="isSelf" class="note">你的角色需要由另一位 Admin 變更。</p>
            <Button v-else type="submit" label="變更角色" :disabled="newRole === account.role" class="submit" />
          </form>
        </template>

        <!-- Security -->
        <template v-else-if="tab === 'security'">
          <ul class="rows">
            <li class="row">
              <div class="row-text"><strong>雙因素驗證</strong><span>{{ account.mfa_enabled ? '已啟用' : '尚未啟用' }}</span></div>
              <span class="flag" :class="{ on: account.mfa_enabled }">{{ account.mfa_enabled ? '已啟用' : '未啟用' }}</span>
            </li>
            <li class="row">
              <div class="row-text"><strong>Google 帳號</strong><span>{{ account.google_linked ? '可以用 Google 登入' : '尚未綁定' }}</span></div>
              <span class="flag" :class="{ on: account.google_linked }">{{ account.google_linked ? '已綁定' : '未綁定' }}</span>
            </li>
            <li v-if="status === 'pending'" class="row">
              <div class="row-text"><strong>啟用信</strong><span>重新寄出啟用信，先前寄出的連結會失效。</span></div>
              <form :action="formUrl" method="post"
                @submit.prevent="confirmSubmit($event, '重寄啟用信', `要重新寄啟用信給 ${account.email} 嗎？先前的連結會失效。`, '重寄')">
                <input type="hidden" name="csrfmiddlewaretoken" :value="csrf">
                <input type="hidden" name="action" value="resend">
                <Button type="submit" label="重寄啟用信" outlined size="small" />
              </form>
            </li>
            <li v-else class="row">
              <div class="row-text"><strong>密碼</strong><span>寄送密碼重設信給對方，由對方自行設定新密碼。</span></div>
              <form :action="formUrl" method="post"
                @submit.prevent="confirmSubmit($event, '寄送密碼重設信', `要寄送密碼重設信給 ${account.email} 嗎？`, '寄送')">
                <input type="hidden" name="csrfmiddlewaretoken" :value="csrf">
                <input type="hidden" name="action" value="password">
                <Button type="submit" label="寄送密碼重設信" outlined size="small" />
              </form>
            </li>
          </ul>
        </template>

        <!-- Activity -->
        <template v-else>
          <ol v-if="detail.audit.length" class="events">
            <li v-for="event in detail.audit" :key="event.id" class="event">
              <span class="event-dot" aria-hidden="true" />
              <div class="event-body">
                <p class="event-line"><strong>{{ event.actor ?? '系統' }}</strong> {{ auditLabel(event.action) }}</p>
                <p v-if="event.reason" class="event-reason">理由：{{ event.reason }}</p>
                <time :datetime="event.created_at" :title="longDateTime(event.created_at)">{{ shortDate(event.created_at) }}</time>
              </div>
            </li>
          </ol>
          <p v-else class="muted">還沒有帳號活動。</p>
          <p class="muted small">
            顯示最近 25 筆。
            <RouterLink :to="{ name: 'app-audit', query: { member: account.id } }">在稽核紀錄查看全部</RouterLink>
          </p>
        </template>
      </section>

      <!-- Danger zone -->
      <section class="danger" aria-labelledby="danger-title">
        <h2 id="danger-title">危險區</h2>
        <p v-if="isSelf" class="note">停用帳號、重設雙因素驗證需要由另一位 Admin 執行。</p>
        <template v-else>
          <div v-if="status !== 'pending'" class="danger-row">
            <div class="row-text">
              <strong>{{ status === 'disabled' ? '重新啟用帳號' : '停用帳號' }}</strong>
              <span>{{ status === 'disabled' ? '對方可以再次登入。' : '對方會立即登出所有裝置，並無法再登入。之後可以重新啟用。' }}</span>
            </div>
            <form :action="formUrl" method="post"
              @submit.prevent="status === 'disabled'
                ? confirmSubmit($event, '重新啟用帳號', `要重新啟用 ${memberName(account)} 的帳號嗎？`, '重新啟用')
                : confirmSubmit($event, '停用帳號', `要停用 ${memberName(account)} 的帳號嗎？對方會立即登出所有裝置。`, '停用帳號', true)">
              <input type="hidden" name="csrfmiddlewaretoken" :value="csrf">
              <input type="hidden" name="action" :value="status === 'disabled' ? 'enable' : 'disable'">
              <Button type="submit" :label="status === 'disabled' ? '重新啟用' : '停用帳號'" :severity="status === 'disabled' ? undefined : 'danger'" outlined size="small" />
            </form>
          </div>
          <div v-if="account.mfa_enabled" class="danger-row mfa">
            <div class="row-text">
              <strong>重設雙因素驗證</strong>
              <span>移除對方的驗證器並登出所有裝置，對方下次登入時要重新設定。只在確認對方身分後執行。</span>
            </div>
            <form :action="formUrl" method="post" class="mfa-form"
              @submit.prevent="confirmSubmit($event, '重設雙因素驗證', `要重設 ${memberName(account)} 的雙因素驗證嗎？這個動作會記錄理由。`, '重設', true)">
              <input type="hidden" name="csrfmiddlewaretoken" :value="csrf">
              <input type="hidden" name="action" value="mfa">
              <label for="mfa-reason">重設理由</label>
              <Textarea id="mfa-reason" v-model="mfaReason" name="reason" maxlength="500" rows="2" auto-resize required />
              <label class="verify">
                <input v-model="mfaVerified" type="checkbox" name="verified">
                <span>已透過獨立管道核對對方身分</span>
              </label>
              <Button type="submit" label="重設雙因素驗證" severity="danger" outlined size="small" :disabled="!mfaReason.trim() || !mfaVerified" />
            </form>
          </div>
          <p v-if="status === 'pending' && !account.mfa_enabled" class="note">待啟用的帳號沒有可執行的危險操作。</p>
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 52rem; margin-inline: auto; padding: var(--ui-space-5) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-5); }
.back { display: inline-flex; align-items: center; gap: var(--ui-space-1); justify-self: start; color: var(--ui-text-muted); font-size: var(--ui-text-sm); text-decoration: none; }
.back:hover { color: var(--ui-accent); }
.loading { display: grid; gap: var(--ui-space-4); }
.head { display: flex; gap: var(--ui-space-4); align-items: center; }
.avatar { flex: none; display: grid; place-items: center; width: 3.5rem; height: 3.5rem; border-radius: 50%; background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); font-size: 1.375rem; font-weight: 700; }
.head-text { min-width: 0; display: grid; gap: var(--ui-space-1); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); overflow-wrap: anywhere; }
.you { color: var(--ui-text-muted); font-size: 1rem; font-weight: 400; }
.sub { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.badges { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); align-items: center; }
.role { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-bg-muted); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); font-weight: 600; }
.role.admin { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.status { display: inline-flex; align-items: center; gap: .375rem; font-size: var(--ui-text-sm); }
.status .dot { width: 7px; height: 7px; border-radius: 50%; }
.status.active .dot { background: var(--ui-public-dot); }
.status.pending .dot { background: var(--ui-lagging-dot); }
.status.disabled { color: var(--ui-text-muted); }
.status.disabled .dot { background: var(--ui-private-dot); }
.notices { display: grid; gap: var(--ui-space-2); }
.tabs { display: flex; gap: var(--ui-space-1); border-bottom: 1px solid var(--ui-border); }
.tab { min-height: 2.5rem; padding: 0 var(--ui-space-4); border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px; background: transparent; color: var(--ui-text-muted); font: inherit; font-weight: 600; cursor: pointer; }
.tab:hover { color: var(--ui-text); }
.tab.on { border-bottom-color: var(--ui-accent); color: var(--ui-accent); }
.panel { display: grid; gap: var(--ui-space-5); }
.facts { margin: 0; display: grid; gap: var(--ui-space-3); }
.facts div { display: grid; grid-template-columns: 6rem minmax(0, 1fr); gap: var(--ui-space-3); }
.facts dt { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.facts dd { margin: 0; overflow-wrap: anywhere; }
.block { display: grid; gap: var(--ui-space-3); padding-top: var(--ui-space-5); border-top: 1px solid var(--ui-border-subtle); }
.roles { margin: 0; padding: 0; border: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--ui-space-2); }
.roles legend { margin-bottom: var(--ui-space-2); padding: 0; font-weight: 600; }
.roles:disabled { opacity: .6; }
.role-option { display: grid; gap: 2px; align-content: start; padding: var(--ui-space-3); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); cursor: pointer; }
.roles:disabled .role-option { cursor: default; }
.role-option.on { border-color: var(--ui-accent); background: var(--ui-accent-soft); }
.role-option:has(input:focus-visible) { box-shadow: var(--ui-focus-ring); }
.role-name { font-weight: 600; }
.role-hint { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.submit { justify-self: start; }
.note, .muted { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.small { font-size: var(--ui-text-xs); }
.rows { list-style: none; margin: 0; padding: 0; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); }
.row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-space-3); padding: var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
.row:last-child { border-bottom: 0; }
.row-text { display: grid; gap: 2px; min-width: 0; flex: 1 1 16rem; }
.row-text span { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.flag { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-private-bg); color: var(--ui-private-text); font-size: var(--ui-text-sm); font-weight: 600; }
.flag.on { background: var(--ui-public-bg); color: var(--ui-public-text); }
.events { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--ui-space-4); }
.event { display: flex; gap: var(--ui-space-3); }
.event-dot { flex: none; width: 8px; height: 8px; margin-top: .45rem; border-radius: 50%; background: var(--ui-border-strong); }
.event-body { display: grid; gap: 2px; min-width: 0; }
.event-line, .event-reason { margin: 0; color: var(--ui-text-secondary); }
.event-line strong { color: var(--ui-text); }
.event-reason { color: var(--ui-text-muted); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.event time { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.danger { display: grid; gap: var(--ui-space-3); padding: var(--ui-space-4) var(--ui-space-5); border: 1px solid var(--ui-danger-border); border-radius: var(--ui-radius-lg); background: var(--ui-danger-bg); }
.danger h2 { margin: 0; color: var(--ui-danger); font-size: 1rem; }
.danger-row { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--ui-space-3); padding-top: var(--ui-space-3); border-top: 1px solid var(--ui-danger-border); }
.danger-row:first-of-type { border-top: 0; padding-top: 0; }
.mfa-form { display: grid; gap: var(--ui-space-2); flex: 1 1 18rem; max-width: 24rem; }
.mfa-form label:not(.verify) { font-weight: 600; font-size: var(--ui-text-sm); }
.verify { display: flex; align-items: center; gap: var(--ui-space-2); font-size: var(--ui-text-sm); }
.verify input { width: 1rem; height: 1rem; accent-color: var(--ui-danger); }
.mfa-form .p-button { justify-self: start; }
@media (max-width: 640px) {
  .roles { grid-template-columns: minmax(0, 1fr); }
  .head { align-items: flex-start; }
  .facts div { grid-template-columns: minmax(0, 1fr); gap: 2px; }
}
</style>
