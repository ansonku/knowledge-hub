<script setup lang="ts">
// P23c: per-file limits (Markdown, HTML, images, videos): a slider and a number field per kind, in whole MB.
// Videos run from 10 MB to 1 GB, so their slider is logarithmic: the common 10–100 MB stretch stays usable.
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { api } from '../../api'
import { useSession } from '../../stores/session'

export type FileLimit = { label: string; mb: number; min: number; max: number; default: number }
export type FileLimitSet = Record<'markdown' | 'html' | 'image' | 'video', FileLimit>
type Kind = keyof FileLimitSet

const props = defineProps<{ limits: FileLimitSet }>()
const emit = defineEmits<{ saved: [response: { file_limits: FileLimitSet }] }>()
const toast = useToast()
const session = useSession()

const KINDS: Kind[] = ['markdown', 'html', 'image', 'video']
const STEPS = 1000
const CLOUDFLARE_MB = 100
const values = ref<Record<Kind, number>>({ markdown: 0, html: 0, image: 0, video: 0 })
const saving = ref(false)
watch(() => props.limits, limits => {
  values.value = { markdown: limits.markdown.mb, html: limits.html.mb, image: limits.image.mb, video: limits.video.mb }
}, { immediate: true })

const logScale = (kind: Kind) => kind === 'video'
const clamp = (kind: Kind, mb: number) => Math.min(props.limits[kind].max, Math.max(props.limits[kind].min, Math.round(mb)))
function toPosition(kind: Kind, mb: number) {
  const { min, max } = props.limits[kind]
  return logScale(kind) ? Math.round(Math.log(mb / min) / Math.log(max / min) * STEPS) : mb
}
function fromPosition(kind: Kind, position: number) {
  const { min, max } = props.limits[kind]
  return logScale(kind) ? clamp(kind, min * Math.pow(max / min, position / STEPS)) : position
}
// Only the log slider needs ticks: its positions are not proportional. The others say their range in words.
const VIDEO_TICKS = [10, 50, 100, 200, 500, 1024]
const ticks = (kind: Kind) => VIDEO_TICKS.map(mb => ({ mb, label: mb >= 1024 ? `${mb / 1024} GB` : `${mb} MB`, left: toPosition(kind, mb) / STEPS * 100 }))
const sizeText = (mb: number) => mb >= 1024 && mb % 1024 === 0 ? `${mb / 1024} GB` : `${mb} MB`

function onSlide(kind: Kind, event: Event) {
  values.value[kind] = fromPosition(kind, +(event.target as HTMLInputElement).value)
}
// The log slider would move several MB per arrow press; step 1 MB like the number field.
function onKey(kind: Kind, event: KeyboardEvent) {
  if (!logScale(kind)) return
  const step = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[event.key]
  if (!step) return
  event.preventDefault()
  values.value[kind] = clamp(kind, values.value[kind] + step)
}
function onNumber(kind: Kind, event: Event) {
  const typed = Number((event.target as HTMLInputElement).value)
  values.value[kind] = clamp(kind, Number.isFinite(typed) && typed > 0 ? typed : props.limits[kind].min)
  ;(event.target as HTMLInputElement).value = String(values.value[kind])
}

const dirty = computed(() => KINDS.some(kind => values.value[kind] !== props.limits[kind].mb))
const atDefaults = computed(() => KINDS.every(kind => values.value[kind] === props.limits[kind].default))
function resetToDefaults() {
  for (const kind of KINDS) values.value[kind] = props.limits[kind].default
}

async function save() {
  saving.value = true
  try {
    const response = await api<{ file_limits: FileLimitSet }>('/api/admin/storage/', 'PUT', { file_limits: { ...values.value } })
    const saved = response.file_limits
    // This admin's own uploads check the new limits at once; other members get them on their next page load.
    session.limits = { ...session.limits, markdown_bytes: saved.markdown.mb * 1024 * 1024, html_bytes: saved.html.mb * 1024 * 1024,
      image_bytes: saved.image.mb * 1024 * 1024, video_bytes: saved.video.mb * 1024 * 1024 }
    emit('saved', response)
    toast.add({ severity: 'success', summary: '已更新單一檔案上限', life: 2500 })
  } catch (cause) {
    toast.add({ severity: 'error', summary: '無法儲存', detail: cause instanceof Error ? cause.message : '', life: 5000 })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="file-limits" aria-labelledby="file-limits-title" @submit.prevent="save">
    <div id="file-limits-title" class="title">單一檔案上限</div>
    <div v-for="kind in KINDS" :key="kind" class="row">
      <div class="row-head">
        <label :for="`file-limit-${kind}`">{{ limits[kind].label }}</label>
        <span class="value">
          <input :id="`file-limit-${kind}-mb`" type="number" inputmode="numeric" :min="limits[kind].min" :max="limits[kind].max" step="1"
            :value="values[kind]" :aria-label="`${limits[kind].label}上限（MB）`" :disabled="saving" @change="onNumber(kind, $event)">
          <span class="unit">MB</span>
        </span>
      </div>
      <input :id="`file-limit-${kind}`" type="range" class="slider" :min="logScale(kind) ? 0 : limits[kind].min"
        :max="logScale(kind) ? STEPS : limits[kind].max" step="1" :value="toPosition(kind, values[kind])"
        :aria-valuetext="sizeText(values[kind])" :disabled="saving" @input="onSlide(kind, $event)" @keydown="onKey(kind, $event)">
      <div v-if="logScale(kind)" class="ticks" aria-hidden="true">
        <span v-for="tick in ticks(kind)" :key="tick.mb" :style="{ left: `${tick.left}%` }"
          :class="{ start: tick.left < 5, end: tick.left > 95 }">{{ tick.label }}</span>
      </div>
      <p class="meta">
        範圍 {{ sizeText(limits[kind].min) }}～{{ sizeText(limits[kind].max) }}，預設 {{ sizeText(limits[kind].default) }}
      </p>
      <p v-if="kind === 'video' && values.video > CLOUDFLARE_MB" class="cloudflare" role="status">
        透過 Cloudflare 免費方案對外時，超過 100 MB 的上傳會被 Cloudflare 拒絕。
      </p>
    </div>
    <div class="actions">
      <Button type="submit" label="儲存" size="small" :disabled="!dirty || saving" :loading="saving" />
      <Button type="button" label="恢復預設值" size="small" severity="secondary" text :disabled="atDefaults || saving" @click="resetToDefaults" />
    </div>
    <p class="note">超過上限的檔案在瀏覽器就會被擋下，不會送出；伺服器也會再檢查一次。已上傳的檔案不受影響。</p>
  </form>
</template>

<style scoped>
.file-limits { display: grid; gap: var(--ui-space-3); padding-top: var(--ui-space-3); border-top: 1px solid var(--ui-border); }
.title { font-weight: 600; font-size: var(--ui-text-sm); }
.row { display: grid; gap: var(--ui-space-1); min-width: 0; }
.row-head { display: flex; align-items: center; justify-content: space-between; gap: var(--ui-space-2); }
.row-head label { color: var(--ui-text-secondary); font-size: var(--ui-text-sm); }
.value { display: inline-flex; align-items: center; gap: var(--ui-space-1); }
.value input {
  width: 5.25rem; padding: .2rem .5rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm);
  background: var(--ui-bg); color: var(--ui-text); font: inherit; font-size: var(--ui-text-sm); font-variant-numeric: tabular-nums; text-align: right;
}
.value input:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 1px; }
.unit { color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.slider { width: 100%; margin: 0; accent-color: var(--ui-accent); }
.slider:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 3px; border-radius: var(--ui-radius-sm); }
.ticks { position: relative; height: 1rem; color: var(--ui-text-muted); font-size: var(--ui-text-xs); font-variant-numeric: tabular-nums; }
.ticks span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
.ticks span.start { transform: none; }
.ticks span.end { transform: translateX(-100%); }
.meta { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-xs); }
.cloudflare { margin: 0; padding: var(--ui-space-1) var(--ui-space-2); border-radius: var(--ui-radius-sm); background: var(--ui-lagging-bg, var(--ui-bg-muted)); color: var(--ui-lagging-text, var(--ui-text)); font-size: var(--ui-text-xs); }
.actions { display: flex; flex-wrap: wrap; gap: var(--ui-space-2); }
.note { margin: 0; color: var(--ui-text-muted); font-size: var(--ui-text-sm); line-height: 1.6; }
@media (max-width: 520px) { .ticks span:nth-child(2), .ticks span:nth-child(4) { visibility: hidden; } }
</style>
