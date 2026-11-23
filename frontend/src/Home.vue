<script setup lang="ts">
import Button from 'primevue/button'
import { onMounted, ref } from 'vue'

type Account = { display_name: string; username: string; role: string }

const account = ref<Account | null>(null)
const accountReady = ref(false)

async function loadAccount() {
  try {
    const response = await fetch('/api/auth/me', { cache: 'no-store', signal: AbortSignal.timeout(5000) })
    if (response.ok) account.value = await response.json()
    accountReady.value = response.ok || response.status === 403
  } catch {
    accountReady.value = false
  }
}

const checking = ref(false)
const status = ref('等待檢查')

async function checkHealth() {
  checking.value = true
  status.value = '正在檢查後端與資料庫'

  try {
    const response = await fetch('/api/health', {
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    })
    if (!response.ok) throw new Error('Health check failed')
    const result = await response.json()
    status.value = result.status === 'ok' ? '後端與資料庫運作正常' : '後端或資料庫暫時無法使用'
  } catch {
    status.value = '後端或資料庫暫時無法使用'
  } finally {
    checking.value = false
  }
}

onMounted(() => {
  void loadAccount()
  void checkHealth()
})
</script>

<template>
  <header>
    <span>Knowledge Hub</span>
    <nav v-if="accountReady" aria-label="帳號">
      <template v-if="account">
        <a href="/accounts/profile/">{{ account.display_name || account.username }}</a>
        <a v-if="account.role === 'admin'" href="/accounts/manage/">帳號管理</a>
        <a href="/accounts/logout/">登出</a>
      </template>
      <a v-else href="/accounts/login/">登入</a>
    </nav>
  </header>
  <main>
    <h1>系統狀態</h1>
    <p role="status">{{ status }}</p>
    <Button label="重新檢查" :disabled="checking" @click="checkHealth" />
  </main>
</template>

<style>
body {
  margin: 0;
  background: #f5f7fb;
  color: #152b49;
  font-family: system-ui, sans-serif;
}
header {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  justify-content: space-between;
  background: #102a51;
  color: white;
  font-weight: 700;
  padding: 1rem max(1.5rem, calc((100% - 48rem) / 2));
}
nav {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}
header a {
  color: inherit;
}
main {
  max-width: 45rem;
  margin: 2rem auto;
  padding: 0 1.5rem;
}
</style>
