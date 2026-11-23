import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import { createApp, h } from 'vue'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import Home from './Home.vue'
import Profile from './Profile.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/library/trash/', component: () => import('./Trash.vue') },
    { path: '/library/', component: () => import('./Library.vue') },
    { path: '/library/:id/versions/', name: 'version-history', component: () => import('./VersionHistory.vue') },
    { path: '/library/:id/', name: 'document-reader', component: () => import('./DocumentReader.vue') },
    { path: '/accounts/profile/', component: Profile },
    { path: '/accounts/manage/:id?', component: () => import('./ManageAccounts.vue') },
  ],
})

createApp({ render: () => h(RouterView) })
  .use(createPinia())
  .use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } })
  .use(router)
  .mount('#app')
