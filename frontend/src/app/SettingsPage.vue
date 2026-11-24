<script setup lang="ts">
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { useSession, type Account } from '../stores/session'
import { useTheme, type ThemeMode } from '../stores/theme'
import UiIcon from './components/UiIcon.vue'
import { useSite } from '../stores/site'

const site = useSite()
const session = useSession()
const theme = useTheme()
const toast = useToast()

// ---- Profile ---------------------------------------------------------------------------
const displayName = ref(session.account?.display_name ?? '')
watch(() => session.account?.display_name, value => { displayName.value = value ?? '' })
const saving = ref(false)
const error = ref('')
const dirty = computed(() => displayName.value.trim() !== (session.account?.display_name ?? ''))
async function saveProfile() {
  if (!dirty.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const me = await api<Account>('/api/auth/me', 'PATCH', { display_name: displayName.value.trim() })
    if (session.account) session.account = { ...session.account, display_name: me.display_name }
    toast.add({ severity: 'success', summary: '已更新顯示名稱', life: 2500 })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法儲存顯示名稱。'
  } finally {
    saving.value = false
  }
}
const roleLabel = computed(() => ({ admin: 'Admin', editor: 'Editor', viewer: 'Viewer' })[session.role ?? 'viewer'])
const roleHint = computed(() => ({
  admin: '可以管理成員、集合與標籤、公開文章，以及永久刪除文件。',
  editor: '可以上傳、編輯文件，管理集合與標籤，並把文件移入回收桶。',
  viewer: '可以閱讀、搜尋、下載文件與比較版本。',
})[session.role ?? 'viewer'])
const initial = computed(() => Array.from(session.displayName)[0]?.toUpperCase() ?? '?')

// ---- Appearance ------------------------------------------------------------------------------
const modes: { value: ThemeMode; label: string; icon: 'sun' | 'moon' | 'panel' }[] = [
  { value: 'system', label: '跟隨系統', icon: 'panel' },
  { value: 'light', label: '淺色', icon: 'sun' },
  { value: 'dark', label: '深色', icon: 'moon' },
]

// ---- Security (Django/allauth pages keep their own re-authentication) ----------------------------
const security = [
  { title: '密碼', text: '變更登入密碼。變更後，其他裝置上的登入狀態會失效。', href: '/accounts/password/change/', action: '變更密碼' },
  { title: '雙因素驗證', text: '使用驗證器 App 產生的一次性驗證碼，並管理復原碼。', href: '/accounts/2fa/', action: '管理雙因素驗證' },
  { title: 'Google 帳號', text: '綁定 Google 帳號後，可以用 Google 登入。需要再次驗證身分。', href: '/accounts/3rdparty/', action: '管理綁定' },
]

onMounted(() => site.setTitle('個人設定'))
</script>

<template>
  <div class="page">
    <header class="head">
      <h1>個人設定</h1>
      <p class="subtitle">管理你的顯示名稱、外觀和登入方式。</p>
    </header>

    <section class="card" aria-labelledby="profile-title">
      <div class="card-head">
        <h2 id="profile-title">帳號資料</h2>
      </div>
      <div class="card-body">
        <div class="identity">
          <span class="avatar" aria-hidden="true">{{ initial }}</span>
          <dl class="facts">
            <div><dt>電子郵件</dt><dd>{{ session.account?.email }}</dd></div>
            <div><dt>帳號</dt><dd>{{ session.account?.username }}</dd></div>
            <div><dt>角色</dt><dd><span class="role">{{ roleLabel }}</span><span class="role-hint">{{ roleHint }}</span></dd></div>
          </dl>
        </div>
        <form class="name-form" @submit.prevent="saveProfile">
          <label for="display-name">顯示名稱</label>
          <p class="help">顯示在活動紀錄、文件作者和頭像上。留空時使用帳號名稱。</p>
          <div class="name-row">
            <InputText id="display-name" v-model="displayName" maxlength="150" autocomplete="nickname" class="name-input" />
            <Button type="submit" label="儲存" :loading="saving" :disabled="!dirty" />
          </div>
          <Message v-if="error" severity="error" size="small">{{ error }}</Message>
        </form>
      </div>
    </section>

    <section class="card" aria-labelledby="appearance-title">
      <div class="card-head">
        <h2 id="appearance-title">外觀</h2>
        <p class="card-text">只影響這個瀏覽器。</p>
      </div>
      <div class="card-body">
        <div class="modes" role="radiogroup" aria-labelledby="appearance-title">
          <label v-for="item in modes" :key="item.value" class="mode" :class="{ on: theme.mode === item.value }">
            <input type="radio" name="appearance" class="ui-visually-hidden" :value="item.value" :checked="theme.mode === item.value"
              @change="theme.setMode(item.value)">
            <UiIcon :name="item.icon" :size="18" />
            <span>{{ item.label }}</span>
          </label>
        </div>
      </div>
    </section>

    <section class="card" aria-labelledby="security-title">
      <div class="card-head">
        <h2 id="security-title">登入與安全</h2>
        <p class="card-text">這些設定會開啟帳號安全頁面，部分操作需要再次輸入密碼或驗證碼。</p>
      </div>
      <ul class="rows">
        <li v-for="item in security" :key="item.href" class="row">
          <div class="row-text">
            <strong>{{ item.title }}</strong>
            <span>{{ item.text }}</span>
          </div>
          <a :href="item.href" class="row-action">{{ item.action }}<UiIcon name="chevronRight" :size="16" /></a>
        </li>
      </ul>
    </section>

    <section class="card" aria-labelledby="session-title">
      <div class="card-head">
        <h2 id="session-title">登入狀態</h2>
      </div>
      <div class="card-body session-row">
        <span>在這個瀏覽器登出 {{ site.name }}。</span>
        <a href="/accounts/logout/" class="row-action"><UiIcon name="logout" :size="16" />登出</a>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { box-sizing: border-box; max-width: 52rem; margin-inline: auto; padding: var(--ui-space-6) var(--ui-gutter) var(--ui-space-7); display: grid; gap: var(--ui-space-5); }
.head h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
.subtitle { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.card { border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); }
.card-head { padding: var(--ui-space-4) var(--ui-space-5); border-bottom: 1px solid var(--ui-border-subtle); }
h2 { margin: 0; font-size: 1rem; font-weight: 600; }
.card-text { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.card-body { padding: var(--ui-space-5); display: grid; gap: var(--ui-space-5); }
.identity { display: flex; gap: var(--ui-space-4); align-items: flex-start; }
.avatar { flex: none; display: grid; place-items: center; width: 3rem; height: 3rem; border-radius: 50%; background: var(--ui-accent); color: #fff; font-size: 1.25rem; font-weight: 700; }
.hub-dark .avatar { color: #0c111b; }
.facts { margin: 0; display: grid; gap: var(--ui-space-3); min-width: 0; }
.facts div { display: grid; grid-template-columns: 5rem minmax(0, 1fr); gap: var(--ui-space-3); }
.facts dt { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.facts dd { margin: 0; overflow-wrap: anywhere; display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--ui-space-2); }
.role { padding: 1px var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-size: var(--ui-text-sm); font-weight: 600; }
.role-hint { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.name-form { display: grid; gap: var(--ui-space-2); padding-top: var(--ui-space-5); border-top: 1px solid var(--ui-border-subtle); }
.name-form label { font-weight: 600; }
.help { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.name-row { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); }
.name-input { flex: 1 1 16rem; max-width: 24rem; }
.modes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--ui-space-2); max-width: 30rem; }
.mode {
  display: flex; align-items: center; justify-content: center; gap: var(--ui-space-2); min-height: 2.75rem;
  border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); color: var(--ui-text-secondary); cursor: pointer;
}
.mode:hover { border-color: var(--ui-text-muted); }
.mode.on { border-color: var(--ui-accent); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-weight: 600; }
.mode:has(input:focus-visible) { box-shadow: var(--ui-focus-ring); }
.rows { list-style: none; margin: 0; padding: 0; }
.row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-space-3); padding: var(--ui-space-4) var(--ui-space-5); border-bottom: 1px solid var(--ui-border-subtle); }
.row:last-child { border-bottom: 0; }
.row-text { display: grid; gap: 2px; min-width: 0; flex: 1 1 18rem; }
.row-text span { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.row-action {
  display: inline-flex; align-items: center; gap: var(--ui-space-1); min-height: 2.25rem; padding: 0 var(--ui-space-3);
  border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); color: var(--ui-text-secondary);
  font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; white-space: nowrap;
}
.row-action:hover { border-color: var(--ui-text-muted); color: var(--ui-text); }
.session-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-space-3); color: var(--ui-text-secondary); }
@media (max-width: 560px) {
  .identity { flex-direction: column; }
  .facts div { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .modes { grid-template-columns: minmax(0, 1fr); }
}
</style>
