<script setup lang="ts">
import { editor, KeyCode, KeyMod, Range, Selection } from './monaco'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import UiIcon, { type IconName } from './app/components/UiIcon.vue'
import { GALLERY_LAYOUTS, LAYOUT_LABELS } from './gallery'
import { plainSnippet, SHORTCUTS, SNIPPETS, type Snippet } from './markdownSnippets'
import { helpers, inFence, registerMarkdownHelpers } from './markdownCompletions'
import { DOC_LINK, resolveLinks } from './app/links'
import { outlineOf, type OutlineEntry } from './markdown'
import DocumentPicker from './DocumentPicker.vue'
import type { DocumentRow } from './app/types'
import {
  continueList, countWords, indentList, insertBlockStyle, insertGallery, insertLink, pasteAsLink, toggleInline, toggleLines,
  type BlockStyle, type InlineStyle, type LineStyle,
} from './markdownCommands'

const value = defineModel<string>({ required: true })
const props = defineProps<{
  readonly: boolean
  /** Focus the editor with the cursor at the end, e.g. in a document that was just created. */
  autofocus?: boolean
  /** The document being edited (left out of document link suggestions). */
  documentId?: string
  /** Its collection: the 選擇文件 dialog starts there (P17). */
  categoryId?: string | null
  /** Uploads one image and resolves with its address; without it the editor takes no images or videos. */
  uploadImage?: (file: File) => Promise<{ url: string }>
  /** Uploads one video, reporting progress; aborting the signal cancels it. Without it the editor takes no videos. */
  uploadVideo?: (file: File, progress: (percent: number) => void, signal: AbortSignal) => Promise<{ url: string }>
}>()
const emit = defineEmits<{
  /** A message for the writer, such as a refused or failed image upload. */
  notify: [message: string]
  /** Ctrl+S: the page moves focus to the version note, where Enter saves. */
  save: []
  /** The source line (1-based, fractional) at the top of the editor, or Infinity at the very bottom. */
  scrollLine: [line: number]
  /** How many image or video uploads are still running (the page holds saving and leaving meanwhile). */
  uploading: [count: number]
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
  | { kind: 'image' }
  | { kind: 'video' }
  | { kind: 'gallery' }
  | { kind: 'outline' }
  | { kind: 'help' })
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
    { kind: 'video', icon: 'video', label: '插入影片（MP4、WebM，200 MB 以內）' },
    { kind: 'gallery', icon: 'gallery', label: '相簿（選取圖片後按下即可包成相簿）' },
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
  [{ kind: 'outline', icon: 'outline', label: '大綱', keys: 'Shift+O' }, { kind: 'help', icon: 'help', label: '語法說明', keys: '/' }],
]
function title(tool: Tool) {
  return tool.keys ? `${tool.label}（${mod}${tool.keys}）` : tool.label
}
function apply(tool: Tool) {
  if (tool.kind === 'outline') { toggleOutline(); return }
  if (!instance || props.readonly) return
  if (tool.kind === 'inline') toggleInline(instance, tool.style)
  else if (tool.kind === 'line') toggleLines(instance, tool.style)
  else if (tool.kind === 'block') insertBlockStyle(instance, tool.style)
  else if (tool.kind === 'image') picker.value?.click()
  else if (tool.kind === 'video') videoPicker.value?.click()
  else if (tool.kind === 'gallery') toggleGalleryMenu()
  else if (tool.kind === 'help') toggleHelp()
  else insertLink(instance)
}
// Gallery layout menu under the 「相簿」 button.
const galleryMenu = ref(false)
const galleryMenuAt = ref({ left: '0px', top: '0px' })
function toggleGalleryMenu() {
  const button = root.value?.querySelector<HTMLElement>('.tool[data-kind="gallery"]')
  if (button) galleryMenuAt.value = { left: `${button.offsetLeft}px`, top: `${button.offsetTop + button.offsetHeight + 4}px` }
  galleryMenu.value = !galleryMenu.value
}
const galleryChoices = [{ value: '', label: '跟隨預設版面' }, ...GALLERY_LAYOUTS.map(value => ({ value, label: `${LAYOUT_LABELS[value]}（${value}）` }))]
function chooseGallery(layout: string) {
  galleryMenu.value = false
  if (instance && !props.readonly) insertGallery(instance, layout)
}
function closeGalleryMenu(event: Event) {
  if (!galleryMenu.value) return
  if (event instanceof KeyboardEvent ? event.key === 'Escape' : !(event.target as Element).closest('.gallery-menu, .tool[data-kind="gallery"]')) {
    galleryMenu.value = false
    instance?.focus()
  }
}
// ---- Outline (P14b): the headings of the text being edited; choosing one moves the cursor there ----
const outlineOpen = ref(false)
const outlineAt = ref({ left: '0px', top: '0px' })
const outlineFilter = ref('')
const outlineEntries = ref<OutlineEntry[]>([])
const outlineIndex = ref(0)
const outlineInput = ref<HTMLInputElement>()
const outlineList = ref<HTMLElement>()
const outlineTop = computed(() => Math.min(...outlineEntries.value.map(entry => entry.level), 6))
const outlineShown = computed(() => {
  const words = outlineFilter.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  return outlineEntries.value.filter(entry => words.every(word => entry.text.toLowerCase().includes(word)))
})
function refreshOutline() {
  outlineEntries.value = model ? outlineOf(model.getValue()) : []
}
function toggleOutline(open = !outlineOpen.value) {
  if (!open) {
    outlineOpen.value = false
    instance?.focus()
    return
  }
  const button = root.value?.querySelector<HTMLElement>('.tool[data-kind="outline"]')
  const box = root.value
  if (button && box) {
    // End under the button's right edge when there is room; always stay inside the editor (the toolbar may wrap).
    const width = Math.min(352, box.clientWidth - 16)
    const left = Math.min(Math.max(8, button.offsetLeft + button.offsetWidth - width), box.clientWidth - width - 8)
    outlineAt.value = { left: `${left}px`, top: `${button.offsetTop + button.offsetHeight + 4}px` }
  }
  refreshOutline()
  outlineFilter.value = ''
  // Start at the section holding the cursor.
  const line = instance?.getPosition()?.lineNumber ?? 1
  const current = outlineEntries.value.reduce((found, entry, index) => entry.line <= line ? index : found, 0)
  outlineIndex.value = current
  outlineOpen.value = true
  void nextTick(() => { outlineInput.value?.focus(); revealOutlineChoice() })
}
function revealOutlineChoice() {
  outlineList.value?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' })
}
function goToHeading(entry: OutlineEntry | undefined) {
  const ed = instance, current = ed?.getModel()
  if (!ed || !current || !entry) return
  outlineOpen.value = false
  const line = Math.min(entry.line, current.getLineCount())
  ed.setPosition({ lineNumber: line, column: current.getLineMaxColumn(line) })
  ed.revealLineNearTop(line)
  ed.focus()
}
function onOutlineKey(event: KeyboardEvent) {
  if (event.isComposing) return
  const count = outlineShown.value.length
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (count) outlineIndex.value = (outlineIndex.value + (event.key === 'ArrowDown' ? 1 : count - 1)) % count
    void nextTick(revealOutlineChoice)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    goToHeading(outlineShown.value[outlineIndex.value])
  } else if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    toggleOutline(false)
  }
}
function closeOutline(event: MouseEvent) {
  if (outlineOpen.value && !(event.target as Element).closest('.outline-menu, .tool[data-kind="outline"]')) outlineOpen.value = false
}

// ---- Syntax help (P11e): a side panel (Ctrl+/) and a slash menu at the start of a line ----
const helpOpen = ref(false)
const helpGroups = computed(() => ['文字', '區塊', '圖片與影片'].map(name => ({
  name, items: SNIPPETS.filter(item => item.group === name && (item.action !== 'video' || props.uploadVideo)),
})))
const helpPanel = ref<HTMLElement>()
function toggleHelp(open = !helpOpen.value) {
  helpOpen.value = open
  if (!open) instance?.focus()
}
function pick(kind: 'image' | 'video' | 'docpicker') {
  if (props.readonly) return
  if (kind === 'docpicker') openDocPicker()
  else if (kind === 'image') picker.value?.click()
  else if (props.uploadVideo) videoPicker.value?.click()
}
// ---- P17: 選擇文件 — pick a document by collection and insert a link where the cursor was ----
const docPickerOpen = ref(false)
let pickerSelection: Selection | null = null
function openDocPicker() {
  pickerSelection = instance?.getSelection() ?? null
  docPickerOpen.value = true
}
/** Inserts the link at once; the dialog hands the focus back to the editor when it has finished closing. */
function closeDocPicker(row?: DocumentRow) {
  docPickerOpen.value = false
  const ed = instance, current = ed?.getModel()
  if (!ed || !current) return
  ed.focus()
  if (pickerSelection) ed.setSelection(pickerSelection)
  if (!row || props.readonly) return
  const sel = ed.getSelection() ?? pickerSelection
  if (!sel) return
  const selected = current.getValueInRange(sel)
  // Selected text on one line becomes the link text; otherwise the title goes in after the selection.
  const useSelection = selected.trim() && !selected.includes('\n')
  const text = useSelection ? selected : row.title.replace(/[[\]]/g, '\\$&')
  const range = useSelection ? sel : new Range(sel.endLineNumber, sel.endColumn, sel.endLineNumber, sel.endColumn)
  ed.executeEdits('docpicker', [{ range, text: `[${text}](/app/docs/${row.id}/)`, forceMoveMarkers: true }])
}

type SnippetEditor = { insert: (template: string) => void }
/** Types `[[` at the cursor and opens the document search (P13b). */
function startDocLink() {
  const ed = instance, sel = ed?.getSelection()
  if (!ed || !sel || props.readonly) return
  ed.executeEdits('doclink', [{ range: sel, text: '[[', forceMoveMarkers: true }])
  ed.trigger('doclink', 'editor.action.triggerSuggest', {})
}
function insertSnippet(snippet: Snippet) {
  const ed = instance, model = ed?.getModel(), sel = ed?.getSelection()
  if (!ed || !model || !sel || props.readonly) return
  ed.focus()
  if (snippet.action === 'doclink') { startDocLink(); return }
  if (snippet.action === 'docpicker') { openDocPicker(); return }
  if (snippet.action) { pick(snippet.action); return }
  if (snippet.block && model.getLineContent(sel.endLineNumber).trim()) {
    // Block syntax starts on a line of its own, after a blank line.
    const end = model.getLineMaxColumn(sel.endLineNumber)
    ed.executeEdits('help', [{ range: new Range(sel.endLineNumber, end, sel.endLineNumber, end), text: '\n\n' }])
    ed.setPosition({ lineNumber: sel.endLineNumber + 2, column: 1 })
  }
  ed.getContribution<SnippetEditor & editor.IEditorContribution>('snippetController2')?.insert(snippet.insert ?? '')
}

const visibleGroups = computed(() => groups.map(group => group.filter(tool =>
  (tool.kind !== 'image' || props.uploadImage) && (tool.kind !== 'video' || (props.uploadImage && props.uploadVideo)))))

// ---- Images and videos: paste, drop or pick; each gets a placeholder until its upload finishes ----
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
const VIDEO_TYPES = ['video/mp4', 'video/webm']
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const MAX_VIDEO_BYTES = 200 * 1024 * 1024 // VIDEO_MAX_BYTES on the server
const PLACEHOLDER = { image: '![上傳中…]()', video: '![影片上傳中…]()' } as const
type Kind = keyof typeof PLACEHOLDER
const picker = ref<HTMLInputElement>()
const videoPicker = ref<HTMLInputElement>()
/** Uploads not finished yet; a video shows its progress in the status bar. */
const pending = ref<{ id: number; kind: Kind; percent: number }[]>([])
let nextUpload = 0
const uploadingImages = computed(() => pending.value.filter(item => item.kind === 'image').length)
const uploadingVideo = computed(() => pending.value.find(item => item.kind === 'video'))
watch(() => pending.value.length, count => emit('uploading', count))
const cancels = new Set<AbortController>()

function altText(file: File, kind: Kind) {
  const fallback = kind === 'image' ? '圖片' : '影片'
  const stem = file.name.replace(/\.[^.]*$/, '').replace(/[[\]()\\\r\n]+/g, ' ').trim().slice(0, 100)
  return !stem || /^(image|video)$/i.test(stem) ? fallback : stem
}

function kindOf(file: File): Kind | undefined {
  if (IMAGE_TYPES.includes(file.type)) return 'image'
  // Some systems report no type (or a generic one) for .webm; the server checks the header either way.
  const typeless = !file.type || file.type === 'application/octet-stream'
  if (props.uploadVideo && (VIDEO_TYPES.includes(file.type) || (typeless && /\.(mp4|webm)$/i.test(file.name)))) return 'video'
}

/** Why a file cannot go in, or nothing when it can. */
function refusal(file: File, kind: Kind | undefined) {
  if (!kind) {
    if (props.uploadVideo && (file.type === 'video/quicktime' || /\.mov$/i.test(file.name))) {
      return `「${file.name}」是 QuickTime（.mov）影片，請先轉成 MP4（H.264）再上傳。`
    }
    return props.uploadVideo
      ? `「${file.name}」不是可以插入的圖片或影片（PNG、JPEG、GIF、WebP、MP4、WebM）。`
      : `「${file.name}」不是 PNG、JPEG、GIF 或 WebP 圖片。`
  }
  if (kind === 'image' && file.size > MAX_IMAGE_BYTES) return `「${file.name}」超過 10 MB。`
  if (kind === 'video' && file.size > MAX_VIDEO_BYTES) return `「${file.name}」超過 200 MB。`
  if (!file.size) return `「${file.name}」是空白檔案。`
}

function mediaFrom(list: FileList | null | undefined) {
  return Array.from(list ?? []).filter(file => file.type.startsWith('image/') || file.type.startsWith('video/'))
}

async function insertFiles(files: File[]) {
  const ed = instance
  if (!ed || !props.uploadImage || props.readonly || !files.length) return
  const accepted: { file: File; kind: Kind }[] = []
  for (const file of files) {
    const kind = kindOf(file)
    const reason = refusal(file, kind)
    if (reason) emit('notify', reason)
    else accepted.push({ file, kind: kind! })
  }
  if (!accepted.length) return
  const texts = accepted.map(item => PLACEHOLDER[item.kind])
  const start = ed.getSelection() ?? new Selection(1, 1, 1, 1)
  ed.pushUndoStop()
  ed.executeEdits('upload', [{ range: start, text: texts.join('\n'), forceMoveMarkers: true }])
  ed.pushUndoStop()
  // Decorations follow the placeholders while the writer keeps typing elsewhere; a video's shows its progress.
  const look = (percent?: number) => ({
    stickiness: editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges, inlineClassName: 'md-uploading',
    ...(percent === undefined ? {} : { after: { content: ` ${percent}%`, inlineClassName: 'md-uploading-progress' } }),
  })
  const marks = ed.createDecorationsCollection(texts.map((text, index) => {
    const line = start.startLineNumber + index
    const column = index ? 1 : start.startColumn
    return { range: new Range(line, column, line, column + text.length), options: look() }
  }))
  const ids = accepted.map(() => ++nextUpload)
  pending.value = [...pending.value, ...accepted.map((item, index) => ({ id: ids[index], kind: item.kind, percent: 0 }))]
  const done = (id: number) => { pending.value = pending.value.filter(other => other.id !== id) }
  const setPercent = (id: number, percent: number) => {
    pending.value = pending.value.map(other => other.id === id ? { ...other, percent } : other)
  }
  // A placeholder the writer deleted (or undid) means "never mind".
  const stillThere = (index: number) => {
    const range = marks.getRange(index)
    return !!range && ed.getModel()?.getValueInRange(range) === texts[index]
  }
  const showProgress = (index: number, percent: number) => {
    marks.set(texts.map((_, other) => ({
      range: marks.getRange(other) ?? new Range(1, 1, 1, 1),
      options: look(other === index ? percent : undefined),
    })))
  }
  for (const [index, { file, kind }] of accepted.entries()) {
    if (!stillThere(index)) { done(ids[index]); continue }
    let replacement = ''
    const cancel = new AbortController()
    cancels.add(cancel)
    const watcher = ed.getModel()?.onDidChangeContent(() => { if (!stillThere(index)) cancel.abort() })
    try {
      const { url } = kind === 'image'
        ? await props.uploadImage(file)
        : await props.uploadVideo!(file, percent => {
          setPercent(ids[index], percent)
          showProgress(index, percent)
        }, cancel.signal)
      replacement = `![${altText(file, kind)}](${url})`
    } catch (cause) {
      if (!cancel.signal.aborted) {
        emit('notify', `「${file.name}」上傳失敗：${cause instanceof Error ? cause.message : '請稍後再試。'}`)
      }
    } finally {
      watcher?.dispose()
      cancels.delete(cancel)
      done(ids[index])
    }
    // If the writer deleted the placeholder meanwhile, leave the text alone (an unused upload is cleaned up later).
    if (!stillThere(index)) continue
    ed.executeEdits('upload', [{ range: marks.getRange(index)!, text: replacement }])
  }
  marks.clear()
}

function onPicked(event: Event) {
  const input = event.target as HTMLInputElement
  void insertFiles(Array.from(input.files ?? []))
  input.value = ''
}

function hasFiles(event: DragEvent) {
  return [...(event.dataTransfer?.types ?? [])].includes('Files')
}
const dragging = ref(false)
function onDragOver(event: DragEvent) {
  if (!props.uploadImage || props.readonly || !hasFiles(event)) return
  event.preventDefault()
  dragging.value = true
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}
function onDragLeave(event: DragEvent) {
  if (!root.value?.contains(event.relatedTarget as Node | null)) dragging.value = false
}
function onDrop(event: DragEvent) {
  dragging.value = false
  if (!props.uploadImage || props.readonly || !hasFiles(event) || !instance) return
  event.preventDefault()
  event.stopPropagation()
  const target = instance.getTargetAtClientPoint(event.clientX, event.clientY)?.position
  if (target) instance.setPosition(target)
  instance.focus()
  // Every dropped file gets an answer: unsupported ones (.mov, PDFs…) are named in a notice.
  void insertFiles(Array.from(event.dataTransfer?.files ?? []))
}

const onDragEnd = () => { dragging.value = false }

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
/** A pasted address of one of this site's documents, as the short path a link should use. */
function pastedDocument(text: string) {
  const trimmed = text.trim()
  if (!trimmed || /\s/.test(trimmed)) return undefined
  try {
    const url = new URL(trimmed, location.href)
    const id = /^(https?:)?\/\//.test(trimmed) && url.origin !== location.origin ? undefined : DOC_LINK.exec(url.pathname)?.[1]
    return id && /^(https?:\/\/|\/)/.test(trimmed) ? { id: id.toLowerCase(), path: `/app/docs/${id.toLowerCase()}/${url.hash}` } : undefined
  } catch {
    return undefined
  }
}
/** P13b: pasting a document's address inserts [its current title](/app/docs/<id>/); unknown ones paste as they are. */
async function pasteDocLink(text: string, target: { id: string; path: string }) {
  const ed = instance
  if (!ed) return
  const states = await resolveLinks([target.id])
  const state = states[target.id]
  const sel = ed.getSelection()
  if (!sel) return
  const title = state?.status === 'ok' && state.title ? state.title.replace(/[[\]]/g, '\\$&') : undefined
  const inserted = title ? `[${title}](${target.path})` : text
  ed.pushUndoStop()
  ed.executeEdits('paste', [{ range: sel, text: inserted, forceMoveMarkers: true }])
  ed.pushUndoStop()
}
function onPaste(event: ClipboardEvent) {
  if (!instance || props.readonly || !instance.hasTextFocus()) return
  const text = event.clipboardData?.getData('text/plain') ?? ''
  const linked = !event.clipboardData?.files.length ? pastedDocument(text) : undefined
  if (linked) {
    event.preventDefault()
    event.stopPropagation()
    // Selected text (on one line) becomes the link text; otherwise the document's current title does.
    const sel = instance.getSelection(), current = instance.getModel()
    const chosen = sel && current && !sel.isEmpty() && sel.startLineNumber === sel.endLineNumber ? current.getValueInRange(sel) : ''
    if (chosen && !chosen.includes('](')) {
      instance.pushUndoStop()
      instance.executeEdits('paste', [{ range: sel!, text: `[${chosen}](${linked.path})`, forceMoveMarkers: true }])
      instance.pushUndoStop()
    } else {
      void pasteDocLink(text, linked)
    }
    return
  }
  const media = mediaFrom(event.clipboardData?.files)
  if (!text && media.length && props.uploadImage) {
    event.preventDefault()
    event.stopPropagation()
    void insertFiles(media)
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
    // Only this editor's own suggestions: the slash menu and gallery layout names (P11e).
    suggestOnTriggerCharacters: true,
    // No icons: the codicon font is not loaded (core editor only), so they would show as empty boxes.
    suggest: { showWords: false, showIcons: false, filterGraceful: true, insertMode: 'replace' },
    // Enter accepts a suggestion only when that changes the text: typing a whole layout name then Enter
    // still starts a new line.
    acceptSuggestionOnEnter: 'smart',
    // Dropped files are images to upload (handled below), never file paths to type in.
    dropIntoEditor: { enabled: false },
  })
  const ed = instance
  const unlessReadonly = (action: () => void) => () => { if (!props.readonly) action() }
  ed.addAction({ id: 'md.bold', label: '粗體', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyB], run: unlessReadonly(() => toggleInline(ed, 'bold')) })
  ed.addAction({ id: 'md.italic', label: '斜體', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyI], run: unlessReadonly(() => toggleInline(ed, 'italic')) })
  ed.addAction({ id: 'md.link', label: '連結', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyK], run: unlessReadonly(() => insertLink(ed)) })
  ed.addAction({ id: 'md.save', label: '儲存', keybindings: [KeyMod.CtrlCmd | KeyCode.KeyS], run: () => emit('save') })
  ed.addAction({ id: 'md.help', label: '語法說明', keybindings: [KeyMod.CtrlCmd | KeyCode.Slash], run: () => toggleHelp() })
  ed.addAction({ id: 'md.outline', label: '大綱', keybindings: [KeyMod.CtrlCmd | KeyMod.Shift | KeyCode.KeyO], run: () => toggleOutline() })
  registerMarkdownHelpers()
  // The document search after `[[` (P13b) closes in several ways Monaco does not undo by itself: a space ends
  // the session, an input method composing Chinese hides the list, and switching input methods can take the focus
  // away for a moment. Whenever the cursor is still in a `[[…` search and no list is showing, open it again.
  let reopen = 0
  const reopenSearch = () => {
    window.clearTimeout(reopen)
    reopen = window.setTimeout(() => {
      const position = ed.getPosition(), current = ed.getModel()
      if (!position || !current || props.readonly || !ed.hasWidgetFocus()) return
      const before = current.getValueInRange(new Range(position.lineNumber, 1, position.lineNumber, position.column))
      const search = /\[\[([^[\]\n]{0,80})$/.exec(before)
      if (!search || inFence(current, position.lineNumber)) return
      const showing = !!root.value?.querySelector('.suggest-widget.visible')
      // A space starts a new word: refresh even a showing list so it searches with every word typed.
      if (showing && !/\s/.test(search[1])) return
      if (showing) ed.trigger('doclink', 'hideSuggestWidget', {})
      ed.trigger('doclink', 'editor.action.triggerSuggest', {})
    }, 150)
  }
  model.onDidChangeContent(reopenSearch)
  ed.onDidCompositionEnd(reopenSearch)
  ed.onDidFocusEditorText(reopenSearch)
  ed.onDidFocusEditorWidget(reopenSearch)
  if (model) helpers.set(model.uri.toString(), { readonly: () => props.readonly, pick, documentId: () => props.documentId })
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
  if (props.autofocus) {
    const last = model.getLineCount()
    ed.setPosition({ lineNumber: last, column: model.getLineMaxColumn(last) })
    ed.focus()
  }
  root.value?.addEventListener('paste', onPaste, true)
  root.value?.addEventListener('dragover', onDragOver, true)
  root.value?.addEventListener('drop', onDrop, true)
  root.value?.addEventListener('dragleave', onDragLeave, true)
  document.addEventListener('mousedown', closeGalleryMenu)
  document.addEventListener('mousedown', closeOutline)
  document.addEventListener('keydown', closeGalleryMenu)
  window.addEventListener('dragend', onDragEnd, true)
  updateCounts()
})

watch(value, text => {
  if (model && text !== model.getValue()) model.setValue(text)
})
watch(() => props.readonly, readOnly => instance?.updateOptions({ readOnly }))

onBeforeUnmount(() => {
  if (model) helpers.delete(model.uri.toString())
  root.value?.removeEventListener('paste', onPaste, true)
  root.value?.removeEventListener('dragover', onDragOver, true)
  root.value?.removeEventListener('drop', onDrop, true)
  root.value?.removeEventListener('dragleave', onDragLeave, true)
  document.removeEventListener('mousedown', closeGalleryMenu)
  document.removeEventListener('mousedown', closeOutline)
  document.removeEventListener('keydown', closeGalleryMenu)
  window.removeEventListener('dragend', onDragEnd, true)
  // Leaving the editor stops uploads that would only land in a draft nobody sees.
  for (const cancel of cancels) cancel.abort()
  if (pending.value.length) emit('uploading', 0)
  instance?.dispose()
  model?.dispose()
})
</script>

<template>
  <div ref="root" class="md-editor" :class="{ dragging }" :data-file-drop="uploadImage && !readonly ? '' : undefined">
    <div class="toolbar" role="toolbar" aria-label="Markdown 格式">
      <template v-for="(group, index) in visibleGroups" :key="index">
        <span v-if="index" class="sep" aria-hidden="true" />
        <!-- mousedown.prevent keeps the selection in the editor while the button is pressed. -->
        <button v-for="tool in group" :key="tool.label" type="button" class="tool"
          :class="{ text: !tool.icon, pressed: (tool.kind === 'gallery' && galleryMenu) || (tool.kind === 'outline' && outlineOpen) }"
          :data-kind="tool.kind" :aria-haspopup="tool.kind === 'gallery' ? 'menu' : tool.kind === 'outline' ? 'dialog' : undefined"
          :aria-expanded="tool.kind === 'gallery' ? galleryMenu : tool.kind === 'outline' ? outlineOpen : undefined"
          :aria-label="title(tool)" :title="title(tool)" :disabled="readonly && tool.kind !== 'outline'" @mousedown.prevent @click="apply(tool)">
          <UiIcon v-if="tool.icon" :name="tool.icon" :size="17" />
          <span v-else aria-hidden="true">{{ tool.text }}</span>
        </button>
      </template>
    </div>
    <div v-if="galleryMenu" class="gallery-menu" role="menu" aria-label="相簿版面" :style="galleryMenuAt">
      <button v-for="choice in galleryChoices" :key="choice.value" type="button" role="menuitem" @mousedown.prevent
        @click="chooseGallery(choice.value)">{{ choice.label }}</button>
    </div>
    <div v-if="outlineOpen" class="outline-menu" role="dialog" aria-label="大綱" :style="outlineAt">
      <input ref="outlineInput" v-model="outlineFilter" class="outline-filter" type="search" placeholder="篩選標題"
        aria-label="篩選標題" role="combobox" aria-controls="md-outline-list" aria-autocomplete="list" :aria-expanded="true"
        :aria-activedescendant="outlineShown.length ? `md-outline-${outlineIndex}` : undefined" @keydown="onOutlineKey" @input="outlineIndex = 0">
      <ul v-if="outlineShown.length" id="md-outline-list" ref="outlineList" class="outline-list" role="listbox" aria-label="標題">
        <li v-for="(entry, index) in outlineShown" :id="`md-outline-${index}`" :key="`${entry.line}-${index}`" role="option"
          :aria-selected="index === outlineIndex" :style="{ paddingInlineStart: `${.5 + Math.min(Math.max(0, entry.level - outlineTop), 3) * .75}rem` }"
          @mousedown.prevent @mousemove="outlineIndex = index" @click="goToHeading(entry)">
          <span class="outline-text">{{ entry.text }}</span><span class="outline-line">{{ entry.line }}</span>
        </li>
      </ul>
      <p v-else class="outline-empty">{{ outlineEntries.length ? '沒有符合的標題。' : '還沒有標題。輸入 # 加空白開始一個標題。' }}</p>
    </div>
    <input ref="picker" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden
      aria-hidden="true" tabindex="-1" @change="onPicked">
    <input ref="videoPicker" type="file" accept="video/mp4,video/webm,.mp4,.webm" hidden
      aria-hidden="true" tabindex="-1" @change="onPicked">
    <div ref="host" class="editor-host" />
    <aside v-if="helpOpen" ref="helpPanel" class="help-panel" aria-label="Markdown 語法說明" @keydown.esc.stop="toggleHelp(false)">
      <div class="help-head">
        <strong>語法說明</strong>
        <button type="button" class="help-close" aria-label="關閉語法說明" @click="toggleHelp(false)"><UiIcon name="close" :size="16" /></button>
      </div>
      <p class="help-tip">在空白行開頭輸入 <kbd>/</kbd> 可以快速插入，例如 <code>/相簿</code>、<code>/表格</code>。</p>
      <section v-for="group in helpGroups" :key="group.name" class="help-group">
        <h3>{{ group.name }}</h3>
        <div v-for="item in group.items" :key="item.id" class="help-item">
          <div class="help-item-head">
            <span class="help-label">{{ item.label }}</span>
            <button type="button" class="help-insert" :disabled="readonly" @click="insertSnippet(item)">
              {{ item.action === 'image' || item.action === 'video' ? '選擇檔案' : '插入' }}
            </button>
          </div>
          <p class="help-desc">{{ item.description }}</p>
          <pre class="help-code"><code>{{ plainSnippet(item) }}</code></pre>
        </div>
      </section>
      <section class="help-group">
        <h3>快捷鍵</h3>
        <dl class="help-keys">
          <template v-for="shortcut in SHORTCUTS" :key="shortcut.keys">
            <dt><kbd>{{ shortcut.keys }}</kbd></dt><dd>{{ shortcut.label }}</dd>
          </template>
        </dl>
      </section>
    </aside>
    <DocumentPicker :visible="docPickerOpen" :start-category="categoryId" :exclude-id="documentId"
      @pick="closeDocPicker" @cancel="closeDocPicker()" @closed="instance?.focus()" />
    <div v-if="dragging" class="drop-hint" aria-hidden="true">
      <UiIcon :name="uploadVideo ? 'video' : 'image'" :size="20" />
      <span>{{ uploadVideo ? '放開即可插入圖片或影片' : '放開即可插入圖片（PNG、JPEG、GIF、WebP）' }}</span>
    </div>
    <div class="status" aria-live="off">
      <span v-if="pending.length" class="uploading" role="status">
        <template v-if="uploadingVideo">正在上傳影片 {{ uploadingVideo.percent }}%</template>
        <template v-if="uploadingVideo && uploadingImages">，</template>
        <template v-if="uploadingImages">正在上傳 {{ uploadingImages }} 張圖片</template>…
      </span>
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
.md-editor { position: relative; }
.help-panel {
  position: absolute; top: 0; right: 0; bottom: 1.75rem; z-index: 9; width: min(22rem, 100%); box-sizing: border-box; overflow-y: auto;
  padding: var(--ui-space-3) var(--ui-space-4) var(--ui-space-5); border-left: 1px solid var(--ui-border);
  background: var(--ui-bg-surface); box-shadow: -8px 0 24px rgb(16 24 40 / .08);
}
.help-head { display: flex; align-items: center; justify-content: space-between; position: sticky; top: calc(-1 * var(--ui-space-3)); margin: calc(-1 * var(--ui-space-3)) calc(-1 * var(--ui-space-4)) 0; padding: var(--ui-space-3) var(--ui-space-4); background: var(--ui-bg-surface); border-bottom: 1px solid var(--ui-border); }
.help-close { display: grid; place-items: center; width: 1.9rem; height: 1.9rem; border: 0; border-radius: var(--ui-radius-sm); background: none; color: var(--ui-text-muted); cursor: pointer; }
.help-close:hover { background: var(--ui-bg-subtle); color: var(--ui-text); }
.help-tip { margin: var(--ui-space-3) 0 0; color: var(--ui-text-secondary); font-size: var(--ui-text-sm); line-height: 1.6; }
.help-group h3 { margin: var(--ui-space-4) 0 var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }
.help-item { padding: var(--ui-space-2) 0; border-top: 1px solid var(--ui-border-subtle, var(--ui-border)); }
.help-item-head { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-2); }
.help-label { font-weight: 600; }
.help-insert { padding: 2px var(--ui-space-2); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-bg-surface); color: var(--ui-accent); font: inherit; font-size: var(--ui-text-xs); font-weight: 600; cursor: pointer; }
.help-insert:hover:not(:disabled) { background: var(--ui-accent-soft); }
.help-insert:disabled { opacity: .5; cursor: default; }
.help-desc { margin: 2px 0 var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-xs); line-height: 1.5; }
.help-code { margin: 0; padding: var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-bg-subtle); font-size: .78rem; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
.help-keys { display: grid; grid-template-columns: auto 1fr; gap: var(--ui-space-2) var(--ui-space-3); margin: 0; font-size: var(--ui-text-sm); }
.help-keys dd { margin: 0; color: var(--ui-text-secondary); }
.help-panel kbd { padding: 1px 5px; border: 1px solid var(--ui-border); border-radius: 4px; background: var(--ui-bg-subtle); font-family: inherit; font-size: .75rem; white-space: nowrap; }
.gallery-menu {
  position: absolute; z-index: 10; display: grid; min-width: 12rem; padding: .3rem;
  border: 1px solid var(--ui-border); border-radius: .5rem; background: var(--ui-bg-surface); box-shadow: var(--ui-shadow-lg);
}
.gallery-menu button { padding: .45rem .7rem; border: 0; border-radius: .35rem; background: none; color: var(--ui-text); font: inherit; text-align: left; cursor: pointer; }
.gallery-menu button:hover, .gallery-menu button:focus-visible { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.outline-menu {
  position: absolute; z-index: 10; display: flex; flex-direction: column; width: min(22rem, calc(100% - 1rem)); max-height: min(24rem, 70%);
  border: 1px solid var(--ui-border); border-radius: .5rem; background: var(--ui-bg-surface); box-shadow: var(--ui-shadow-lg); overflow: hidden;
}
.outline-filter {
  margin: .4rem; padding: .4rem .6rem; border: 1px solid var(--ui-border); border-radius: .35rem; background: var(--ui-bg-surface);
  color: var(--ui-text); font: inherit; font-size: var(--ui-text-sm);
}
.outline-filter:focus { outline: 2px solid var(--ui-accent); outline-offset: -1px; }
.outline-list { flex: 1; min-height: 0; list-style: none; margin: 0; padding: 0 .3rem .3rem; overflow-y: auto; }
.outline-list li {
  display: flex; gap: var(--ui-space-2); align-items: baseline; padding-block: .35rem; padding-inline-end: .5rem; border-radius: .35rem;
  color: var(--ui-text); font-size: var(--ui-text-sm); cursor: pointer;
}
.outline-list li[aria-selected="true"] { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.outline-text { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.outline-line { color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-variant-numeric: tabular-nums; }
.outline-empty { margin: 0; padding: .5rem .75rem .75rem; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.tool.pressed { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.md-editor.dragging { border-color: var(--ui-accent); box-shadow: 0 0 0 2px var(--ui-accent-soft); }
.drop-hint {
  position: absolute; left: 50%; bottom: 2.75rem; transform: translateX(-50%); display: inline-flex; align-items: center; gap: var(--ui-space-2);
  padding: var(--ui-space-2) var(--ui-space-4); border-radius: var(--ui-radius-md); background: var(--ui-accent); color: #fff;
  font-weight: 600; box-shadow: var(--ui-shadow-lg); pointer-events: none; white-space: nowrap; z-index: 5;
}
.editor-host :deep(.md-uploading) { color: var(--ui-text-muted); font-style: italic; }
.editor-host :deep(.md-uploading-progress) { color: var(--ui-accent); font-weight: 600; }
.uploading { margin-right: auto; color: var(--ui-accent); font-weight: 600; }
.status {
  display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .25rem 1rem; padding: .25rem .75rem;
  border-top: 1px solid var(--ui-border); background: var(--ui-bg-subtle); color: var(--ui-text-muted);
  font-size: var(--ui-text-xs); font-variant-numeric: tabular-nums;
}
</style>
