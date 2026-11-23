import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type ThemeMode = 'system' | 'light' | 'dark'
const storageKey = 'knowledge-hub.app.theme'

function stored(): ThemeMode {
  try {
    const value = localStorage.getItem(storageKey)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch { /* storage may be disabled */ }
  return 'system'
}

/**
 * Appearance for the redesigned workspace. The `.hub-dark` class is applied to <html>
 * only while a new layout is mounted, so legacy pages always render light.
 */
export const useTheme = defineStore('theme', () => {
  const mode = ref<ThemeMode>(stored())
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const systemDark = ref(media.matches)
  media.addEventListener('change', event => { systemDark.value = event.matches })
  const active = ref(false)

  const isDark = computed(() => mode.value === 'dark' || (mode.value === 'system' && systemDark.value))

  watch([isDark, active], ([dark, on]) => {
    document.documentElement.classList.toggle('hub-dark', dark && on)
    document.documentElement.style.colorScheme = on ? (dark ? 'dark' : 'light') : ''
  }, { immediate: true })

  function setMode(next: ThemeMode) {
    mode.value = next
    try { localStorage.setItem(storageKey, next) } catch { /* storage may be disabled */ }
  }

  function cycle() {
    setMode(isDark.value ? 'light' : 'dark')
  }

  /** Called by layouts that support dark mode. */
  function attach() {
    active.value = true
    return () => { active.value = false }
  }

  return { mode, isDark, setMode, cycle, attach }
})
