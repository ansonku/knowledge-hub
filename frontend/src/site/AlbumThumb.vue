<script setup lang="ts">
// P21b: an album article's cover — wide on cards (with the picture count), a small square in compact lists.
// The picture is a 480 px thumbnail; its title is right beside it, so it carries no alt text.
import type { AlbumCover } from './public'

withDefaults(defineProps<{ cover: AlbumCover; variant?: 'wide' | 'mini' }>(), { variant: 'mini' })
</script>

<template>
  <span v-if="cover.url" class="album-thumb" :class="`album-${variant}`">
    <img :src="cover.url" alt="" loading="lazy" decoding="async" :width="variant === 'wide' ? 480 : 96" :height="variant === 'wide' ? 270 : 96">
    <span v-if="variant === 'wide'" class="count" :aria-label="`相簿，${cover.count} 張圖片`">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="7" width="14" height="13" rx="2" /><path d="M7 3h12a2 2 0 0 1 2 2v12" /></svg>
      {{ cover.count }} 張
    </span>
  </span>
</template>

<style scoped>
.album-thumb { position: relative; display: block; flex: none; overflow: hidden; background: var(--ui-bg-muted); }
.album-thumb img { display: block; width: 100%; height: 100%; object-fit: cover; }
.album-wide { aspect-ratio: 16 / 9; max-width: 100%; }
.album-mini { width: 3rem; height: 3rem; border-radius: .5rem; }
.count {
  position: absolute; right: .55rem; bottom: .55rem; display: inline-flex; align-items: center; gap: .3rem; padding: .1rem .5rem;
  border-radius: var(--ui-radius-pill); background: rgb(16 24 40 / .72); color: #fff; font-size: var(--ui-text-xs); font-weight: 600;
}
</style>
