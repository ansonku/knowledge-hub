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
import './styles/search.css'
import { themeOptions } from './theme'

const router = createRouter({
  history: createWebHistory(),
  // Only the public home scrolls to a hash (collection links jump to the article list);
  // every other route keeps the browser's position, as before.
  scrollBehavior: to => (to.name === 'site-home' && to.hash ? { el: to.hash, top: 80, behavior: 'smooth' } : false),
  routes: [
    {
      path: '/articles/',
      component: () => import('./site/PublicLayout.vue'),
      children: [
        { path: '', name: 'site-home', component: () => import('./site/SiteHome.vue') },
        { path: ':id/', name: 'public-article', component: () => import('./site/SiteArticle.vue') },
      ],
    },
    // Member reading portal: the public portal's layout over every readable document (login required).
    {
      path: '/read/',
      component: () => import('./site/PublicLayout.vue'),
      meta: { portal: 'member' },
      children: [
        { path: '', name: 'read-home', component: () => import('./site/SiteHome.vue') },
        { path: ':id/', name: 'read-article', component: () => import('./site/SiteArticle.vue') },
      ],
    },
    // Django sends admins back here after re-authentication; member management lives in the workspace.
    {
      path: '/accounts/manage/:id?',
      redirect: to => typeof to.params.id === 'string' && to.params.id
        ? { name: 'app-member', params: { id: to.params.id } } : { name: 'app-members' },
    },
    {
      path: '/app/',
      component: () => import('./app/AppLayout.vue'),
      children: [
        { path: '', name: 'app-home', component: () => import('./app/HomePage.vue') },
        { path: 'library/', name: 'app-library', component: () => import('./app/LibraryPage.vue') },
        { path: 'recent/', name: 'app-recent', component: () => import('./app/LibraryPage.vue'), meta: { preset: 'recent' } },
        { path: 'favorites/', name: 'app-favorites', component: () => import('./app/LibraryPage.vue'), meta: { preset: 'favorites' } },
        { path: 'published/', name: 'app-published', component: () => import('./app/LibraryPage.vue'), meta: { preset: 'published' } },
        { path: 'trash/', name: 'app-trash', component: () => import('./app/TrashPage.vue') },
        { path: 'collections/:id/', name: 'app-collection', component: () => import('./app/LibraryPage.vue') },
        { path: 'docs/:id/', name: 'app-document', component: () => import('./app/DocumentPage.vue') },
        { path: 'docs/:id/compare/', name: 'app-compare', component: () => import('./app/ComparePage.vue') },
        { path: 'settings/', name: 'app-settings', component: () => import('./app/SettingsPage.vue') },
        { path: 'admin/taxonomy/', name: 'app-taxonomy', component: () => import('./app/admin/TaxonomyPage.vue') },
        { path: 'admin/public/', name: 'app-public-overview', component: () => import('./app/admin/PublicOverviewPage.vue') },
        { path: 'admin/system/', name: 'app-system', component: () => import('./app/admin/SystemPage.vue') },
        { path: 'admin/audit/', name: 'app-audit', component: () => import('./app/admin/AuditPage.vue') },
        { path: 'admin/members/', name: 'app-members', component: () => import('./app/admin/MembersPage.vue') },
        { path: 'admin/members/:id/', name: 'app-member', component: () => import('./app/admin/MemberPage.vue') },
        { path: ':pathMatch(.*)*', redirect: { name: 'app-home' } },
      ],
    },
    // `/` is answered by Django (members → /app/, visitors → /articles/); any other unknown
    // path that Nginx hands to the SPA lands in the workspace, which sends visitors to log in.
    { path: '/:pathMatch(.*)*', redirect: '/app/' },
  ],
})

createApp({ render: () => h(RouterView) })
  .use(createPinia())
  .use(PrimeVue, { theme: themeOptions })
  .use(ToastService)
  .use(ConfirmationService)
  .use(router)
  .mount('#app')
