<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Select from 'primevue/select'
import { onMounted, ref } from 'vue'

type PublicationStatus = {
  title: string
  versions: { id: string; number: number }[]
  publication: { title: string; version__number: number } | null
}

const props = defineProps<{ id: string; csrf: string; format: 'html' | 'md' }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const status = ref<PublicationStatus>()
const version = ref<string>()
const confirmation = ref<'POST' | 'DELETE'>()
const busy = ref(false)
const error = ref('')
const endpoint = `/api/documents/${props.id}/publication/`

async function update(method: 'GET' | 'POST' | 'DELETE') {
  busy.value = true
  error.value = ''
  try {
    const response = await fetch(endpoint, {
      method, cache: 'no-store',
      headers: method === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRFToken': props.csrf },
      body: method === 'POST' ? JSON.stringify({ version: version.value, title: status.value?.title }) : undefined,
    })
    const data = response.status === 204 ? null : await response.json()
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : '無法更新公開設定。')
    if (data) {
      status.value = data
      version.value = version.value ?? data.versions[0]?.id
    } else if (status.value) {
      status.value.publication = null
    }
    confirmation.value = undefined
    if (method !== 'GET') emit('changed')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '無法讀取公開設定。'
  } finally {
    busy.value = false
  }
}

onMounted(() => void update('GET'))
</script>

<template>
  <Dialog :visible="true" modal header="文章公開設定" :style="{ width: 'min(94vw, 35rem)' }"
    @update:visible="value => { if (!value && !busy) emit('close') }">
    <Message v-if="error" severity="error">{{ error }}</Message>
    <p v-if="!status && busy" role="status">正在讀取公開設定…</p>
    <template v-if="status">
      <p v-if="status.publication">
        Public・v{{ status.publication.version__number }}・{{ status.publication.title }}
        <RouterLink :to="{ name: 'public-article', params: { id } }">開啟公開頁</RouterLink>
      </p>
      <p v-else>Private・僅登入成員可閱讀</p>
      <p>公開標題為「{{ status.title }}」。訪客可以從首頁閱讀你確認發布的版本。</p>
      <p v-if="format === 'html'">公開 HTML 會轉成靜態內容，保留文字與基本排版。</p>
      <label for="publication-version">發布版本</label>
      <Select v-model="version" input-id="publication-version" :disabled="busy || Boolean(confirmation)"
        :options="status.versions" :option-label="item => `v${item.number}`" option-value="id" />
      <RouterLink v-if="version" :to="{ name: 'document-reader', params: { id }, query: { version } }"
        target="_blank" rel="noopener" class="review-link">檢視選定版本（另開分頁）</RouterLink>
      <p v-if="confirmation === 'POST'" role="status">
        確認發布「{{ status.title }}」v{{ status.versions.find(item => item.id === version)?.number }}？
      </p>
      <p v-if="confirmation === 'DELETE'" role="status">確認下架？公開網址將立即失效。</p>
      <div class="publication-actions">
        <template v-if="confirmation">
          <Button :label="confirmation === 'POST' ? '確認發布' : '確認下架'" :loading="busy" @click="update(confirmation)" />
          <Button label="取消" text :disabled="busy" @click="confirmation = undefined" />
        </template>
        <template v-else>
          <Button label="發布選定版本" :disabled="busy || !version" @click="confirmation = 'POST'" />
          <Button v-if="status.publication" label="下架" severity="danger" outlined :disabled="busy" @click="confirmation = 'DELETE'" />
        </template>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
label { display: block; margin-bottom: .4rem; }
.review-link { display: inline-block; margin: .5rem; }
.publication-actions { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1rem; }
</style>
