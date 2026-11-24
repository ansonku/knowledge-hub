import { computed, ref, watch, type Ref } from 'vue'
import { api, ApiError, getCsrfToken, isAuthError, upload } from '../../api'
import type { Format, Label } from '../types'

export type VersionInfo = {
  id: string
  number: number
  filename: string
  note: string
  source: 'upload' | 'markdown_edit' | 'restore' | string
  author: string | null
  created_at: string
  size?: number
  restored_from_number: number | null
}

export type DocumentDetails = {
  id: string
  title: string
  format: Format
  category: string | null
  category_name: string | null
  tags: Label[]
  current_version: VersionInfo
  updated_at: string
  preview_available?: boolean
  /** Viewer-specific and publication fields returned by GET only. */
  is_favorite?: boolean
  is_public?: boolean
  published_version?: number | null
}

export type PublicationStatus = {
  title: string
  versions: { id: string; number: number }[]
  publication: { title: string; version__number: number } | null
}

export function versionSource(version: VersionInfo) {
  if (version.source === 'restore') return `還原自 v${version.restored_from_number ?? '?'}`
  if (version.source === 'markdown_edit') return '線上編輯'
  return '上傳檔案'
}

function redirectToLogin() {
  const next = `${window.location.pathname}${window.location.search}`
  window.location.assign(`/accounts/login/?next=${encodeURIComponent(next)}`)
}

/**
 * Loads one document (optionally a historical version), its Markdown source and
 * the editing draft. Saving creates a new immutable version guarded by base_version.
 */
export function useDocument(documentId: Ref<string>, versionId: Ref<string | undefined>) {
  const file = ref<DocumentDetails>()
  const historical = ref<VersionInfo>()
  const source = ref('')
  const draft = ref('')
  const loading = ref(true)
  const error = ref('')
  const saving = ref(false)
  const saveError = ref('')

  const shownVersion = computed(() => historical.value ?? file.value?.current_version)
  const dirty = computed(() => draft.value !== source.value)
  const downloadUrl = computed(() => {
    if (!file.value) return ''
    const base = `/api/documents/${encodeURIComponent(file.value.id)}/`
    return historical.value
      ? `${base}versions/${historical.value.id}/download/`
      : `${base}download/?version=${file.value.current_version.id}`
  })

  let controller: AbortController | undefined

  async function load() {
    controller?.abort()
    const request = new AbortController()
    controller = request
    loading.value = true
    error.value = ''
    saveError.value = ''
    historical.value = undefined
    source.value = draft.value = ''
    try {
      const id = encodeURIComponent(documentId.value)
      const details = await api<DocumentDetails>(`/api/documents/${id}/`)
      if (request.signal.aborted) return
      if (versionId.value) {
        const selected = await api<VersionInfo>(`/api/documents/${id}/versions/${encodeURIComponent(versionId.value)}/`)
          .catch(cause => { throw cause instanceof ApiError && cause.status === 404 ? new Error('找不到指定的文件版本。') : cause })
        if (request.signal.aborted) return
        if (selected.id !== details.current_version.id) historical.value = selected
      }
      file.value = details
      if (details.format === 'md') {
        const response = await fetch(downloadUrl.value, { cache: 'no-store', signal: request.signal })
        if (response.status === 401 || response.status === 403) return redirectToLogin()
        if (response.status === 409) throw new Error('文件已有新版本，請重新載入。')
        if (!response.ok) throw new Error('無法讀取 Markdown 原始檔。')
        const text = await response.text()
        if (request.signal.aborted) return
        source.value = draft.value = text
      }
    } catch (cause) {
      if (request.signal.aborted) return
      if (isAuthError(cause)) return redirectToLogin()
      file.value = undefined
      error.value = cause instanceof ApiError && cause.status === 404
        ? '找不到這份文件，可能已移入回收桶。'
        : cause instanceof Error ? cause.message : '無法載入文件。'
    } finally {
      if (!request.signal.aborted) loading.value = false
    }
  }

  /** Save the draft as a new version. Returns the new version number on success. */
  async function save(note: string): Promise<number | undefined> {
    if (!file.value || !dirty.value || saving.value || historical.value) return
    saving.value = true
    saveError.value = ''
    const text = draft.value
    const form = new FormData()
    form.append('file', new Blob([text], { type: 'text/markdown;charset=utf-8' }), file.value.current_version.filename)
    form.append('base_version', file.value.current_version.id)
    form.append('note', note.trim())
    try {
      const saved = await upload<DocumentDetails>(`/api/documents/${encodeURIComponent(file.value.id)}/markdown/`, form)
      file.value = { ...file.value, ...saved }
      source.value = text
      return saved.current_version.number
    } catch (cause) {
      // 409 is either a version conflict or duplicate content; the server message says which.
      saveError.value = cause instanceof Error && cause.message ? cause.message : '無法儲存新版本，草稿仍保留在編輯區。'
    } finally {
      saving.value = false
    }
  }

  function discard() {
    draft.value = source.value
    saveError.value = ''
  }

  /** Issue a short-lived sandboxed preview URL for an HTML document. */
  async function issuePreview(): Promise<string> {
    if (!file.value?.preview_available) throw new Error('這個環境不提供 HTML 預覽。')
    const base = `/api/documents/${encodeURIComponent(file.value.id)}/`
    const path = historical.value ? `versions/${historical.value.id}/preview/` : 'preview/'
    let url: unknown
    try {
      ;({ url } = await api<{ url: unknown }>(base + path, 'POST', { version: shownVersion.value?.id }))
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) throw new Error('文件已有新版本，請重新載入頁面。')
      throw new Error('目前無法開啟 HTML 預覽。')
    }
    if (typeof url !== 'string' || !/^\/preview\/[A-Za-z0-9_-]{43}\/$/.test(url)) throw new Error('預覽連結無效。')
    return url
  }

  /** Apply metadata returned by PATCH without reloading the source. */
  function applyMetadata(next: Partial<DocumentDetails>) {
    if (file.value) file.value = { ...file.value, ...next }
  }

  watch([documentId, versionId], load, { immediate: true })

  return {
    file, historical, shownVersion, source, draft, dirty, loading, error, saving, saveError, downloadUrl,
    load, save, discard, issuePreview, applyMetadata, abort: () => controller?.abort(), csrf: getCsrfToken,
  }
}
