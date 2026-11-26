<script setup lang="ts">
// P16b: text with the search words marked. Text nodes only, never HTML.
import { computed } from 'vue'
import { splitMatches } from './searchTerms'

const props = defineProps<{ text: string; terms: string[] }>()
const parts = computed(() => splitMatches(props.text, props.terms))
</script>

<template><template v-for="(part, index) in parts" :key="index"><mark v-if="part.hit" class="search-hit">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></template>
