import type { Citation } from './review-api'
export type SupportingTerm = { term_id: string; side: 'agreement' | 'proposal'; text: string; origin: string; citations: Citation[] }
export type Suggestion = {
  id: string; fingerprint: string; comparison_id: string; comparison_fingerprint: string
  proposal_id: string; proposal_fingerprint: string; category: string
  stale: boolean; stale_reasons: string[]; created_at: string
  output: { status: 'suggested' | 'needs_more_information'; question: string | null; explanation: string }
  supporting_terms: SupportingTerm[]
}
