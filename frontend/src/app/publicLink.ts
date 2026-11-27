// The public-site page of the document being viewed, when it is published (set by DocumentPage, used by the command palette).
import { ref } from 'vue'

export const currentPublicArticle = ref<{ id: string; title: string } | null>(null)

/** Open a public-site page in a new tab: a quick look at what visitors see, without leaving the work in progress. */
export function openPublic(path = '/articles/') {
  window.open(path, '_blank', 'noopener')
}
