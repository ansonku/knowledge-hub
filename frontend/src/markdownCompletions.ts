// P11e: suggestions inside the Markdown editor, registered once for every editor on the page.
//   - Slash menu: `/` at the start of a line (only spaces before it) lists SNIPPETS; typing filters them.
//   - `:::gallery ` lists the layout names.
// Monaco's suggestion providers are global per language, so each editor registers its hooks by model URI.
import { GALLERY_LAYOUTS, LAYOUT_LABELS } from './gallery'
import { plainSnippet, SNIPPETS } from './markdownSnippets'
import { editor, languages, Range } from './monaco'

export type EditorHelpers = { readonly: () => boolean; pick: (kind: 'image' | 'video') => void }
export const helpers = new Map<string, EditorHelpers>()
const PICK = 'hub.markdown.pick'
let registered = false

function lineBefore(model: editor.ITextModel, line: number, column: number) {
  return model.getValueInRange(new Range(line, 1, line, column))
}

/** Inside a fenced code block a `/` or `:::gallery` is code, not a command. */
function inFence(model: editor.ITextModel, line: number) {
  let open = false
  for (let index = 1; index < line; index++) if (/^\s{0,3}(```|~~~)/.test(model.getLineContent(index))) open = !open
  return open
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
          insertText: snippet.insert ?? '',
          insertTextRules: snippet.insert ? languages.CompletionItemInsertTextRule.InsertAsSnippet : undefined,
          command: snippet.action ? { id: PICK, title: snippet.label, arguments: [model.uri.toString(), snippet.action] } : undefined,
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
