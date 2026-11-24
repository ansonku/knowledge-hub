// Markdown editing commands for the Monaco editor: toolbar actions, shortcuts and list continuation.
// Every command edits the plain Markdown text, so what is saved is exactly what the writer sees.
import { Range, Selection, type editor } from './monaco'

type Editor = editor.IStandaloneCodeEditor
type Model = editor.ITextModel

export type InlineStyle = 'bold' | 'italic' | 'strike' | 'code'
export type LineStyle = 'h2' | 'h3' | 'quote' | 'bullet' | 'ordered' | 'task'
export type BlockStyle = 'codeBlock' | 'table' | 'rule'

const INLINE: Record<InlineStyle, { char: string; size: number; placeholder: string }> = {
  bold: { char: '*', size: 2, placeholder: '粗體文字' },
  italic: { char: '*', size: 1, placeholder: '斜體文字' },
  strike: { char: '~', size: 2, placeholder: '刪除文字' },
  code: { char: '`', size: 1, placeholder: '程式碼' },
}

/** Indent, then one heading, quote or list marker (with an optional task box). */
const PREFIX = /^(\s*)(#{1,6}\s+|>\s?|[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+[.)]\s+)?/
/** A list item: indent, marker, spacing, optional task box. */
const LIST_ITEM = /^(\s*)([-*+]|\d+[.)])(\s+)(\[[ xX]\]\s+)?/
const QUOTE = /^(\s*(?:>\s?)+)/
const URL_ONLY = /^https?:\/\/\S+$/

function edit(ed: Editor, edits: { range: Range; text: string }[], selection?: Selection) {
  ed.pushUndoStop()
  ed.executeEdits('markdown', edits.map(item => ({ ...item, forceMoveMarkers: true })), selection ? [selection] : undefined)
  ed.pushUndoStop()
  ed.focus()
}

function run(model: Model, line: number, column: number, char: string, step: 1 | -1) {
  const text = model.getLineContent(line)
  let count = 0
  for (let index = column - 1 + (step < 0 ? -1 : 0); index >= 0 && index < text.length && text[index] === char; index += step) count++
  return count
}

/** Bold, italic, strikethrough or inline code: wraps the selection, or removes the marks when already there. */
export function toggleInline(ed: Editor, style: InlineStyle) {
  const model = ed.getModel(), sel = ed.getSelection()
  if (!model || !sel) return
  const { char, size, placeholder } = INLINE[style]
  const mark = char.repeat(size)
  const text = model.getValueInRange(sel)
  const singleLine = sel.startLineNumber === sel.endLineNumber
  const isOn = (count: number) => size === 1 ? count % 2 === 1 : count >= 2

  // The marks sit just outside the selection: remove them.
  const before = run(model, sel.startLineNumber, sel.startColumn, char, -1)
  const after = run(model, sel.endLineNumber, sel.endColumn, char, 1)
  if (text && isOn(Math.min(before, after))) {
    const shift = singleLine ? size : 0
    edit(ed, [
      { range: new Range(sel.endLineNumber, sel.endColumn, sel.endLineNumber, sel.endColumn + size), text: '' },
      { range: new Range(sel.startLineNumber, sel.startColumn - size, sel.startLineNumber, sel.startColumn), text: '' },
    ], new Selection(sel.startLineNumber, sel.startColumn - size, sel.endLineNumber, sel.endColumn - shift))
    return
  }
  // The selection includes the marks: unwrap it.
  if (singleLine && text.length > size * 2 && text.startsWith(mark) && text.endsWith(mark)
      && (size === 2 || !text.startsWith(char.repeat(2)))) {
    const inner = text.slice(size, -size)
    edit(ed, [{ range: sel, text: inner }],
      new Selection(sel.startLineNumber, sel.startColumn, sel.startLineNumber, sel.startColumn + inner.length))
    return
  }
  const inner = text || placeholder
  const endLine = singleLine ? sel.startLineNumber : sel.endLineNumber
  const endColumn = text && !singleLine ? sel.endColumn : sel.startColumn + size + inner.length
  edit(ed, [{ range: sel, text: mark + inner + mark }], new Selection(sel.startLineNumber, sel.startColumn + size, endLine, endColumn))
}

function selectedLines(sel: Selection) {
  const last = sel.endColumn === 1 && sel.endLineNumber > sel.startLineNumber ? sel.endLineNumber - 1 : sel.endLineNumber
  const lines: number[] = []
  for (let line = sel.startLineNumber; line <= last; line++) lines.push(line)
  return lines
}

function kindOf(marker: string | undefined): LineStyle | null {
  if (!marker) return null
  const trimmed = marker.trim()
  if (trimmed === '##') return 'h2'
  if (trimmed === '###') return 'h3'
  if (trimmed.startsWith('>')) return 'quote'
  if (/^[-*+]\s+\[/.test(trimmed)) return 'task'
  if (/^[-*+]$/.test(trimmed)) return 'bullet'
  if (/^\d/.test(trimmed)) return 'ordered'
  return null
}

/** Headings, quotes and lists: applied to every selected line; applying the same style again removes it. */
export function toggleLines(ed: Editor, style: LineStyle) {
  const model = ed.getModel(), sel = ed.getSelection()
  if (!model || !sel) return
  const lines = selectedLines(sel)
  const filled = lines.filter(line => model.getLineContent(line).trim() !== '')
  const targets = filled.length ? filled : lines
  const allOn = targets.every(line => kindOf(PREFIX.exec(model.getLineContent(line))?.[2]) === style)
  let number = 0
  const edits = targets.map(line => {
    const match = PREFIX.exec(model.getLineContent(line))!
    // Headings never keep an indent; lists and quotes do.
    const indent = style === 'h2' || style === 'h3' ? '' : match[1]
    let prefix = ''
    if (!allOn) {
      number++
      prefix = { h2: '## ', h3: '### ', quote: '> ', bullet: '- ', ordered: `${number}. `, task: '- [ ] ' }[style]
    }
    return { range: new Range(line, 1, line, match[0].length + 1), text: (allOn ? match[1] : indent) + prefix, old: match[0].length }
  })
  if (targets.length === 1 && sel.isEmpty()) {
    const item = edits[0]
    const column = Math.max(item.text.length + 1, sel.startColumn + item.text.length - item.old)
    edit(ed, edits, new Selection(sel.startLineNumber, column, sel.startLineNumber, column))
    return
  }
  edit(ed, edits)
  const first = lines[0], last = lines[lines.length - 1]
  ed.setSelection(new Selection(first, 1, last, model.getLineMaxColumn(last)))
}

/** Wraps the selection as a link; a selected address becomes the target and the text is left to fill in. */
export function insertLink(ed: Editor) {
  const model = ed.getModel(), sel = ed.getSelection()
  if (!model || !sel) return
  const text = sel.startLineNumber === sel.endLineNumber ? model.getValueInRange(sel) : ''
  const line = sel.startLineNumber, column = sel.startColumn
  const range = text ? sel : new Range(line, column, line, column)
  if (URL_ONLY.test(text.trim())) {
    edit(ed, [{ range, text: `[連結文字](${text.trim()})` }], new Selection(line, column + 1, line, column + 5))
  } else if (text) {
    const start = column + text.length + 3
    edit(ed, [{ range, text: `[${text}](https://)` }], new Selection(line, start, line, start + 8))
  } else {
    edit(ed, [{ range, text: '[連結文字](https://)' }], new Selection(line, column + 1, line, column + 5))
  }
}

/** Pasting an address over selected text turns the text into a link. Returns true when it handled the paste. */
export function pasteAsLink(ed: Editor, pasted: string) {
  const model = ed.getModel(), sel = ed.getSelection()
  const url = pasted.trim()
  if (!model || !sel || sel.isEmpty() || sel.startLineNumber !== sel.endLineNumber || !URL_ONLY.test(url)) return false
  const text = model.getValueInRange(sel)
  if (URL_ONLY.test(text.trim()) || text.includes('](')) return false
  const end = sel.startColumn + text.length + url.length + 4
  edit(ed, [{ range: sel, text: `[${text}](${url})` }], new Selection(sel.startLineNumber, end, sel.startLineNumber, end))
  return true
}

/** Inserts a block on its own lines, with a blank line before and after so it never merges with a paragraph. */
function insertBlock(ed: Editor, lines: string[], select: { line: number; from: number; to: number }) {
  const model = ed.getModel(), sel = ed.getSelection()
  if (!model || !sel) return
  const line = sel.endLineNumber
  const content = model.getLineContent(line)
  const empty = content.trim() === ''
  const range = empty ? new Range(line, 1, line, content.length + 1) : new Range(line, content.length + 1, line, content.length + 1)
  const before = empty ? (line > 1 && model.getLineContent(line - 1).trim() !== '' ? '\n' : '') : '\n\n'
  const after = line < model.getLineCount() && model.getLineContent(line + 1).trim() !== '' ? '\n' : ''
  const start = line + (before.match(/\n/g)?.length ?? 0)
  edit(ed, [{ range, text: before + lines.join('\n') + after }],
    new Selection(start + select.line, select.from, start + select.line, select.to))
}

export function insertBlockStyle(ed: Editor, style: BlockStyle) {
  const model = ed.getModel(), sel = ed.getSelection()
  if (!model || !sel) return
  if (style === 'codeBlock' && !sel.isEmpty()) {
    const lines = selectedLines(sel)
    const first = lines[0], last = lines[lines.length - 1]
    edit(ed, [
      { range: new Range(last, model.getLineMaxColumn(last), last, model.getLineMaxColumn(last)), text: '\n```' },
      { range: new Range(first, 1, first, 1), text: '```\n' },
    ], new Selection(first, 4, first, 4))
    return
  }
  if (style === 'codeBlock') insertBlock(ed, ['```', '程式碼', '```'], { line: 1, from: 1, to: 4 })
  else if (style === 'table') insertBlock(ed, ['| 欄位 1 | 欄位 2 | 欄位 3 |', '| --- | --- | --- |', '| 內容 | 內容 | 內容 |'], { line: 0, from: 3, to: 7 })
  else insertBlock(ed, ['---', ''], { line: 1, from: 1, to: 1 })
}

function inCodeFence(model: Model, line: number) {
  let open = false
  for (let index = 1; index < line; index++) if (/^\s*(```|~~~)/.test(model.getLineContent(index))) open = !open
  return open
}

/**
 * Enter inside a list item or quote starts the next one; Enter on an empty item ends the list.
 * Returns true when it handled the key.
 */
export function continueList(ed: Editor) {
  const model = ed.getModel(), sel = ed.getSelection()
  if (!model || !sel || !sel.isEmpty() || (ed.getSelections()?.length ?? 0) > 1) return false
  const line = sel.startLineNumber
  const text = model.getLineContent(line)
  if (inCodeFence(model, line)) return false
  const item = LIST_ITEM.exec(text)
  const quote = item ? null : QUOTE.exec(text)
  const prefix = item?.[0] ?? quote?.[0]
  if (!prefix || sel.startColumn <= prefix.length) return false
  if (text.trim() === prefix.trim()) {
    // An empty item: end the list (or quote) and leave a plain line.
    edit(ed, [{ range: new Range(line, 1, line, text.length + 1), text: '' }], new Selection(line, 1, line, 1))
    return true
  }
  let next = prefix
  if (item) {
    const [, indent, marker, space, task] = item
    const numbered = /^(\d+)([.)])$/.exec(marker)
    next = indent + (numbered ? `${Number(numbered[1]) + 1}${numbered[2]}` : marker) + space + (task ? '[ ] ' : '')
  }
  const column = sel.startColumn
  edit(ed, [{ range: new Range(line, column, line, column), text: '\n' + next }],
    new Selection(line + 1, next.length + 1, line + 1, next.length + 1))
  return true
}

/**
 * Tab nests a list item under the item above it; Shift+Tab moves it out one level.
 * Returns true when it handled the key.
 */
export function indentList(ed: Editor, outdent: boolean) {
  const model = ed.getModel(), sel = ed.getSelection()
  if (!model || !sel || sel.startLineNumber !== sel.endLineNumber || (ed.getSelections()?.length ?? 0) > 1) return false
  const line = sel.startLineNumber
  const item = LIST_ITEM.exec(model.getLineContent(line))
  if (!item || inCodeFence(model, line)) return false
  const current = item[1].length
  let target: number | null = null
  for (let index = line - 1; index >= Math.max(1, line - 200); index--) {
    const above = LIST_ITEM.exec(model.getLineContent(index))
    if (!above) {
      if (model.getLineContent(index).trim() === '' || /^\s/.test(model.getLineContent(index))) continue
      break
    }
    const indent = above[1].length
    if (outdent && indent < current) { target = indent; break }
    if (!outdent && indent <= current) { target = indent === current ? indent + above[2].length + above[3].length : null; break }
  }
  if (outdent && target === null) target = 0
  if (target === null || target === current) return true
  const delta = target - current
  const column = Math.max(1, sel.startColumn + delta)
  edit(ed, [{ range: new Range(line, 1, line, current + 1), text: ' '.repeat(target) }], new Selection(line, column, line, column))
  return true
}

const HAN = /[㐀-䶿一-鿿豈-﫿]/g

/** Han characters count one each; other text counts by word. */
export function countWords(text: string) {
  const han = text.match(HAN)?.length ?? 0
  const words = text.replace(HAN, ' ').match(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)?.length ?? 0
  return han + words
}
