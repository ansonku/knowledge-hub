<script setup lang="ts">
import Skeleton from 'primevue/skeleton'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import MarkdownBody from '../MarkdownBody.vue'
import { renderMarkdown } from '../markdown'
import { jumpToHeading } from '../headings'
import { colorClass, markOf, publicApi, publicDate, type PublicArticle } from './public'

const route = useRoute()
const id = computed(() => String(route.params.id))
const article = ref<PublicArticle>()
const loading = ref(true)
const error = ref('')
const content = ref<HTMLElement>()

let controller: AbortController | undefined
async function load() {
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = ''
  try {
    const result = await publicApi<PublicArticle>(`/api/public/articles/${encodeURIComponent(id.value)}/`, request.signal)
    if (request.signal.aborted) return
    article.value = result
    document.title = `${result.title} · Knowledge Hub`
    await nextTick()
    const anchor = window.location.hash.slice(1)
    if (/^section-\d+$/.test(anchor)) requestAnimationFrame(() => jumpToHeading(content.value, anchor, false))
    else window.scrollTo({ top: 0 })
  } catch (cause) {
    if (request.signal.aborted) return
    article.value = undefined
    error.value = (cause as { status?: number }).status === 404 ? '找不到這篇公開文章，可能已經下架。' : '暫時無法載入文章，請稍後再試。'
    document.title = '公開文章 · Knowledge Hub'
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}
watch(id, load, { immediate: true })

// ---- Markdown -------------------------------------------------------------------------
const rendered = computed(() => article.value?.format === 'md' ? renderMarkdown(article.value.body) : undefined)
/** Many Markdown files open with an H1 equal to the title; the page header already shows it. */
const leadingTitle = computed(() => {
  const first = rendered.value?.headings[0]
  return Boolean(first && first.level === 1 && first.id === 'section-1' && first.text.trim() === article.value?.title.trim())
})
const headings = computed(() => {
  const list = rendered.value?.headings ?? []
  return leadingTitle.value ? list.slice(1) : list
})
const topLevel = computed(() => Math.min(...headings.value.map(heading => heading.level), 6))
function jump(target: string) {
  jumpToHeading(content.value, target)
}

// ---- HTML: static, script-free reading copy (sandbox="" and a restrictive CSP) --------------------
const htmlDocument = computed(() => `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font:1rem/1.7 system-ui,sans-serif;color:#1f2a3d;background:#fff;margin:clamp(.75rem,3vw,1.5rem);overflow-wrap:anywhere}
svg{display:block;max-width:100%;height:auto} svg[viewBox]{width:100%} pre{overflow-x:auto;background:#f2f4f7;padding:1rem;border-radius:8px} table{display:block;overflow-x:auto;max-width:100%;border-collapse:collapse} th,td{padding:.5rem;border:1px solid #d0d5dd}</style>
</head><body class="public-html-body">${article.value?.body ?? ''}</body></html>`)

// ---- Neighbours within the collection (siblings are newest first) -------------------------
const position = computed(() => article.value?.siblings.findIndex(item => item.document_id === id.value) ?? -1)
const newer = computed(() => position.value > 0 ? article.value?.siblings[position.value - 1] : undefined)
const older = computed(() => position.value >= 0 ? article.value?.siblings[position.value + 1] : undefined)

// ---- Copy link -------------------------------------------------------------------------
const copied = ref(false)
async function copyLink() {
  const url = `${window.location.origin}/articles/${id.value}/`
  try {
    await navigator.clipboard.writeText(url)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    window.prompt('複製這個連結：', url)
  }
}
</script>

<template>
  <div class="article-page" :class="{ 'has-nav': article?.collection, 'has-toc': headings.length, 'is-html': article?.format === 'html' }">
    <aside v-if="article?.collection" class="collection-nav" aria-label="同集合文章">
      <RouterLink :to="{ name: 'site-home', query: { collection: article.collection.id }, hash: '#latest' }" class="nav-head">
        <span class="ui-col-mark nav-mark" :class="colorClass(article.collection)" aria-hidden="true">{{ markOf(article.collection.name) }}</span>
        <span>{{ article.collection.name }}</span>
      </RouterLink>
      <ol class="nav-list">
        <li v-for="item in article.siblings" :key="item.document_id">
          <RouterLink :to="{ name: 'public-article', params: { id: item.document_id } }" class="nav-item"
            :class="{ on: item.document_id === id }" :aria-current="item.document_id === id ? 'page' : undefined">{{ item.title }}</RouterLink>
        </li>
      </ol>
    </aside>

    <article class="main-column" :aria-busy="loading">
      <nav class="crumbs" aria-label="目前位置">
        <RouterLink :to="{ name: 'site-home' }">公開文章</RouterLink>
        <template v-if="article?.collection">
          <span aria-hidden="true">/</span>
          <RouterLink :to="{ name: 'site-home', query: { collection: article.collection.id }, hash: '#latest' }">{{ article.collection.name }}</RouterLink>
        </template>
      </nav>

      <div v-if="loading && !article" class="loading">
        <Skeleton width="70%" height="2.5rem" /><Skeleton width="40%" /><Skeleton height="12rem" />
      </div>
      <div v-else-if="error" class="state" role="alert">
        <UiIcon name="alert" :size="28" />
        <p class="state-title">{{ error }}</p>
        <div class="state-actions">
          <button type="button" class="text-button" @click="load">重試</button>
          <RouterLink :to="{ name: 'site-home' }" class="text-button">回到公開文章</RouterLink>
        </div>
      </div>

      <template v-else-if="article">
        <header class="article-head">
          <h1>{{ article.title }}</h1>
          <div class="meta">
            <span v-if="article.collection" class="collection-tag" :class="colorClass(article.collection)">{{ article.collection.name }}</span>
            <time :datetime="article.published_at">{{ publicDate(article.published_at) }}</time>
            <span aria-hidden="true">·</span>
            <span>約 {{ article.reading_minutes }} 分鐘閱讀</span>
          </div>
        </header>

        <div v-if="rendered" ref="content" class="reading" :class="{ 'skip-title': leadingTitle }">
          <MarkdownBody :rendered="rendered" />
        </div>
        <iframe v-else :srcdoc="htmlDocument" sandbox="" referrerpolicy="no-referrer" title="HTML 文章正文" class="html-frame" />

        <footer class="article-foot">
          <div class="foot-row">
            <span class="updated">更新於 <time :datetime="article.published_at">{{ publicDate(article.published_at) }}</time></span>
            <button type="button" class="copy" @click="copyLink">
              <UiIcon :name="copied ? 'check' : 'files'" :size="16" />{{ copied ? '已複製連結' : '複製連結' }}
            </button>
          </div>
          <nav v-if="newer || older" class="neighbours" aria-label="同集合的其他文章">
            <RouterLink v-if="newer" :to="{ name: 'public-article', params: { id: newer.document_id } }" class="neighbour">
              <span class="neighbour-label"><UiIcon name="chevronLeft" :size="14" />上一篇</span>
              <span class="neighbour-title">{{ newer.title }}</span>
            </RouterLink>
            <span v-else />
            <RouterLink v-if="older" :to="{ name: 'public-article', params: { id: older.document_id } }" class="neighbour next">
              <span class="neighbour-label">下一篇<UiIcon name="chevronRight" :size="14" /></span>
              <span class="neighbour-title">{{ older.title }}</span>
            </RouterLink>
          </nav>
        </footer>
      </template>
    </article>

    <nav v-if="headings.length" class="toc" aria-label="本頁目錄">
      <span class="toc-title">本頁目錄</span>
      <a v-for="heading in headings" :key="heading.id" :href="`#${heading.id}`" class="toc-link"
        :style="{ paddingLeft: `${(heading.level - topLevel) * .75 + .75}rem` }" @click.prevent="jump(heading.id)">{{ heading.text }}</a>
    </nav>
  </div>
</template>

<style scoped>
.article-page {
  box-sizing: border-box; max-width: 90rem; margin: 0 auto; padding: var(--ui-space-6) var(--ui-gutter) 5rem;
  display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--ui-space-6); justify-content: center;
}
.article-page.has-nav { grid-template-columns: 14rem minmax(0, 48rem); }
.article-page.has-toc { grid-template-columns: minmax(0, 48rem) 14rem; }
.article-page.has-nav.has-toc { grid-template-columns: 14rem minmax(0, 48rem) 14rem; }
.article-page:not(.has-nav):not(.has-toc) { grid-template-columns: minmax(0, 52rem); }
/* HTML articles carry their own layout (diagrams, wide tables): give them the full width beside the collection list. */
.article-page.is-html.has-nav { grid-template-columns: 14rem minmax(0, 1fr); }
.article-page.is-html:not(.has-nav) { grid-template-columns: minmax(0, 72rem); }

.collection-nav, .toc { position: sticky; top: 5rem; align-self: start; max-height: calc(100vh - 6rem); overflow-y: auto; font-size: var(--ui-text-sm); }
.nav-head { display: flex; align-items: center; gap: var(--ui-space-2); margin-bottom: var(--ui-space-3); color: var(--ui-text); font-weight: 700; text-decoration: none; }
.nav-head:hover { color: var(--ui-accent); }
.nav-mark { width: 1.5rem; height: 1.5rem; font-size: .75rem; }
.nav-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.nav-item { display: block; padding: .375rem .625rem; border-radius: var(--ui-radius-md); color: var(--ui-text-secondary); text-decoration: none; line-height: 1.45; overflow-wrap: anywhere; }
.nav-item:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.nav-item.on { background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-weight: 600; }

.main-column { min-width: 0; }
.crumbs { display: flex; flex-wrap: wrap; gap: .375rem; margin-bottom: var(--ui-space-4); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.crumbs a { color: inherit; text-decoration: none; }
.crumbs a:hover { color: var(--ui-accent); text-decoration: underline; }
.loading { display: grid; gap: var(--ui-space-4); }
.article-head { display: grid; gap: var(--ui-space-3); margin-bottom: var(--ui-space-6); padding-bottom: var(--ui-space-5); border-bottom: 1px solid var(--ui-border-subtle); }
h1 { margin: 0; font-size: clamp(1.75rem, 1.3rem + 1.6vw, 2.375rem); line-height: 1.25; font-weight: 700; letter-spacing: -.015em; overflow-wrap: anywhere; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: .625rem; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.collection-tag { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); font-weight: 600; }

.reading { color: var(--ui-text-reading-color); font-size: var(--ui-text-reading); line-height: var(--ui-leading-reading); overflow-wrap: anywhere; }
.reading :deep(.markdown-body > div > *:first-child) { margin-top: 0; }
.reading.skip-title :deep(.markdown-body > div > h1:first-child) { display: none; }
.reading.skip-title :deep(.markdown-body > div > h1:first-child + *) { margin-top: 0; }
.reading :deep(h1), .reading :deep(h2), .reading :deep(h3), .reading :deep(h4) { color: var(--ui-text); line-height: 1.35; scroll-margin-top: 5.5rem; }
.reading :deep(h1) { font-size: 1.625rem; margin: 2.25rem 0 .75rem; }
.reading :deep(h2) { font-size: 1.375rem; margin: 2.25rem 0 .75rem; }
.reading :deep(h3) { font-size: 1.1875rem; margin: 1.75rem 0 .5rem; }
.reading :deep(h4) { font-size: 1.0625rem; margin: 1.5rem 0 .5rem; }
.reading :deep(p), .reading :deep(ul), .reading :deep(ol), .reading :deep(blockquote) { margin: 0 0 1.125rem; }
.reading :deep(a) { color: var(--ui-accent); text-underline-offset: .18em; }
.reading :deep(:not(pre) > code) { padding: .125rem .375rem; border-radius: var(--ui-radius-sm); background: var(--ui-code-inline-bg); font-size: .875em; }
.reading :deep(pre) { overflow-x: auto; margin: 0 0 1.25rem; padding: var(--ui-space-4) 1.125rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-subtle); font-size: .8125rem; line-height: 1.7; }
.reading :deep(blockquote) { padding: .25rem 1rem; border-left: 3px solid var(--ui-border-strong); color: var(--ui-text-secondary); }
.reading :deep(table) { display: block; max-width: 100%; overflow-x: auto; margin: 0 0 1.25rem; border-collapse: collapse; font-size: .9375rem; }
.reading :deep(th), .reading :deep(td) { padding: .5rem .875rem; border: 1px solid var(--ui-border); text-align: left; }
.reading :deep(th) { background: var(--ui-bg-subtle); font-weight: 600; }
.reading :deep(img) { max-width: 100%; height: auto; border-radius: var(--ui-radius-md); }
.reading :deep(hr) { border: 0; border-top: 1px solid var(--ui-border); margin: 2rem 0; }
.html-frame { display: block; box-sizing: border-box; width: 100%; height: 78vh; min-height: 32rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: #fff; }

.article-foot { display: grid; gap: var(--ui-space-5); margin-top: var(--ui-space-7); padding-top: var(--ui-space-5); border-top: 1px solid var(--ui-border-subtle); }
.foot-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ui-space-3); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.copy { display: inline-flex; align-items: center; gap: var(--ui-space-2); min-height: 2.5rem; padding: 0 var(--ui-space-4); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; font-weight: 600; cursor: pointer; }
.copy:hover { border-color: var(--ui-text-muted); color: var(--ui-text); }
.neighbours { display: grid; grid-template-columns: 1fr 1fr; gap: var(--ui-space-3); }
.neighbour { display: grid; gap: var(--ui-space-1); padding: var(--ui-space-4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); color: var(--ui-text); text-decoration: none; }
.neighbour:hover { border-color: var(--ui-accent); }
.neighbour.next { text-align: right; justify-items: end; }
.neighbour-label { display: inline-flex; align-items: center; gap: var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.neighbour-title { font-weight: 600; overflow-wrap: anywhere; }

.toc { display: flex; flex-direction: column; gap: 2px; }
.toc-title { margin-bottom: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }
.toc-link { padding-top: .25rem; padding-bottom: .25rem; border-left: 2px solid var(--ui-border); color: var(--ui-text-secondary); text-decoration: none; line-height: 1.45; }
.toc-link:hover { border-left-color: var(--ui-accent); color: var(--ui-accent); }

.state { display: grid; justify-items: center; gap: var(--ui-space-3); padding: var(--ui-space-7) 0; color: var(--ui-text-muted); text-align: center; }
.state-title { margin: 0; color: var(--ui-text); font-size: var(--ui-text-lg); font-weight: 600; }
.state-actions { display: flex; gap: var(--ui-space-4); }
.text-button { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; text-decoration: none; cursor: pointer; }

/* Below 1200px the table of contents goes; below 900px the collection list moves under the article. */
@media (max-width: 1200px) {
  .toc { display: none; }
  .article-page.has-toc { grid-template-columns: minmax(0, 52rem); }
  .article-page.has-nav, .article-page.has-nav.has-toc { grid-template-columns: 14rem minmax(0, 48rem); }
}
@media (max-width: 900px) {
  .article-page.has-nav, .article-page.has-nav.has-toc, .article-page.has-toc, .article-page.is-html.has-nav { grid-template-columns: minmax(0, 1fr); }
  .collection-nav { position: static; max-height: none; order: 2; padding-top: var(--ui-space-5); border-top: 1px solid var(--ui-border-subtle); }
}
@media (max-width: 560px) {
  .neighbours { grid-template-columns: 1fr; }
  .neighbour.next { text-align: left; justify-items: start; }
}
</style>
