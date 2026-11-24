<script setup lang="ts">
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { useSession } from '../stores/session'
import { UNCATEGORIZED, useTaxonomy } from '../stores/taxonomy'
import { useTheme, type ThemeMode } from '../stores/theme'
import { useWorkspace } from '../stores/workspace'
import UiIcon, { type IconName } from './components/UiIcon.vue'

const emit = defineEmits<{ search: []; navigate: [] }>()

const session = useSession()
const taxonomy = useTaxonomy()
const workspace = useWorkspace()
const theme = useTheme()
const route = useRoute()
const router = useRouter()

type NavItem = { name: string; label: string; icon: IconName; to: RouteLocationRaw; badge?: string; tone?: 'warn' }
const primary = computed<NavItem[]>(() => [
  { name: 'app-home', label: '首頁', icon: 'home', to: { name: 'app-home' } },
  { name: 'app-library', label: '全部文件', icon: 'files', to: { name: 'app-library' } },
  { name: 'app-recent', label: '最近閱讀', icon: 'clock', to: { name: 'app-recent' } },
  { name: 'app-favorites', label: '收藏', icon: 'star', to: { name: 'app-favorites' } },
])
const secondary = computed<NavItem[]>(() => [
  {
    name: 'app-published', label: '已公開文章', icon: 'globe', to: { name: 'app-published' },
    badge: workspace.lagging ? `${workspace.lagging} 落後` : undefined, tone: 'warn',
  },
  ...(session.canEdit ? [{
    name: 'app-trash', label: '回收桶', icon: 'trash' as const, to: { name: 'app-trash' },
    badge: workspace.trash ? String(workspace.trash) : undefined,
  }] : []),
])
const isActive = (name: string) => route.name === name

// Collapsed category ids; everything starts expanded so the tree is discoverable.
const collapsed = ref(new Set<string>())
const activeCategory = computed(() => route.name === 'app-collection' ? String(route.params.id) : '')

watch(activeCategory, id => {
  for (const ancestor of taxonomy.pathOf(id)) if (ancestor.id !== id) collapsed.value.delete(ancestor.id)
}, { immediate: true })

const visibleNodes = computed(() => taxonomy.tree.filter(node =>
  !taxonomy.pathOf(node.id).slice(0, -1).some(ancestor => collapsed.value.has(ancestor.id))))

function toggle(id: string) {
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsed.value = next
}

const themeLabels: Record<ThemeMode, string> = { system: '跟隨系統', light: '淺色', dark: '深色' }
const userMenu = ref<InstanceType<typeof Menu>>()
const userItems = computed<MenuItem[]>(() => [
  { label: session.account?.email ?? '', disabled: true, class: 'user-menu-email' },
  { separator: true },
  {
    label: '外觀',
    items: (['system', 'light', 'dark'] as ThemeMode[]).map(mode => ({
      label: `${theme.mode === mode ? '✓ ' : ' '}${themeLabels[mode]}`,
      command: () => theme.setMode(mode),
    })),
  },
  { separator: true },
  { label: '個人設定', command: () => { void router.push({ name: 'app-settings' }); emit('navigate') } },
  { separator: true },
  { label: '登出', url: '/accounts/logout/' },
])
const roleLabel = computed(() => ({ admin: 'Admin', editor: 'Editor', viewer: 'Viewer' })[session.role ?? 'viewer'])
const initial = computed(() => Array.from(session.displayName)[0]?.toUpperCase() ?? '?')
const markOf = (name: string) => Array.from(name)[0]?.toUpperCase() ?? '?'
</script>

<template>
  <nav class="sidebar" aria-label="工作區導覽">
    <RouterLink :to="{ name: 'app-home' }" class="brand" @click="emit('navigate')">
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <rect width="28" height="28" rx="7" fill="var(--ui-accent)" />
        <path d="M8 9h7a5 5 0 0 1 0 10H8zM8 14h6" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span>Knowledge Hub</span>
    </RouterLink>

    <button type="button" class="search" aria-haspopup="dialog" @click="emit('search')">
      <UiIcon name="search" :size="16" />
      <span>搜尋或執行指令</span>
      <kbd>Ctrl K</kbd>
    </button>

    <div class="group">
      <RouterLink v-for="item in primary" :key="item.name" :to="item.to" class="item" :class="{ active: isActive(item.name) }"
        :aria-current="isActive(item.name) ? 'page' : undefined" @click="emit('navigate')">
        <UiIcon :name="item.icon" :size="17" /><span class="label">{{ item.label }}</span>
      </RouterLink>
    </div>

    <div class="group">
      <div class="group-head">
        <span id="collections-heading">集合</span>
        <RouterLink v-if="session.canEdit" :to="{ name: 'app-taxonomy', query: { new: 'collection' } }" class="icon-button"
          aria-label="新增集合" title="新增集合" @click="emit('navigate')">
          <UiIcon name="plus" :size="15" />
        </RouterLink>
      </div>
      <ul class="tree" aria-labelledby="collections-heading">
        <li v-for="node in visibleNodes" :key="node.id" class="tree-row" :style="{ '--depth': node.depth }">
          <button v-if="node.hasChildren" type="button" class="twisty" :aria-expanded="!collapsed.has(node.id)"
            :aria-label="`${collapsed.has(node.id) ? '展開' : '收合'}${node.name}`" @click="toggle(node.id)">
            <UiIcon :name="collapsed.has(node.id) ? 'chevronRight' : 'chevronDown'" :size="14" />
          </button>
          <span v-else class="twisty-spacer" />
          <RouterLink :to="{ name: 'app-collection', params: { id: node.id } }" class="item tree-item"
            :class="{ active: activeCategory === node.id, root: node.depth === 0 }"
            :aria-current="activeCategory === node.id ? 'page' : undefined" @click="emit('navigate')">
            <span v-if="node.depth === 0" class="ui-col-mark mark" :class="`ui-col-${node.color || 'gray'}`" aria-hidden="true">{{ markOf(node.name) }}</span>
            <span class="label">{{ node.name }}</span>
            <span class="count" :aria-label="`${taxonomy.totalOf(node.id)} 份文件`">{{ taxonomy.totalOf(node.id) || '' }}</span>
          </RouterLink>
        </li>
        <li class="tree-row" :style="{ '--depth': 0 }">
          <span class="twisty-spacer" />
          <RouterLink :to="{ name: 'app-collection', params: { id: UNCATEGORIZED } }" class="item tree-item"
            :class="{ active: activeCategory === UNCATEGORIZED }"
            :aria-current="activeCategory === UNCATEGORIZED ? 'page' : undefined" @click="emit('navigate')">
            <span class="label muted">未分類</span>
            <span class="count">{{ workspace.uncategorized || '' }}</span>
          </RouterLink>
        </li>
      </ul>
    </div>

    <div class="divider" />

    <div class="group">
      <RouterLink v-for="item in secondary" :key="item.name" :to="item.to" class="item" :class="{ active: isActive(item.name) }"
        :aria-current="isActive(item.name) ? 'page' : undefined" @click="emit('navigate')">
        <UiIcon :name="item.icon" :size="17" /><span class="label">{{ item.label }}</span>
        <span v-if="item.badge" class="badge" :class="item.tone">{{ item.badge }}</span>
      </RouterLink>
      <RouterLink v-if="session.canEdit" :to="{ name: 'app-taxonomy' }" class="item" :class="{ active: route.name === 'app-taxonomy' }"
        :aria-current="route.name === 'app-taxonomy' ? 'page' : undefined" @click="emit('navigate')">
        <UiIcon name="sliders" :size="17" /><span class="label">集合與標籤</span>
      </RouterLink>
      <RouterLink v-if="session.isAdmin" :to="{ name: 'app-members' }" class="item"
        :class="{ active: String(route.name ?? '').startsWith('app-member') }"
        :aria-current="String(route.name ?? '').startsWith('app-member') ? 'page' : undefined" @click="emit('navigate')">
        <UiIcon name="users" :size="17" /><span class="label">成員管理</span>
      </RouterLink>
    </div>

    <div class="spacer" />

    <button type="button" class="account" aria-haspopup="menu" aria-controls="user-menu" @click="userMenu?.toggle($event)">
      <span class="avatar" aria-hidden="true">{{ initial }}</span>
      <span class="account-text">
        <span class="account-name">{{ session.displayName }}</span>
        <span class="account-role">{{ roleLabel }}</span>
      </span>
      <UiIcon name="chevronDown" :size="15" />
    </button>
    <Menu id="user-menu" ref="userMenu" :model="userItems" popup />
  </nav>
</template>

<style scoped>
.sidebar {
  box-sizing: border-box; display: flex; flex-direction: column; gap: var(--ui-space-4);
  min-height: 100%; padding: var(--ui-space-4) var(--ui-space-3);
  background: var(--ui-bg-shell); color: var(--ui-text);
}
.brand { display: flex; align-items: center; gap: .625rem; padding: var(--ui-space-1) var(--ui-space-2); color: var(--ui-text); text-decoration: none; font-weight: 700; font-size: .9375rem; letter-spacing: -.01em; border-radius: var(--ui-radius-md); }
.search {
  display: flex; align-items: center; gap: .625rem; min-height: 2.375rem; padding: 0 .625rem;
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface);
  color: var(--ui-text-muted); font: inherit; font-size: var(--ui-text-sm); text-align: left; cursor: pointer;
}
.search:hover { border-color: var(--ui-border-strong); }
.search span { flex: 1; }
.search kbd { font-family: var(--ui-font-sans); font-size: .6875rem; font-weight: 500; padding: 1px 5px; border: 1px solid var(--ui-border); border-radius: 4px; background: var(--ui-bg-subtle); color: var(--ui-text-muted); }
.group { display: flex; flex-direction: column; gap: 2px; }
.group-head { display: flex; align-items: center; justify-content: space-between; padding: 0 .625rem var(--ui-space-1); }
.group-head > span { font-size: var(--ui-text-xs); font-weight: 600; color: var(--ui-text-muted); letter-spacing: .02em; }
.icon-button { display: grid; place-items: center; width: 1.75rem; height: 1.75rem; border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.icon-button:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.item {
  display: flex; align-items: center; gap: .625rem; min-height: 2.25rem; padding: 0 .625rem;
  border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-secondary);
  font: inherit; font-size: var(--ui-text-md); font-weight: 500; text-align: left; text-decoration: none; cursor: pointer;
}
.item:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.item.active { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); font-weight: 600; }
.label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.muted { color: var(--ui-text-muted); }
.count { color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 500; }
.badge { padding: 1px 7px; border-radius: var(--ui-radius-pill); background: var(--ui-bg-muted); color: var(--ui-text-secondary); font-size: .6875rem; font-weight: 600; white-space: nowrap; }
.badge.warn { background: var(--ui-lagging-bg); color: var(--ui-lagging-text); }
.tree { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.tree-row { display: flex; align-items: center; gap: 2px; padding-left: calc(var(--depth) * 1rem); }
.twisty, .twisty-spacer { flex: none; width: 1.5rem; height: 1.5rem; }
.twisty { display: grid; place-items: center; border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.twisty:hover { background: var(--ui-bg-muted); }
.tree-item { flex: 1; min-width: 0; min-height: 2rem; padding-left: .375rem; gap: .5rem; font-size: .84375rem; }
.tree-item.root { color: var(--ui-text); font-weight: 600; }
.tree-item.active { font-weight: 600; }
.mark { width: 1.125rem; height: 1.125rem; font-size: .6875rem; }
.divider { height: 1px; margin: 0 var(--ui-space-2); background: var(--ui-border); }
.spacer { flex: 1; }
.account { display: flex; align-items: center; gap: .625rem; padding: var(--ui-space-2) .625rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); font: inherit; text-align: left; cursor: pointer; }
/* Keep the account button fully visible when the sidebar scrolls (short windows): clicking a
   half-hidden button scrolls the sidebar, and PrimeVue closes the popup menu on scroll. */
.account { position: sticky; bottom: 0; z-index: 1; margin-inline: calc(-1 * var(--ui-space-3)); padding-inline: calc(.625rem + var(--ui-space-3)); border-radius: 0; background: var(--ui-bg-shell); box-shadow: 0 -1px 0 var(--ui-border-subtle); }
.account:hover { background: var(--ui-bg-muted); }
.avatar { flex: none; display: grid; place-items: center; width: 1.875rem; height: 1.875rem; border-radius: 50%; background: var(--ui-accent); color: #fff; font-size: var(--ui-text-sm); font-weight: 600; }
.account-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.account-name { color: var(--ui-text); font-weight: 600; font-size: .84375rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-role { font-size: var(--ui-text-xs); }
</style>
