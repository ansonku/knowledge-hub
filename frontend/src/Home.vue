<script setup lang="ts">
import Button from 'primevue/button'
import { onMounted, ref } from 'vue'

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

onMounted(checkHealth)
</script>

<template>
  <header>AI Knowledge Hub</header>
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
  background: #102a51;
  color: white;
  font-weight: 700;
  padding: 1rem max(1.5rem, calc((100% - 48rem) / 2));
}
main {
  max-width: 45rem;
  margin: 2rem auto;
  padding: 0 1.5rem;
}
button {
  border: 0;
  border-radius: .4rem;
  background: #074cc1;
  color: white;
  padding: .65rem 1rem;
  font: inherit;
  cursor: pointer;
}
button:disabled {
  opacity: .65;
  cursor: wait;
}
</style>
