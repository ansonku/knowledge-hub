import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { createApp, h } from 'vue'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import Home from './Home.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', component: Home }],
})

createApp({ render: () => h(RouterView) })
  .use(createPinia())
  .use(PrimeVue, { unstyled: true })
  .use(router)
  .mount('#app')
