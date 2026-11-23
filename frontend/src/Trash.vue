<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { onMounted, ref, watch } from 'vue'

type Document = {
  id: string
  title: string
  format: 'md' | 'html'
  category: string | null
  trashed_at: string
  version_count: number
}

const rows = ref<Document[]>([])
const count = ref(0)
const page = ref(1)
const pageSize = ref(25)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const noticePending = ref(false)
const role = ref('')
const csrf = ref('')
const selected = ref<Document>()
const typedTitle = ref('')
const submitting = ref(false)
const confirmationError = ref('')
const dateTime = new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/trash/?page=${page.value}`, { cache: 'no-store' })
    if (response.status === 403) throw new Error('只有 Admin 和 Editor 可以管理回收桶。')
    if (!response.ok) throw new Error('無法載入回收桶。')
    const data = await response.json()
    rows.value = data.results
    count.value = data.count
    pageSize.value = data.page_size
    if (!rows.value.length && page.value > 1) page.value = Math.max(1, Math.ceil(count.value / pageSize.value))
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '無法載入回收桶。'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const response = await fetch('/api/auth/me', { cache: 'no-store' })
    if (response.status === 403) {
      window.location.assign('/accounts/login/?next=/library/trash/')
      return
    }
    if (!response.ok) throw new Error()
    const account = await response.json()
    role.value = account.role
    csrf.value = account.csrf_token
    await load()
  } catch {
    loading.value = false
    error.value = '無法確認登入狀態，請重新整理頁面。'
  }
})
watch(page, load)

function confirmDelete(document: Document) {
  selected.value = document
  typedTitle.value = ''
  confirmationError.value = ''
}

async function act(document: Document, action: 'restore' | 'delete') {
  if (submitting.value || (action === 'delete' && typedTitle.value !== document.title)) return
  submitting.value = true
  confirmationError.value = ''
  notice.value = ''
  try {
    const response = await fetch(`/api/trash/${document.id}/${action}/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf.value },
      body: JSON.stringify(action === 'delete' ? { title: typedTitle.value, confirm: true } : {}),
    })
    const body = response.status === 204 ? null : await response.json().catch(() => null)
    if (!response.ok) throw new Error(body?.detail || '無法完成操作。')
    noticePending.value = response.status === 202
    notice.value = noticePending.value ? body.detail
      : action === 'delete' ? `已永久刪除「${document.title}」。` : `已將「${document.title}」和所有版本還原到知識總覽。`
    selected.value = undefined
    await load()
  } catch (failure) {
    const reason = failure instanceof Error ? failure.message : '無法完成操作。'
    if (selected.value) confirmationError.value = reason
    else error.value = reason
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <header>
    <RouterLink to="/" class="site-brand">Knowledge Hub</RouterLink>
    <RouterLink to="/library/">知識總覽</RouterLink>
  </header>
  <main class="trash">
    <h1>回收桶</h1>
    <p>還原會將文件及其所有版本移回知識總覽。</p>
    <Message v-if="notice" :severity="noticePending ? 'warn' : 'success'">{{ notice }}</Message>
    <Message v-if="error" severity="error">{{ error }}</Message>
    <p v-else-if="loading" role="status">正在載入文件。</p>
    <p v-else-if="!rows.length">回收桶沒有文件。</p>
    <ul v-else class="trash-list">
      <li v-for="doc in rows" :key="doc.id">
        <div>
          <strong>{{ doc.title }}</strong>
          <Tag :value="doc.format === 'html' ? 'HTML' : 'Markdown'" severity="secondary" />
          <p>{{ doc.category ?? '未分類' }} · {{ doc.version_count }} 個版本 · {{ dateTime.format(new Date(doc.trashed_at)) }}</p>
        </div>
        <div class="trash-actions">
          <Button label="還原" outlined :disabled="submitting" @click="act(doc, 'restore')" />
          <Button v-if="role === 'admin'" label="永久刪除" severity="danger" text :disabled="submitting"
            @click="confirmDelete(doc)" />
        </div>
      </li>
    </ul>
    <nav v-if="count > pageSize" aria-label="回收桶分頁" class="trash-actions">
      <Button v-if="page > 1" label="上一頁" text @click="page--" />
      <span>第 {{ page }} 頁</span>
      <Button v-if="page * pageSize < count" label="下一頁" text @click="page++" />
    </nav>
    <Dialog :visible="!!selected" header="確認永久刪除" modal :closable="!submitting" :close-on-escape="!submitting"
      :style="{ width: 'min(94vw, 34rem)' }" @update:visible="visible => { if (!visible && !submitting) selected = undefined }">
      <form v-if="selected" class="confirmation" @submit.prevent="act(selected, 'delete')">
        <p>將永久刪除「{{ selected.title }}」以及全部 {{ selected.version_count }} 個版本。這個動作無法復原。</p>
        <label for="permanent-title">輸入完整文件標題以確認</label>
        <InputText id="permanent-title" v-model="typedTitle" autocomplete="off" :disabled="submitting" />
        <Message v-if="confirmationError" severity="error">{{ confirmationError }}</Message>
        <Button type="submit" label="確認永久刪除" severity="danger" :disabled="typedTitle !== selected.title" :loading="submitting" />
      </form>
    </Dialog>
  </main>
</template>

<style scoped>
.trash { max-width: 62rem; }
.trash-list { list-style: none; padding: 0; display: grid; gap: .65rem; }
.trash-list li { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; padding: 1rem; background: white; border: 1px solid #dfe6f0; border-radius: .65rem; }
.trash-list strong { overflow-wrap: anywhere; margin-right: .65rem; }
.trash-list p { margin: .55rem 0 0; color: #52647c; }
.trash-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; }
.confirmation { display: grid; gap: .7rem; }
.confirmation button { justify-self: end; }
</style>
