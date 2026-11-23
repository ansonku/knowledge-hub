<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { editor } from './monaco'

const props = defineProps<{ original: string; modified: string; format: 'md' | 'html'; compact?: boolean }>()
const target = ref<HTMLElement>()
let instance: ReturnType<typeof editor.createDiffEditor> | undefined
let original: ReturnType<typeof editor.createModel> | undefined
let modified: ReturnType<typeof editor.createModel> | undefined

onMounted(() => {
  if (!target.value) return
  const language = props.format === 'md' ? 'markdown' : 'plaintext'
  original = editor.createModel(props.original, language)
  modified = editor.createModel(props.modified, language)
  instance = editor.createDiffEditor(target.value, {
    automaticLayout: true,
    originalEditable: false,
    readOnly: true,
    renderSideBySide: true,
    scrollBeyondLastLine: false,
    minimap: { enabled: false },
    // Opt-in for the redesigned compare page; the legacy dialog keeps its full view.
    ...(props.compact ? { hideUnchangedRegions: { enabled: true, contextLineCount: 3 }, diffWordWrap: 'on' as const } : {}),
    originalAriaLabel: '原版本內容',
    modifiedAriaLabel: '比較版本內容',
  })
  instance.setModel({ original, modified })
})

onBeforeUnmount(() => {
  instance?.dispose()
  original?.dispose()
  modified?.dispose()
})
</script>

<template>
  <div ref="target" class="diff" />
</template>

<style scoped>
.diff { height: clamp(28rem, 66vh, 60rem); }
</style>
