<script setup lang="ts">
// P25c: 網站設定 › 帳號安全 — require admins to use two-factor.
import Message from 'primevue/message'
import ToggleSwitch from 'primevue/toggleswitch'
import { useToast } from 'primevue/usetoast'
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import { activateUrl } from '../../mfaGate'
import { useSession } from '../../stores/session'

type Security = { require_admin_mfa: boolean; admins: number; admins_without_mfa: number }
const toast = useToast()
const session = useSession()
const data = ref<Security>()
const saving = ref(false)
const error = ref('')

onMounted(async () => {
  try { data.value = await api<Security>('/api/admin/security/') } catch (cause) { error.value = cause instanceof Error ? cause.message : '無法載入。' }
})

async function change(value: boolean) {
  if (!data.value) return
  saving.value = true
  error.value = ''
  try {
    data.value = await api<Security>('/api/admin/security/', 'PUT', { require_admin_mfa: value })
    toast.add({ severity: 'success', summary: value ? '已要求管理員開啟雙因素驗證' : '已取消要求', life: 2500 })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法儲存。'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section id="security" class="card" aria-labelledby="security-title">
    <h2 id="security-title">帳號安全</h2>
    <div v-if="data" class="toggle-row">
      <label for="require-admin-mfa" class="toggle-text">
        <strong>要求管理員開啟雙因素驗證</strong>
        <span>開啟後，還沒有雙因素驗證的管理員要先完成設定，才能使用管理中心與管理功能；工作區不受影響。</span>
      </label>
      <ToggleSwitch :model-value="data.require_admin_mfa" input-id="require-admin-mfa" :disabled="saving || (!data.require_admin_mfa && !session.mfa?.enabled)"
        @update:model-value="change" />
    </div>
    <p v-if="data && !data.require_admin_mfa && !session.mfa?.enabled" class="note">
      請先<a :href="activateUrl()">為自己的帳號開啟雙因素驗證</a>，才能要求所有管理員開啟。
    </p>
    <p v-if="data" class="note">
      {{ data.admins }} 位管理員中，{{ data.admins_without_mfa ? `有 ${data.admins_without_mfa} 位尚未開啟。` : '全部都已開啟。' }}
    </p>
    <p class="note">手機與復原碼都遺失時，由其他管理員在「成員管理」重設；只有一位管理員時，在主機上執行 <code>reset_hub_mfa &lt;Email&gt; --reason "…"</code>。</p>
    <Message v-if="error" severity="error" size="small">{{ error }}</Message>
  </section>
</template>

<style scoped src="./systemPages.css"></style>
<style scoped>
.toggle-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--ui-space-3); align-items: center; }
.toggle-text { display: grid; gap: 2px; cursor: pointer; }
.toggle-text span { color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.card h2 { margin: 0; }
</style>
