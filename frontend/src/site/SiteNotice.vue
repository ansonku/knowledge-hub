<script setup lang="ts">
import { computed, ref } from 'vue'
import UiIcon from '../app/components/UiIcon.vue'
import { useSite } from '../stores/site'

// Announcement banner (P6c) on the public site, the reading portal and the workspace. Plain text only.
// Dismissal is per browser and shared with the Django pages (public/assets/account-notice.js).
const KEY = 'knowledge-hub.notice-dismissed'
const site = useSite()
const dismissed = ref<string | null>(read())

function read() {
  try { return localStorage.getItem(KEY) } catch { return null }
}
const visible = computed(() => site.notice && site.notice.id !== dismissed.value ? site.notice : null)
const icon = computed(() => (visible.value?.level === 'info' ? 'info' : 'alert'))
const external = computed(() => /^https?:/i.test(visible.value?.link ?? ''))

function dismiss() {
  const id = visible.value?.id
  if (!id) return
  try { localStorage.setItem(KEY, id) } catch { /* hidden until the page reloads */ }
  dismissed.value = id
}
</script>

<template>
  <div v-if="visible" class="site-notice" :class="visible.level" role="status">
    <UiIcon :name="icon" :size="17" class="notice-icon" />
    <span class="notice-text">
      {{ visible.text }}
      <a v-if="visible.link" :href="visible.link" class="notice-link" :target="external ? '_blank' : undefined"
        :rel="external ? 'noopener noreferrer' : undefined">查看詳情</a>
    </span>
    <button type="button" class="notice-close" aria-label="關閉公告" @click="dismiss"><UiIcon name="close" :size="16" /></button>
  </div>
</template>

<style scoped>
.site-notice { display: flex; align-items: center; justify-content: center; gap: var(--ui-space-3); padding: var(--ui-space-2) var(--ui-space-3) var(--ui-space-2) var(--ui-space-5); border-bottom: 1px solid var(--notice-border); background: var(--notice-bg); color: var(--notice-text); font-size: var(--ui-text-sm); line-height: 1.5; }
.site-notice.info { --notice-bg: var(--ui-accent-soft); --notice-text: var(--ui-accent-on-soft); --notice-border: var(--ui-border); }
.site-notice.warning { --notice-bg: var(--ui-lagging-bg); --notice-text: var(--ui-lagging-text); --notice-border: var(--ui-lagging-border); }
.site-notice.urgent { --notice-bg: var(--ui-danger-bg); --notice-text: var(--ui-danger); --notice-border: var(--ui-danger-border); }
.notice-icon { flex: none; }
.notice-text { overflow-wrap: anywhere; }
.notice-link { margin-left: var(--ui-space-1); color: inherit; font-weight: 600; text-underline-offset: .18em; }
.notice-close { flex: none; display: grid; place-items: center; width: 2rem; height: 2rem; border: 0; border-radius: var(--ui-radius-sm); background: transparent; color: inherit; cursor: pointer; }
.notice-close:hover { background: rgb(0 0 0 / .06); }
</style>
