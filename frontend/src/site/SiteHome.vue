<script setup lang="ts">
import Skeleton from 'primevue/skeleton'
import HighlightText from '../HighlightText.vue'
import AlbumThumb from './AlbumThumb.vue'
import { searchTerms } from '../searchTerms'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import UiIcon from '../app/components/UiIcon.vue'
import { useSite } from '../stores/site'
import {
  cardDate, collectionStyle, colorClass, markOf, portalMode, portals, publicApi, publicDate, shortPublicDate, usePublicNav,
  type PublicCard, type PublicCardPage, type PublicNode,
} from './public'

const route = useRoute()
const router = useRouter()
const site = useSite()
const mode = portalMode(route)
const names = portals[mode]
const member = mode === 'member'
const portal = usePublicNav(mode)

const queryText = (key: string) => typeof route.query[key] === 'string' ? route.query[key] as string : ''
const keywords = computed(() => queryText('q').trim())
const terms = computed(() => searchTerms(keywords.value))
const collection = computed(() => queryText('collection'))
const showAll = computed(() => queryText('view') === 'all')
const page = computed(() => Math.max(1, Number.parseInt(queryText('page') || '1', 10) || 1))
/** Overview (tiles + latest) unless the reader searched, picked a collection or asked for every article. */
const listing = computed(() => Boolean(keywords.value || collection.value || showAll.value))

function setQuery(patch: Record<string, string | number | undefined>) {
  const query: LocationQueryRaw = { ...route.query, page: undefined, ...patch }
  for (const key of Object.keys(query)) if (query[key] === '' || query[key] === undefined || query[key] === 1) delete query[key]
  void router.replace({ query })
}

/** Page buttons: a history entry per page (Back returns to it) and the new page starts at the top. */
function goToPage(target: number) {
  const query: LocationQueryRaw = { ...route.query, page: target > 1 ? target : undefined }
  if (query.page === undefined) delete query.page
  void router.push({ query }).then(() => window.scrollTo({ top: 0 }))
}

// ---- Articles from the API (cards need excerpts) ----------------------------------------------------
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
  const params = new URLSearchParams({ page: String(listing.value ? page.value : 1) })
  if (keywords.value) params.set('q', keywords.value)
  if (collection.value) params.set('collection', collection.value)
  try {
    const result = await publicApi<PublicCardPage>(`${names.list}?${params}`, request.signal)
    if (request.signal.aborted) return
    data.value = result
    if (listing.value && result.page !== page.value) setQuery({ page: result.page })
  } catch (cause) {
    if (request.signal.aborted) return
    data.value = undefined
    error.value = (cause as { status?: number }).status === 400 ? '找不到這個集合。' : '暫時無法載入文章，請稍後再試。'
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}
watch([keywords, collection, showAll, page], loadArticles, { immediate: true })

const latest = computed(() => data.value?.results.slice(0, 6) ?? [])

// ---- Popular (public site only; empty until enough articles have views) ----------------------------
const popular = ref<PublicCard[]>([])
if (!member) {
  void publicApi<{ results: PublicCard[] }>('/api/public/popular/').then(result => { popular.value = result.results }).catch(() => { popular.value = [] })
}

// ---- Featured (public site only): picked by Admins, shown after popular (decisions 17–18) ----------
const featured = ref<PublicCard[]>([])
if (!member) {
  void publicApi<{ results: PublicCard[] }>('/api/public/featured/').then(result => { featured.value = result.results }).catch(() => { featured.value = [] })
}

// ---- Overview tiles from the navigation data ---------------------------------------------------------------
const roots = computed(() => portal.childrenOf(null))
function tile(node: PublicNode) {
  const ids = portal.subtree(node.id)
  const articles = portal.nav.value.articles
    .filter(article => article.collection_id && ids.includes(article.collection_id))
    .slice(0, 3)
    .map(article => ({ ...article, sub: article.collection_id !== node.id ? portal.byId(article.collection_id)?.name ?? '' : '' }))
  const nested = node.total_count - node.article_count
  return {
    node, articles, children: portal.childrenOf(node.id),
    countLabel: nested ? `${node.total_count} 篇文章（含子集合 ${nested} 篇）` : `${node.total_count} 篇文章`,
  }
}
const tiles = computed(() => roots.value.map(tile))
const looseCount = computed(() => portal.articlesOf(null).length)
const stats = computed(() => ({
  articles: portal.nav.value.articles.length,
  collections: portal.nav.value.collections.length,
  updated: portal.lastUpdated.value ? shortPublicDate(portal.lastUpdated.value) : '—',
}))

// ---- Listing header ---------------------------------------------------------------------------------------------
const activeNode = computed(() => portal.byId(collection.value))
const activePath = computed(() => portal.pathIds(collection.value).map(id => portal.byId(id)!).filter(Boolean))
const listHeading = computed(() => {
  if (keywords.value) return `搜尋「${keywords.value}」`
  if (collection.value) return activeNode.value?.name ?? '集合'
  return member ? '全部文件' : '全部文章'
})
const cardPath = (card: PublicCard) => card.path.map(item => item.name).join(' › ')

watch([listHeading, listing, () => site.name], () => site.setTitle(listing.value ? listHeading.value : undefined), { immediate: true })
</script>

<template>
  <div class="home">
    <!-- Overview -->
    <template v-if="!listing">
      <section class="hero" aria-labelledby="hero-title">
        <div class="inner hero-inner">
          <div class="hero-text">
            <span class="eyebrow">{{ member ? '成員閱讀入口' : '公開知識庫' }}</span>
            <h1 id="hero-title">{{ site.name }}</h1>
            <p v-if="member" class="lead">團隊所有文件的閱讀入口，包含內部文件。標示「公開」的文件也會出現在公開知識站。</p>
            <p v-else-if="site.tagline" class="lead">{{ site.tagline }}</p>
          </div>
          <dl class="stats">
            <div><dt>{{ member ? '文件' : '公開文章' }}</dt><dd>{{ stats.articles }}</dd></div>
            <div><dt>集合</dt><dd>{{ stats.collections }}</dd></div>
            <div><dt>最近更新</dt><dd>{{ stats.updated }}</dd></div>
          </dl>
        </div>
      </section>

      <div class="inner content">
        <section class="block" aria-labelledby="latest-title">
          <div class="block-head">
            <h2 id="latest-title">{{ member ? '最近更新' : '最新文章' }}</h2>
            <RouterLink :to="{ name: names.home, query: { view: 'all' } }" class="more">{{ member ? '全部文件' : '全部文章' }} <UiIcon name="arrowRight" :size="14" /></RouterLink>
          </div>
          <p v-if="error" class="state" role="alert">{{ error }} <button type="button" class="link" @click="loadArticles">重試</button></p>
          <div v-else class="cards">
            <template v-if="loading && !data">
              <Skeleton v-for="index in 6" :key="index" height="10rem" border-radius="14px" />
            </template>
            <RouterLink v-for="card in latest" v-else :key="card.document_id" :to="{ name: names.articleRoute, params: { id: card.document_id } }"
              class="card" :style="collectionStyle(card.collection)">
              <AlbumThumb v-if="card.cover?.url" :cover="card.cover" variant="wide" class="card-cover" />
              <span v-else class="card-cover card-band" aria-hidden="true" />
              <span class="card-meta">
                <span v-if="card.path.length" class="tag" :class="colorClass(card.collection)">{{ cardPath(card) }}</span>
                <span v-if="member" class="visibility" :class="{ public: card.public }">{{ card.public ? '公開' : '內部' }}</span>
                <time :datetime="cardDate(card)">{{ publicDate(cardDate(card)) }}</time>
                <span aria-hidden="true">·</span><span>約 {{ card.reading_minutes }} 分鐘</span>
              </span>
              <span class="card-title">{{ card.title }}</span>
              <span v-if="card.excerpt" class="card-excerpt">{{ card.excerpt }}</span>
            </RouterLink>
            <p v-if="!loading && !latest.length" class="state">{{ member ? '這裡還沒有文件。' : '這裡還沒有公開文章。' }}</p>
          </div>
        </section>

        <section v-if="popular.length" class="block" aria-labelledby="popular-title">
          <div class="block-head">
            <h2 id="popular-title">熱門文章</h2>
            <span class="block-note">最近 30 天最多人閱讀</span>
          </div>
          <ol class="popular">
            <li v-for="(card, index) in popular" :key="card.document_id">
              <RouterLink :to="{ name: names.articleRoute, params: { id: card.document_id } }" class="popular-item">
                <span class="rank" aria-hidden="true">{{ index + 1 }}</span>
                <AlbumThumb v-if="card.cover" :cover="card.cover" />
                <span class="popular-text">
                  <span class="popular-title">{{ card.title }}</span>
                  <span class="popular-meta">
                    <span v-if="card.path.length" class="tag" :class="colorClass(card.collection)">{{ cardPath(card) }}</span>
                    <span>約 {{ card.reading_minutes }} 分鐘</span>
                  </span>
                </span>
              </RouterLink>
            </li>
          </ol>
        </section>

        <section v-if="featured.length" class="block" aria-labelledby="featured-title">
          <div class="block-head">
            <h2 id="featured-title">精選文章</h2>
            <span class="block-note">管理員推薦的入門與重點文章</span>
          </div>
          <div class="featured">
            <RouterLink v-for="card in featured" :key="card.document_id" :to="{ name: names.articleRoute, params: { id: card.document_id } }"
              class="card featured-card" :style="collectionStyle(card.collection)">
              <AlbumThumb v-if="card.cover?.url" :cover="card.cover" variant="wide" class="card-cover" />
              <span v-else class="card-cover card-band" aria-hidden="true" />
              <span class="card-meta">
                <UiIcon name="star" :size="15" filled class="featured-star" />
                <span v-if="card.path.length" class="tag" :class="colorClass(card.collection)">{{ cardPath(card) }}</span>
                <span>約 {{ card.reading_minutes }} 分鐘</span>
              </span>
              <span class="card-title">{{ card.title }}</span>
              <span v-if="card.excerpt" class="card-excerpt">{{ card.excerpt }}</span>
              <span class="featured-more">閱讀 <UiIcon name="arrowRight" :size="14" /></span>
            </RouterLink>
          </div>
        </section>

        <section v-if="tiles.length || !portal.navLoaded.value" class="block" aria-labelledby="browse-title">
          <div class="block-head">
            <h2 id="browse-title">依集合瀏覽</h2>
            <span class="block-note">每個集合列出最新的文章</span>
          </div>
          <div class="tiles">
            <template v-if="!portal.navLoaded.value">
              <Skeleton v-for="index in 3" :key="index" height="15rem" border-radius="14px" />
            </template>
            <article v-for="item in tiles" v-else :key="item.node.id" class="tile" :style="collectionStyle(item.node)">
              <div class="tile-bar" aria-hidden="true" />
              <div class="tile-body">
                <div class="tile-head">
                  <span class="ui-col-mark tile-mark" :class="colorClass(item.node)" aria-hidden="true">{{ markOf(item.node.name) }}</span>
                  <div class="tile-title">
                    <RouterLink :to="{ name: names.home, query: { collection: item.node.id } }" class="tile-name">{{ item.node.name }}</RouterLink>
                    <span class="tile-count">{{ item.countLabel }}</span>
                  </div>
                </div>
                <div v-if="item.children.length" class="chips">
                  <span class="chips-label">子集合</span>
                  <RouterLink v-for="child in item.children" :key="child.id" :to="{ name: names.home, query: { collection: child.id } }" class="chip">
                    <span class="ui-col-mark chip-mark" :class="colorClass(child)" aria-hidden="true">{{ markOf(child.name) }}</span>{{ child.name }}<span class="chip-count">{{ child.total_count }}</span>
                  </RouterLink>
                </div>
                <ul class="tile-list">
                  <li v-for="article in item.articles" :key="article.document_id">
                    <RouterLink :to="{ name: names.articleRoute, params: { id: article.document_id } }" class="tile-link">
                      <AlbumThumb v-if="article.cover" :cover="article.cover" class="tile-thumb" />
                      <span class="tile-link-title">{{ article.title }}<span v-if="article.sub" class="sub">{{ article.sub }}</span></span>
                      <time :datetime="article.date">{{ shortPublicDate(article.date) }}</time>
                    </RouterLink>
                  </li>
                </ul>
                <RouterLink :to="{ name: names.home, query: { collection: item.node.id } }" class="more">查看全部 <UiIcon name="arrowRight" :size="14" /></RouterLink>
              </div>
            </article>
          </div>
          <p v-if="looseCount" class="block-note">另有 {{ looseCount }} 篇文章未歸入集合，可在左側「其他文章」找到。</p>
        </section>
      </div>
    </template>

    <!-- Listing: search, a collection, or every article -->
    <div v-else class="inner content listing">
      <header class="list-head" :style="activeNode ? collectionStyle(activeNode) : undefined">
        <nav v-if="activePath.length > 1" class="crumbs" aria-label="上層集合">
          <RouterLink :to="{ name: names.home }">首頁</RouterLink>
          <template v-for="node in activePath.slice(0, -1)" :key="node.id">
            <span aria-hidden="true">/</span>
            <RouterLink :to="{ name: names.home, query: { collection: node.id } }">{{ node.name }}</RouterLink>
          </template>
        </nav>
        <div class="list-title">
          <span v-if="activeNode" class="ui-col-mark list-mark" :class="colorClass(activeNode)" aria-hidden="true">{{ markOf(activeNode.name) }}</span>
          <h1>{{ listHeading }}</h1>
        </div>
        <p class="result-line" aria-live="polite">{{ loading && !data ? '正在載入…' : `${data?.count ?? 0} 篇文章` }}</p>
        <div v-if="activeNode && portal.childrenOf(activeNode.id).length" class="chips">
          <span class="chips-label">子集合</span>
          <RouterLink v-for="child in portal.childrenOf(activeNode.id)" :key="child.id" :to="{ name: names.home, query: { collection: child.id } }" class="chip">
            <span class="ui-col-mark chip-mark" :class="colorClass(child)" aria-hidden="true">{{ markOf(child.name) }}</span>{{ child.name }}<span class="chip-count">{{ child.total_count }}</span>
          </RouterLink>
        </div>
      </header>

      <p v-if="error" class="state" role="alert">{{ error }} <button type="button" class="link" @click="loadArticles">重試</button></p>
      <div v-else-if="loading && !data" class="cards"><Skeleton v-for="index in 6" :key="index" height="10rem" border-radius="14px" /></div>
      <div v-else-if="data?.results.length" class="cards" :class="{ stale: loading }">
        <RouterLink v-for="card in data.results" :key="card.document_id"
          :to="{ name: names.articleRoute, params: { id: card.document_id }, query: terms.length ? { hl: terms.join(' ') } : {} }"
          class="card" :style="collectionStyle(card.collection)">
          <AlbumThumb v-if="card.cover?.url" :cover="card.cover" variant="wide" class="card-cover" />
              <span v-else class="card-cover card-band" aria-hidden="true" />
          <span class="card-meta">
            <span v-if="card.path.length" class="tag" :class="colorClass(card.collection)">{{ cardPath(card) }}</span>
            <span v-if="member" class="visibility" :class="{ public: card.public }">{{ card.public ? '公開' : '內部' }}</span>
                <time :datetime="cardDate(card)">{{ publicDate(cardDate(card)) }}</time>
            <span aria-hidden="true">·</span><span>約 {{ card.reading_minutes }} 分鐘</span>
          </span>
          <span class="card-title"><HighlightText :text="card.title" :terms="terms" /></span>
          <!-- P16b: a search shows where each result matched instead of its opening lines. -->
          <span v-if="card.matches?.snippets.length" class="card-excerpt card-snippet">
            <template v-for="(piece, index) in card.matches.snippets" :key="index"><HighlightText :text="piece" :terms="terms" /><br v-if="index < card.matches.snippets.length - 1"></template>
          </span>
          <span v-else-if="card.excerpt" class="card-excerpt">{{ card.excerpt }}</span>
        </RouterLink>
      </div>
      <div v-else class="empty">
        <UiIcon name="search" :size="28" />
        <p class="empty-title">{{ keywords ? `找不到符合「${keywords}」的文章` : '這裡還沒有公開文章' }}</p>
        <RouterLink :to="{ name: names.home }" class="more">回到首頁</RouterLink>
      </div>

      <nav v-if="data && data.pages > 1" class="pager" aria-label="分頁">
        <button type="button" class="page-button" :disabled="page <= 1" @click="goToPage(page - 1)"><UiIcon name="chevronLeft" :size="16" />上一頁</button>
        <span>第 {{ data.page }} / {{ data.pages }} 頁</span>
        <button type="button" class="page-button" :disabled="page >= data.pages" @click="goToPage(page + 1)">下一頁<UiIcon name="chevronRight" :size="16" /></button>
      </nav>
    </div>
  </div>
</template>

<style scoped>
.inner { box-sizing: border-box; max-width: 85rem; margin: 0 auto; }
.hero { padding: clamp(2rem, 4vw, 3.5rem) clamp(1rem, 3vw, 3rem) clamp(1.75rem, 3vw, 3rem); border-bottom: 1px solid var(--ui-border-subtle); background: color-mix(in srgb, var(--ui-accent-soft) 70%, var(--ui-bg-surface)); }
.hero-inner { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--ui-space-5); }
.hero-text { display: grid; gap: var(--ui-space-3); max-width: 48rem; }
.eyebrow { color: var(--ui-accent-on-soft); font-size: var(--ui-text-sm); font-weight: 600; letter-spacing: .02em; }
h1 { margin: 0; font-size: clamp(1.875rem, 1.3rem + 2vw, 2.75rem); line-height: 1.15; font-weight: 700; letter-spacing: -.02em; overflow-wrap: anywhere; }
.lead { margin: 0; color: var(--ui-text-secondary); font-size: 1.0625rem; line-height: 1.7; }
.stats { display: flex; gap: var(--ui-space-6); margin: 0; }
.stats div { display: flex; flex-direction: column-reverse; gap: 2px; }
.stats dt { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.stats dd { margin: 0; font-size: 1.75rem; font-weight: 700; font-variant-numeric: tabular-nums; }

.content { width: 100%; padding: clamp(1.5rem, 3vw, 2.5rem) clamp(1rem, 3vw, 3rem) clamp(2.5rem, 5vw, 4rem); display: grid; gap: clamp(2rem, 4vw, 3rem); align-content: start; }
.block { display: grid; gap: var(--ui-space-4); }
.block-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--ui-space-3); }
h2 { margin: 0; font-size: 1.25rem; font-weight: 700; }
.block-note { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.more { display: inline-flex; align-items: center; gap: var(--ui-space-1); color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; text-decoration: none; }
.more:hover { text-decoration: underline; }

.tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr)); gap: var(--ui-space-4); }
.tile { display: flex; flex-direction: column; border: 1px solid var(--ui-border); border-radius: .875rem; overflow: hidden; background: var(--ui-bg-surface); }
.tile-bar { height: 4px; background: var(--col-fg); opacity: .75; }
.tile-body { display: grid; gap: var(--ui-space-4); padding: 1.25rem 1.375rem 1.375rem; }
.tile-head { display: flex; align-items: center; gap: var(--ui-space-3); }
.tile-mark { width: 2.5rem; height: 2.5rem; border-radius: .625rem; font-size: 1.0625rem; }
.tile-title { display: grid; min-width: 0; }
.tile-name { color: var(--ui-text); font-size: 1.0625rem; font-weight: 700; text-decoration: none; overflow-wrap: anywhere; }
.tile-name:hover { color: var(--ui-accent); text-decoration: underline; }
.tile-count { color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.chips { display: flex; flex-wrap: wrap; align-items: center; gap: .375rem; font-size: var(--ui-text-sm); }
.chips-label { color: var(--ui-text-muted); }
.chip { display: inline-flex; align-items: center; gap: .375rem; padding: 2px .625rem 2px 3px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-pill); color: var(--ui-text-secondary); text-decoration: none; }
.chip:hover { border-color: var(--ui-border-strong); color: var(--ui-text); }
.chip-mark { width: 1.125rem; height: 1.125rem; border-radius: 50%; font-size: .625rem; }
.chip-count { color: var(--ui-text-muted); }
.tile-list { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--ui-border-subtle); }
.tile-list li { border-bottom: 1px solid var(--ui-border-subtle); }
.tile-thumb { width: 2.25rem; height: 2.25rem; border-radius: .375rem; align-self: center; }
.tile-link:has(.tile-thumb) { align-items: center; }
.tile-link:has(.tile-thumb) .tile-link-title { flex: 1; }
.tile-link { display: flex; align-items: baseline; justify-content: space-between; gap: var(--ui-space-3); padding: .625rem 0; color: var(--ui-text); font-size: .90625rem; text-decoration: none; }
.tile-link:hover .tile-link-title { color: var(--ui-accent); text-decoration: underline; }
.tile-link-title { min-width: 0; overflow-wrap: anywhere; }
.sub { margin-left: .375rem; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.tile-link time { flex: none; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }

/* Up to five in one row (the list has at most five), wrapping evenly on narrower screens. */
/* Up to four, in one row when there is room. */
.featured { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 17rem), 1fr)); gap: var(--ui-space-4); }
.featured-card { background: var(--ui-accent-soft); border-color: color-mix(in srgb, var(--ui-accent) 25%, var(--ui-border)); }
.featured-card .card-title { font-size: 1.1875rem; }
.featured-star { color: #d99a00; }
.featured-more { display: inline-flex; align-items: center; gap: var(--ui-space-1); margin-top: auto; color: var(--ui-accent); font-size: var(--ui-text-sm); font-weight: 600; }
.popular { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(max(min(100%, 14rem), calc((100% - 4 * var(--ui-space-3)) / 5)), 1fr)); gap: var(--ui-space-3); }
.popular-item :deep(.album-thumb) { align-self: center; }
.popular-item { display: flex; align-items: flex-start; gap: var(--ui-space-3); height: 100%; box-sizing: border-box; padding: var(--ui-space-4); border: 1px solid var(--ui-border); border-radius: .875rem; background: var(--ui-bg-surface); color: var(--ui-text); text-decoration: none; }
.popular-item:hover { border-color: var(--ui-border-strong); box-shadow: var(--ui-shadow-sm); }
.popular-item:hover .popular-title { color: var(--ui-accent); }
.rank { flex: none; display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: 50%; background: var(--ui-accent-soft); color: var(--ui-accent-on-soft); font-weight: 700; font-variant-numeric: tabular-nums; }
.popular-text { display: grid; gap: var(--ui-space-1); min-width: 0; }
.popular-title { font-weight: 700; line-height: 1.4; overflow-wrap: anywhere; }
.popular-meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr)); gap: var(--ui-space-4); }
.cards.stale { opacity: .6; }
/* P21b: an album's cover runs to the card's edges above its text. */
.card .card-cover { margin: -1.25rem -1.375rem .25rem; max-width: none; align-self: stretch; }  /* wider than the padded box */
/* Decision 39 (option 4): a card without a cover gets a plain band in its collection's colour, the same
   height as a cover, so a row of cards lines up without empty space. No text inside. */
.card-band { display: block; flex: none; aspect-ratio: 16 / 9;
  background: linear-gradient(135deg, var(--col-bg, var(--ui-col-gray-bg)) 0%, color-mix(in srgb, var(--col-fg, var(--ui-col-gray-fg)) 22%, var(--col-bg, var(--ui-col-gray-bg))) 100%); }
.card { overflow: hidden; }
.card { display: flex; flex-direction: column; gap: .625rem; padding: 1.25rem 1.375rem; border: 1px solid var(--ui-border); border-radius: .875rem; background: var(--ui-bg-surface); color: var(--ui-text); text-decoration: none; transition: border-color .15s, box-shadow .15s; }
.card:hover { border-color: var(--ui-border-strong); box-shadow: var(--ui-shadow-sm); }
.card:hover .card-title { color: var(--ui-accent); }
.card-meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ui-space-2); color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.tag { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); font-weight: 600; }
.visibility { padding: 2px var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-private-bg); color: var(--ui-private-text); font-weight: 600; }
.visibility.public { background: var(--ui-public-bg); color: var(--ui-public-text); }
.card-title { font-size: 1.0625rem; font-weight: 700; line-height: 1.4; overflow-wrap: anywhere; }
.card-excerpt { color: var(--ui-text-secondary); font-size: .90625rem; line-height: 1.7; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3; overflow: hidden; }

.list-head { display: grid; gap: var(--ui-space-2); padding-bottom: var(--ui-space-2); }
.crumbs { display: flex; flex-wrap: wrap; gap: .375rem; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.crumbs a { color: inherit; text-decoration: none; }
.crumbs a:hover { color: var(--ui-accent); text-decoration: underline; }
.list-title { display: flex; align-items: center; gap: var(--ui-space-3); }
.list-title h1 { font-size: clamp(1.625rem, 1.2rem + 1.4vw, 2.25rem); }
.list-mark { width: 2.5rem; height: 2.5rem; border-radius: .625rem; font-size: 1.0625rem; }
.result-line { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.state { margin: 0; color: var(--ui-text-muted); }
.link { padding: 0; border: 0; background: none; color: var(--ui-accent); font: inherit; font-weight: 600; cursor: pointer; }
.empty { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-7) 0; border: 1px dashed var(--ui-border-strong); border-radius: var(--ui-radius-lg); color: var(--ui-text-muted); text-align: center; }
.empty p { margin: 0; }
.empty-title { color: var(--ui-text); font-weight: 600; font-size: var(--ui-text-lg); }
.pager { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-3); color: var(--ui-text-muted); font-size: var(--ui-text-sm); }
.page-button { display: inline-flex; align-items: center; gap: var(--ui-space-1); min-height: 2.5rem; padding: 0 var(--ui-space-3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-bg-surface); color: var(--ui-text-secondary); font: inherit; cursor: pointer; }
.page-button:disabled { opacity: .45; cursor: default; }
@media (max-width: 640px) {
  .stats { gap: var(--ui-space-5); }
  .stats dd { font-size: 1.375rem; }
}
</style>
