import '@fontsource-variable/inter'
import '@fontsource-variable/noto-sans-tc'
import '@fontsource-variable/jetbrains-mono'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ConfirmationService from 'primevue/confirmationservice'
import ToastService from 'primevue/toastservice'
import { createApp, h } from 'vue'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import './styles/tokens.css'
import './app.css'
import Profile from './Profile.vue'
import { themeOptions } from './theme'

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
    {
      path: '/app/',
      component: () => import('./app/AppLayout.vue'),
      children: [
        { path: '', redirect: { name: 'app-library' } },
        { path: 'library/', name: 'app-library', component: () => import('./app/LibraryPage.vue') },
        { path: 'collections/:id/', name: 'app-collection', component: () => import('./app/LibraryPage.vue') },
        // Until the new document page lands in P1c, documents open in the legacy reader.
        { path: 'docs/:id/', name: 'app-document', redirect: to => `/library/${String(to.params.id)}/` },
        { path: ':pathMatch(.*)*', redirect: { name: 'app-library' } },
      ],
    },
  ],
})

createApp({ render: () => h(RouterView) })
  .use(createPinia())
  .use(PrimeVue, { theme: themeOptions })
  .use(ToastService)
  .use(ConfirmationService)
  .use(router)
  .mount('#app')
