import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'
import { createApp, h } from 'vue'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import './app.css'
import Profile from './Profile.vue'

const hubTheme = definePreset(Aura, {
  semantic: {
    primary: {
      50: '{blue.50}', 100: '{blue.100}', 200: '{blue.200}', 300: '{blue.300}',
      400: '{blue.400}', 500: '{blue.500}', 600: '{blue.600}', 700: '{blue.700}',
      800: '{blue.800}', 900: '{blue.900}', 950: '{blue.950}',
    },
    colorScheme: {
      light: { primary: { color: '{blue.700}', hoverColor: '{blue.800}', activeColor: '{blue.900}' } },
    },
  },
})

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
  .use(PrimeVue, { theme: { preset: hubTheme, options: { darkModeSelector: false } } })
  .use(router)
  .mount('#app')
