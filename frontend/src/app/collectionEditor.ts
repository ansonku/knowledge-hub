// P15: one collection dialog for the whole workspace (sidebar +, collection pages, 集合與標籤), opened in
// place instead of navigating to the admin page.
import { reactive } from 'vue'

export type CollectionRequest =
  | { mode: 'create'; parent: string | null; /** Stay on the current page (集合與標籤) instead of opening the new collection. */ stay: boolean }
  | { mode: 'edit'; id: string }

export const collectionEditor = reactive<{ request?: CollectionRequest; /** The collection created last (to highlight it). */ created?: string }>({})

export function newCollection(parent: string | null = null, options: { stay?: boolean } = {}) {
  collectionEditor.request = { mode: 'create', parent, stay: options.stay ?? false }
}
export function editCollection(id: string) {
  collectionEditor.request = { mode: 'edit', id }
}
export function closeCollectionEditor() {
  collectionEditor.request = undefined
}
