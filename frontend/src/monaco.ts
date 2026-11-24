import { editor, KeyCode, KeyMod, Range, Selection } from 'monaco-editor/editor/editor.api'
import 'monaco-editor/languages/definitions/markdown/register'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'

const environment = globalThis as typeof globalThis & { MonacoEnvironment?: { getWorker: () => Worker } }
environment.MonacoEnvironment ??= { getWorker: () => new EditorWorker() }

export { editor, KeyCode, KeyMod, Range, Selection }
