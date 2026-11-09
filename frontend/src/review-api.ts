import { csrfForRequest, forgetServerSession } from './server-session'
import { boundedRead } from './read-queue'

export const categories = ['equipment', 'pickup', 'return_time', 'currency', 'amounts', 'deposit_conditions', 'cancellation_conditions', 'included_items'] as const
export type Category = typeof categories[number]
export const kinds = ['rental_total', 'deposit', 'total_payable', 'tax', 'delivery', 'other'] as const
export type MoneyKind = typeof kinds[number]
export type Citation = { source_id: string; quotation: string; page_number: number | null }
export type Claim = {
  ambiguous: boolean; citations: Citation[]; name?: string; quantity?: number | null
  value?: string | { local_datetime: string | null; timezone: string | null }
  kind?: MoneyKind; label?: string; amount?: string; currency?: string | null
}
export type Entry = { origin: 'source_supported' | 'customer_entered'; claim: Claim; reason?: string }
export type Agreement = {
  id: string; draft_id: string; version: number; fingerprint: string; created_at: string
  content: { extraction: Record<Category, Entry[]>; explicit_none_categories: string[] }
  audit: { customer_label: string; review_reason?: string; kind: string; changes: unknown[] }
}
export type Draft = { id: string; version: number }
export type Booking = { id: string; title: string }
export type Source = { created_at: string; id: string; source_type: string; medium: string; filename: string | null; original_text: string; pages: { page_number: number; original_text: string }[] }
export type ReviewState = {
  agreement_id: string | null; fingerprint: string | null; source_ids: string[]; latest_draft_id: string | null
  blockers: string[]; confirmation_current: boolean; requires_review: boolean
  confirmation: { customer_label: string; created_at: string } | null
}
export class ApiError extends Error {
  constructor(public status: number, message: string, public serverMessage?: string) { super(message) }
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const signal = options.signal ?? AbortSignal.timeout(95000)
  const work = () => performRequest<T>(path, { ...options, signal })
  return !options.method || ['GET', 'HEAD'].includes(options.method.toUpperCase()) ? boundedRead(signal, work) : work()
}
async function performRequest<T>(path: string, options: RequestInit): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase())) headers.set('X-BeforePay-CSRF', await csrfForRequest())
  // Multipart boundaries belong to the browser. JSON remains the default for
  // existing callers, including all review and payment endpoints.
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', cache: 'no-store', headers, signal: options.signal ?? AbortSignal.timeout(95000) })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) forgetServerSession()
    const detail = data?.detail
    const message = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map((e: { loc: (string | number)[]; msg: string }) => `${e.loc.join('.')}: ${e.msg}`).join('; ')
      : [detail?.code, ...(detail?.blockers ?? [])].filter(Boolean).join(': ')
    const demoNotice = typeof detail?.code === 'string' && (detail.code.startsWith('demo_') || detail.code === 'public_demo_payment_disabled')
    throw new ApiError(response.status, demoNotice && typeof detail.message === 'string' ? detail.message : message || `Request failed (${response.status}).`, typeof detail?.message === 'string' ? detail.message : undefined)
  }
  if (options.method && options.method !== 'GET') window.dispatchEvent(new Event('contextkey:changed'))
  return data as T
}
export async function allPages<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = []
  for (let offset = 0; ; offset += 100) {
    const page = await request<T[]>(`${path}?limit=100&offset=${offset}`, { signal })
    items.push(...page)
    if (page.length < 100) return items
  }
}
export const post = <T,>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) })
