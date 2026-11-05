import type { Workspace } from './workspace-state'

// Public demo labels only. This key is neither a credential nor an access token.
export const DEMO_ROLE_KEY = 'beforepay:demo-role'
export const demoNames = { buyer: 'Buyer Demo', merchant: 'Merchant Demo' }
export function readDemoRole(): Workspace | null {
  try {
    const role = sessionStorage.getItem(DEMO_ROLE_KEY)
    return role === 'buyer' || role === 'merchant' ? role : null
  } catch { return null }
}
export function retainDemoRole(role: Workspace | null): boolean {
  try {
    if (role) sessionStorage.setItem(DEMO_ROLE_KEY, role)
    else sessionStorage.removeItem(DEMO_ROLE_KEY)
    return true
  } catch { return false }
}
