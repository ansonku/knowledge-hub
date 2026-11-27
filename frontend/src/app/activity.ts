import { LAYOUT_LABELS, type GalleryLayout } from '../gallery'
import type { Format } from './types'

export type ActivityItem = {
  id: number
  action: 'created' | 'uploaded' | 'edited' | 'restored_version' | 'metadata' | 'trashed' | 'restored' | 'published' | 'withdrawn' | 'featured' | 'unfeatured' | 'version_deleted'
  actor: string | null
  version_number: number | null
  detail: {
    note?: string
    restored_from?: number
    republished?: boolean
    automatic?: boolean
    reason?: string
    title?: { from: string; to: string }
    category?: { from: string | null; to: string | null }
    tags?: { added: string[]; removed: string[] }
    presentation?: { from: string; to: string }
    gallery_layout?: { from: string; to: string }
    cover?: { from: boolean; to: boolean }
  }
  created_at: string
  document: { id: string; title: string; format: Format }
}

export type ActivityPage = { page: number; has_more: boolean; results: ActivityItem[] }

/** Verb phrase for an activity, e.g. "上傳了 v3". The document title is rendered separately. */
export function activityVerb(item: ActivityItem) {
  const version = item.version_number ? `v${item.version_number}` : ''
  switch (item.action) {
    case 'created': return '新增了文件'
    case 'uploaded': return `上傳了 ${version}`
    case 'edited': return `編輯並儲存為 ${version}`
    case 'restored_version': return `從 v${item.detail.restored_from ?? '?'} 還原為 ${version}`
    case 'metadata': return '更新了文件資料'
    case 'trashed': return '移入回收桶'
    case 'restored': return '從回收桶還原'
    case 'published': return item.detail.republished ? `重新發布 ${version}` : `發布 ${version} 為公開文章`
    case 'withdrawn': return '下架了公開文章'
    case 'featured': return '加入首頁精選'
    case 'unfeatured': return item.detail.automatic ? '因下架自動移出首頁精選' : '移出首頁精選'
    case 'version_deleted': return `永久刪除了 ${version}`
  }
}

/** Secondary line: the version note or a summary of metadata changes. */
export function activityDetail(item: ActivityItem) {
  const { detail } = item
  if (detail.note) return detail.note
  if (item.action === 'version_deleted') return detail.reason ? `原因：${detail.reason}` : ''
  const parts: string[] = []
  if (detail.title) parts.push(`標題改為「${detail.title.to}」`)
  if (detail.category) parts.push(`集合改為「${detail.category.to ?? '未分類'}」`)
  if (detail.tags?.added.length) parts.push(`加上標籤 ${detail.tags.added.join('、')}`)
  if (detail.tags?.removed.length) parts.push(`移除標籤 ${detail.tags.removed.join('、')}`)
  if (detail.presentation) parts.push(`呈現方式改為「${detail.presentation.to === 'gallery' ? '相簿' : '文章'}」`)
  if (detail.gallery_layout) {
    const to = detail.gallery_layout.to as GalleryLayout | ''
    parts.push(`相簿版面改為「${to ? LAYOUT_LABELS[to] ?? to : '跟隨系統預設'}」`)
  }
  if (detail.cover) parts.push(detail.cover.to ? (detail.cover.from ? '更換封面' : '設定封面') : '移除封面')
  return parts.join('；')
}

export function initialOf(name: string | null) {
  return Array.from(name ?? '系')[0]?.toUpperCase() ?? '?'
}
