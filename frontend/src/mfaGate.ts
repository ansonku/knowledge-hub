// P25c: set when an admin API answers 403 with mfa_required (the site requires admins to use two-factor and this
// admin has not turned it on). The management centre then shows the "turn it on first" page.
import { ref } from 'vue'

export const mfaBlocked = ref(false)

export function noteMfaRequired(status: number, body: unknown) {
  if (status === 403 && body && typeof body === 'object' && (body as { mfa_required?: boolean }).mfa_required) mfaBlocked.value = true
}

/** The two-factor set-up page, coming back to `next` (a same-site path) afterwards. */
export const activateUrl = (next = window.location.pathname) => `/accounts/2fa/totp/activate/?next=${encodeURIComponent(next)}`
