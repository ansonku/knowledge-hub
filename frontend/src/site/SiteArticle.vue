<script setup lang="ts">
import Skeleton from 'primevue/skeleton'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import MarkdownBody from '../MarkdownBody.vue'
import { renderMarkdown } from '../markdown'
import { jumpToHeading } from '../headings'
import { collectionStyle, colorClass, publicApi, publicDate, usePublicNav, type PublicArticle } from './public'
import { useSite } from '../stores/site'

const site = useSite()
const route = useRoute()
const id = computed(() => String(route.params.id))
const article = ref<PublicArticle>()
const loading = ref(true)
const error = ref('')
const content = ref<HTMLElement>()
const portal = usePublicNav()

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
    site.setTitle(result.title)
    await nextTick()
    const anchor = window.location.hash.slice(1)
    if (/^section-\d+$/.test(anchor)) requestAnimationFrame(() => jumpToHeading(content.value, anchor, false))
    else window.scrollTo({ top: 0 })
  } catch (cause) {
    if (request.signal.aborted) return
    article.value = undefined
    error.value = (cause as { status?: number }).status === 404 ? '找不到這篇公開文章，可能已經下架。' : '暫時無法載入文章，請稍後再試。'
    site.setTitle()
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

// ---- Previous / next in the navigation's reading order -------------------------------------
const position = computed(() => portal.ordered.value.findIndex(item => item.document_id === id.value))
const newer = computed(() => position.value > 0 ? portal.ordered.value[position.value - 1] : undefined)
const older = computed(() => position.value >= 0 ? portal.ordered.value[position.value + 1] : undefined)

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
  <div class="article-page" :class="{ 'has-toc': headings.length, 'is-html': article?.format === 'html' }">
    <div v-if="loading && !article" class="loading">
      <Skeleton width="30%" /><Skeleton width="60%" height="2.5rem" /><Skeleton height="14rem" />
    </div>
    <div v-else-if="error" class="state" role="alert">
      <UiIcon name="alert" :size="28" />
      <p class="state-title">{{ error }}</p>
      <div class="state-actions">
        <button type="button" class="text-button" @click="load">重試</button>
        <RouterLink :to="{ name: 'site-home' }" class="text-button">回到首頁</RouterLink>
      </div>
    </div>

    <template v-else-if="article">
      <!-- Header band tinted with the article's collection colour -->
      <header class="band" :style="collectionStyle(article.collection)">
        <div class="band-inner">
          <nav class="crumbs" aria-label="目前位置">
            <RouterLink :to="{ name: 'site-home' }">首頁</RouterLink>
            <template v-for="node in article.path" :key="node.id">
              <span aria-hidden="true">/</span>
              <RouterLink :to="{ name: 'site-home', query: { collection: node.id } }">{{ node.name }}</RouterLink>
            </template>
          </nav>
          <h1>{{ article.title }}</h1>
          <div class="meta">
            <template v-for="(node, index) in article.path" :key="node.id">
              <span v-if="index" class="sep" aria-hidden="true">›</span>
              <RouterLink :to="{ name: 'site-home', query: { collection: node.id } }" class="tag" :class="colorClass(node)">{{ node.name }}</RouterLink>
            </template>
            <span>發布於 <time :datetime="article.published_at">{{ publicDate(article.published_at) }}</time></span>
            <span aria-hidden="true">·</span>
            <span>約 {{ article.reading_minutes }} 分鐘閱讀</span>
            <span class="spacer" />
            <button type="button" class="copy" @click="copyLink">
              <UiIcon :name="copied ? 'check' : 'files'" :size="15" />{{ copied ? '已複製連結' : '複製連結' }}
            </button>
          </div>
        </div>
      </header>

      <div class="columns">
        <article class="body" :aria-busy="loading">
          <div v-if="rendered" ref="content" class="reading" :class="{ 'skip-title': leadingTitle }">
            <MarkdownBody :rendered="rendered" />
          </div>
          <iframe v-else :srcdoc="htmlDocument" sandbox="" referrerpolicy="no-referrer" title="HTML 文章正文" class="html-frame" />

          <nav v-if="newer || older" class="neighbours" aria-label="上一篇與下一篇">
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
        </article>

        <aside v-if="headings.length" class="toc" aria-label="本頁目錄">
          <span class="toc-title">本頁目錄</span>
          <a v-for="heading in headings" :key="heading.id" :href="`#${heading.id}`" class="toc-link"
            :style="{ paddingLeft: `${(heading.level - topLevel) * .875 + .75}rem` }" @click.prevent="jump(heading.id)">{{ heading.text }}</a>
          <p class="toc-foot">更新於 {{ publicDate(article.published_at) }}<br>由團隊成員發布</p>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.article-page { display: flex; flex-direction: column; }
.loading { display: grid; gap: var(--ui-space-4); padding: var(--ui-space-6) clamp(1rem, 3.5vw, 3.5rem); }
.band { padding: clamp(1.5rem, 3vw, 2rem) clamp(1rem, 3.5vw, 3.5rem) clamp(1.25rem, 2.5vw, 1.75rem); border-bottom: 1px solid color-mix(in srgb, var(--col-bg) 80%, var(--ui-border)); background: color-mix(in srgb, var(--col-bg) 45%, var(--ui-bg-surface)); }
.band-inner { max-width: 74rem; display: grid; gap: var(--ui-space-3); }
.crumbs { display: flex; flex-wrap: wrap; gap: .375rem; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.crumbs a { color: inherit; text-decoration: none; }
.crumbs a:hover { color: var(--ui-accent); text-decoration: underline; }
h1 { margin: 0; font-size: clamp(1.75rem, 1.3rem + 1.5vw, 2.375rem); line-height: 1.22; font-weight: 700; letter-spacing: -.015em; overflow-wrap: anywhere; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .75rem; color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.tag { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); font-weight: 600; text-decoration: none; }
.tag:hover { text-decoration: underline; }
.sep { margin: 0 -.375rem; color: var(--ui-text-muted); }
.spacer { flex: 1; }
.copy { display: inline-flex; align-items: center; gap: .375rem; min-height: 2.125rem; padding: 0 var(--ui-space-3); border: 1px solid color-mix(in srgb, var(--col-fg) 25%, var(--ui-border)); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; font-weight: 600; cursor: pointer; }
.copy:hover { color: var(--ui-text); }

.columns { display: flex; align-items: flex-start; justify-content: space-between; gap: clamp(2rem, 4vw, 3rem); padding: clamp(1.5rem, 3vw, 2.5rem) clamp(1rem, 3.5vw, 3.5rem) clamp(2.5rem, 5vw, 4rem); }
.body { flex: 1 1 auto; min-width: 0; max-width: 58rem; }
.is-html .body { max-width: none; }
.reading { color: var(--ui-text-reading-color); font-size: var(--ui-text-reading); line-height: var(--ui-leading-reading); overflow-wrap: anywhere; }
.reading :deep(.markdown-body > div > *:first-child) { margin-top: 0; }
.reading.skip-title :deep(.markdown-body > div > h1:first-child) { display: none; }
.reading.skip-title :deep(.markdown-body > div > h1:first-child + *) { margin-top: 0; }
.reading :deep(h1), .reading :deep(h2), .reading :deep(h3), .reading :deep(h4) { color: var(--ui-text); line-height: 1.35; scroll-margin-top: 5.5rem; }
.reading :deep(h1) { font-size: 1.625rem; margin: 2.25rem 0 .75rem; }
.reading :deep(h2) { font-size: 1.5rem; margin: 2.25rem 0 .75rem; }
.reading :deep(h3) { font-size: 1.1875rem; margin: 1.75rem 0 .5rem; }
.reading :deep(h4) { font-size: 1.0625rem; margin: 1.5rem 0 .5rem; }
.reading :deep(p), .reading :deep(ul), .reading :deep(ol), .reading :deep(blockquote) { margin: 0 0 1.125rem; }
.reading :deep(a) { color: var(--ui-accent); text-underline-offset: .18em; }
.reading :deep(:not(pre) > code) { padding: .125rem .375rem; border-radius: var(--ui-radius-sm); background: var(--ui-code-inline-bg); font-size: .875em; }
.reading :deep(pre) { overflow-x: auto; margin: 0 0 1.25rem; padding: var(--ui-space-4) 1.125rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-bg-subtle); font-size: .84375rem; line-height: 1.7; }
.reading :deep(blockquote) { padding: .625rem 1.125rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-bg-subtle); color: var(--ui-text-secondary); }
.reading :deep(table) { display: block; max-width: 100%; overflow-x: auto; margin: 0 0 1.25rem; border-collapse: collapse; font-size: .9375rem; }
.reading :deep(th), .reading :deep(td) { padding: .5rem .875rem; border: 1px solid var(--ui-border); text-align: left; }
.reading :deep(th) { background: var(--ui-bg-subtle); font-weight: 600; }
.reading :deep(img) { max-width: 100%; height: auto; border-radius: var(--ui-radius-md); }
.reading :deep(hr) { border: 0; border-top: 1px solid var(--ui-border); margin: 2rem 0; }
.html-frame { display: block; box-sizing: border-box; width: 100%; height: 78vh; min-height: 32rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: #fff; }

.neighbours { display: grid; grid-template-columns: 1fr 1fr; gap: var(--ui-space-3); margin-top: var(--ui-space-7); padding-top: var(--ui-space-5); border-top: 1px solid var(--ui-border-subtle); }
.neighbour { display: grid; gap: var(--ui-space-1); padding: var(--ui-space-4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); color: var(--ui-text); text-decoration: none; }
.neighbour:hover { border-color: var(--ui-accent); }
.neighbour.next { text-align: right; justify-items: end; }
.neighbour-label { display: inline-flex; align-items: center; gap: var(--ui-space-1); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.neighbour-title { font-weight: 600; overflow-wrap: anywhere; }

.toc { flex: 0 0 15rem; margin-left: auto; position: sticky; top: 5.5rem; max-height: calc(100vh - 7rem); overflow-y: auto; display: flex; flex-direction: column; gap: 2px; font-size: var(--ui-text-sm); }
.toc-title { margin-bottom: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-weight: 600; }
.toc-link { padding-top: .3125rem; padding-bottom: .3125rem; border-left: 2px solid var(--ui-border); color: var(--ui-text-secondary); text-decoration: none; line-height: 1.45; }
.toc-link:hover { border-left-color: var(--ui-accent); color: var(--ui-accent); }
.toc-foot { margin: var(--ui-space-5) 0 0; padding-top: var(--ui-space-4); border-top: 1px solid var(--ui-border-subtle); color: var(--ui-text-muted); font-size: var(--ui-text-xs); line-height: 1.6; }

.state { display: grid; justify-items: center; gap: var(--ui-space-3); padding: var(--ui-space-7) var(--ui-space-4); color: var(--ui-text-muted); text-align: center; }
.state-title { margin: 0; color: var(--ui-text); font-size: var(--ui-text-lg); font-weight: 600; }
.state-actions { display: flex; gap: var(--ui-space-4); }
.text-button { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; text-decoration: none; cursor: pointer; }

/* Below 1360px (nav + body + contents no longer fit comfortably) the table of contents gives
   its room to the body; previous/next stack on phones. */
@media (max-width: 1360px) {
  .toc { display: none; }
}
@media (max-width: 560px) {
  .neighbours { grid-template-columns: 1fr; }
  .neighbour.next { text-align: left; justify-items: start; }
  .spacer { display: none; }
}
</style>
