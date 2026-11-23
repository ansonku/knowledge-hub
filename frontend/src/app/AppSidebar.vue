<script setup lang="ts">
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useSession } from '../stores/session'
import { UNCATEGORIZED, useTaxonomy } from '../stores/taxonomy'
import UiIcon from './components/UiIcon.vue'

const emit = defineEmits<{ search: []; manageTaxonomy: []; navigate: [] }>()

const session = useSession()
const taxonomy = useTaxonomy()
const route = useRoute()

// Collapsed category ids; everything starts expanded so the tree is discoverable.
const collapsed = ref(new Set<string>())
const activeCategory = computed(() => route.name === 'app-collection' ? String(route.params.id) : '')
const onLibrary = computed(() => route.name === 'app-library')

// Keep the active category's ancestors open.
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

const userMenu = ref<InstanceType<typeof Menu>>()
const userItems = computed<MenuItem[]>(() => [
  { label: session.account?.email ?? '', disabled: true, class: 'user-menu-email' },
  { separator: true },
  { label: '個人設定', url: '/accounts/profile/' },
  { label: '切換到舊版介面', url: '/library/' },
  { separator: true },
  { label: '登出', url: '/accounts/logout/' },
])
const roleLabel = computed(() => ({ admin: 'Admin', editor: 'Editor', viewer: 'Viewer' })[session.role ?? 'viewer'])
const initial = computed(() => Array.from(session.displayName)[0]?.toUpperCase() ?? '?')
</script>

<template>
  <nav class="sidebar" aria-label="工作區導覽">
    <RouterLink to="/app/" class="brand" @click="emit('navigate')">
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <rect width="28" height="28" rx="7" fill="var(--ui-accent)" />
        <path d="M8 9h7a5 5 0 0 1 0 10H8zM8 14h6" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span>Knowledge Hub</span>
    </RouterLink>

    <button type="button" class="search" @click="emit('search')">
      <UiIcon name="search" :size="16" />
      <span>搜尋文件</span>
      <kbd>Ctrl K</kbd>
    </button>

    <div class="group">
      <RouterLink to="/app/library/" class="item" :class="{ active: onLibrary }" :aria-current="onLibrary ? 'page' : undefined"
        @click="emit('navigate')">
        <UiIcon name="files" :size="17" /><span class="label">全部文件</span>
      </RouterLink>
    </div>

    <div class="group">
      <div class="group-head">
        <span id="collections-heading">集合</span>
        <button v-if="session.canEdit" type="button" class="icon-button" aria-label="管理集合與標籤"
          @click="emit('manageTaxonomy')">
          <UiIcon name="plus" :size="15" />
        </button>
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
            <span class="label">{{ node.name }}</span>
          </RouterLink>
        </li>
        <li class="tree-row" :style="{ '--depth': 0 }">
          <span class="twisty-spacer" />
          <RouterLink :to="{ name: 'app-collection', params: { id: UNCATEGORIZED } }" class="item tree-item"
            :class="{ active: activeCategory === UNCATEGORIZED }"
            :aria-current="activeCategory === UNCATEGORIZED ? 'page' : undefined" @click="emit('navigate')">
            <span class="label muted">未分類</span>
          </RouterLink>
        </li>
      </ul>
    </div>

    <div class="divider" />

    <div class="group">
      <a v-if="session.canEdit" href="/library/trash/" class="item">
        <UiIcon name="trash" :size="17" /><span class="label">回收桶</span>
      </a>
      <button v-if="session.canEdit" type="button" class="item" @click="emit('manageTaxonomy')">
        <UiIcon name="sliders" :size="17" /><span class="label">集合與標籤</span>
      </button>
      <a v-if="session.isAdmin" href="/accounts/manage/" class="item">
        <UiIcon name="users" :size="17" /><span class="label">帳號管理</span>
      </a>
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
  min-height: 100%; padding: var(--ui-space-4) var(--ui-space-3) var(--ui-space-4);
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
.search kbd { font-size: .6875rem; font-weight: 500; padding: 1px 5px; border: 1px solid var(--ui-border); border-radius: 4px; background: var(--ui-bg-subtle); color: var(--ui-text-muted); }
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
.tree { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.tree-row { display: flex; align-items: center; gap: 2px; padding-left: calc(var(--depth) * 1rem); }
.twisty, .twisty-spacer { flex: none; width: 1.5rem; height: 1.5rem; }
.twisty { display: grid; place-items: center; border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.twisty:hover { background: var(--ui-bg-muted); }
.tree-item { flex: 1; min-width: 0; min-height: 2rem; padding-left: .375rem; font-size: .84375rem; }
.tree-item.root { color: var(--ui-text); font-weight: 600; }
.tree-item.active { font-weight: 600; }
.divider { height: 1px; margin: 0 var(--ui-space-2); background: var(--ui-border); }
.spacer { flex: 1; }
.account { display: flex; align-items: center; gap: .625rem; padding: var(--ui-space-2) .625rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); font: inherit; text-align: left; cursor: pointer; }
.account:hover { background: var(--ui-bg-muted); }
.avatar { flex: none; display: grid; place-items: center; width: 1.875rem; height: 1.875rem; border-radius: 50%; background: var(--ui-accent); color: #fff; font-size: var(--ui-text-sm); font-weight: 600; }
.account-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.account-name { color: var(--ui-text); font-weight: 600; font-size: .84375rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-role { font-size: var(--ui-text-xs); }
</style>
