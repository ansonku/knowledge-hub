<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import { colorClass, markOf, usePublicNav, type PublicNode } from './public'

/** One collection in the public navigation: its own articles, then its sub-collections (recursively). */
const props = defineProps<{ node: PublicNode; open: Set<string>; currentArticle: string; currentCollection: string | null }>()
const emit = defineEmits<{ toggle: [node: PublicNode]; navigate: [] }>()
const { childrenOf, articlesOf } = usePublicNav()

const expanded = computed(() => props.open.has(props.node.id))
const children = computed(() => childrenOf(props.node.id))
const articles = computed(() => articlesOf(props.node.id))
const isCurrent = computed(() => props.currentCollection === props.node.id && !props.currentArticle)
const leafStyle = computed(() => ({
  '--leaf-fg': `var(--ui-col-${props.node.color || 'gray'}-fg)`, '--leaf-bg': `var(--ui-col-${props.node.color || 'gray'}-bg)`,
}))
</script>

<template>
  <div class="node" :class="{ nested: node.depth > 0 }">
    <div class="node-row" :class="{ on: isCurrent }">
      <button type="button" class="twisty" :aria-expanded="expanded" :aria-label="`${expanded ? '收合' : '展開'}${node.name}`"
        @click="emit('toggle', node)">
        <UiIcon :name="expanded ? 'chevronDown' : 'chevronRight'" :size="14" />
      </button>
      <RouterLink :to="{ name: 'site-home', query: { collection: node.id } }" class="node-link"
        :aria-current="isCurrent ? 'page' : undefined" @click="emit('navigate')">
        <span class="ui-col-mark mark" :class="colorClass(node)" aria-hidden="true">{{ markOf(node.name) }}</span>
        <span class="node-name">{{ node.name }}</span>
        <span class="count">{{ node.total_count }}</span>
      </RouterLink>
    </div>
    <ul v-if="expanded" class="leaves">
      <li v-for="article in articles" :key="article.document_id">
        <RouterLink :to="{ name: 'public-article', params: { id: article.document_id } }" class="leaf"
          :class="{ on: article.document_id === currentArticle }" :style="leafStyle"
          :aria-current="article.document_id === currentArticle ? 'page' : undefined" @click="emit('navigate')">{{ article.title }}</RouterLink>
      </li>
      <li v-for="child in children" :key="child.id">
        <PortalNavNode :node="child" :open="open" :current-article="currentArticle" :current-collection="currentCollection"
          @toggle="value => emit('toggle', value)" @navigate="emit('navigate')" />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.node-row { display: flex; align-items: center; gap: 2px; border-radius: var(--ui-radius-md); }
.node-row:hover, .node-row.on { background: var(--ui-bg-muted); }
.twisty { flex: none; display: grid; place-items: center; width: 1.5rem; height: 1.75rem; border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.twisty:hover { color: var(--ui-text); }
.node-link { flex: 1; min-width: 0; display: flex; align-items: center; gap: .5rem; padding: .375rem .5rem .375rem 0; color: var(--ui-text); font-weight: 600; text-decoration: none; }
.mark { width: 1.375rem; height: 1.375rem; font-size: .75rem; }
.nested .mark { width: 1.125rem; height: 1.125rem; font-size: .6875rem; }
.nested .node-link { font-size: .84375rem; }
.node-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.count { flex: none; color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 500; }
.leaves { list-style: none; margin: 0 0 0 1.125rem; padding: 0 0 0 .625rem; border-left: 1px solid var(--ui-border-strong); }
.leaf { display: block; padding: .3125rem .625rem; border-radius: 0 var(--ui-radius-sm) var(--ui-radius-sm) 0; color: var(--ui-text-secondary); font-size: .84375rem; line-height: 1.45; text-decoration: none; overflow-wrap: anywhere; }
.leaf:hover { color: var(--ui-text); background: var(--ui-bg-muted); }
.leaf.on { margin-left: calc(-.625rem - 1px); padding-left: calc(1.25rem - 2px); border-left: 3px solid var(--leaf-fg); background: var(--leaf-bg); color: var(--leaf-fg); font-weight: 600; }
</style>
