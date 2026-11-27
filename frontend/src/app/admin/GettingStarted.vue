<script setup lang="ts">
// P24c: the getting-started card at the top of the management centre, for admins of a new site.
// Ticks come from the site's data; closing it is remembered in this browser.
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api } from '../../api'
import { activateUrl } from '../../mfaGate'
import { useSession } from '../../stores/session'
import UiIcon from '../components/UiIcon.vue'

type Tasks = { admin: boolean; members: boolean; collections: boolean; documents: boolean; mfa: boolean }
const session = useSession()
const route = useRoute()
const tasks = ref<Tasks>()
const key = computed(() => `knowledge-hub.app.getting-started-closed.${session.account?.id ?? ''}`)
const closed = ref(false)

onMounted(async () => {
  try { closed.value = localStorage.getItem(key.value) === '1' } catch { /* storage may be disabled */ }
  if (closed.value || !session.isAdmin) return
  try {
    tasks.value = (await api<{ tasks: Tasks }>('/api/admin/getting-started/')).tasks
  } catch { /* the card is optional */ }
})

const ITEMS: { key: keyof Tasks; title: string; text: string; action?: string; to?: string; href?: string }[] = [
  { key: 'admin', title: '建立管理員帳號', text: '首次設定時已完成。' },
  { key: 'members', title: '邀請成員', text: '寄出邀請，指定 Editor 或 Viewer。', action: '前往成員管理', to: 'app-members' },
  { key: 'collections', title: '建立集合', text: '先規劃分類，例如操作指南、規格書。', action: '新增集合', to: 'app-taxonomy' },
  { key: 'documents', title: '上傳第一份文件', text: '拖入 .md、.html，或直接新增 Markdown。', action: '前往全部文件', to: 'app-library' },
  { key: 'mfa', title: '開啟雙因素驗證', text: '為管理員帳號多加一層保護。', action: '設定雙因素驗證', href: activateUrl('/app/admin/') },
]
const done = computed(() => tasks.value ? ITEMS.filter(item => tasks.value![item.key]).length : 0)
// Only a new site gets the card: once members, collections and documents exist it stays away, even without
// two-factor (that one is a suggestion on the list, not a reason to keep showing the card).
const settingUp = computed(() => !!tasks.value && !(tasks.value.members && tasks.value.collections && tasks.value.documents))
const visible = computed(() => !closed.value && settingUp.value && route.name !== 'app-about')

function close() {
  closed.value = true
  try { localStorage.setItem(key.value, '1') } catch { /* storage may be disabled */ }
}
</script>

<template>
  <section v-if="visible" class="welcome" aria-labelledby="getting-started-title">
    <div class="top">
      <div>
        <h2 id="getting-started-title">歡迎使用 Knowledge Hub</h2>
        <p>完成以下幾件事，就可以開始和團隊一起使用。</p>
      </div>
      <button type="button" class="close" aria-label="關閉開始使用卡片" @click="close"><UiIcon name="close" :size="16" /></button>
    </div>
    <div class="progress">
      <span>{{ done }}／{{ ITEMS.length }} 完成</span>
      <span class="bar" role="progressbar" :aria-valuenow="done" aria-valuemin="0" :aria-valuemax="ITEMS.length" aria-label="開始使用進度"><span :style="{ width: `${done / ITEMS.length * 100}%` }" /></span>
    </div>
    <ul class="tasks">
      <li v-for="item in ITEMS" :key="item.key" :class="{ done: tasks?.[item.key] }">
        <span class="tick" aria-hidden="true"><UiIcon v-if="tasks?.[item.key]" name="check" :size="13" /></span>
        <div>
          <strong>{{ item.title }}<span class="sr-only">{{ tasks?.[item.key] ? '（已完成）' : '（未完成）' }}</span></strong>
          <span>{{ item.text }}</span>
          <template v-if="!tasks?.[item.key] && item.action">
            <RouterLink v-if="item.to" :to="{ name: item.to }" class="go">{{ item.action }} →</RouterLink>
            <a v-else :href="item.href" class="go">{{ item.action }} →</a>
          </template>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.welcome { margin: var(--ui-space-5) var(--ui-gutter) 0; max-width: 100rem; box-sizing: border-box; padding: var(--ui-space-5); border-radius: var(--ui-radius-lg);
  border: 1px solid color-mix(in srgb, var(--ui-accent) 30%, var(--ui-border)); background: linear-gradient(135deg, var(--ui-accent-soft), var(--ui-bg-surface) 65%);
  display: grid; gap: var(--ui-space-4); }
.top { display: flex; justify-content: space-between; gap: var(--ui-space-3); align-items: start; }
h2 { margin: 0; font-size: var(--ui-text-lg); }
.top p { margin: var(--ui-space-1) 0 0; color: var(--ui-text-secondary); }
.close { border: 0; background: none; color: var(--ui-text-muted); padding: 6px; border-radius: var(--ui-radius-sm); cursor: pointer; }
.close:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.progress { display: flex; align-items: center; gap: var(--ui-space-3); font-size: var(--ui-text-xs); color: var(--ui-text-muted); font-variant-numeric: tabular-nums; }
.bar { flex: 1; max-width: 14rem; height: 6px; border-radius: 6px; background: var(--ui-border); overflow: hidden; }
.bar span { display: block; height: 100%; background: var(--ui-public-dot, #16a34a); border-radius: inherit; transition: width .3s; }
.tasks { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr)); gap: var(--ui-space-2); }
.tasks li { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: var(--ui-space-2); align-items: start; padding: var(--ui-space-3); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); border: 1px solid var(--ui-border); }
.tick { width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid var(--ui-border-strong, var(--ui-border)); display: grid; place-items: center; color: transparent; }
.done .tick { background: var(--ui-public-dot, #16a34a); border-color: var(--ui-public-dot, #16a34a); color: #fff; }
.tasks strong { display: block; font-size: var(--ui-text-sm); }
.done strong { color: var(--ui-text-muted); text-decoration: line-through; }
.tasks span { color: var(--ui-text-secondary); font-size: var(--ui-text-xs); }
.go { display: inline-block; margin-top: 4px; color: var(--ui-accent); font-size: var(--ui-text-xs); font-weight: 600; text-decoration: none; }
.go:hover { text-decoration: underline; }
.close:focus-visible, .go:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
