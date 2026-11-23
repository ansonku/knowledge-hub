import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api'
import type { Category, Label } from '../app/types'

export type CategoryNode = Category & { depth: number; hasChildren: boolean }

export const UNCATEGORIZED = 'uncategorized'

export const useTaxonomy = defineStore('taxonomy', () => {
  const categories = ref<Category[]>([])
  const tags = ref<Label[]>([])
  const loaded = ref(false)

  async function load() {
    const [nextCategories, nextTags] = await Promise.all([
      api<Category[]>('/api/categories/'),
      api<Label[]>('/api/tags/'),
    ])
    categories.value = nextCategories
    tags.value = nextTags
    loaded.value = true
  }

  /** Depth-first, sorted as the API returns them within each parent. */
  const tree = computed<CategoryNode[]>(() => {
    const nodes: CategoryNode[] = []
    const append = (parent: string | null, depth: number) => {
      for (const item of categories.value.filter(category => category.parent === parent)) {
        nodes.push({ ...item, depth, hasChildren: categories.value.some(child => child.parent === item.id) })
        append(item.id, depth + 1)
      }
    }
    append(null, 0)
    return nodes
  })

  /** Options for Select components, indented to show nesting. */
  const categoryOptions = computed(() =>
    tree.value.map(node => ({ id: node.id, name: `${'　'.repeat(node.depth)}${node.name}` })))

  function byId(id: string | null | undefined) {
    return categories.value.find(category => category.id === id)
  }

  /** Ancestors from the root down to and including the category. */
  function pathOf(id: string | null | undefined): Category[] {
    const path: Category[] = []
    const seen = new Set<string>()
    let current = byId(id)
    while (current && !seen.has(current.id)) {
      seen.add(current.id)
      path.unshift(current)
      current = byId(current.parent)
    }
    return path
  }

  /** Document count of each collection including its sub-collections. */
  const totals = computed(() => {
    const result = new Map<string, number>()
    for (const node of [...tree.value].reverse()) {
      const children = categories.value.filter(child => child.parent === node.id)
      result.set(node.id, (node.document_count ?? 0) + children.reduce((sum, child) => sum + (result.get(child.id) ?? 0), 0))
    }
    return result
  })
  const totalOf = (id: string) => totals.value.get(id) ?? 0

  const pathLabel = (id: string | null | undefined) => pathOf(id).map(item => item.name).join(' / ') || '未分類'

  return { categories, tags, loaded, load, tree, categoryOptions, byId, pathOf, pathLabel, totalOf }
})
