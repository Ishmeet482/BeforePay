/** CSRF material lives in JS memory. The opaque session stays HttpOnly. */
type SessionDescription = { active: boolean; csrf_token: string; expires_at: string }
let current: SessionDescription | null = null
let pending: Promise<SessionDescription> | null = null
const endpoint = '/api/demo-sessions'
const expired = 'Demo session missing, expired or signed out. Unsaved inputs are retained. Enter the demo explicitly to start a new isolated workspace; previous saved bookings remain preserved.'

async function exchange(method: string, token?: string): Promise<SessionDescription | null> {
  const response = await fetch(endpoint, { method, credentials: 'same-origin', cache: 'no-store', headers: token ? { 'X-BeforePay-CSRF': token } : {}, signal: AbortSignal.timeout(20000) })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(response.status === 401 ? expired : typeof data?.detail?.message === 'string' ? data.detail.message : 'Could not establish or close the isolated demo session. Check backend availability and allowed origin settings; your inputs are retained.')
  return data
}
export function forgetServerSession() { current = null }
export async function csrfForRequest(): Promise<string> {
  if (current && Date.parse(current.expires_at) > Date.now()) return current.csrf_token
  pending ??= exchange('GET').then(data => {
    if (!data?.active || !/^[a-f0-9]{64}$/.test(data.csrf_token)) throw new Error(expired)
    current = data; return data
  }).finally(() => { pending = null })
  return (await pending).csrf_token
}
export async function enterServerSession(allowNew: () => boolean = () => true) {
  // Explicit login only. Switching reuses the active cookie and original TTL.
  try {
    const existing = await exchange('GET')
    if (existing?.active) { current = existing; return false }
  } catch (e) { if (!(e instanceof Error) || e.message !== expired) throw e }
  if (!allowNew()) throw new Error('New session cancelled. Your unsaved inputs remain in this tab.')
  const data = await exchange('POST')
  if (!data?.active || !/^[a-f0-9]{64}$/.test(data.csrf_token)) throw new Error(expired)
  current = data
  return true
}
export async function leaveServerSession() {
  let token: string | undefined
  try { token = await csrfForRequest() } catch { /* Expired cookies can be cleared. */ }
  await exchange('DELETE', token)
  current = null
}
