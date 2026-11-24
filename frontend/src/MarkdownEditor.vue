<script setup lang="ts">
import { editor } from './monaco'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const value = defineModel<string>({ required: true })
const props = defineProps<{ readonly: boolean }>()
const host = ref<HTMLElement>()
let instance: ReturnType<typeof editor.create> | undefined
let model: ReturnType<typeof editor.createModel> | undefined

onMounted(() => {
  if (!host.value) return
  model = editor.createModel(value.value, 'markdown')
  instance = editor.create(host.value, {
    model,
    ariaLabel: 'Markdown 編輯器',
    automaticLayout: true,
    minimap: { enabled: false },
    readOnly: props.readonly,
    scrollBeyondLastLine: false,
    // Wrap at the editor edge, but never beyond 140 columns on very wide screens.
    wordWrap: 'bounded',
    wordWrapColumn: 140,
    fontSize: 15,
  })
  instance.onDidChangeModelContent(() => {
    if (model) value.value = model.getValue()
  })
})

watch(value, text => {
  if (model && text !== model.getValue()) model.setValue(text)
})
watch(() => props.readonly, readOnly => instance?.updateOptions({ readOnly }))

onBeforeUnmount(() => {
  instance?.dispose()
  model?.dispose()
})
</script>

<template>
  <div ref="host" class="editor-host" />
</template>

<style scoped>
.editor-host { height: clamp(28rem, calc(100vh - 23rem), 64rem); border-radius: .5rem; overflow: hidden; }
</style>
