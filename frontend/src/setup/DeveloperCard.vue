<script setup lang="ts">
// P24: the developer card — on the setup wizard's licence step and on the About page.
// Support links that are not set yet show "即將開放" and cannot be clicked.
import { computed } from 'vue'
import type { About } from './setup'

const props = defineProps<{ about: About }>()
const initials = computed(() => props.about.developer.name.replace(/[^a-z]/gi, '').slice(0, 2).toUpperCase() || 'KH')
const githubLabel = computed(() => props.about.developer.github.replace(/^https?:\/\//, ''))
const ICONS: Record<string, string> = {
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  code: '<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>',
  heart: '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
  cup: '<path d="M5 8h11v6a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5z"/><path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16"/><path d="M8 3.5c0 1 1 1 1 2M11.5 3.5c0 1 1 1 1 2"/>',
  star: '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
}
const svg = (name: string) =>
  `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`
</script>

<template>
  <div class="dev">
    <div class="avatar" aria-hidden="true">{{ initials }}</div>
    <div class="dev-body">
      <div class="dev-name">{{ about.developer.name }}</div>
      <div class="dev-role">開發與維護 Knowledge Hub</div>
      <div class="dev-links">
        <span><span v-html="svg('mail')" />{{ about.developer.email }}</span>
        <span><span v-html="svg('code')" /><a :href="about.developer.github" target="_blank" rel="noopener">{{ githubLabel }}</a></span>
      </div>
      <div class="badges">
        <span class="badge">版本 <b>v{{ about.version }}</b></span>
        <span class="badge">授權 <b>{{ about.license || '待定' }}</b></span>
        <span class="badge">© <b>{{ about.copyright }}</b></span>
      </div>
      <div class="support-row">
        <a v-if="about.support.github_sponsors" class="support-btn heart" :href="about.support.github_sponsors" target="_blank" rel="noopener"><span v-html="svg('heart')" />GitHub Sponsors</a>
        <span v-else class="support-btn heart soon" aria-disabled="true"><span v-html="svg('heart')" />GitHub Sponsors<em>即將開放</em></span>
        <a v-if="about.support.buy_me_a_coffee" class="support-btn coffee" :href="about.support.buy_me_a_coffee" target="_blank" rel="noopener"><span v-html="svg('cup')" />請我喝杯咖啡</a>
        <span v-else class="support-btn coffee soon" aria-disabled="true"><span v-html="svg('cup')" />請我喝杯咖啡<em>即將開放</em></span>
        <a class="support-btn" :href="about.developer.github" target="_blank" rel="noopener"><span v-html="svg('star')" />在 GitHub 加星號</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dev { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 18px; align-items: center; padding: 20px; border: 1px solid var(--ui-border); border-radius: 16px; background: linear-gradient(135deg, var(--ui-accent-soft), transparent 70%); }
.dev-body { min-width: 0; }
.avatar { width: 64px; height: 64px; border-radius: 18px; display: grid; place-items: center; background: linear-gradient(145deg, #4f7bff, #1e4fd8); color: #fff; font-weight: 700; font-size: 1.3rem; }
.dev-name { font-size: 1.1rem; font-weight: 700; }
.dev-role { color: var(--ui-text-muted); font-size: .82rem; }
.dev-links { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 8px; font-size: .84rem; }
.dev-links > span { display: inline-flex; align-items: center; gap: 6px; color: var(--ui-text-secondary); min-width: 0; overflow-wrap: anywhere; }
.dev-links a { color: var(--ui-accent); text-decoration: none; }
.dev-links a:hover { text-decoration: underline; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; font-size: .76rem; font-weight: 600; background: var(--ui-bg-surface); border: 1px solid var(--ui-border); color: var(--ui-text-secondary); }
.badge b { color: var(--ui-text); }
.support-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.support-btn { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: 9px; border: 1px solid var(--ui-border); background: var(--ui-bg-surface); color: var(--ui-text); font-size: .8rem; font-weight: 600; text-decoration: none; }
.support-btn:hover:not(.soon) { border-color: var(--ui-accent); }
.support-btn:focus-visible, .dev-links a:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.support-btn.heart :deep(svg) { color: #e0436b; }
.support-btn.coffee :deep(svg) { color: #e2a63b; }
.soon { cursor: default; opacity: .75; }
.soon em { font-style: normal; font-size: .68rem; font-weight: 600; padding: 0 6px; margin-left: 2px; border-radius: 999px; background: var(--ui-bg-muted); color: var(--ui-text-muted); }
@media (max-width: 640px) { .dev { grid-template-columns: minmax(0, 1fr); } }
</style>
