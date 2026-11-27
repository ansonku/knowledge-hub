<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import HighlightText from '../../HighlightText.vue'
import { matchedFields, searchTerms } from '../../searchTerms'
import { groupsFor } from '../admin/adminNav'
import { currentPublicArticle, openPublic } from '../publicLink'
import { api } from '../../api'
import { useSession } from '../../stores/session'
import { useTaxonomy } from '../../stores/taxonomy'
import { useTheme } from '../../stores/theme'
import type { DocumentPage, DocumentRow } from '../types'
import UiIcon, { type IconName } from './UiIcon.vue'

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ upload: []; create: [] }>()

const router = useRouter()
const session = useSession()
const taxonomy = useTaxonomy()
const theme = useTheme()

type Command = { id: string; group: string; label: string; hint?: string; snippet?: string; keywords?: string; icon: IconName; run: () => void }

const query = ref('')
const active = ref(0)
const input = ref<HTMLInputElement>()
const documents = ref<DocumentRow[]>([])
const recent = ref<DocumentRow[]>([])
const searching = ref(false)
let returnFocus: HTMLElement | null = null
let request = 0

function go(to: Parameters<typeof router.push>[0]) {
  open.value = false
  void router.push(to)
}

const navigation = computed<Command[]>(() => [
  { id: 'nav-home', group: '前往', label: '首頁', icon: 'home', run: () => go({ name: 'app-home' }) },
  { id: 'nav-library', group: '前往', label: '全部文件', icon: 'files', run: () => go({ name: 'app-library' }) },
  { id: 'nav-recent', group: '前往', label: '最近閱讀', icon: 'clock', run: () => go({ name: 'app-recent' }) },
  { id: 'nav-favorites', group: '前往', label: '收藏', icon: 'star', run: () => go({ name: 'app-favorites' }) },
  { id: 'nav-published', group: '前往', label: '已公開文章', icon: 'globe', run: () => go({ name: 'app-published' }) },
  ...(session.canEdit ? [{ id: 'nav-trash', group: '前往', label: '回收桶', icon: 'trash' as const, run: () => go({ name: 'app-trash' }) }] : []),
  { id: 'nav-portal', group: '前往', label: '閱讀入口', icon: 'book', run: () => { open.value = false; window.location.assign('/read/') } },
  { id: 'nav-public', group: '前往', label: '公開站', hint: '新分頁', keywords: 'articles 訪客', icon: 'external', run: () => { open.value = false; openPublic() } },
  ...(currentPublicArticle.value ? [{
    id: 'nav-public-article', group: '前往', label: '在公開站查看這篇文章', hint: currentPublicArticle.value.title, keywords: '公開站 articles 訪客',
    icon: 'external' as const, run: () => { open.value = false; openPublic(`/articles/${currentPublicArticle.value!.id}/`) },
  }] : []),
])
const actions = computed<Command[]>(() => [
  ...(session.canEdit ? [
    { id: 'act-upload', group: '動作', label: '上傳文件', icon: 'upload' as const, run: () => { open.value = false; emit('upload') } },
    { id: 'act-create', group: '動作', label: '新增 Markdown 文件', icon: 'edit' as const, run: () => { open.value = false; emit('create') } },
  ] : []),
  {
    id: 'act-theme', group: '動作', label: theme.isDark ? '切換為淺色模式' : '切換為深色模式',
    icon: theme.isDark ? 'sun' : 'moon', run: () => { theme.cycle(); open.value = false },
  },
])

function documentCommand(row: DocumentRow, group: string, words: string[] = []): Command {
  return {
    id: `doc-${group}-${row.id}`, group, label: row.title, hint: taxonomy.pathLabel(row.category), icon: 'files',
    // P16b: a search result shows where it matched and opens with the words marked.
    snippet: row.matches?.snippets[0] ?? (matchedFields(row.matches) || undefined),
    run: () => go({ name: 'app-document', params: { id: row.id }, query: words.length ? { hl: words.join(' ') } : {} }),
  }
}
const words = computed(() => searchTerms(query.value))

// P19 (E2＋): every management page this member may open, and the settings inside them (with an anchor).
const SETTINGS: { label: string; page: string; hash: string; keywords: string }[] = [
  { label: '站名與介紹', page: 'app-site-settings', hash: '#site', keywords: '站台設定 站名 介紹 名稱 site name' },
  { label: '公告橫幅', page: 'app-site-settings', hash: '#notice', keywords: '公告 橫幅 notice banner' },
  { label: '相簿與燈箱', page: 'app-site-settings', hash: '#gallery', keywords: '相簿 燈箱 gallery lightbox 動畫' },
  { label: '立即執行維護', page: 'app-maintenance', hash: '#jobs', keywords: '維護 清理 索引 一致性 maintenance 備份 backup' },
  { label: '儲存空間', page: 'app-system', hash: '#storage', keywords: '儲存 空間 磁碟 storage disk' },
  { label: '儲存空間上限', page: 'app-system', hash: '#storage', keywords: '上限 配額 容量 quota limit storage' },
]
const admin = computed<Command[]>(() => {
  const groups = groupsFor(session.canEdit, session.isAdmin)
  const pages = groups.flatMap(group => group.pages.map(page => ({ ...page, group: group.name })))
  return [
    ...pages.map<Command>(page => ({
      id: `admin-${page.name}`, group: '管理', label: page.label, hint: page.group, icon: page.icon, keywords: '管理',
      run: () => go({ name: page.name }),
    })),
    ...SETTINGS.filter(item => pages.some(page => page.name === item.page)).map<Command>(item => ({
      id: `setting-${item.hash}`, group: '設定', label: item.label, hint: pages.find(page => page.name === item.page)?.label,
      icon: 'sliders', keywords: item.keywords, run: () => go({ name: item.page, hash: item.hash }),
    })),
  ]
})

const results = computed<Command[]>(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) {
    return [...recent.value.map(row => documentCommand(row, '最近閱讀')), ...navigation.value, ...actions.value]
  }
  const matches = (text: string) => text.toLowerCase().includes(term)
  const collections = taxonomy.tree.filter(node => matches(node.name)).slice(0, 5).map<Command>(node => ({
    id: `col-${node.id}`, group: '集合', label: node.name, hint: taxonomy.pathLabel(node.parent) === '未分類' ? undefined : taxonomy.pathLabel(node.parent),
    icon: 'folder', run: () => go({ name: 'app-collection', params: { id: node.id } }),
  }))
  // Commands whose name matches come first: typing「上傳」or「新增」should run that command on Enter,
  // not open a document that merely mentions the words.
  return [
    ...[...actions.value, ...navigation.value, ...admin.value].filter(command => matches(`${command.label} ${command.keywords ?? ''}`)),
    ...documents.value.map(row => documentCommand(row, '文件', words.value)),
    ...collections,
  ]
})

const groups = computed(() => {
  const ordered: { name: string; items: (Command & { index: number })[] }[] = []
  results.value.forEach((command, index) => {
    let group = ordered.find(item => item.name === command.group)
    if (!group) ordered.push(group = { name: command.group, items: [] })
    group.items.push({ ...command, index })
  })
  return ordered
})

watch(query, (value, _, onCleanup) => {
  active.value = 0
  const term = value.trim()
  if (!term) { documents.value = []; searching.value = false; return }
  searching.value = true
  const timer = setTimeout(async () => {
    const current = ++request
    try {
      const page = await api<DocumentPage>(`/api/documents/?${new URLSearchParams({ q: term })}`)
      if (current === request) documents.value = page.results.slice(0, 8)
    } catch {
      if (current === request) documents.value = []
    } finally {
      if (current === request) searching.value = false
    }
  }, 180)
  onCleanup(() => clearTimeout(timer))
})

watch(open, async visible => {
  if (visible) {
    returnFocus = document.activeElement as HTMLElement | null
    query.value = ''
    active.value = 0
    await nextTick()
    input.value?.focus()
    try {
      recent.value = (await api<{ results: DocumentRow[] }>('/api/me/recent/?limit=5')).results
    } catch {
      recent.value = []
    }
  } else {
    returnFocus?.focus?.()
  }
})

function onKeydown(event: KeyboardEvent) {
  const total = results.value.length
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    active.value = total ? (active.value + 1) % total : 0
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    active.value = total ? (active.value - 1 + total) % total : 0
  } else if (event.key === 'Enter') {
    event.preventDefault()
    results.value[active.value]?.run()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    open.value = false
  } else if (event.key === 'Tab') {
    event.preventDefault()
  }
}

watch(active, async index => {
  await nextTick()
  document.getElementById(`cmd-${index}`)?.scrollIntoView({ block: 'nearest' })
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="hub-app palette-layer" @mousedown.self="open = false">
      <div class="palette" role="dialog" aria-modal="true" aria-label="搜尋或執行指令">
        <div class="field">
          <UiIcon name="search" :size="18" />
          <input ref="input" v-model="query" type="text" role="combobox" aria-autocomplete="list" aria-expanded="true"
            aria-controls="palette-list" :aria-activedescendant="results.length ? `cmd-${active}` : undefined"
            placeholder="搜尋文件、集合或指令…" autocomplete="off" spellcheck="false" @keydown="onKeydown">
          <kbd>Esc</kbd>
        </div>
        <ul id="palette-list" class="list" role="listbox" aria-label="結果">
          <template v-for="group in groups" :key="group.name">
            <li class="group" role="presentation">{{ group.name }}</li>
            <li v-for="item in group.items" :id="`cmd-${item.index}`" :key="item.id" role="option" class="option"
              :class="{ active: item.index === active }" :aria-selected="item.index === active"
              @mousemove="active = item.index" @click="item.run()">
              <UiIcon :name="item.icon" :size="16" />
              <span v-if="item.snippet" class="label stacked">
                <span class="label-title"><HighlightText :text="item.label" :terms="words" /></span>
                <span class="snippet"><HighlightText :text="item.snippet" :terms="words" /></span>
              </span>
              <span v-else class="label">{{ item.label }}</span>
              <span v-if="item.hint" class="hint">{{ item.hint }}</span>
              <UiIcon v-if="item.index === active" name="enter" :size="14" class="enter" />
            </li>
          </template>
          <li v-if="!results.length" class="empty" role="presentation">
            {{ searching ? '搜尋中…' : '找不到符合的文件或指令' }}
          </li>
        </ul>
        <div class="footer" aria-hidden="true">
          <span><kbd>↑</kbd><kbd>↓</kbd> 選擇</span><span><kbd>Enter</kbd> 開啟</span><span><kbd>Esc</kbd> 關閉</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.palette-layer {
  position: fixed; inset: 0; z-index: 1100; display: flex; justify-content: center; align-items: flex-start;
  padding: 12vh var(--ui-space-4) var(--ui-space-4); background: rgb(16 24 40 / .45); min-height: 0;
}
.palette {
  width: min(40rem, 100%); max-height: 70vh; display: flex; flex-direction: column; overflow: hidden;
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface);
  box-shadow: 0 24px 64px rgb(16 24 40 / .28);
}
.field { display: flex; align-items: center; gap: var(--ui-space-3); padding: 0 var(--ui-space-4); border-bottom: 1px solid var(--ui-border); color: var(--ui-text-muted); }
.field input { flex: 1; min-width: 0; height: 3.25rem; border: 0; outline: none; background: transparent; color: var(--ui-text); font: inherit; font-size: 1rem; }
.field input:focus-visible { box-shadow: none; }
kbd { font-family: var(--ui-font-sans); font-size: .6875rem; padding: 1px 5px; border: 1px solid var(--ui-border); border-radius: 4px; background: var(--ui-bg-subtle); color: var(--ui-text-muted); }
.list { flex: 1; overflow-y: auto; margin: 0; padding: var(--ui-space-2); list-style: none; }
.group { padding: var(--ui-space-3) var(--ui-space-2) var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }
.option { display: flex; align-items: center; gap: var(--ui-space-3); min-height: 2.5rem; padding: 0 var(--ui-space-3); border-radius: var(--ui-radius-md); color: var(--ui-text-secondary); cursor: pointer; }
.option.active { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); }
.label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ui-text); font-weight: 500; }
.option.active .label { color: inherit; }
.label.stacked { display: grid; min-width: 0; }
.label-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.snippet { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 400; }
.hint { color: var(--ui-text-muted); font-size: var(--ui-text-xs); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 40%; }
.enter { color: inherit; }
.empty { padding: var(--ui-space-6) var(--ui-space-3); color: var(--ui-text-muted); text-align: center; }
.footer { display: flex; gap: var(--ui-space-4); padding: var(--ui-space-2) var(--ui-space-4); border-top: 1px solid var(--ui-border); background: var(--ui-bg-subtle); color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.footer kbd { margin-right: 2px; }
@media (max-width: 640px) {
  .palette-layer { padding-top: var(--ui-space-4); }
  .footer { display: none; }
}
</style>
