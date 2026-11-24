<script setup lang="ts">
// Stroke icons drawn on a 24px grid; decorative unless the parent labels them.
const paths = {
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  files: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14M20 20l-4-4',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  sliders: 'M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4',
  users: 'M16 20v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 20v-1a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8',
  globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3',
  plus: 'M12 5v14M5 12h14',
  upload: 'M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
  download: 'M12 4v12M7 11l5 5 5-5M4 20h16',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  chevronDown: 'M6 9l6 6 6-6',
  chevronRight: 'M9 6l6 6-6 6',
  chevronLeft: 'M15 6l-6 6 6 6',
  close: 'M6 6l12 12M18 6 6 18',
  menu: 'M4 6h16M4 12h16M4 18h16',
  check: 'M5 12l5 5 9-10',
  alert: 'M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  logout: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3',
  user: 'M20 21v-1a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
  history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2',
  panel: 'M4 5h16v14H4zM15 5v14',
  swap: 'M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7',
  clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  star: 'M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8L3.5 9.7l5.9-.9z',
  moon: 'M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  book: 'M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h7',
  enter: 'M9 10l-5 5 5 5M20 4v7a4 4 0 0 1-4 4H4',
} as const

export type IconName = keyof typeof paths

withDefaults(defineProps<{ name: IconName; size?: number; filled?: boolean }>(), { size: 18, filled: false })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" :fill="filled ? 'currentColor' : 'none'" stroke="currentColor"
    :stroke-width="name === 'more' ? 3 : 1.9" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true" focusable="false" class="ui-icon">
    <path :d="paths[name]" />
  </svg>
</template>

<style scoped>
.ui-icon { flex: none; }
</style>
