<script setup lang="ts">
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import { onMounted, ref } from 'vue'

type Profile = {
  username: string
  email: string
  role: string
  display_name: string
  csrf_token: string
}

const profile = ref<Profile>()
const displayName = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)

async function loadProfile() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/auth/me', { cache: 'no-store' })
    if (response.status === 403) {
      window.location.assign('/accounts/login/?next=/accounts/profile/')
      return
    }
    if (!response.ok) throw new Error()
    profile.value = await response.json() as Profile
    displayName.value = profile.value.display_name
  } catch {
    error.value = '無法載入個人設定，請再試一次。'
  } finally {
    loading.value = false
  }
}

async function saveProfile() {
  if (!profile.value || saving.value) return
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    const response = await fetch('/api/auth/me', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': profile.value.csrf_token,
      },
      body: JSON.stringify({ display_name: displayName.value }),
    })
    if (response.status === 403) {
      error.value = '登入狀態已變更，請重新整理頁面後再試。'
      return
    }
    if (!response.ok) throw new Error()
    profile.value = await response.json() as Profile
    displayName.value = profile.value.display_name
    saved.value = true
  } catch {
    error.value = '無法儲存顯示名稱，請再試一次。'
  } finally {
    saving.value = false
  }
}

onMounted(loadProfile)
</script>

<template>
  <div class="profile-page">
    <a class="skip-link" href="#main-content">跳至內容</a>
    <header class="site-header profile-header">
      <RouterLink to="/" class="site-brand">Knowledge Hub</RouterLink>
      <nav v-if="profile" aria-label="帳號">
        <a v-if="profile.role === 'admin'" href="/accounts/manage/">帳號管理</a>
        <a href="/accounts/logout/">登出</a>
      </nav>
    </header>

    <main id="main-content" tabindex="-1" class="management-main profile-content">
      <h1>個人設定</h1>
      <ProgressSpinner v-if="loading" aria-label="正在載入個人設定" />
      <template v-else-if="profile">
        <Card>
          <template #title>帳號資料</template>
          <template #content>
            <dl class="account-fields">
              <div><dt>電子郵件</dt><dd>{{ profile.email }}</dd></div>
              <div><dt>角色</dt><dd><Tag :value="profile.role" severity="secondary" /></dd></div>
            </dl>
            <form class="profile-form" @submit.prevent="saveProfile">
              <label for="display-name">顯示名稱</label>
              <InputText id="display-name" v-model="displayName" maxlength="150" autocomplete="nickname" fluid />
              <Message v-if="error" severity="error">{{ error }}</Message>
              <Message v-if="saved" severity="success">已儲存顯示名稱。</Message>
              <Button type="submit" label="儲存變更" :loading="saving" :disabled="displayName === profile.display_name" />
            </form>
          </template>
        </Card>
        <Card>
          <template #title>登入與安全性</template>
          <template #content>
            <div class="security-links">
              <Button as="a" href="/accounts/password/change/" label="變更密碼" severity="secondary" outlined />
              <Button as="a" href="/accounts/3rdparty/" label="Google 帳號綁定" severity="secondary" outlined />
              <Button as="a" href="/accounts/2fa/" label="雙因素驗證" severity="secondary" outlined />
            </div>
          </template>
        </Card>
      </template>
      <template v-else>
        <Message severity="error">{{ error }}</Message>
        <Button label="重新載入" @click="loadProfile" />
      </template>
    </main>
  </div>
</template>

<style scoped>
.profile-page { min-height: 100vh; background: #f5f7fb; }
.profile-header nav, .security-links { display: flex; flex-wrap: wrap; gap: .75rem; }
.profile-content { display: grid; gap: 1.25rem; }
.account-fields { display: flex; flex-wrap: wrap; gap: 1rem 2rem; margin: 0 0 1.5rem; }
.account-fields dt { color: #42536a; font-size: .875rem; }
.account-fields dd { margin: .25rem 0 0; overflow-wrap: anywhere; }
.profile-form { display: grid; justify-items: start; gap: .65rem; }
.profile-form label { font-weight: 600; }
.profile-form button { margin-top: .4rem; }
</style>
