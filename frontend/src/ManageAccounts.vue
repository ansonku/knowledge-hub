<script setup lang="ts">
import Button from 'primevue/button'
import Card from 'primevue/card'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

type Account = {
  id: string
  username: string
  email: string
  role: string
  is_active: boolean
  pending_activation: boolean
}
type Context = {
  csrf_token: string
  roles: [string, string][]
  notices: { text: string; warning: boolean }[]
}
type Listing = Context & { results: Account[]; count: number; page: number; page_count: number }
type Detail = Context & {
  account: Account
  actions: [string, string][]
  audit: { id: number; action: string; created_at: string; actor: string | null; reason: string | null }[]
}

const route = useRoute()
const base = '/accounts/manage/'
const userId = typeof route.params.id === 'string' ? route.params.id : ''
const formUrl = userId ? `${base}${userId}/` : base
const listing = ref<Listing>()
const detail = ref<Detail>()
const context = computed(() => listing.value ?? detail.value)
const loading = ref(true)
const error = ref('')
const role = ref('viewer')
const action = ref('')
const reason = ref('')
const verified = ref(false)
const options = (choices: [string, string][] = []) => choices.map(([value, label]) => ({ value, label }))
const roleOptions = computed(() => options(context.value?.roles))
const actionOptions = computed(() => options(detail.value?.actions))
const formatter = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short' })

function status(account: Account) {
  if (account.pending_activation) return { label: '待啟用', severity: 'warn' }
  if (account.is_active) return { label: '使用中', severity: 'success' }
  return { label: '已停用', severity: 'secondary' }
}

async function load() {
  try {
    const url = userId ? `/api/users/${encodeURIComponent(userId)}/` : `/api/users/${location.search}`
    const response = await fetch(url, { cache: 'no-store' })
    if (response.status === 403) {
      const session = await fetch('/api/auth/me', { cache: 'no-store' })
      if (session.status === 403) {
        window.location.assign(`/accounts/login/?next=${encodeURIComponent(formUrl)}`)
        return
      }
      error.value = '只有管理員可以管理帳號。'
      return
    }
    if (response.status === 404) {
      error.value = '找不到這個帳號。'
      return
    }
    if (!response.ok) throw new Error()
    if (userId) {
      const result: Detail = await response.json()
      detail.value = result
      role.value = result.account.role
    } else {
      listing.value = await response.json() as Listing
    }
  } catch {
    error.value = '無法載入帳號管理，請重新整理頁面。'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <header class="admin-header">
    <a href="/" class="site-brand">Knowledge Hub</a>
    <nav aria-label="帳號">
      <a href="/accounts/profile/">個人設定</a>
      <a href="/accounts/logout/">登出</a>
    </nav>
  </header>

  <main class="admin-main">
    <a v-if="userId" :href="base">返回帳號清單</a>
    <h1>{{ detail ? `管理 ${detail.account.username}` : '帳號管理' }}</h1>
    <ProgressSpinner v-if="loading" aria-label="正在載入帳號管理" />
    <Message v-else-if="error" severity="error">{{ error }}</Message>
    <template v-if="context">
      <Message v-for="(notice, index) in context.notices" :key="index" :severity="notice.warning ? 'warn' : 'success'">
        {{ notice.text }}
      </Message>
    </template>

    <template v-if="listing">
      <Card>
        <template #title>使用者</template>
        <template #content>
          <DataTable :value="listing.results" data-key="id" table-style="min-width: 30rem">
            <template #empty>目前沒有使用者。</template>
            <Column header="帳號">
              <template #body="{ data }"><a :href="`${base}${data.id}/`">{{ data.username }}</a></template>
            </Column>
            <Column field="email" header="電子郵件" />
            <Column field="role" header="角色" />
            <Column header="狀態">
              <template #body="{ data }"><Tag :value="status(data).label" :severity="status(data).severity" /></template>
            </Column>
          </DataTable>
          <nav class="pagination" aria-label="使用者分頁">
            <Button v-if="listing.page > 1" as="a" :href="`?page=${listing.page - 1}`" label="上一頁" outlined />
            <span>第 {{ listing.page }} 頁，共 {{ listing.page_count }} 頁</span>
            <Button v-if="listing.page < listing.page_count" as="a" :href="`?page=${listing.page + 1}`" label="下一頁" outlined />
          </nav>
        </template>
      </Card>
      <Card>
        <template #title>邀請使用者</template>
        <template #content>
          <form :action="formUrl" method="post" class="form-grid">
            <input type="hidden" name="csrfmiddlewaretoken" :value="listing.csrf_token">
            <label for="username">帳號名稱</label>
            <InputText id="username" name="username" maxlength="150" required fluid />
            <label for="email">電子郵件</label>
            <InputText id="email" name="email" type="email" maxlength="254" required fluid />
            <label for="display-name">顯示名稱</label>
            <InputText id="display-name" name="display_name" maxlength="150" fluid />
            <label for="invite-role">角色</label>
            <Select v-model="role" input-id="invite-role" :options="roleOptions" option-label="label" option-value="value" fluid />
            <input type="hidden" name="role" :value="role">
            <Button type="submit" label="建立帳號並寄送啟用信" />
          </form>
        </template>
      </Card>
    </template>

    <template v-if="detail">
      <Card>
        <template #title>帳號資料</template>
        <template #content>
          <p>{{ detail.account.email }} · {{ detail.account.role }} · <Tag :value="status(detail.account).label" :severity="status(detail.account).severity" /></p>
          <form :action="formUrl" method="post" class="form-grid">
            <input type="hidden" name="csrfmiddlewaretoken" :value="detail.csrf_token">
            <label for="action">操作</label>
            <Select v-model="action" input-id="action" :options="actionOptions" option-label="label" option-value="value" placeholder="選擇操作" fluid />
            <input type="hidden" name="action" :value="action">
            <template v-if="action === 'role'">
              <label for="new-role">新角色</label>
              <Select v-model="role" input-id="new-role" :options="roleOptions" option-label="label" option-value="value" fluid />
              <input type="hidden" name="role" :value="role">
            </template>
            <template v-if="action === 'mfa'">
              <label for="reason">重設理由</label>
              <Textarea id="reason" v-model="reason" name="reason" maxlength="500" required auto-resize fluid />
              <div class="verification">
                <Checkbox v-model="verified" input-id="verified" binary />
                <label for="verified">已透過獨立管道核對對方身分</label>
                <input v-if="verified" type="hidden" name="verified" value="on">
              </div>
            </template>
            <Button type="submit" label="執行操作" :disabled="!action || (action === 'mfa' && (!verified || !reason.trim()))" :severity="action === 'disable' || action === 'mfa' ? 'danger' : 'primary'" />
          </form>
        </template>
      </Card>
      <Card>
        <template #title>最近的帳號活動</template>
        <template #content>
          <DataTable :value="detail.audit" data-key="id" table-style="min-width: 28rem">
            <template #empty>目前沒有活動。</template>
            <Column header="時間">
              <template #body="{ data }">{{ formatter.format(new Date(data.created_at)) }}</template>
            </Column>
            <Column header="操作者">
              <template #body="{ data }">{{ data.actor ?? '系統' }}</template>
            </Column>
            <Column field="action" header="操作" />
            <Column field="reason" header="理由" />
          </DataTable>
        </template>
      </Card>
    </template>
  </main>
</template>

<style scoped>
.admin-header nav, .pagination, .verification { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }
.admin-main { max-width: 58rem; display: grid; gap: 1.25rem; }
.admin-main h1 { margin: 0; font-size: clamp(1.75rem, 4vw, 2.35rem); }
.form-grid { display: grid; gap: .65rem; max-width: 34rem; }
.form-grid > button { justify-self: start; margin-top: .4rem; }
.pagination { margin-top: 1rem; }
</style>
