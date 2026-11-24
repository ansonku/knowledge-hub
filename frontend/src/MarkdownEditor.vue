<script setup lang="ts">
import { editor, KeyCode, KeyMod, Range, Selection } from './monaco'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import UiIcon, { type IconName } from './app/components/UiIcon.vue'
import {
  continueList, countWords, indentList, insertBlockStyle, insertLink, pasteAsLink, toggleInline, toggleLines,
  type BlockStyle, type InlineStyle, type LineStyle,
} from './markdownCommands'

const value = defineModel<string>({ required: true })
const props = defineProps<{
  readonly: boolean
  /** Uploads one image and resolves with its address; without it the editor takes no images. */
  uploadImage?: (file: File) => Promise<{ url: string }>
}>()
const emit = defineEmits<{
  /** A message for the writer, such as a refused or failed image upload. */
  notify: [message: string]
  /** Ctrl+S: the page moves focus to the version note, where Enter saves. */
  save: []
  /** The source line (1-based, fractional) at the top of the editor, or Infinity at the very bottom. */
  scrollLine: [line: number]
}>()
const root = ref<HTMLElement>()
const host = ref<HTMLElement>()
let instance: ReturnType<typeof editor.create> | undefined
let model: ReturnType<typeof editor.createModel> | undefined

const mac = /Mac|iPhone|iPad/.test(navigator.platform)
const mod = mac ? '⌘' : 'Ctrl+'

type Look = { icon?: IconName; text?: string; label: string; keys?: string }
type Tool = Look & (
  | { kind: 'inline'; style: InlineStyle }
  | { kind: 'line'; style: LineStyle }
  | { kind: 'block'; style: BlockStyle }
  | { kind: 'link' }
  | { kind: 'image' })
const groups: Tool[][] = [
  [
    { kind: 'line', style: 'h2', text: 'H2', label: '標題 2' },
    { kind: 'line', style: 'h3', text: 'H3', label: '標題 3' },
  ],
  [
    { kind: 'inline', style: 'bold', icon: 'bold', label: '粗體', keys: 'B' },
    { kind: 'inline', style: 'italic', icon: 'italic', label: '斜體', keys: 'I' },
    { kind: 'inline', style: 'strike', icon: 'strike', label: '刪除線' },
    { kind: 'inline', style: 'code', icon: 'code', label: '行內程式碼' },
    { kind: 'link', icon: 'link', label: '連結', keys: 'K' },
    { kind: 'image', icon: 'image', label: '插入圖片' },
  ],
  [
    { kind: 'line', style: 'quote', icon: 'quote', label: '引用' },
    { kind: 'line', style: 'bullet', icon: 'listBullet', label: '項目清單' },
    { kind: 'line', style: 'ordered', icon: 'listOrdered', label: '編號清單' },
    { kind: 'line', style: 'task', icon: 'listTask', label: '待辦清單' },
  ],
  [
    { kind: 'block', style: 'codeBlock', icon: 'codeBlock', label: '程式碼區塊' },
    { kind: 'block', style: 'table', icon: 'table', label: '表格' },
    { kind: 'block', style: 'rule', icon: 'rule', label: '分隔線' },
  ],
]
function title(tool: Tool) {
  return tool.keys ? `${tool.label}（${mod}${tool.keys}）` : tool.label
}
function apply(tool: Tool) {
  if (!instance || props.readonly) return
  if (tool.kind === 'inline') toggleInline(instance, tool.style)
  else if (tool.kind === 'line') toggleLines(instance, tool.style)
  else if (tool.kind === 'block') insertBlockStyle(instance, tool.style)
  else if (tool.kind === 'image') picker.value?.click()
  else insertLink(instance)
}
const visibleGroups = computed(() => props.uploadImage ? groups : groups.map(group => group.filter(tool => tool.kind !== 'image')))

// ---- Images: paste, drop or pick; each gets a placeholder until its upload finishes ----
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const PLACEHOLDER = '![上傳中…]()'
const picker = ref<HTMLInputElement>()
const uploading = ref(0)

function altText(file: File) {
  const stem = file.name.replace(/\.[^.]*$/, '').replace(/[[\]()\\\r\n]+/g, ' ').trim().slice(0, 100)
  return !stem || /^image$/i.test(stem) ? '圖片' : stem
}

function imagesFrom(list: FileList | null | undefined) {
  return Array.from(list ?? []).filter(file => file.type.startsWith('image/'))
}

async function insertImages(files: File[]) {
  const ed = instance, upload = props.uploadImage
  if (!ed || !upload || props.readonly || !files.length) return
  const accepted = files.filter(file => {
    if (!IMAGE_TYPES.includes(file.type)) emit('notify', `「${file.name}」不是 PNG、JPEG、GIF 或 WebP 圖片。`)
    else if (file.size > MAX_IMAGE_BYTES) emit('notify', `「${file.name}」超過 10 MB。`)
    else return true
    return false
  })
  if (!accepted.length) return
  const start = ed.getSelection() ?? new Selection(1, 1, 1, 1)
  ed.pushUndoStop()
  ed.executeEdits('image', [{ range: start, text: accepted.map(() => PLACEHOLDER).join('\n'), forceMoveMarkers: true }])
  ed.pushUndoStop()
  // Decorations follow the placeholders while the writer keeps typing elsewhere.
  const marks = ed.createDecorationsCollection(accepted.map((_, index) => {
    const line = start.startLineNumber + index
    const column = index ? 1 : start.startColumn
    return {
      range: new Range(line, column, line, column + PLACEHOLDER.length),
      options: { stickiness: editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges, inlineClassName: 'md-uploading' },
    }
  }))
  uploading.value += accepted.length
  for (const [index, file] of accepted.entries()) {
    let replacement = ''
    try {
      const { url } = await upload(file)
      replacement = `![${altText(file)}](${url})`
    } catch (cause) {
      emit('notify', `「${file.name}」上傳失敗：${cause instanceof Error ? cause.message : '請稍後再試。'}`)
    }
    uploading.value--
    const range = marks.getRange(index)
    const current = ed.getModel()
    // If the writer deleted the placeholder meanwhile, leave the text alone (the unused upload is cleaned up later).
    if (!range || !current || current.getValueInRange(range) !== PLACEHOLDER) continue
    ed.executeEdits('image', [{ range, text: replacement }])
  }
  marks.clear()
}

function onPicked() {
  void insertImages(imagesFrom(picker.value?.files))
  if (picker.value) picker.value.value = ''
}

function hasFiles(event: DragEvent) {
  return [...(event.dataTransfer?.types ?? [])].includes('Files')
}
function onDragOver(event: DragEvent) {
  if (!props.uploadImage || props.readonly || !hasFiles(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}
function onDrop(event: DragEvent) {
  if (!props.uploadImage || props.readonly || !hasFiles(event) || !instance) return
  event.preventDefault()
  event.stopPropagation()
  const target = instance.getTargetAtClientPoint(event.clientX, event.clientY)?.position
  if (target) instance.setPosition(target)
  instance.focus()
  void insertImages(imagesFrom(event.dataTransfer?.files))
}

// Status bar
const words = ref(0)
const lines = ref(1)
const cursor = ref({ line: 1, column: 1 })
function updateCounts() {
  if (!model) return
  words.value = countWords(model.getValue())
  lines.value = model.getLineCount()
}

function reportScroll() {
  if (!instance) return
  const top = instance.getScrollTop()
  const height = instance.getLayoutInfo().height
  if (top > 0 && top + height >= instance.getScrollHeight() - 2) {
    emit('scrollLine', Infinity)
    return
  }
  const first = instance.getVisibleRanges()[0]?.startLineNumber ?? 1
  const start = instance.getTopForLineNumber(first)
  const span = instance.getTopForLineNumber(first + 1) - start || 1
  emit('scrollLine', first + Math.min(1, Math.max(0, (top - start) / span)))
}

/**
 * Pasting an address over selected text makes a link; pasting a picture (with no text alongside it,
 * unlike copied spreadsheet cells) uploads it; everything else pastes as usual.
 */
function onPaste(event: ClipboardEvent) {
  if (!instance || props.readonly || !instance.hasTextFocus()) return
  const text = event.clipboardData?.getData('text/plain') ?? ''
  const images = imagesFrom(event.clipboardData?.files)
  if (!text && images.length && props.uploadImage) {
    event.preventDefault()
    event.stopPropagation()
    void insertImages(images)
    return
  }
  if (pasteAsLink(instance, text)) {
    event.preventDefault()
    event.stopPropagation()
  }
}

onMounted(() => {
  if (!host.value) return
  model = editor.createModel(value.value, 'markdown')
  instance = editor.create(host.value, {
    model,
    ariaLabel: 'Markdown 編輯器',
    automaticLayout: true,
    minimap: { enabled: false },
    readOnly: props.readonly,
    scrollBeyondLastLine: false,
    // Wrap at the editor edge, but never beyond 140 columns on very wide screens.
    wordWrap: 'bounded',
    wordWrapColumn: 140,
    fontSize: 15,
    // Prose needs no word completion popups.
    quickSuggestions: false,
    wordBasedSuggestions: 'off',
    suggestOnTriggerCharacters: false,
    // Dropped files are images to upload (handled below), never file paths to type in.
    dropIntoEditor: { enabled: false },
  })
  const ed = instance
  const unlessReadonly = (action: () => void) => () => { if (!props.readonly) action() }
  ed.addAction({ id: 'md.bold', label: '粗體', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyB], run: unlessReadonly(() => toggleInline(ed, 'bold')) })
  ed.addAction({ id: 'md.italic', label: '斜體', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyI], run: unlessReadonly(() => toggleInline(ed, 'italic')) })
  ed.addAction({ id: 'md.link', label: '連結', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyK], run: unlessReadonly(() => insertLink(ed)) })
  ed.addAction({ id: 'md.save', label: '儲存', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyS], run: () => emit('save') })
  ed.onKeyDown(event => {
    // Never act while an input method is composing: Enter there confirms the Chinese text.
    if (props.readonly || event.browserEvent.isComposing || event.ctrlKey || event.altKey || event.metaKey) return
    const handled = event.keyCode === KeyCode.Enter && !event.shiftKey ? continueList(ed)
      : event.keyCode === KeyCode.Tab ? indentList(ed, event.shiftKey) : false
    if (handled) {
      event.preventDefault()
      event.stopPropagation()
    }
  })
  ed.onDidChangeModelContent(() => {
    if (model) value.value = model.getValue()
    updateCounts()
  })
  ed.onDidChangeCursorPosition(event => { cursor.value = { line: event.position.lineNumber, column: event.position.column } })
  ed.onDidScrollChange(event => { if (event.scrollTopChanged) reportScroll() })
  root.value?.addEventListener('paste', onPaste, true)
  root.value?.addEventListener('dragover', onDragOver, true)
  root.value?.addEventListener('drop', onDrop, true)
  updateCounts()
})

watch(value, text => {
  if (model && text !== model.getValue()) model.setValue(text)
})
watch(() => props.readonly, readOnly => instance?.updateOptions({ readOnly }))

onBeforeUnmount(() => {
  root.value?.removeEventListener('paste', onPaste, true)
  root.value?.removeEventListener('dragover', onDragOver, true)
  root.value?.removeEventListener('drop', onDrop, true)
  instance?.dispose()
  model?.dispose()
})
</script>

<template>
  <div ref="root" class="md-editor">
    <div class="toolbar" role="toolbar" aria-label="Markdown 格式">
      <template v-for="(group, index) in visibleGroups" :key="index">
        <span v-if="index" class="sep" aria-hidden="true" />
        <!-- mousedown.prevent keeps the selection in the editor while the button is pressed. -->
        <button v-for="tool in group" :key="tool.label" type="button" class="tool" :class="{ text: !tool.icon }"
          :aria-label="title(tool)" :title="title(tool)" :disabled="readonly" @mousedown.prevent @click="apply(tool)">
          <UiIcon v-if="tool.icon" :name="tool.icon" :size="17" />
          <span v-else aria-hidden="true">{{ tool.text }}</span>
        </button>
      </template>
    </div>
    <input ref="picker" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden
      aria-hidden="true" tabindex="-1" @change="onPicked">
    <div ref="host" class="editor-host" />
    <div class="status" aria-live="off">
      <span v-if="uploading" class="uploading" role="status">正在上傳 {{ uploading }} 張圖片…</span>
      <span>{{ words.toLocaleString() }} 字</span>
      <span>{{ lines.toLocaleString() }} 行</span>
      <span>第 {{ cursor.line }} 行，第 {{ cursor.column }} 欄</span>
    </div>
  </div>
</template>

<style scoped>
.md-editor {
  display: flex; flex-direction: column; height: var(--editor-height, clamp(28rem, calc(100vh - 23rem), 64rem)); box-sizing: border-box;
  border: 1px solid var(--ui-border); border-radius: .5rem; overflow: hidden; background: var(--ui-bg-surface);
}
.toolbar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 2px; padding: .3125rem .375rem;
  border-bottom: 1px solid var(--ui-border); background: var(--ui-bg-subtle);
}
.tool {
  display: grid; place-items: center; min-width: 2rem; height: 2rem; padding: 0 .375rem; border: 0; border-radius: var(--ui-radius-sm);
  background: transparent; color: var(--ui-text-secondary); font: inherit; font-size: var(--ui-text-sm); font-weight: 700; cursor: pointer;
}
.tool:hover:not(:disabled) { background: var(--ui-bg-muted); color: var(--ui-text); }
.tool:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: -2px; }
.tool:disabled { opacity: .45; cursor: default; }
.sep { width: 1px; height: 1.25rem; margin: 0 .25rem; background: var(--ui-border-strong); }
.editor-host { flex: 1; min-height: 0; }
.editor-host :deep(.md-uploading) { color: var(--ui-text-muted); font-style: italic; }
.uploading { margin-right: auto; color: var(--ui-accent); font-weight: 600; }
.status {
  display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .25rem 1rem; padding: .25rem .75rem;
  border-top: 1px solid var(--ui-border); background: var(--ui-bg-subtle); color: var(--ui-text-muted);
  font-size: var(--ui-text-xs); font-variant-numeric: tabular-nums;
}
</style>
