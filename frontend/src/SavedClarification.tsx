import CorrectionReview from './CorrectionReview'
import { EvidenceButton, humanTime, Status } from './product-ui'
import TechnicalDetails from './TechnicalDetails'
import MerchantReplyThread from './MerchantReplyThread'
import type { Suggestion } from './clarification-types'
export default function SavedClarification({ item, bookingId, stale, merchant = false, refreshToken, onSaved }: { item: Suggestion; bookingId: string; stale: boolean; merchant?: boolean; refreshToken: number; onSaved?: () => void }) {
  return <article className="saved-clarification"><Status tone={stale ? 'attention' : 'neutral'}>{stale ? 'Historical / not current' : 'Current at last check · advisory'}</Status><p className="hint">Recorded {humanTime(item.created_at)}</p>
    {item.output.status === 'needs_more_information' ? <h4>Needs more information</h4> : <><h4>Question for the merchant</h4><p className="clarification-question">{item.output.question}</p></>}<p>{item.output.explanation}</p>
    {!!item.supporting_terms.length && <div className="clarification-support"><h4>Supporting saved terms</h4>{item.supporting_terms.map(term => <details key={term.term_id} open={merchant}><summary>{term.side === 'agreement' ? 'Buyer agreement' : 'Merchant proposal'} · open exact supporting term</summary><blockquote>{term.text}</blockquote><p className="hint">{term.origin === 'source_supported' ? 'Source-supported agreement term' : term.origin === 'merchant_entered' ? 'Merchant-entered saved term · no document citation' : 'Customer-entered term · no source citation'}</p>{term.citations.length > 0 && <EvidenceButton title="Original support for clarification" citations={term.citations} />}</details>)}</div>}
    <MerchantReplyThread bookingId={bookingId} suggestion={item} stale={stale} merchant={merchant} refreshToken={refreshToken} onSaved={onSaved} />
    {merchant && <CorrectionReview bookingId={bookingId} suggestionId={item.id} refreshToken={refreshToken} />}
    <TechnicalDetails label="Suggestion binding and stale reasons" data={{ suggestion_id: item.id, fingerprint: item.fingerprint, comparison_id: item.comparison_id, comparison_fingerprint: item.comparison_fingerprint, stale_reasons: item.stale_reasons }} />
  </article>
}
