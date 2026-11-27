// P23c: per-file limits set by admins (Markdown, HTML, images, videos). The browser checks before sending so an
// oversized file never leaves the machine; the server checks again.
export type FileKind = 'markdown' | 'html' | 'image' | 'video'
export type Limits = { markdown_bytes: number; html_bytes: number; image_bytes: number; video_bytes: number; batch: number }

const MB = 1024 * 1024
export const DEFAULT_LIMITS: Limits = { markdown_bytes: 50 * MB, html_bytes: 50 * MB, image_bytes: 10 * MB, video_bytes: 200 * MB, batch: 20 }
const LABELS: Record<FileKind, string> = { markdown: 'Markdown 文件', html: 'HTML 文件', image: '圖片', video: '影片' }

export function sizeLabel(bytes: number) {
  if (bytes >= 1024 * MB) return `${+(bytes / 1024 / MB).toFixed(1)} GB`
  if (bytes >= MB) return `${+(bytes / MB).toFixed(bytes >= 10 * MB ? 0 : 1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

export function limitOf(kind: FileKind, limits: Limits) {
  return limits[`${kind}_bytes`]
}

export const documentKind = (format: string): FileKind => format === 'md' ? 'markdown' : 'html'

/** 「影片超過上限 50 MB（這個檔案 120 MB）。」, or '' when the file fits. */
export function overLimit(kind: FileKind, size: number, limits: Limits) {
  const limit = limitOf(kind, limits)
  return size > limit ? `${LABELS[kind]}超過上限 ${sizeLabel(limit)}（這個檔案 ${sizeLabel(size)}）。` : ''
}
