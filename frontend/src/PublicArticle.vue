<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownBody from './MarkdownBody.vue'
import ReaderContents from './ReaderContents.vue'
import { renderMarkdown } from './markdown'
import { jumpToHeading, layouts, useReaderLayout } from './reader-layout'

type Article = { title: string; format: 'html' | 'md'; body: string }
const route = useRoute()
const article = ref<Article>()
const content = ref<HTMLElement>()
const retry = ref(0)
const { layout, restoreLayout, toggleFullPage } = useReaderLayout(computed(() => article.value?.format))
const loading = ref(true)
const error = ref('')
const markdown = computed(() => article.value?.format === 'md' ? renderMarkdown(article.value.body) : null)
const html = computed(() => `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font:1rem/1.7 system-ui,sans-serif;color:#152b49;margin:clamp(.75rem,3vw,1.5rem);overflow-wrap:anywhere}
svg{display:block;max-width:100%;height:auto} svg[viewBox]{width:100%} pre{overflow-x:auto;background:#eef2f7;padding:1rem} table{display:block;overflow-x:auto;max-width:100%;border-collapse:collapse} th,td{padding:.5rem;border:1px solid #cbd5e1}</style>
</head><body class="public-html-body">${article.value?.body ?? ''}</body></html>`)

watch([() => route.params.id, retry], async ([id], _, onCleanup) => {
  const request = new AbortController()
  onCleanup(() => request.abort())
  loading.value = true
  error.value = ''
  article.value = undefined
  try {
    const response = await fetch(`/api/public/articles/${encodeURIComponent(String(id))}/`, {
      cache: 'no-store', signal: request.signal,
    })
    if (response.status === 404) {
      error.value = '找不到這篇公開文章。'
    } else {
      if (!response.ok) throw new Error()
      const published: Article = await response.json()
      if (request.signal.aborted) return
      article.value = published
      restoreLayout(published.format)
    }
  } catch {
    if (!request.signal.aborted) error.value = '暫時無法載入文章。'
  } finally {
    if (!request.signal.aborted) {
      loading.value = false
      await nextTick()
      const anchor = window.location.hash.slice(1)
      if (!request.signal.aborted && /^section-\d+$/.test(anchor)) jumpToHeading(content.value, anchor, false)
    }
  }
}, { immediate: true })
</script>

<template>
  <div class="reader">
    <a class="skip-link" href="#main-content">跳至內容</a>
    <header class="site-header">
      <RouterLink to="/" class="site-brand">Knowledge Hub</RouterLink>
      <RouterLink to="/library/">知識總覽</RouterLink>
    </header>
    <main id="main-content" tabindex="-1" class="reader-main" :class="{ 'reader-main-full': layout === 'full' }">
      <nav class="breadcrumbs" aria-label="目前位置">
        <RouterLink to="/library/">知識總覽</RouterLink>
      </nav>

      <div v-if="loading" class="reader-feedback"><ProgressSpinner aria-label="正在載入文件" /></div>
      <div v-else-if="error" class="reader-feedback">
        <Message severity="error">{{ error }}</Message>
        <Button label="重新載入" outlined @click="retry++" />
      </div>
      <template v-else-if="article">
        <div class="reading-toolbar">
          <div class="identity">
            <h1>{{ article.title }}</h1>
            <Tag :value="article.format === 'md' ? 'Markdown' : 'HTML'" severity="info" />
          </div>
          <div class="reader-actions">
            <Select v-model="layout" :options="layouts" option-label="label" option-value="value" aria-label="閱讀版面" />
            <Button :label="layout === 'full' ? '還原版面' : '最大化'" severity="secondary" outlined @click="toggleFullPage" />
          </div>
        </div>
        <div class="reading-layout" :class="[`layout-${layout}`, { 'html-layout': !markdown }]">
          <aside v-if="layout === 'standard'" class="reader-sidebar" aria-label="文件導覽">
            <span>文件庫</span>
            <RouterLink to="/library/">全部文件</RouterLink>
          </aside>
          <ReaderContents v-if="layout === 'standard' && markdown?.headings.length" :headings="markdown.headings"
            @jump="id => jumpToHeading(content, id)" />
          <section v-if="markdown" class="reading-paper" aria-label="文章內容">
            <div ref="content"><MarkdownBody :rendered="markdown" /></div>
          </section>
          <section v-else class="html-preview" aria-label="文章內容">
            <iframe :srcdoc="html" sandbox="" referrerpolicy="no-referrer" title="HTML 文章正文" class="html-frame" />
          </section>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped src="./reader.css"></style>
