// P11e: suggestions inside the Markdown editor, registered once for every editor on the page.
//   - Slash menu: `/` at the start of a line (only spaces before it) lists SNIPPETS; typing filters them.
//   - `:::gallery ` lists the layout names.
// Monaco's suggestion providers are global per language, so each editor registers its hooks by model URI.
import { GALLERY_LAYOUTS, LAYOUT_LABELS } from './gallery'
import { plainSnippet, SNIPPETS } from './markdownSnippets'
import { api } from './api'
import type { DocumentRow } from './app/types'
import { useTaxonomy } from './stores/taxonomy'
import { editor, languages, Range } from './monaco'

export type EditorHelpers = {
  readonly: () => boolean
  pick: (kind: 'image' | 'video') => void
  /** The document being edited: it is left out of the document link suggestions. */
  documentId: () => string | undefined
}
export const helpers = new Map<string, EditorHelpers>()
const PICK = 'hub.markdown.pick'
let registered = false

function lineBefore(model: editor.ITextModel, line: number, column: number) {
  return model.getValueInRange(new Range(line, 1, line, column))
}

/** Inside a fenced code block a `/` or `:::gallery` is code, not a command. */
export function inFence(model: editor.ITextModel, line: number) {
  let open = false
  for (let index = 1; index < line; index++) if (/^\s{0,3}(```|~~~)/.test(model.getLineContent(index))) open = !open
  return open
}

const search = (params: Record<string, string>) =>
  api<{ results: DocumentRow[] }>(`/api/documents/?${new URLSearchParams(params)}`).then(page => page.results)

/**
 * `[[韌體 更新`: words that name a collection narrow the search to it (and its sub-collections), the other
 * words search inside; those come first, then the plain search for everything typed.
 */
async function searchDocuments(query: string) {
  const taxonomy = useTaxonomy()
  const words = query.split(/\s+/).filter(Boolean)
  const lower = (text: string) => text.toLocaleLowerCase()
  const narrowed: Promise<DocumentRow[]>[] = []
  for (const [position, word] of words.entries()) {
    const matches = taxonomy.categories.filter(category => lower(category.name).includes(lower(word)))
      .sort((a, b) => a.name.length - b.name.length).slice(0, 2)
    const rest = words.filter((_, other) => other !== position).join(' ')
    for (const category of matches) narrowed.push(search({ category: category.id, ...(rest ? { q: rest } : {}) }))
    if (narrowed.length >= 2) break
  }
  const groups = await Promise.all([...narrowed, search({ q: query })])
  const seen = new Set<string>()
  return groups.flat().filter(row => !seen.has(row.id) && seen.add(row.id))
}

export function registerMarkdownHelpers() {
  if (registered) return
  registered = true
  editor.registerCommand(PICK, (_accessor, uri: string, kind: 'image' | 'video') => helpers.get(uri)?.pick(kind))

  languages.registerCompletionItemProvider('markdown', {
    triggerCharacters: ['/'],
    provideCompletionItems(model, position) {
      const hooks = helpers.get(model.uri.toString())
      const typed = /^(\s*)\/([^\s/]*)$/.exec(lineBefore(model, position.lineNumber, position.column))
      if (!hooks || hooks.readonly() || !typed || inFence(model, position.lineNumber)) return { suggestions: [] }
      const range = new Range(position.lineNumber, typed[1].length + 1, position.lineNumber, position.column)
      return {
        suggestions: SNIPPETS.map((snippet, index) => ({
          label: { label: `/${snippet.label}`, description: snippet.group },
          kind: snippet.action ? languages.CompletionItemKind.File : languages.CompletionItemKind.Snippet,
          detail: snippet.description,
          documentation: { value: '```markdown\n' + plainSnippet(snippet) + '\n```' },
          filterText: `/${snippet.label} ${snippet.keywords}`,
          sortText: String(index).padStart(3, '0'),
          range,
          insertText: snippet.action === 'doclink' ? '[[' : snippet.insert ?? '',
          insertTextRules: snippet.insert ? languages.CompletionItemInsertTextRule.InsertAsSnippet : undefined,
          // 連結文件 types `[[` and opens the document search right away.
          command: snippet.action === 'doclink' ? { id: 'editor.action.triggerSuggest', title: snippet.label }
            : snippet.action ? { id: PICK, title: snippet.label, arguments: [model.uri.toString(), snippet.action] } : undefined,
        })),
      }
    },
  })

  // P13b: `[[` searches documents (recently read ones before anything is typed) and inserts a standard link.
  languages.registerCompletionItemProvider('markdown', {
    triggerCharacters: ['['],
    async provideCompletionItems(model, position) {
      const hooks = helpers.get(model.uri.toString())
      const typed = /\[\[([^[\]\n]{0,80})$/.exec(lineBefore(model, position.lineNumber, position.column))
      if (!hooks || hooks.readonly() || !typed || inFence(model, position.lineNumber)) return { suggestions: [] }
      const query = typed[1].trim()
      // Auto-closed brackets ("[[|]]") go away with the inserted link.
      const after = model.getLineContent(position.lineNumber).slice(position.column - 1)
      const closing = after.startsWith(']]') ? 2 : after.startsWith(']') ? 1 : 0
      const range = new Range(position.lineNumber, position.column - typed[0].length, position.lineNumber, position.column + closing)
      let rows: DocumentRow[] = []
      try {
        rows = query ? await searchDocuments(query) : (await api<{ results: DocumentRow[] }>('/api/me/recent/?limit=10')).results
      } catch {
        return { suggestions: [], incomplete: true }
      }
      const taxonomy = useTaxonomy()
      const current = hooks.documentId()
      const label = (title: string) => title.replace(/[[\]]/g, '\\$&')
      return {
        incomplete: true,
        suggestions: rows.filter(row => row.id !== current).slice(0, 12).map((row, index) => ({
          label: { label: row.title, description: taxonomy.pathLabel(row.category) },
          kind: languages.CompletionItemKind.Reference,
          detail: query ? '插入文件連結' : '最近閱讀',
          filterText: typed[0],
          sortText: String(index).padStart(3, '0'),
          range,
          insertText: `[${label(row.title)}](/app/docs/${row.id}/)`,
        })),
      }
    },
  })

  languages.registerCompletionItemProvider('markdown', {
    triggerCharacters: [' '],
    provideCompletionItems(model, position) {
      const hooks = helpers.get(model.uri.toString())
      const typed = /^\s*:::[ \t]*gallery[ \t]+([a-z]*)$/i.exec(lineBefore(model, position.lineNumber, position.column))
      if (!hooks || hooks.readonly() || !typed || inFence(model, position.lineNumber)) return { suggestions: [] }
      const range = new Range(position.lineNumber, position.column - typed[1].length, position.lineNumber, position.column)
      return {
        suggestions: GALLERY_LAYOUTS.map((layout, index) => ({
          label: { label: layout, description: LAYOUT_LABELS[layout] },
          kind: languages.CompletionItemKind.EnumMember,
          detail: `相簿版面：${LAYOUT_LABELS[layout]}`,
          sortText: String(index),
          range,
          insertText: layout,
        })),
      }
    },
  })
}
