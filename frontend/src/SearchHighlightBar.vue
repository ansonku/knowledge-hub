<script setup lang="ts">
// P16c: the small bar above an article opened from a search: count, previous / next, close.
import UiIcon from './app/components/UiIcon.vue'

defineProps<{
  terms: string[]
  count: number
  /** 0-based position of the current match. */
  index: number
  /** HTML documents run in a sandbox: their text cannot be marked. */
  unsupported?: boolean
}>()
defineEmits<{ previous: []; next: []; close: [] }>()
</script>

<template>
  <div class="search-bar" role="search" aria-label="搜尋標示">
    <UiIcon name="search" :size="15" />
    <span class="text" role="status">
      <template v-if="unsupported">HTML 文件無法標示關鍵字</template>
      <template v-else-if="count">找到 {{ count }} 處「{{ terms.join(' ') }}」 · 第 {{ index + 1 }} 處</template>
      <template v-else>內文中沒有「{{ terms.join(' ') }}」（可能是標題、集合或標籤符合）</template>
    </span>
    <template v-if="!unsupported && count">
      <button type="button" class="bar-button" aria-label="上一處（Shift+Enter）" title="上一處（Shift+Enter）" @click="$emit('previous')">
        <UiIcon name="chevronUp" :size="16" />
      </button>
      <button type="button" class="bar-button" aria-label="下一處（Enter）" title="下一處（Enter）" @click="$emit('next')">
        <UiIcon name="chevronDown" :size="16" />
      </button>
    </template>
    <button type="button" class="bar-button" aria-label="關閉標示（Esc）" title="關閉標示（Esc）" @click="$emit('close')">
      <UiIcon name="close" :size="16" />
    </button>
  </div>
</template>

<style scoped>
.search-bar {
  position: sticky; top: var(--search-bar-top, .75rem); z-index: 6; display: flex; align-items: center; gap: var(--ui-space-2);
  width: fit-content; max-width: 100%; box-sizing: border-box; margin: 0 0 var(--ui-space-4) auto; padding: .3rem .4rem .3rem .75rem;
  border: 1px solid var(--ui-border); border-radius: var(--ui-radius-pill); background: var(--ui-bg-surface);
  box-shadow: var(--ui-shadow-md, 0 4px 14px rgb(16 24 40 / .1)); color: var(--ui-text-secondary); font-size: var(--ui-text-sm);
}
.text { min-width: 0; overflow-wrap: anywhere; }
.bar-button {
  display: grid; place-items: center; flex: none; width: 1.9rem; height: 1.9rem; border: 0; border-radius: 50%;
  background: transparent; color: var(--ui-text-secondary); cursor: pointer;
}
.bar-button:hover { background: var(--ui-bg-subtle); color: var(--ui-text); }
.bar-button:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 1px; }
</style>
