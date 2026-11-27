<script setup lang="ts">
// P25c: shown in place of a management page while the site requires admins to use two-factor and this admin
// has not turned it on. The workspace keeps working; setting it up returns here.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { activateUrl } from '../../mfaGate'
import UiIcon from '../components/UiIcon.vue'

const route = useRoute()
const setUp = computed(() => activateUrl(route.fullPath))
</script>

<template>
  <section class="gate" aria-labelledby="mfa-gate-title">
    <span class="shield" aria-hidden="true">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /></svg>
    </span>
    <h1 id="mfa-gate-title">管理員需要開啟雙因素驗證</h1>
    <p>這個網站要求管理員開啟雙因素驗證，才能進入管理中心。管理員可以管理成員、公開內容與系統設定，帳號被盜用的影響比較大。</p>
    <p class="hint"><UiIcon name="info" :size="16" />工作區的文件仍然可以照常閱讀與編輯；只有管理中心要先完成設定，大約一分鐘。</p>
    <div class="actions">
      <RouterLink :to="{ name: 'app-home' }" class="btn">回到工作區</RouterLink>
      <a :href="setUp" class="btn primary">開始設定雙因素驗證</a>
    </div>
  </section>
</template>

<style scoped>
.gate { box-sizing: border-box; max-width: 38rem; margin: var(--ui-space-7) var(--ui-gutter); padding: var(--ui-space-6); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); display: grid; gap: var(--ui-space-3); }
.shield { width: 48px; height: 48px; border-radius: 14px; display: grid; place-items: center; background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
h1 { margin: 0; font-size: var(--ui-text-title); line-height: var(--ui-leading-tight); }
p { margin: 0; color: var(--ui-text-secondary); }
.hint { display: flex; gap: var(--ui-space-2); align-items: flex-start; padding: var(--ui-space-3); border-radius: var(--ui-radius-md); background: var(--ui-accent-soft); font-size: var(--ui-text-sm); }
.hint :deep(svg) { flex: none; margin-top: 3px; color: var(--ui-accent); }
.actions { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); justify-content: flex-end; padding-top: var(--ui-space-2); }
.btn { display: inline-flex; align-items: center; height: 40px; padding: 0 var(--ui-space-4); border-radius: var(--ui-radius-md); border: 1px solid var(--ui-border); color: var(--ui-text); font-weight: 600; text-decoration: none; }
.btn.primary { background: var(--ui-accent); border-color: var(--ui-accent); color: var(--ui-text-inverse, #fff); }
.btn:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
</style>
