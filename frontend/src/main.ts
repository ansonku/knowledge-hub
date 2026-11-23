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
        { path: '', name: 'app-home', component: () => import('./app/HomePage.vue') },
        { path: 'library/', name: 'app-library', component: () => import('./app/LibraryPage.vue') },
        { path: 'recent/', name: 'app-recent', component: () => import('./app/RecentPage.vue') },
        { path: 'favorites/', name: 'app-favorites', component: () => import('./app/LibraryPage.vue'), meta: { preset: 'favorites' } },
        { path: 'published/', name: 'app-published', component: () => import('./app/LibraryPage.vue'), meta: { preset: 'published' } },
        // The redesigned trash lands in P2d; until then it opens the legacy page.
        { path: 'trash/', name: 'app-trash', redirect: '/library/trash/' },
        { path: 'collections/:id/', name: 'app-collection', component: () => import('./app/LibraryPage.vue') },
        { path: 'docs/:id/', name: 'app-document', component: () => import('./app/DocumentPage.vue') },
        { path: 'docs/:id/compare/', name: 'app-compare', component: () => import('./app/ComparePage.vue') },
        { path: ':pathMatch(.*)*', redirect: { name: 'app-home' } },
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
