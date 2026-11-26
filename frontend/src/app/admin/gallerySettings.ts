// Audit wording for P11d's site-wide lightbox and gallery settings.
import { LAYOUT_LABELS, type GalleryLayout } from '../../gallery'

const EFFECTS: Record<string, string> = { center: '背景先出、圖片從中間浮現', zoom: '從縮圖放大', fade: '淡入' }
const SPEEDS: Record<string, string> = { fast: '快', normal: '標準', slow: '慢' }

function show(key: string, value: unknown) {
  if (key === 'effect') return EFFECTS[String(value)] ?? String(value)
  if (key === 'speed') return SPEEDS[String(value)] ?? String(value)
  if (key === 'backdrop') return (Number(value) / 100).toFixed(2)
  if (key === 'layout') return LAYOUT_LABELS[value as GalleryLayout] ?? String(value)
  if (key === 'member_download' || key === 'respect_reduced_motion') return value ? '開' : '關'
  if (key === 'interval') return `${String(value)} 秒`
  return String(value)
}
const NAMES: Record<string, string> = { effect: '燈箱效果', speed: '動畫速度', backdrop: '背景暗度', layout: '預設相簿版面', member_download: '成員下載', respect_reduced_motion: '配合減少動態效果', interval: '自動播放間隔' }

/** e.g. "燈箱效果：淡入 → 從縮圖放大；預設相簿版面：齊邊 → 瀑布流" */
export function gallerySummary(changes: Record<string, { from: unknown; to: unknown }>) {
  return Object.entries(changes)
    .map(([key, change]) => `${NAMES[key] ?? key}：${show(key, change.from)} → ${show(key, change.to)}`)
    .join('；')
}
