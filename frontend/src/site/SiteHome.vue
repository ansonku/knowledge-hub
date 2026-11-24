<script setup lang="ts">
import Skeleton from 'primevue/skeleton'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import {
  colorClass, markOf, publicApi, publicDate, type PublicCardPage, type PublicCollectionCount,
} from './public'

const route = useRoute()
const router = useRouter()

const queryText = (key: string) => typeof route.query[key] === 'string' ? route.query[key] as string : ''
const keywords = computed(() => queryText('q').trim())
const collection = computed(() => queryText('collection'))
const page = computed(() => Math.max(1, Number.parseInt(queryText('page') || '1', 10) || 1))

function setQuery(patch: Record<string, string | number | undefined>) {
  const query: LocationQueryRaw = { ...route.query, page: undefined, ...patch }
  for (const key of Object.keys(query)) if (query[key] === '' || query[key] === undefined || query[key] === 1) delete query[key]
  void router.replace({ query, hash: route.hash })
}

// ---- Search box -------------------------------------------------------------------
const searchText = ref(keywords.value)
watch(keywords, value => { searchText.value = value })
function search() {
  setQuery({ q: searchText.value.trim() })
}
function clearSearch() {
  searchText.value = ''
  setQuery({ q: '' })
}

// ---- Collections --------------------------------------------------------------------
const collections = ref<PublicCollectionCount[]>([])
const collectionsLoading = ref(true)
async function loadCollections() {
  collectionsLoading.value = true
  try {
    collections.value = (await publicApi<{ results: PublicCollectionCount[] }>('/api/public/collections/')).results
  } catch {
    collections.value = []
  } finally {
    collectionsLoading.value = false
  }
}
const activeCollection = computed(() => collections.value.find(item => item.id === collection.value))

// ---- Articles -----------------------------------------------------------------------
const data = ref<PublicCardPage>()
const loading = ref(true)
const error = ref('')
let controller: AbortController | undefined
async function loadArticles() {
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ page: String(page.value) })
  if (keywords.value) params.set('q', keywords.value)
  if (collection.value) params.set('collection', collection.value)
  try {
    const result = await publicApi<PublicCardPage>(`/api/public/articles/?${params}`, request.signal)
    if (request.signal.aborted) return
    data.value = result
    if (result.page !== page.value) setQuery({ page: result.page })
  } catch (cause) {
    if (request.signal.aborted) return
    data.value = undefined
    error.value = (cause as { status?: number }).status === 400 ? '找不到這個集合。' : '暫時無法載入文章，請稍後再試。'
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}
watch([keywords, collection, page], loadArticles, { immediate: true })

const listHeading = computed(() => {
  if (keywords.value) return `搜尋「${keywords.value}」`
  return activeCollection.value ? activeCollection.value.name : '最新文章'
})
const resultLine = computed(() => {
  if (loading.value && !data.value) return '正在載入…'
  if (!data.value) return ''
  return `${data.value.count} 篇文章`
})

onMounted(() => {
  void loadCollections()
  void nextTick(() => { document.title = '公開文章 · Knowledge Hub' })
})
</script>

<template>
  <div class="home">
    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-inner">
        <h1 id="hero-title">團隊公開的知識與文章</h1>
        <p class="lead">由團隊成員撰寫並審核後發布的技術規範、操作指南與參考文件。</p>
        <form class="search" role="search" @submit.prevent="search">
          <UiIcon name="search" :size="20" />
          <label for="public-q" class="ui-visually-hidden">搜尋公開文章</label>
          <input id="public-q" v-model="searchText" type="search" maxlength="240" placeholder="搜尋公開文章的標題或內文" enterkeyhint="search">
          <button v-if="searchText" type="button" class="clear" aria-label="清除搜尋" @click="clearSearch">
            <UiIcon name="close" :size="16" />
          </button>
          <button type="submit" class="submit">搜尋</button>
        </form>
      </div>
    </section>

    <div class="content">
      <section v-if="!keywords && (collectionsLoading || collections.length)" class="block" aria-labelledby="browse-title">
        <h2 id="browse-title">依集合瀏覽</h2>
        <div class="collections">
          <template v-if="collectionsLoading">
            <Skeleton v-for="index in 3" :key="index" height="8.5rem" border-radius="14px" />
          </template>
          <RouterLink v-for="item in collections" v-else :key="item.id"
            :to="{ name: 'site-home', query: { collection: item.id }, hash: '#latest' }" class="collection-card">
            <span class="ui-col-mark card-mark" :class="colorClass(item)" aria-hidden="true">{{ markOf(item.name) }}</span>
            <span class="card-name">{{ item.name }}</span>
            <span class="card-count">{{ item.article_count }} 篇文章 <UiIcon name="arrowRight" :size="14" /></span>
          </RouterLink>
        </div>
      </section>

      <section id="latest" class="block" aria-labelledby="latest-title">
        <div class="list-head">
          <div>
            <h2 id="latest-title">{{ listHeading }}</h2>
            <p class="result-line" aria-live="polite">{{ resultLine }}</p>
          </div>
          <div v-if="collections.length > 1 || collection" class="chips" role="group" aria-label="依集合篩選">
            <button type="button" class="chip" :class="{ on: !collection }" :aria-pressed="!collection" @click="setQuery({ collection: '' })">全部</button>
            <button v-for="item in collections" :key="item.id" type="button" class="chip" :class="{ on: collection === item.id }"
              :aria-pressed="collection === item.id" @click="setQuery({ collection: item.id })">{{ item.name }}</button>
          </div>
        </div>

        <p v-if="error" class="state error" role="alert">
          {{ error }}
          <button type="button" class="link" @click="loadArticles">重試</button>
        </p>
        <ol v-else-if="loading && !data" class="articles" aria-busy="true">
          <li v-for="index in 4" :key="index" class="article"><Skeleton width="40%" /><Skeleton width="70%" height="1.5rem" /><Skeleton /></li>
        </ol>
        <ol v-else-if="data?.results.length" class="articles" :class="{ stale: loading }" :aria-busy="loading">
          <li v-for="item in data.results" :key="item.document_id" class="article">
            <article>
              <div class="meta">
                <span v-if="item.collection" class="collection-tag" :class="colorClass(item.collection)">{{ item.collection.name }}</span>
                <time :datetime="item.published_at">{{ publicDate(item.published_at) }}</time>
                <span aria-hidden="true">·</span>
                <span>約 {{ item.reading_minutes }} 分鐘閱讀</span>
              </div>
              <h3><a :href="`/articles/${item.document_id}/`">{{ item.title }}</a></h3>
              <p v-if="item.excerpt" class="excerpt">{{ item.excerpt }}</p>
            </article>
          </li>
        </ol>
        <div v-else class="state empty">
          <UiIcon name="search" :size="28" />
          <p class="empty-title">{{ keywords ? `找不到符合「${keywords}」的文章` : '這裡還沒有公開文章' }}</p>
          <p v-if="keywords">換個關鍵字再試一次。</p>
          <button v-if="keywords || collection" type="button" class="link" @click="searchText = ''; setQuery({ q: '', collection: '' })">查看全部文章</button>
        </div>

        <nav v-if="data && data.pages > 1" class="pager" aria-label="分頁">
          <button type="button" class="page-button" :disabled="page <= 1" @click="setQuery({ page: page - 1 })">
            <UiIcon name="chevronLeft" :size="16" />上一頁
          </button>
          <span>第 {{ data.page }} / {{ data.pages }} 頁</span>
          <button type="button" class="page-button" :disabled="page >= data.pages" @click="setQuery({ page: page + 1 })">
            下一頁<UiIcon name="chevronRight" :size="16" />
          </button>
        </nav>
      </section>
    </div>
  </div>
</template>

<style scoped>
.hero { padding: clamp(3rem, 7vw, 4.5rem) var(--ui-gutter) clamp(2.5rem, 5vw, 3.5rem); border-bottom: 1px solid var(--ui-border-subtle); background: var(--ui-bg-subtle); text-align: center; }
.hero-inner { max-width: 45rem; margin: 0 auto; display: grid; justify-items: center; gap: var(--ui-space-4); }
h1 { margin: 0; font-size: clamp(1.875rem, 1.3rem + 2vw, 2.75rem); line-height: 1.2; font-weight: 700; letter-spacing: -.02em; }
.lead { margin: 0; color: var(--ui-text-secondary); font-size: 1.0625rem; line-height: 1.7; }
.search {
  position: relative; margin-top: var(--ui-space-3); width: 100%; display: flex; align-items: center; gap: var(--ui-space-2);
  min-height: 3.5rem; padding: 0 .5rem 0 1.125rem; box-sizing: border-box; color: var(--ui-text-muted);
  border: 1px solid var(--ui-border-strong); border-radius: .875rem; background: var(--ui-bg-surface); box-shadow: 0 4px 16px rgb(16 24 40 / .06);
}
.search:focus-within { border-color: var(--ui-accent); box-shadow: var(--ui-focus-ring); }
.search input { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; color: var(--ui-text); font: inherit; font-size: 1rem; }
.search input:focus-visible { box-shadow: none; }
.search input::-webkit-search-cancel-button { display: none; }
.clear { display: grid; place-items: center; width: 2rem; height: 2rem; border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-muted); cursor: pointer; }
.clear:hover { background: var(--ui-bg-muted); color: var(--ui-text); }
.submit { height: 2.625rem; padding: 0 1.125rem; border: 0; border-radius: .625rem; background: var(--ui-accent); color: #fff; font: inherit; font-weight: 600; cursor: pointer; }
.submit:hover { background: var(--ui-accent-hover); }
.hub-dark .submit { color: #0c111b; }

.content { box-sizing: border-box; max-width: 70rem; margin: 0 auto; padding: clamp(2rem, 5vw, 3.5rem) var(--ui-gutter) 5rem; display: grid; gap: clamp(2.5rem, 5vw, 3.5rem); }
.block { display: grid; gap: 1.125rem; min-width: 0; scroll-margin-top: 5rem; }
h2 { margin: 0; font-size: 1.25rem; font-weight: 700; }
.collections { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: var(--ui-space-4); }
.collection-card {
  display: grid; gap: var(--ui-space-3); justify-items: start; padding: 1.375rem; border: 1px solid var(--ui-border);
  border-radius: .875rem; background: var(--ui-bg-surface); color: var(--ui-text); text-decoration: none; transition: border-color .15s, box-shadow .15s;
}
.collection-card:hover { border-color: var(--ui-border-strong); box-shadow: var(--ui-shadow-sm); }
.card-mark { width: 2.5rem; height: 2.5rem; border-radius: .625rem; font-size: 1rem; }
.card-name { font-size: 1.0625rem; font-weight: 700; overflow-wrap: anywhere; }
.card-count { display: inline-flex; align-items: center; gap: var(--ui-space-1); color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; }

.list-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--ui-space-3); }
.result-line { margin: var(--ui-space-1) 0 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.chips { display: flex; flex-wrap: wrap; gap: .375rem; }
.chip { min-height: 2.125rem; padding: 0 .875rem; border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-pill); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; font-size: var(--ui-text-sm); cursor: pointer; }
.chip:hover { border-color: var(--ui-text-muted); }
.chip.on { border-color: var(--ui-text); background: var(--ui-text); color: var(--ui-bg-surface); font-weight: 600; }
.articles { list-style: none; margin: 0; padding: 0; }
.articles.stale { opacity: .6; transition: opacity .15s; }
.article { display: grid; gap: var(--ui-space-2); padding: 1.375rem 0; border-top: 1px solid var(--ui-border-subtle); }
.article article { display: grid; gap: var(--ui-space-2); }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: .625rem; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.collection-tag { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); font-weight: 600; }
h3 { margin: 0; font-size: 1.1875rem; line-height: 1.4; font-weight: 700; overflow-wrap: anywhere; }
h3 a { color: var(--ui-text); text-decoration: none; }
h3 a:hover { color: var(--ui-accent); text-decoration: underline; text-underline-offset: .18em; }
.excerpt { margin: 0; max-width: 72ch; color: var(--ui-text-secondary); font-size: .96875rem; line-height: 1.75; overflow-wrap: anywhere; }
.state { margin: 0; padding: var(--ui-space-6) 0; border-top: 1px solid var(--ui-border-subtle); color: var(--ui-text-muted); }
.empty { display: grid; justify-items: center; gap: var(--ui-space-2); text-align: center; }
.empty p { margin: 0; }
.empty-title { color: var(--ui-text); font-weight: 600; font-size: var(--ui-text-lg); }
.link { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; cursor: pointer; }
.pager { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-3); padding-top: var(--ui-space-4); border-top: 1px solid var(--ui-border-subtle); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.page-button { display: inline-flex; align-items: center; gap: var(--ui-space-1); min-height: 2.5rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; cursor: pointer; }
.page-button:disabled { opacity: .45; cursor: default; }
@media (max-width: 640px) {
  .submit { display: none; }
  .search { padding-right: .375rem; }
}
</style>
