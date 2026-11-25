import { editor, KeyCode, KeyMod, languages, Range, Selection } from 'monaco-editor/editor/editor.api'
import 'monaco-editor/languages/definitions/markdown/register'
// P11e: the suggestion popup (slash menu, gallery layout names) and snippets with placeholders.
import 'monaco-editor/editor/contrib/suggest/browser/suggestController'
import 'monaco-editor/editor/contrib/snippet/browser/snippetController2'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'

const environment = globalThis as typeof globalThis & { MonacoEnvironment?: { getWorker: () => Worker } }
environment.MonacoEnvironment ??= { getWorker: () => new EditorWorker() }

export { editor, KeyCode, KeyMod, languages, Range, Selection }
