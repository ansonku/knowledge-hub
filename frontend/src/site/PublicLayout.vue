<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import { useSession } from '../stores/session'
import { useTheme } from '../stores/theme'
import { colorClass, markOf, publicApi, type PublicCollectionCount } from './public'

const route = useRoute()
const session = useSession()
const theme = useTheme()
const detachTheme = theme.attach()

// Members get a shortcut into the workspace; visitors get the login link. Purely presentational.
void session.load()
const loginHref = computed(() => `/accounts/login/?next=${encodeURIComponent('/app/')}`)

const collections = ref<PublicCollectionCount[]>([])
const NAV_LIMIT = 5
onMounted(async () => {
  try {
    collections.value = (await publicApi<{ results: PublicCollectionCount[] }>('/api/public/collections/')).results
  } catch { /* the header still works without collection links */ }
})
onBeforeUnmount(detachTheme)
const activeCollection = computed(() => typeof route.query.collection === 'string' ? route.query.collection : '')
</script>

<template>
  <div class="hub-app site">
    <a class="skip" href="#site-main">跳至內容</a>
    <header class="site-head">
      <div class="head-inner">
        <RouterLink :to="{ name: 'site-home' }" class="brand">
          <span class="brand-mark" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 28 28"><rect width="28" height="28" rx="7" fill="currentColor" /><path d="M8 9h7a5 5 0 0 1 0 10H8zM8 14h6" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" /></svg>
          </span>
          <span class="brand-name">Knowledge Hub</span>
        </RouterLink>
        <nav v-if="collections.length" class="collections-nav" aria-label="公開集合">
          <RouterLink v-for="item in collections.slice(0, NAV_LIMIT)" :key="item.id"
            :to="{ name: 'site-home', query: { collection: item.id }, hash: '#latest' }"
            class="nav-link" :class="{ on: activeCollection === item.id }" :aria-current="activeCollection === item.id ? 'page' : undefined">
            <span class="ui-col-mark nav-mark" :class="colorClass(item)" aria-hidden="true">{{ markOf(item.name) }}</span>{{ item.name }}
          </RouterLink>
        </nav>
        <span class="spacer" />
        <button type="button" class="icon-button" :aria-label="theme.isDark ? '切換為淺色' : '切換為深色'" @click="theme.cycle()">
          <UiIcon :name="theme.isDark ? 'sun' : 'moon'" :size="18" />
        </button>
        <a v-if="session.status === 'member'" href="/app/" class="member-link primary">進入工作區</a>
        <a v-else :href="loginHref" class="member-link">成員登入</a>
      </div>
    </header>

    <main id="site-main" class="site-main" tabindex="-1">
      <RouterView />
    </main>

    <footer class="site-foot">
      <div class="foot-inner">
        <span>© {{ new Date().getFullYear() }} Knowledge Hub · 內容由成員發布</span>
        <span>本站只收錄經審核公開的文章</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.site { min-height: 100vh; display: flex; flex-direction: column; background: var(--ui-bg-surface); }
.skip {
  position: fixed; z-index: 100; top: .5rem; left: .5rem; padding: .55rem .85rem;
  border-radius: var(--ui-radius-md); background: var(--ui-bg-inverse); color: var(--ui-text-inverse);
  transform: translateY(calc(-100% - 1rem));
}
.skip:focus { transform: none; }
.site-head { position: sticky; top: 0; z-index: 20; border-bottom: 1px solid var(--ui-border); background: color-mix(in srgb, var(--ui-bg-surface) 92%, transparent); backdrop-filter: blur(8px); }
.head-inner, .foot-inner { box-sizing: border-box; max-width: 70rem; margin: 0 auto; padding: 0 var(--ui-gutter); }
.head-inner { min-height: 4rem; display: flex; align-items: center; gap: var(--ui-space-2) var(--ui-space-5); }
.brand { display: flex; align-items: center; gap: .625rem; color: var(--ui-text); text-decoration: none; }
.brand-mark { display: grid; color: var(--ui-accent); }
.brand-name { font-weight: 700; font-size: 1rem; white-space: nowrap; }
.collections-nav { display: flex; gap: var(--ui-space-1); min-width: 0; overflow-x: auto; scrollbar-width: none; }
.nav-link { display: inline-flex; align-items: center; gap: var(--ui-space-2); padding: .5rem .625rem; border-radius: var(--ui-radius-md); color: var(--ui-text-secondary); text-decoration: none; white-space: nowrap; }
.nav-link:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.nav-link.on { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-weight: 600; }
.nav-mark { width: 1.25rem; height: 1.25rem; font-size: .6875rem; }
.spacer { flex: 1; }
.icon-button { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.icon-button:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.member-link {
  display: inline-flex; align-items: center; height: 2.375rem; padding: 0 1rem; box-sizing: border-box;
  border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md);
  color: var(--ui-text-secondary); font-weight: 600; text-decoration: none; white-space: nowrap;
}
.member-link:hover { border-color: var(--ui-text-muted); color: var(--ui-text); }
.member-link.primary { border-color: var(--ui-accent); background: var(--ui-accent); color: #fff; }
.member-link.primary:hover { background: var(--ui-accent-hover); }
.site-main { flex: 1; outline: none; }
.site-foot { border-top: 1px solid var(--ui-border); background: var(--ui-bg-subtle); }
.foot-inner { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--ui-space-3); padding-top: 1.75rem; padding-bottom: 1.75rem; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
/* On phones the collection links move out of the header; the home page lists them. */
@media (max-width: 760px) {
  .collections-nav { display: none; }
  .head-inner { gap: var(--ui-space-2); }
}
</style>
