<script setup lang="ts">
// P24c: 關於 — the software, its developer and support links, the licence and terms, and who accepted them.
import Skeleton from 'primevue/skeleton'
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import DeveloperCard from '../../setup/DeveloperCard.vue'
import type { About } from '../../setup/setup'
import { useSite } from '../../stores/site'
import { longDateTime } from '../types'

type Accepted = { by: string | null; at: string; via: string; terms_version: number | null }
const site = useSite()
const about = ref<About & { accepted: Accepted[] }>()
const error = ref('')

onMounted(async () => {
  site.setTitle('關於')
  try {
    about.value = await api('/api/admin/about/')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法載入。'
  }
})
const via = (value: string) => value === 'setup' ? '首次設定精靈' : '主機指令'
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>關於</h1>
        <p class="subtitle">版本、開發者、授權與條款。</p>
      </div>
    </header>
    <p v-if="error" class="note">{{ error }}</p>
    <Skeleton v-else-if="!about" height="14rem" />
    <template v-else>
      <section class="card" aria-labelledby="about-dev">
        <h2 id="about-dev">開發者</h2>
        <DeveloperCard :about="about" />
        <p class="note">Knowledge Hub 是開源專案。贊助連結開通前顯示「即將開放」。</p>
      </section>
      <section class="card" aria-labelledby="about-terms">
        <div class="terms-head">
          <h2 id="about-terms">使用說明與授權條款</h2>
          <span class="version">條款版本 {{ about.terms_version }}</span>
        </div>
        <div class="terms" tabindex="0" aria-labelledby="about-terms">
          <template v-for="part in about.terms" :key="part.title"><h3>{{ part.title }}</h3><p>{{ part.body }}</p></template>
        </div>
        <div class="accepted">
          <h3>同意紀錄</h3>
          <ul v-if="about.accepted.length">
            <li v-for="row in about.accepted" :key="row.at">
              <strong>{{ row.by ?? '（帳號已刪除）' }}</strong>
              <span>{{ longDateTime(row.at) }} · 透過{{ via(row.via) }}{{ row.terms_version ? ` · 同意條款版本 ${row.terms_version}` : ' · 當時尚無條款' }}</span>
            </li>
          </ul>
          <p v-else class="note">沒有紀錄。</p>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped src="./systemPages.css"></style>
<style scoped>
.page { max-width: 60rem; }
.card { display: grid; gap: var(--ui-space-3); }
.card h2 { margin: 0; font-size: var(--ui-text-md); }
.terms-head { display: flex; justify-content: space-between; align-items: baseline; gap: var(--ui-space-3); }
.version { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.terms { padding: var(--ui-space-4); border-radius: var(--ui-radius-md); background: var(--ui-bg-subtle); border: 1px solid var(--ui-border-subtle);
  display: grid; gap: var(--ui-space-2); color: var(--ui-text-secondary); font-size: var(--ui-text-sm); line-height: 1.75; }
.terms h3, .accepted h3 { margin: var(--ui-space-1) 0 0; font-size: var(--ui-text-sm); color: var(--ui-text); }
.terms p { margin: 0; white-space: pre-line; }
.terms:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.accepted ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--ui-space-2); }
.accepted li { display: grid; gap: 2px; font-size: var(--ui-text-sm); }
.accepted li span { color: var(--ui-text-muted); }
</style>
