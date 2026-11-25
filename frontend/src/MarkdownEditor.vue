<script setup lang="ts">
import { editor, KeyCode, KeyMod, Range, Selection } from './monaco'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import UiIcon, { type IconName } from './app/components/UiIcon.vue'
import { GALLERY_LAYOUTS, LAYOUT_LABELS } from './gallery'
import {
  continueList, countWords, indentList, insertBlockStyle, insertGallery, insertLink, pasteAsLink, toggleInline, toggleLines,
  type BlockStyle, type InlineStyle, type LineStyle,
} from './markdownCommands'

const value = defineModel<string>({ required: true })
const props = defineProps<{
  readonly: boolean
  /** Focus the editor with the cursor at the end, e.g. in a document that was just created. */
  autofocus?: boolean
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
  | { kind: 'gallery' })
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
  else if (tool.kind === 'video') videoPicker.value?.click()
  else if (tool.kind === 'gallery') toggleGalleryMenu()
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
function onPaste(event: ClipboardEvent) {
  if (!instance || props.readonly || !instance.hasTextFocus()) return
  const text = event.clipboardData?.getData('text/plain') ?? ''
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
  document.addEventListener('keydown', closeGalleryMenu)
  window.addEventListener('dragend', onDragEnd, true)
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
  root.value?.removeEventListener('dragleave', onDragLeave, true)
  document.removeEventListener('mousedown', closeGalleryMenu)
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
        <button v-for="tool in group" :key="tool.label" type="button" class="tool" :class="{ text: !tool.icon, pressed: tool.kind === 'gallery' && galleryMenu }"
          :data-kind="tool.kind" :aria-haspopup="tool.kind === 'gallery' ? 'menu' : undefined" :aria-expanded="tool.kind === 'gallery' ? galleryMenu : undefined"
          :aria-label="title(tool)" :title="title(tool)" :disabled="readonly" @mousedown.prevent @click="apply(tool)">
          <UiIcon v-if="tool.icon" :name="tool.icon" :size="17" />
          <span v-else aria-hidden="true">{{ tool.text }}</span>
        </button>
      </template>
    </div>
    <div v-if="galleryMenu" class="gallery-menu" role="menu" aria-label="相簿版面" :style="galleryMenuAt">
      <button v-for="choice in galleryChoices" :key="choice.value" type="button" role="menuitem" @mousedown.prevent
        @click="chooseGallery(choice.value)">{{ choice.label }}</button>
    </div>
    <input ref="picker" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden
      aria-hidden="true" tabindex="-1" @change="onPicked">
    <input ref="videoPicker" type="file" accept="video/mp4,video/webm,.mp4,.webm" hidden
      aria-hidden="true" tabindex="-1" @change="onPicked">
    <div ref="host" class="editor-host" />
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
.gallery-menu {
  position: absolute; z-index: 10; display: grid; min-width: 12rem; padding: .3rem;
  border: 1px solid var(--ui-border); border-radius: .5rem; background: var(--ui-bg-surface); box-shadow: var(--ui-shadow-lg);
}
.gallery-menu button { padding: .45rem .7rem; border: 0; border-radius: .35rem; background: none; color: var(--ui-text); font: inherit; text-align: left; cursor: pointer; }
.gallery-menu button:hover, .gallery-menu button:focus-visible { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
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
