import { defineStore } from 'pinia'
import { overLimit } from '../fileLimits'
import { computed, ref } from 'vue'
import { ApiError, upload } from '../api'
import type { DocumentRow } from '../app/types'
import { useSession } from './session'

export type UploadState = 'queued' | 'uploading' | 'complete' | 'duplicate' | 'failed' | 'skipped'
export type UploadItem = {
  id: number
  file: File
  category: string | null
  state: UploadState
  progress: number
  message: string
  force: boolean
  documentId?: string
  title?: string
}

/**
 * Non-modal upload queue for new documents. Every file becomes its own document
 * (never matched to an existing one by filename); new versions still start from a document.
 */
export const useUploads = defineStore('uploads', () => {
  const items = ref<UploadItem[]>([])
  const open = ref(false)
  let nextId = 1
  let running = false

  const active = computed(() => items.value.filter(item => item.state === 'queued' || item.state === 'uploading'))
  const finished = computed(() => items.value.filter(item => item.state === 'complete').length)
  const needsAttention = computed(() => items.value.some(item => item.state === 'duplicate' || item.state === 'failed'))

  function validate(file: File) {
    const session = useSession()
    if (!/\.(md|html)$/i.test(file.name)) return '只支援 .md 或 .html 檔案。'
    if (!file.size) return '空白檔案無法上傳。'
    const tooBig = overLimit(/\.md$/i.test(file.name) ? 'markdown' : 'html', file.size, session.limits)
    if (tooBig) return tooBig
    return ''
  }

  function add(files: FileList | File[], category: string | null) {
    const list = Array.from(files)
    if (!list.length) return
    const limit = useSession().limits.batch
    for (const [index, file] of list.entries()) {
      const message = index >= limit ? `一次最多 ${limit} 個檔案，請分批上傳。` : validate(file)
      items.value.push({
        id: nextId++, file, category, state: message ? 'failed' : 'queued', progress: 0, message, force: false,
      })
    }
    open.value = true
    void process()
  }

  function retry(item: UploadItem, force = false) {
    item.state = 'queued'
    item.force = force
    item.message = ''
    item.progress = 0
    void process()
  }

  function skip(item: UploadItem) {
    item.state = 'skipped'
    item.message = '已略過'
  }

  function clear() {
    items.value = items.value.filter(item => item.state === 'queued' || item.state === 'uploading')
    if (!items.value.length) open.value = false
  }

  async function process() {
    if (running) return
    running = true
    let completed = 0
    try {
      let item: UploadItem | undefined
      while ((item = items.value.find(candidate => candidate.state === 'queued'))) {
        item.state = 'uploading'
        const data = new FormData()
        data.append('file', item.file)
        if (item.category) data.append('category', item.category)
        if (item.force) data.append('force', 'true')
        const current = item
        try {
          const saved = await upload<DocumentRow>('/api/documents/', data, percent => { current.progress = percent })
          current.state = 'complete'
          current.documentId = saved.id
          current.title = saved.title
          current.message = '已新增 · v1'
          completed++
        } catch (cause) {
          current.state = cause instanceof ApiError && cause.status === 409 ? 'duplicate' : 'failed'
          current.message = cause instanceof Error ? cause.message : '上傳失敗。'
        }
      }
    } finally {
      running = false
    }
    if (completed) window.dispatchEvent(new CustomEvent('hub:documents-changed'))
  }

  /** Documents this tray has created, for setting their collection and tags afterwards. */
  const created = computed(() => items.value.filter(item => item.state === 'complete' && item.documentId))

  /** After the batch got a new collection, show it as each file's destination. */
  function moved(category: string | null) {
    for (const item of created.value) item.category = category
  }

  return { items, open, active, finished, needsAttention, created, add, retry, skip, clear, moved }
})
