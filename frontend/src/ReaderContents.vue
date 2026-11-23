<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { RenderedMarkdown } from './markdown'

defineProps<{ headings: RenderedMarkdown['headings'] }>()
const emit = defineEmits<{ jump: [id: string] }>()
const desktop = window.matchMedia('(min-width: 1051px)')
const contents = ref<HTMLDetailsElement>()

function setDefaultVisibility() {
  if (contents.value) contents.value.open = desktop.matches
}

onMounted(() => {
  setDefaultVisibility()
  desktop.addEventListener('change', setDefaultVisibility)
})
onUnmounted(() => desktop.removeEventListener('change', setDefaultVisibility))
</script>

<template>
  <details ref="contents" class="reader-sidebar reader-toc">
    <summary>本頁目錄</summary>
    <nav aria-label="本頁目錄">
      <a v-for="heading in headings" :key="heading.id" :href="`#${heading.id}`"
        :style="{ paddingInlineStart: `${Math.max(0, heading.level - 1) * .65}rem` }"
        @click.prevent="emit('jump', heading.id)">{{ heading.text }}</a>
    </nav>
  </details>
</template>

<style scoped>
summary { cursor: pointer; font-size: .875rem; font-weight: 700; }
nav { display: grid; gap: .55rem; max-height: 60vh; overflow: auto; margin-top: .7rem; }
a { width: fit-content; color: #214d99; overflow-wrap: anywhere; font-size: .875rem; text-underline-offset: .18em; }
</style>
