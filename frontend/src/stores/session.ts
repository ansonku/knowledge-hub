import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, isAuthError, setCsrfToken } from '../api'

export type Role = 'admin' | 'editor' | 'viewer'
export type Account = {
  id: string
  username: string
  email: string
  display_name: string
  role: Role
}
type MeResponse = Account & { csrf_token: string }

// Visibility helpers only; the backend enforces every permission on each request.
export const useSession = defineStore('session', () => {
  const account = ref<Account>()
  const status = ref<'idle' | 'loading' | 'member' | 'guest' | 'error'>('idle')
  let pending: Promise<void> | undefined

  const role = computed(() => account.value?.role)
  const isAdmin = computed(() => role.value === 'admin')
  const canEdit = computed(() => role.value === 'admin' || role.value === 'editor')
  const displayName = computed(() => account.value?.display_name || account.value?.username || '')

  function load(force = false) {
    if (pending && !force) return pending
    status.value = 'loading'
    pending = api<MeResponse>('/api/auth/me')
      .then(({ csrf_token, ...me }) => {
        setCsrfToken(csrf_token)
        account.value = me
        status.value = 'member'
      })
      .catch(error => {
        account.value = undefined
        status.value = isAuthError(error) ? 'guest' : 'error'
        pending = undefined
      })
    return pending
  }

  return { account, status, role, isAdmin, canEdit, displayName, load }
})
