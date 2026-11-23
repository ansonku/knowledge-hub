import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import { createApp, h } from 'vue'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import './app.css'
import Profile from './Profile.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', alias: '/library/', name: 'library', component: () => import('./Library.vue') },
    { path: '/articles/:id/', name: 'public-article', component: () => import('./PublicArticle.vue') },
    { path: '/library/trash/', component: () => import('./Trash.vue') },
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
