<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import PortalNavNode from './PortalNavNode.vue'
import { portalMode, portals, usePublicNav, type PublicNode } from './public'

const emit = defineEmits<{ navigate: [] }>()
const route = useRoute()
const mode = portalMode(route)
const names = portals[mode]
const { nav, navLoaded, childrenOf, articlesOf, pathIds } = usePublicNav(mode)

const currentArticle = computed(() => route.name === names.articleRoute ? String(route.params.id) : '')
const currentCollection = computed(() => {
  if (currentArticle.value) return nav.value.articles.find(article => article.document_id === currentArticle.value)?.collection_id ?? null
  return typeof route.query.collection === 'string' ? route.query.collection : null
})

/** Small sites start fully open; larger ones open only the path to where the reader is. */
const SMALL_SITE = 30
const open = ref(new Set<string>())
watch([navLoaded, currentCollection], () => {
  const next = new Set(open.value)
  if (nav.value.articles.length <= SMALL_SITE && !currentArticle.value) for (const node of nav.value.collections) next.add(node.id)
  for (const id of pathIds(currentCollection.value)) next.add(id)
  open.value = next
}, { immediate: true })
function toggle(node: PublicNode) {
  const next = new Set(open.value)
  if (next.has(node.id)) next.delete(node.id)
  else next.add(node.id)
  open.value = next
}
const roots = computed(() => childrenOf(null))
const loose = computed(() => articlesOf(null))
const isHome = computed(() => route.name === names.home && !route.query.collection && !route.query.q && !route.query.view)
const isAll = computed(() => route.name === names.home && route.query.view === 'all')
</script>

<template>
  <nav class="portal-nav" aria-label="公開文章導覽">
    <div class="group">
      <RouterLink :to="{ name: names.home }" class="item" :class="{ on: isHome }" :aria-current="isHome ? 'page' : undefined" @click="emit('navigate')">
        <UiIcon name="home" :size="17" /><span>首頁</span>
      </RouterLink>
      <RouterLink :to="{ name: names.home, query: { view: 'all' } }" class="item" :class="{ on: isAll }" :aria-current="isAll ? 'page' : undefined" @click="emit('navigate')">
        <UiIcon name="clock" :size="17" /><span>{{ mode === 'member' ? '最近更新' : '最新文章' }}</span>
      </RouterLink>
    </div>

    <div v-if="roots.length || loose.length" class="group">
      <span class="group-title">集合</span>
      <ul class="tree">
        <template v-for="node in roots" :key="node.id">
          <li><PortalNavNode :node="node" :open="open" :current-article="currentArticle" :current-collection="currentCollection"
            @toggle="toggle" @navigate="emit('navigate')" /></li>
        </template>
        <li v-if="loose.length">
          <div class="node-row">
            <span class="twisty-space" />
            <span class="ui-col-mark mark ui-col-gray" aria-hidden="true">·</span>
            <span class="node-name">其他文章</span>
            <span class="count">{{ loose.length }}</span>
          </div>
          <ul class="leaves">
            <li v-for="article in loose" :key="article.document_id">
              <RouterLink :to="{ name: names.articleRoute, params: { id: article.document_id } }" class="leaf"
                :class="{ on: article.document_id === currentArticle }" :aria-current="article.document_id === currentArticle ? 'page' : undefined"
                @click="emit('navigate')">{{ article.title }}</RouterLink>
            </li>
          </ul>
        </li>
      </ul>
    </div>
  </nav>
</template>


<style scoped>
.portal-nav { display: flex; flex-direction: column; gap: var(--ui-space-5); font-size: var(--ui-text-md); }
.group { display: flex; flex-direction: column; gap: 2px; }
.group-title { padding: 0 .625rem var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }
.item { display: flex; align-items: center; gap: .625rem; padding: .5rem .625rem; border-radius: var(--ui-radius-md); color: var(--ui-text-secondary); text-decoration: none; }
.item:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.item.on { background: var(--ui-accent-selected); color: var(--ui-accent-on-soft); font-weight: 600; }
.tree, .leaves { list-style: none; margin: 0; padding: 0; }
.node-row { display: flex; align-items: center; gap: .5rem; padding: .375rem .5rem .375rem 0; }
.twisty-space { flex: none; width: 1.5rem; }
.mark { width: 1.375rem; height: 1.375rem; font-size: .75rem; }
.node-name { flex: 1; min-width: 0; color: var(--ui-text-secondary); font-weight: 600; }
.count { flex: none; color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 500; }
.leaves { margin-left: 1.125rem; padding-left: .625rem; border-left: 1px solid var(--ui-border-strong); }
.leaf { display: block; padding: .3125rem .625rem; border-radius: 0 var(--ui-radius-sm) var(--ui-radius-sm) 0; color: var(--ui-text-secondary); font-size: .84375rem; line-height: 1.45; text-decoration: none; overflow-wrap: anywhere; }
.leaf:hover { color: var(--ui-text); background: var(--ui-bg-muted); }
.leaf.on { margin-left: calc(-.625rem - 1px); padding-left: calc(1.25rem - 2px); border-left: 3px solid var(--ui-text-muted); background: var(--ui-bg-muted); color: var(--ui-text); font-weight: 600; }
</style>
