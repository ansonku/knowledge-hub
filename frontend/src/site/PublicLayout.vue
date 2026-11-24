<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import { useSession } from '../stores/session'
import { useSite } from '../stores/site'
import { useTheme } from '../stores/theme'
import PortalNav from './PortalNav.vue'
import { portalMode, portals } from './public'

const route = useRoute()
const router = useRouter()
const session = useSession()
const site = useSite()
const theme = useTheme()
const detachTheme = theme.attach()
onBeforeUnmount(detachTheme)

const mode = portalMode(route)
const names = portals[mode]
const member = mode === 'member'

// Public site: members get a shortcut into the workspace, visitors the login link (presentational only).
// Member portal: sign-in is required; the APIs refuse visitors anyway, this just sends them to log in.
const ready = ref(!member)
void session.load().then(() => {
  if (member && session.status === 'guest') {
    window.location.assign(`/accounts/login/?next=${encodeURIComponent(route.fullPath)}`)
    return
  }
  ready.value = true
})
const loginHref = computed(() => `/accounts/login/?next=${encodeURIComponent('/app/')}`)

// ---- Search (the home page shows the results) -----------------------------------------------------
const search = ref(typeof route.query.q === 'string' ? route.query.q : '')
watch(() => route.query.q, value => { search.value = typeof value === 'string' ? value : '' })
const searchInput = ref<HTMLInputElement>()
function submitSearch() {
  const q = search.value.trim()
  void router.push({ name: names.home, query: q ? { q } : {} })
  drawerOpen.value = false
}
function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    searchInput.value?.focus()
  } else if (event.key === 'Escape') {
    drawerOpen.value = false
  }
}
window.addEventListener('keydown', onKeydown)
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

// ---- Mobile drawer ---------------------------------------------------------------------------------------
const drawerOpen = ref(false)
watch(() => route.fullPath, () => { drawerOpen.value = false })
</script>

<template>
  <div class="hub-app portal" :class="{ 'drawer-open': drawerOpen }">
    <a class="skip" href="#portal-main">跳至內容</a>
    <header class="topbar">
      <button type="button" class="icon-button menu" aria-label="開啟導覽" aria-controls="portal-nav" :aria-expanded="drawerOpen" @click="drawerOpen = true">
        <UiIcon name="menu" :size="20" />
      </button>
      <RouterLink :to="{ name: names.home }" class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 28 28"><rect width="28" height="28" rx="7" fill="currentColor" /><path d="M8 9h7a5 5 0 0 1 0 10H8zM8 14h6" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" /></svg>
        </span>
        <span class="brand-name">{{ site.name }}</span>
        <span v-if="member" class="portal-tag">閱讀入口</span>
      </RouterLink>
      <form class="search" role="search" @submit.prevent="submitSearch">
        <UiIcon name="search" :size="16" />
        <label for="portal-search" class="ui-visually-hidden">搜尋公開文章</label>
        <input id="portal-search" ref="searchInput" v-model="search" type="search" maxlength="240"
          :placeholder="member ? '搜尋所有文件的標題或內文' : '搜尋文章標題或內文'" enterkeyhint="search">
        <kbd aria-hidden="true">Ctrl K</kbd>
      </form>
      <span class="spacer" />
      <button type="button" class="icon-button" :aria-label="theme.isDark ? '切換為淺色' : '切換為深色'" @click="theme.cycle()">
        <UiIcon :name="theme.isDark ? 'sun' : 'moon'" :size="18" />
      </button>
      <template v-if="member">
        <a href="/articles/" class="member-link secondary">公開知識站</a>
        <a href="/app/" class="member-link primary">工作區</a>
      </template>
      <a v-else-if="session.status === 'member'" href="/app/" class="member-link primary">進入工作區</a>
      <a v-else :href="loginHref" class="member-link">成員登入</a>
    </header>

    <div v-if="ready" class="body">
      <div v-if="drawerOpen" class="scrim" aria-hidden="true" @click="drawerOpen = false" />
      <aside id="portal-nav" class="side">
        <PortalNav @navigate="drawerOpen = false" />
      </aside>
      <main id="portal-main" class="main" tabindex="-1">
        <RouterView />
        <footer class="foot">
          <span>© {{ new Date().getFullYear() }} {{ site.name }} · 內容由成員發布</span>
          <span>{{ member ? '成員閱讀入口：包含內部文件，請勿外流' : '本站只收錄經審核公開的文章' }}</span>
        </footer>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* Full-bleed shell: top bar across the window, navigation flush with the left edge. */
.portal { min-height: 100vh; display: flex; flex-direction: column; background: var(--ui-bg-surface); }
.skip {
  position: fixed; z-index: 100; top: .5rem; left: .5rem; padding: .55rem .85rem;
  border-radius: var(--ui-radius-md); background: var(--ui-bg-inverse); color: var(--ui-text-inverse);
  transform: translateY(calc(-100% - 1rem));
}
.skip:focus { transform: none; }
.topbar {
  position: sticky; top: 0; z-index: 30; display: flex; align-items: center; gap: var(--ui-space-3) var(--ui-space-5);
  min-height: 4rem; padding: 0 var(--ui-space-5); box-sizing: border-box; border-bottom: 1px solid var(--ui-border);
  background: var(--ui-bg-surface);
}
.brand { flex: none; display: flex; align-items: center; gap: .625rem; min-width: calc(var(--portal-nav) - var(--ui-space-5) - var(--ui-space-5)); color: var(--ui-text); text-decoration: none; }
.brand-mark { display: grid; color: var(--ui-accent); }
.portal-tag { flex: none; padding: 1px .5rem; border-radius: var(--ui-radius-pill); background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-size: var(--ui-text-xs); font-weight: 600; }
.brand-name { font-weight: 700; font-size: 1rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search {
  flex: 1 1 20rem; max-width: 35rem; display: flex; align-items: center; gap: var(--ui-space-2); height: 2.5rem; padding: 0 var(--ui-space-3);
  border: 1px solid var(--ui-border-strong); border-radius: .625rem; background: var(--ui-bg-subtle); color: var(--ui-text-muted); box-sizing: border-box;
}
.search:focus-within { border-color: var(--ui-accent); box-shadow: var(--ui-focus-ring); background: var(--ui-bg-surface); }
.search input { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; color: var(--ui-text); font: inherit; }
.search input:focus-visible { box-shadow: none; }
.search input::-webkit-search-cancel-button { display: none; }
kbd { padding: 1px 6px; border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-sm); font: inherit; font-size: var(--ui-text-xs); }
.spacer { flex: 1; }
.icon-button { flex: none; display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.icon-button:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.menu { display: none; }
.member-link {
  flex: none; display: inline-flex; align-items: center; height: 2.375rem; padding: 0 1rem; box-sizing: border-box;
  border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md);
  color: var(--ui-text-secondary); font-weight: 600; text-decoration: none; white-space: nowrap;
}
.member-link:hover { border-color: var(--ui-text-muted); color: var(--ui-text); }
.member-link.primary { border-color: var(--ui-accent); background: var(--ui-accent); color: #fff; }
.hub-dark .member-link.primary { color: #0c111b; }
.body { flex: 1; display: flex; align-items: stretch; --portal-nav: 17.5rem; }
.portal { --portal-nav: 17.5rem; }
.side {
  flex: none; width: var(--portal-nav); box-sizing: border-box; padding: var(--ui-space-5) var(--ui-space-4);
  border-right: 1px solid var(--ui-border); background: var(--ui-bg-shell);
  position: sticky; top: 4rem; align-self: flex-start; height: calc(100vh - 4rem); overflow-y: auto;
}
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; outline: none; }
.main > :first-child { flex: 1; }
.foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--ui-space-3); padding: var(--ui-space-5) clamp(1rem, 3vw, 3rem); border-top: 1px solid var(--ui-border); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.scrim { display: none; }

@media (max-width: 1000px) {
  .menu { display: grid; }
  .brand { width: auto; min-width: 0; }
  .search kbd { display: none; }
  .side {
    position: fixed; z-index: 50; top: 0; left: 0; width: min(85vw, 20rem); height: 100%;
    transform: translateX(-100%); visibility: hidden; transition: transform .2s ease; box-shadow: var(--ui-shadow-lg);
  }
  .drawer-open .side { transform: none; visibility: visible; }
  .scrim { display: block; position: fixed; z-index: 40; inset: 0; background: rgb(16 24 40 / .4); }
}
@media (max-width: 640px) {
  .topbar { flex-wrap: wrap; gap: var(--ui-space-2); padding: var(--ui-space-2) var(--ui-space-3); }
  .search { order: 10; flex: 1 1 100%; max-width: none; }
  .brand-name { max-width: 10rem; }
  .member-link { padding: 0 .75rem; }
  /* Phones: keep one action in the member portal's top bar. */
  .member-link.secondary { display: none; }
}
@media (prefers-reduced-motion: reduce) { .side { transition: none; } }
</style>
