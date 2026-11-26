<script setup lang="ts">
import { useSite } from '../../stores/site'
import Button from 'primevue/button'
import Drawer from 'primevue/drawer'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Skeleton from 'primevue/skeleton'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { api, ApiError } from '../../api'
import { useSession, type Role } from '../../stores/session'
import { shortDate, longDateTime } from '../types'
import UiIcon from '../components/UiIcon.vue'
import {
  FORM_LIST, initialOf, memberName, roleHints, roleLabels, statusLabels, statusOf,
  type MemberListing, type MemberStatus, type Notice,
} from './members'

const site = useSite()
const route = useRoute()
const router = useRouter()
const session = useSession()

const queryText = (key: string) => typeof route.query[key] === 'string' ? route.query[key] as string : ''
const keywords = computed(() => queryText('q'))
const role = computed(() => queryText('role') as Role | '')
const status = computed(() => queryText('status') as MemberStatus | '')
const page = computed(() => Math.max(1, Number.parseInt(queryText('page') || '1', 10) || 1))
function setQuery(patch: Record<string, string | number | undefined>, resetPage = true) {
  const query: LocationQueryRaw = { ...route.query, ...(resetPage ? { page: undefined } : {}), ...patch }
  for (const key of Object.keys(query)) if (query[key] === '' || query[key] === undefined || query[key] === 1) delete query[key]
  void router.replace({ query })
}
const searchText = ref(keywords.value)
watch(keywords, value => { if (value !== searchText.value.trim()) searchText.value = value })
watch(searchText, (text, _, onCleanup) => {
  const timer = setTimeout(() => { if (text.trim() !== keywords.value) setQuery({ q: text.trim() }) }, 250)
  onCleanup(() => clearTimeout(timer))
})
const roleOptions = (['admin', 'editor', 'viewer'] as Role[]).map(id => ({ id, name: roleLabels[id] }))
const statusOptions = (['active', 'pending', 'disabled'] as MemberStatus[]).map(id => ({ id, name: statusLabels[id] }))
const hasFilters = computed(() => Boolean(keywords.value || role.value || status.value))

// ---- Data -------------------------------------------------------------------------------
const listing = ref<MemberListing>()
const loading = ref(true)
const error = ref('')
const notices = ref<Notice[]>([])
let request = 0
async function load() {
  const current = ++request
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ page: String(page.value) })
  if (keywords.value) params.set('q', keywords.value)
  if (role.value) params.set('role', role.value)
  if (status.value) params.set('status', status.value)
  try {
    const data = await api<MemberListing>(`/api/users/?${params}`)
    if (current !== request) return
    listing.value = data
    // Django flashes the outcome of the last form submission; it is shown once.
    if (data.notices.length) notices.value = data.notices
    if (data.page !== page.value) setQuery({ page: data.page }, false)
  } catch (cause) {
    if (current !== request) return
    error.value = cause instanceof ApiError && cause.status === 403 ? '只有 Admin 可以管理成員。' : '無法載入成員清單。'
  } finally {
    if (current === request) loading.value = false
  }
}
watch([keywords, role, status, page], load)

// ---- Invitation (native POST to the Django form endpoint) ---------------------------------
const draftKey = 'knowledge-hub.app.invite-draft'
const inviteOpen = ref(false)
const invite = ref({ username: '', email: '', display_name: '', role: 'viewer' as Role })
const inviteReady = computed(() => invite.value.username.trim() && /.+@.+\..+/.test(invite.value.email.trim()))
function openInvite() {
  inviteOpen.value = true
}
function rememberDraft() {
  try { sessionStorage.setItem(draftKey, JSON.stringify(invite.value)) } catch { /* storage may be disabled */ }
}
function restoreDraft(reopen: boolean) {
  try {
    const raw = sessionStorage.getItem(draftKey)
    sessionStorage.removeItem(draftKey)
    if (raw && reopen) {
      invite.value = { ...invite.value, ...JSON.parse(raw) }
      inviteOpen.value = true
    }
  } catch { /* ignore */ }
}

onMounted(async () => {
  site.setTitle('成員管理')
  if (!session.isAdmin) {
    loading.value = false
    error.value = '只有 Admin 可以管理成員。'
    return
  }
  await load()
  // Back from a submission: a success notice means the invitation went through; an error notice
  // reopens the panel with what was typed. (When Django asks for re-authentication first, allauth
  // replays the original POST afterwards, so the notices always describe the real outcome.)
  restoreDraft(notices.value.some(notice => notice.warning) && !notices.value.some(notice => !notice.warning))
})

const pageCount = computed(() => listing.value?.page_count ?? 1)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>成員</h1>
        <p class="subtitle" aria-live="polite">{{ loading && !listing ? '正在載入…' : `${listing?.count ?? 0} 位成員` }}</p>
      </div>
      <Button v-if="session.isAdmin" class="invite-button" @click="openInvite">
        <UiIcon name="plus" :size="16" /><span>邀請成員</span>
      </Button>
    </header>

    <div v-if="notices.length" class="notices">
      <Message v-for="(notice, index) in notices" :key="index" :severity="notice.warning ? 'error' : 'success'" closable
        @close="notices.splice(index, 1)">{{ notice.text }}</Message>
    </div>

    <Message v-if="error" severity="error">{{ error }}</Message>
    <template v-else>
      <div class="toolbar" role="search">
        <label class="search-box">
          <span class="ui-visually-hidden">搜尋成員</span>
          <UiIcon name="search" :size="16" />
          <input id="member-search" v-model="searchText" type="search" maxlength="150" placeholder="搜尋帳號、名稱或電子郵件">
        </label>
        <Select :model-value="role || null" :options="roleOptions" option-label="name" option-value="id" show-clear
          placeholder="所有角色" aria-label="依角色篩選" class="facet" @update:model-value="value => setQuery({ role: value ?? '' })" />
        <Select :model-value="status || null" :options="statusOptions" option-label="name" option-value="id" show-clear
          placeholder="所有狀態" aria-label="依狀態篩選" class="facet" @update:model-value="value => setQuery({ status: value ?? '' })" />
        <Button v-if="hasFilters" label="清除篩選" text severity="secondary" @click="searchText = ''; setQuery({ q: '', role: '', status: '' })" />
      </div>

      <div class="table-wrap" role="region" aria-label="成員清單" tabindex="0">
        <table class="table" :aria-busy="loading">
          <thead>
            <tr>
              <th scope="col">成員</th>
              <th scope="col" class="col-role">角色</th>
              <th scope="col" class="col-status">狀態</th>
              <th scope="col" class="col-date">最後登入</th>
            </tr>
          </thead>
          <tbody v-if="loading && !listing">
            <tr v-for="index in 5" :key="index"><td colspan="4"><Skeleton width="60%" /></td></tr>
          </tbody>
          <tbody v-else :class="{ stale: loading }">
            <tr v-for="member in listing?.results" :key="member.id">
              <td class="cell-member">
                <RouterLink :to="{ name: 'app-member', params: { id: member.id } }" class="member">
                  <span class="avatar" aria-hidden="true">{{ initialOf(memberName(member)) }}</span>
                  <span class="member-text">
                    <span class="member-name">{{ memberName(member) }}<span v-if="member.id === session.account?.id" class="you">（你）</span></span>
                    <span class="member-mail">{{ member.username }} · {{ member.email }}</span>
                  </span>
                </RouterLink>
              </td>
              <td class="cell-role"><span class="role" :class="member.role">{{ roleLabels[member.role] }}</span></td>
              <td class="cell-status"><span class="status" :class="statusOf(member)"><span class="dot" aria-hidden="true" />{{ statusLabels[statusOf(member)] }}</span></td>
              <td class="cell-date">
                <time v-if="member.last_login" :datetime="member.last_login" :title="longDateTime(member.last_login)">{{ shortDate(member.last_login) }}</time>
                <span v-else class="muted">從未登入</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!loading && listing && !listing.results.length" class="empty">
          <UiIcon name="users" :size="28" />
          <p>{{ hasFilters ? '沒有符合條件的成員。' : '還沒有成員。' }}</p>
        </div>
      </div>

      <nav v-if="pageCount > 1" class="pager" aria-label="分頁">
        <Button label="上一頁" text size="small" :disabled="page <= 1" @click="setQuery({ page: page - 1 }, false)" />
        <span>第 {{ page }} / {{ pageCount }} 頁</span>
        <Button label="下一頁" text size="small" :disabled="page >= pageCount" @click="setQuery({ page: page + 1 }, false)" />
      </nav>
    </template>

    <Drawer v-model:visible="inviteOpen" position="right" header="邀請成員" class="invite-drawer" :style="{ width: 'min(100vw, 26rem)' }">
      <form :action="FORM_LIST" method="post" class="invite-form" @submit="rememberDraft">
        <input type="hidden" name="csrfmiddlewaretoken" :value="listing?.csrf_token">
        <p class="help">系統會建立待啟用帳號，並寄出啟用信。對方設定密碼後才能登入。</p>
        <div class="field">
          <label for="invite-username">帳號名稱</label>
          <InputText id="invite-username" v-model="invite.username" name="username" maxlength="150" required autocomplete="off" />
        </div>
        <div class="field">
          <label for="invite-email">電子郵件</label>
          <InputText id="invite-email" v-model="invite.email" name="email" type="email" maxlength="254" required autocomplete="off" />
        </div>
        <div class="field">
          <label for="invite-name">顯示名稱 <span class="optional">選填</span></label>
          <InputText id="invite-name" v-model="invite.display_name" name="display_name" maxlength="150" autocomplete="off" />
        </div>
        <fieldset class="field roles">
          <legend>角色</legend>
          <label v-for="option in roleOptions" :key="option.id" class="role-option" :class="{ on: invite.role === option.id }">
            <input v-model="invite.role" type="radio" name="role" :value="option.id" class="ui-visually-hidden">
            <span class="role-name">{{ option.name }}</span>
            <span class="role-hint">{{ roleHints[option.id] }}</span>
          </label>
        </fieldset>
        <div class="actions">
          <Button type="button" label="取消" text severity="secondary" @click="inviteOpen = false" />
          <Button type="submit" label="建立帳號並寄出啟用信" :disabled="!inviteReady || !listing" />
        </div>
      </form>
    </Drawer>
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 100rem; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-4); }
.page-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--ui-space-4); }
.eyebrow { margin: 0 0 var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.invite-button { gap: var(--ui-space-2); }
.notices { display: grid; gap: var(--ui-space-2); }
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); }
.search-box {
  flex: 1 1 18rem; display: flex; align-items: center; gap: var(--ui-space-2); min-height: 2.5rem; padding: 0 var(--ui-space-3);
  border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-muted); box-sizing: border-box;
}
.search-box:focus-within { border-color: var(--ui-accent); box-shadow: var(--ui-focus-ring); }
.search-box input { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; color: var(--ui-text); font: inherit; font-size: var(--ui-text-md); }
.search-box input:focus-visible { box-shadow: none; }
.facet { min-width: 9.5rem; min-height: 2.5rem; align-items: center; }
.table-wrap { position: relative; overflow-x: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.table { width: 100%; border-collapse: collapse; }
.table th { padding: .625rem var(--ui-space-3); background: var(--ui-bg-subtle); border-bottom: 1px solid var(--ui-border); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; text-align: left; white-space: nowrap; }
.table th:first-child, .table td:first-child { padding-left: var(--ui-space-4); }
.table td { padding: var(--ui-space-3); border-bottom: 1px solid var(--ui-border-subtle); color: var(--ui-text-secondary); vertical-align: middle; }
.table tbody tr:last-child td { border-bottom: 0; }
.table tbody tr:hover td { background: var(--ui-bg-subtle); }
.stale { opacity: .6; }
.col-role { width: 8rem; } .col-status { width: 8rem; } .col-date { width: 9rem; }
.member { display: flex; align-items: center; gap: var(--ui-space-3); color: inherit; text-decoration: none; min-width: 0; }
.avatar { flex: none; display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: 50%; background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); font-weight: 700; font-size: var(--ui-text-sm); }
.member-text { display: grid; gap: 2px; min-width: 0; }
.member-name { color: var(--ui-text); font-weight: 600; overflow-wrap: anywhere; }
.member:hover .member-name { color: var(--ui-accent); text-decoration: underline; text-underline-offset: .18em; }
.you { color: var(--ui-text-muted); font-weight: 400; }
.member-mail { color: var(--ui-text-muted); font-size: var(--ui-text-sm); overflow-wrap: anywhere; }
.role { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-bg-muted); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); font-weight: 600; }
.role.admin { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.status { display: inline-flex; align-items: center; gap: .375rem; font-size: var(--ui-text-sm); white-space: nowrap; }
.status .dot { width: 7px; height: 7px; border-radius: 50%; }
.status.active .dot { background: var(--ui-public-dot); }
.status.pending .dot { background: var(--ui-lagging-dot); }
.status.disabled { color: var(--ui-text-muted); }
.status.disabled .dot { background: var(--ui-private-dot); }
.cell-date { white-space: nowrap; }
.muted { color: var(--ui-text-muted); }
.empty { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-7) var(--ui-space-4); color: var(--ui-text-muted); }
.empty p { margin: 0; }
.pager { display: flex; align-items: center; justify-content: center; gap: var(--ui-space-3); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.invite-form { display: grid; gap: var(--ui-space-4); }
.help { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); line-height: 1.6; }
.field { display: grid; gap: var(--ui-space-2); }
.field > label, legend { font-weight: 600; }
.optional { color: var(--ui-text-muted); font-weight: 400; font-size: var(--ui-text-sm); }
.roles { margin: 0; padding: 0; border: 0; display: grid; gap: var(--ui-space-2); }
.roles legend { margin-bottom: var(--ui-space-2); padding: 0; }
.role-option { display: grid; gap: 2px; padding: var(--ui-space-3); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); cursor: pointer; }
.role-option.on { border-color: var(--ui-accent); background: var(--ui-accent-soft); }
.role-option:has(input:focus-visible) { box-shadow: var(--ui-focus-ring); }
.role-name { font-weight: 600; }
.role-hint { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.actions { display: flex; justify-content: flex-end; gap: var(--ui-space-2); }
@media (max-width: 720px) {
  .table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .table, .table tbody { display: block; }
  .table tbody tr { display: grid; grid-template-columns: auto auto 1fr; grid-template-areas: "member member member" "role status date"; gap: var(--ui-space-2) var(--ui-space-3); padding: var(--ui-space-3) var(--ui-space-4); border-bottom: 1px solid var(--ui-border-subtle); }
  .table tbody tr:last-child { border-bottom: 0; }
  .table td, .table td:first-child { padding: 0; border: 0; }
  .table tbody tr:hover td { background: transparent; }
  .cell-member { grid-area: member; }
  .cell-role { grid-area: role; padding-left: 2.75rem !important; }
  .cell-status { grid-area: status; }
  .cell-date { grid-area: date; justify-self: end; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
  .facet { flex: 1 1 8rem; min-width: 0; }
}
</style>
