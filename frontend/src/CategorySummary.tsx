import type { Category } from './review-api'
import { claim, titles, type Row } from './conditions'
import { amountNames, describeClaim, EvidenceButton, money } from './product-ui'

function Evidence({ row, category }: { row: Row; category: Category }) {
  return row.original?.claim.citations.length
    ? <EvidenceButton title={titles[category]} citations={row.original.claim.citations} />
    : <small>{row.original?.origin === 'customer_entered' ? 'Customer-entered · no source citation' : 'No source citation'}</small>
}
function RowNotes({ row }: { row: Row }) {
  return <>{row.ambiguous && <strong className="field-error row-note">Needs clarification</strong>}{row.original?.reason && <small className="row-note">Correction reason: {row.original.reason}</small>}</>
}
function summary(category: Category, row: Row) {
  try { return describeClaim({ ...claim(category, row), citations: [] }) }
  catch { return 'Editing — check the fields below' }
}
function amount(row: Row) {
  if (row.amount && row.currency) return money(row.amount, row.currency)
  if (row.amount) return `${row.amount} · currency not specified`
  if (row.currency) return `${row.currency} · amount not specified`
  return 'Not specified'
}
/** Read-only presentation of current form values. No arithmetic, approval or persistence. */
export default function CategorySummary({ category, rows, noItems }: { category: Category; rows: Row[]; noItems: boolean }) {
  if (category === 'equipment' || category === 'included_items') return <div className="term-summary"><table className="data-table term-table item-table"><caption className="sr-only">{titles[category]} — item quantities and supporting evidence</caption><colgroup><col /><col className="quantity-col" /><col className="evidence-col" /></colgroup><thead><tr><th scope="col">Item</th><th scope="col" className="numeric">Quantity</th><th scope="col" className="table-actions">Evidence</th></tr></thead><tbody>{rows.length ? rows.map(row => <tr key={row.key}><th scope="row"><span className="original-wording">{row.name || 'Not specified'}</span><RowNotes row={row} /></th><td className="numeric">{row.quantity || 'Not specified'}</td><td className="table-actions"><Evidence row={row} category={category} /></td></tr>) : <tr><td colSpan={3} className="empty-value">{category === 'included_items' && noItems ? 'Explicitly no included items' : 'Not specified'}</td></tr>}</tbody></table></div>
  if (category === 'amounts') return <div className="term-summary"><table className="data-table term-table amount-table"><caption className="sr-only">Stated rental fee, deposit and inclusive total; no amounts calculated</caption><colgroup><col /><col className="amount-col" /><col className="evidence-col" /></colgroup><thead><tr><th scope="col">Charge</th><th scope="col" className="numeric">Amount / currency</th><th scope="col" className="table-actions">Evidence</th></tr></thead><tbody>{rows.length ? rows.map(row => <tr key={row.key} className={row.kind === 'total_payable' ? 'total-row' : undefined}><th scope="row">{amountNames[row.kind] || row.kind || 'Not specified'}{row.name && row.name !== amountNames[row.kind] && <small className="original-wording">{row.name}</small>}<RowNotes row={row} /></th><td className="numeric"><span className="money-value">{amount(row)}</span></td><td className="table-actions"><Evidence row={row} category={category} /></td></tr>) : <tr><td colSpan={3} className="empty-value">Not specified</td></tr>}</tbody></table></div>
  return <div className={`term-summary ${category.includes('conditions') ? 'policy-summary' : 'value-summary'}`}>{rows.length ? rows.map(row => <div className="summary-line" key={row.key}><div><p className="original-wording">{summary(category, row)}</p><RowNotes row={row} /></div><div className="summary-evidence"><Evidence row={row} category={category} /></div></div>) : <p className="empty-value">Not specified</p>}</div>
}
