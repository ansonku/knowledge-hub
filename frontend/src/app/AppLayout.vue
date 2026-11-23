<script setup lang="ts">
import Button from 'primevue/button'
import ConfirmDialog from 'primevue/confirmdialog'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Toast from 'primevue/toast'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useSession } from '../stores/session'
import { useTaxonomy } from '../stores/taxonomy'
import { useTheme } from '../stores/theme'
import { useWorkspace } from '../stores/workspace'
import AppSidebar from './AppSidebar.vue'
import CommandPalette from './components/CommandPalette.vue'
import TaxonomyDialog from './components/TaxonomyDialog.vue'
import UiIcon from './components/UiIcon.vue'
import UploadTray from './components/UploadTray.vue'
import { useUploads } from '../stores/uploads'

const session = useSession()
const taxonomy = useTaxonomy()
const workspace = useWorkspace()
const theme = useTheme()
const route = useRoute()
const detachTheme = theme.attach()

const ready = ref(false)
const failed = ref(false)
const drawerOpen = ref(false)
const taxonomyOpen = ref(false)
const paletteOpen = ref(false)
const uploads = useUploads()
const chooser = ref<HTMLInputElement>()
const dragDepth = ref(0)

async function start() {
  failed.value = false
  await session.load(true)
  if (session.status === 'guest') {
    window.location.assign(`/accounts/login/?next=${encodeURIComponent(route.fullPath)}`)
    return
  }
  if (session.status !== 'member') {
    failed.value = true
    return
  }
  try {
    await taxonomy.load()
    ready.value = true
    void workspace.refresh(true)
  } catch {
    failed.value = true
  }
}

function openSearch() {
  drawerOpen.value = false
  paletteOpen.value = true
}

/** Collection the user is looking at, used as the default for new uploads. */
const uploadCategory = () => route.name === 'app-collection' && route.params.id !== 'uncategorized' ? String(route.params.id) : null
const dropTarget = () => taxonomy.pathLabel(uploadCategory())

function chooseFiles() {
  if (session.canEdit) chooser.value?.click()
}
function onChosen(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) uploads.add(input.files, uploadCategory())
  input.value = ''
}

// Drop files anywhere in the workspace to upload them as new documents.
const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes('Files')
function onDragEnter(event: DragEvent) {
  if (!session.canEdit || !hasFiles(event)) return
  event.preventDefault()
  dragDepth.value++
}
function onDragOver(event: DragEvent) {
  if (session.canEdit && hasFiles(event)) event.preventDefault()
}
function onDragLeave(event: DragEvent) {
  if (session.canEdit && hasFiles(event)) dragDepth.value = Math.max(0, dragDepth.value - 1)
}
function onDrop(event: DragEvent) {
  if (!session.canEdit || !hasFiles(event)) return
  event.preventDefault()
  dragDepth.value = 0
  if (event.dataTransfer?.files.length) uploads.add(event.dataTransfer.files, uploadCategory())
}
const onDocumentsChanged = () => { void workspace.refresh(true) }

function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    if (ready.value) paletteOpen.value = !paletteOpen.value
  } else if (event.key === 'Escape' && drawerOpen.value) {
    drawerOpen.value = false
  }
}

watch(() => route.fullPath, () => {
  drawerOpen.value = false
  void workspace.refresh()
})

onMounted(() => {
  document.title = 'Knowledge Hub'
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('hub:documents-changed', onDocumentsChanged)
  void start()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('hub:documents-changed', onDocumentsChanged)
  detachTheme()
})
</script>

<template>
  <div class="hub-app shell" :class="{ 'drawer-open': drawerOpen }" @dragenter="onDragEnter" @dragover="onDragOver"
    @dragleave="onDragLeave" @drop="onDrop">
    <a class="skip" href="#app-main">跳至內容</a>
    <Toast position="bottom-right" />
    <ConfirmDialog :style="{ width: 'min(94vw, 28rem)' }" />

    <div v-if="!ready" class="boot" role="status">
      <template v-if="failed">
        <Message severity="error">無法載入工作區，請檢查連線後再試。</Message>
        <Button label="重新載入" outlined @click="start" />
      </template>
      <ProgressSpinner v-else aria-label="正在載入工作區" style="width: 2.5rem; height: 2.5rem" />
    </div>

    <template v-else>
      <header class="mobile-bar">
        <button type="button" class="mobile-toggle" aria-label="開啟導覽" aria-controls="app-sidebar"
          :aria-expanded="drawerOpen" @click="drawerOpen = true">
          <UiIcon name="menu" :size="20" />
        </button>
        <span class="mobile-brand">Knowledge Hub</span>
        <button type="button" class="mobile-toggle" aria-label="搜尋或執行指令" @click="openSearch">
          <UiIcon name="search" :size="20" />
        </button>
      </header>
      <div v-if="drawerOpen" class="scrim" aria-hidden="true" @click="drawerOpen = false" />
      <aside id="app-sidebar" class="sidebar-slot">
        <AppSidebar @search="openSearch" @manage-taxonomy="taxonomyOpen = true" @navigate="drawerOpen = false" />
      </aside>
      <main id="app-main" class="main" tabindex="-1">
        <RouterView @upload="chooseFiles" />
      </main>
      <TaxonomyDialog v-model:visible="taxonomyOpen" @changed="workspace.refresh(true)" />
      <CommandPalette v-model:open="paletteOpen" @upload="chooseFiles" @manage-taxonomy="taxonomyOpen = true" />
      <input ref="chooser" type="file" accept=".md,.html" multiple hidden @change="onChosen">
      <UploadTray />
      <div v-if="dragDepth > 0" class="drop" aria-hidden="true">
        <div class="drop-card">
          <UiIcon name="upload" :size="28" />
          <strong>放開即可上傳</strong>
          <span>每個檔案會建立一份新文件，放入「{{ dropTarget() }}」</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--ui-sidebar-width) minmax(0, 1fr);
  grid-template-rows: auto 1fr;
}
.skip {
  position: fixed; z-index: 100; top: .5rem; left: .5rem; padding: .55rem .85rem;
  border-radius: var(--ui-radius-md); background: var(--ui-bg-inverse); color: var(--ui-text-inverse);
  transform: translateY(calc(-100% - 1rem));
}
.skip:focus { transform: none; }
.boot { grid-column: 1 / -1; grid-row: 1 / -1; display: grid; place-content: center; justify-items: center; gap: var(--ui-space-4); padding: var(--ui-gutter); }
.mobile-bar { display: none; }
.sidebar-slot {
  grid-column: 1; grid-row: 1 / -1;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  border-right: 1px solid var(--ui-border);
}
.main { grid-column: 2; grid-row: 1 / -1; min-width: 0; background: var(--ui-bg-surface); outline: none; }
.scrim { display: none; }
.drop {
  position: fixed; inset: 0; z-index: 1050; display: grid; place-items: center; padding: var(--ui-space-5);
  background: rgb(29 78 216 / .12); border: 3px dashed var(--ui-accent); pointer-events: none;
}
.drop-card { display: grid; justify-items: center; gap: var(--ui-space-2); padding: var(--ui-space-6) var(--ui-space-7); border-radius: var(--ui-radius-lg); background: var(--ui-bg-surface); color: var(--ui-text-secondary); box-shadow: var(--ui-shadow-lg); text-align: center; }
.drop-card strong { color: var(--ui-text); font-size: var(--ui-text-lg); }

@media (max-width: 900px) {
  .shell { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto 1fr; }
  .mobile-bar {
    display: flex; align-items: center; gap: var(--ui-space-2); position: sticky; top: 0; z-index: 20;
    min-height: var(--ui-topbar-height); padding: 0 var(--ui-space-2); box-sizing: border-box;
    border-bottom: 1px solid var(--ui-border); background: var(--ui-bg-surface);
  }
  .mobile-brand { flex: 1; font-weight: 700; }
  .mobile-toggle {
    display: grid; place-items: center; width: var(--ui-target); height: var(--ui-target);
    border: 0; border-radius: var(--ui-radius-md); background: transparent; color: var(--ui-text-secondary); cursor: pointer;
  }
  .main { grid-column: 1; grid-row: 2; }
  .sidebar-slot {
    position: fixed; z-index: 40; inset: 0 auto 0 0; width: min(85vw, 18rem); height: 100%;
    transform: translateX(-100%); transition: transform .2s ease; visibility: hidden;
    box-shadow: var(--ui-shadow-lg);
  }
  .drawer-open .sidebar-slot { transform: none; visibility: visible; }
  .scrim { display: block; position: fixed; z-index: 30; inset: 0; background: rgb(16 24 40 / .4); }
}
@media (prefers-reduced-motion: reduce) {
  .sidebar-slot { transition: none; }
}
</style>
