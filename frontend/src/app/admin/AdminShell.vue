<script setup lang="ts">
// P19 (E2＋): the frame of every management page — a two-row menu (groups, then the group's pages) that
// sticks to the top while scrolling, with marks where something needs attention. The page renders below.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MfaRequired from './MfaRequired.vue'
import { mfaBlocked } from '../../mfaGate'
import GettingStarted from './GettingStarted.vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useAttention } from '../../stores/attention'
import { useSession } from '../../stores/session'
import { groupOf, groupsFor, lastPageOfGroup, pageOf, rememberAdminPage } from './adminNav'
import UiIcon from '../components/UiIcon.vue'

const route = useRoute()
const router = useRouter()
const session = useSession()
const mfaHeld = computed(() => session.isAdmin && (!!session.mfa?.required || mfaBlocked.value))
const attention = useAttention()
const groups = computed(() => groupsFor(session.canEdit, session.isAdmin))
const routeName = computed(() => String(route.name ?? ''))
const roleLabel = computed(() => session.isAdmin ? 'Admin' : 'Editor')
const currentGroup = computed(() => groupOf(groups.value, routeName.value))
const currentPage = computed(() => pageOf(groups.value, routeName.value))
const groupMark = (name: string) => groups.value.find(group => group.name === name)?.pages.some(page => attention.markOf(page.name))

watch(routeName, () => {
  if (currentGroup.value && currentPage.value) rememberAdminPage(currentGroup.value.name, currentPage.value.name)
}, { immediate: true })

// Phones pick the group from a list; wider screens show the groups as a row.
const narrow = window.matchMedia('(max-width: 640px)')
const phone = ref(narrow.matches)
const onNarrow = (event: MediaQueryListEvent) => { phone.value = event.matches }
function pickGroup(event: Event) {
  const group = groups.value.find(item => item.name === (event.target as HTMLSelectElement).value)
  if (group) void router.push({ name: lastPageOfGroup(group) })
}

// Smaller once the page scrolls under it.
const compact = ref(false)
const onScroll = () => { compact.value = window.scrollY > 24 }

// /app/admin/site/#notice (from Ctrl+K): bring that card into view and mark it for a moment.
function revealHash() {
  const id = route.hash.slice(1)
  if (!id) return
  window.setTimeout(() => {
    const target = document.getElementById(id)
    if (!target) return
    target.scrollIntoView({ block: 'start' })
    target.classList.add('admin-flash')
    window.setTimeout(() => target.classList.remove('admin-flash'), 1800)
  }, 250)
}
watch(() => route.fullPath, () => void nextTick(revealHash))

onMounted(() => {
  narrow.addEventListener('change', onNarrow)
  window.addEventListener('scroll', onScroll, { passive: true })
  void attention.load()
  revealHash()
})
onBeforeUnmount(() => {
  narrow.removeEventListener('change', onNarrow)
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div class="admin-shell">
    <div v-if="currentGroup" class="admin-nav" :class="{ compact }">
      <!-- A clear title for the management area (P19 E2＋). -->
      <header class="admin-head">
        <span class="admin-icon" aria-hidden="true"><UiIcon name="sliders" :size="18" /></span>
        <span class="admin-title">
          <strong>管理中心</strong>
          <small>{{ session.isAdmin ? '內容、成員與系統的管理' : '文件內容的管理' }}</small>
        </span>
        <span class="role" :title="`目前身分：${roleLabel}`">{{ roleLabel }}</span>
      </header>
      <template v-if="groups.length > 1">
        <label v-if="phone" class="group-pick">
          <span class="ui-visually-hidden">管理分組</span>
          <select :value="currentGroup.name" @change="pickGroup">
            <option v-for="group in groups" :key="group.name" :value="group.name">{{ group.name }}{{ groupMark(group.name) ? ' •' : '' }}</option>
          </select>
        </label>
        <nav v-else class="groups" aria-label="管理分組">
          <RouterLink v-for="group in groups" :key="group.name" :to="{ name: lastPageOfGroup(group) }" class="group"
            :class="{ on: group.name === currentGroup.name }" :aria-current="group.name === currentGroup.name ? 'true' : undefined">
            {{ group.name }}<span v-if="groupMark(group.name)" class="dot" aria-label="有需要注意的項目" />
          </RouterLink>
        </nav>
      </template>
      <nav class="pages" :aria-label="currentGroup.name">
        <RouterLink v-for="page in currentGroup.pages" :key="page.name" :to="{ name: page.name }" class="page-link"
          :class="{ on: page.name === currentPage?.name }" :aria-current="page.name === currentPage?.name ? 'page' : undefined">
          {{ page.label }}
          <span v-if="typeof attention.markOf(page.name) === 'number'" class="count" :aria-label="`${attention.markOf(page.name)} 份文件有失效連結`">{{ attention.markOf(page.name) }}</span>
          <span v-else-if="attention.markOf(page.name)" class="dot" aria-label="有需要注意的項目" />
        </RouterLink>
      </nav>
    </div>
    <!-- P25c: the site requires admins to use two-factor and this admin has not turned it on yet. -->
    <MfaRequired v-if="mfaHeld" />
    <template v-else>
      <GettingStarted v-if="session.isAdmin" />
      <RouterView />
    </template>
  </div>
</template>

<style scoped>
.admin-nav {
  position: sticky; top: 0; z-index: 20; display: grid; gap: var(--ui-space-2);
  padding: var(--ui-space-4) var(--ui-gutter) 0; border-bottom: 1px solid var(--ui-border); background: var(--ui-bg-surface);
  transition: padding .15s, box-shadow .15s;
}
.admin-nav.compact { padding-top: var(--ui-space-2); box-shadow: 0 6px 12px -10px rgb(16 24 40 / .35); }
.admin-head { display: flex; align-items: center; gap: var(--ui-space-3); padding-bottom: var(--ui-space-2); }
.admin-icon {
  flex: none; display: grid; place-items: center; width: 2.25rem; height: 2.25rem; border-radius: var(--ui-radius-md);
  background: var(--ui-accent); color: #fff; transition: width .15s, height .15s;
}
.admin-title { flex: 1; min-width: 0; display: grid; line-height: 1.3; }
.admin-title strong { font-size: 1.125rem; letter-spacing: .02em; }
.admin-title small { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.role {
  flex: none; padding: .15rem .6rem; border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-pill);
  color: var(--ui-text-secondary); font-size: var(--ui-text-xs); font-weight: 600; letter-spacing: .03em;
}
/* Scrolled: the title stays as a thin line above the menu. */
.compact .admin-head { padding-bottom: var(--ui-space-1); }
.compact .admin-icon { width: 1.6rem; height: 1.6rem; }
.compact .admin-title strong { font-size: var(--ui-text-md); }
.compact .admin-title small { display: none; }
.groups { display: flex; flex-wrap: wrap; gap: var(--ui-space-1); }
.group {
  display: inline-flex; align-items: center; gap: .35rem; padding: .3rem .8rem; border-radius: var(--ui-radius-pill);
  color: var(--ui-text-muted); font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; transition: padding .15s;
}
.group:hover:not(.on) { background: var(--ui-bg-muted); color: var(--ui-text); }
.group.on { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.compact .group { padding-block: .15rem; }
.pages { display: flex; gap: var(--ui-space-1); overflow-x: auto; scrollbar-width: thin; }
.page-link {
  flex: none; display: inline-flex; align-items: center; gap: .35rem; margin-bottom: -1px; padding: .5rem .7rem;
  border-bottom: 2px solid transparent; color: var(--ui-text-muted); font-weight: 500; text-decoration: none; white-space: nowrap;
}
.page-link:hover { color: var(--ui-text); }
.page-link.on { border-bottom-color: var(--ui-accent); color: var(--ui-accent-on-soft); font-weight: 600; }
.count { display: inline-grid; place-items: center; min-width: 1.15rem; height: 1.15rem; padding: 0 .3rem; border-radius: var(--ui-radius-pill);
  background: var(--ui-danger-bg); color: var(--ui-danger); font-size: .7rem; font-weight: 700; }
.dot { width: .45rem; height: .45rem; border-radius: 50%; background: var(--ui-danger); }
.group:focus-visible, .page-link:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: -2px; border-radius: var(--ui-radius-sm); }
.group-pick select { padding: .35rem .6rem; border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text); font: inherit; font-weight: 600; }
@media (max-width: 900px) {
  /* Below the sticky phone header. */
  .admin-nav { top: var(--ui-topbar-height); }
}
</style>

<style>
/* A card reached from Ctrl+K: room for the sticky menu above it, and a short highlight. */
.admin-shell [id] { scroll-margin-top: 7.5rem; }
.admin-flash { outline: 2px solid var(--ui-accent); outline-offset: 3px; }
@media (prefers-reduced-motion: no-preference) {
  .admin-flash { animation: admin-flash 1.8s ease-out; }
  @keyframes admin-flash { 0%, 45% { background-color: var(--ui-accent-soft); } }
}
</style>
