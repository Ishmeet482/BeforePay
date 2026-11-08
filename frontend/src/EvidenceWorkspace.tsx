import CategorySummary from './CategorySummary'
import { WorkspaceReadContext } from './WorkspaceFrame'
import { useContext, useEffect, useRef, useState } from 'react'
import { allPages, ApiError, request, type Agreement, type Draft, type ReviewState, type Source } from './review-api'
import { friendlyError } from './conditions'
import TechnicalDetails from './TechnicalDetails'
import { Action, humanTime, TaskIntro } from './product-ui'
import { row, titles } from './conditions'
import type { Category, Claim } from './review-api'

type Summary = Pick<Source, 'id' | 'source_type' | 'medium' | 'filename'> & { created_at: string }
type SavedDraft = Draft & { created_at: string; input_source_ids: string[]; content: { needs_clarification: boolean; extraction?: Partial<Record<Category, Claim[]>> } }
const MAX_TEXT = 100000
const MAX_FILE = 5 * 1024 * 1024
const MAX_SOURCES = 20

export function intakeError(error: unknown): string {
  if (!(error instanceof Error)) return 'Request failed. Refresh saved sources and drafts before trying again.'
  if (error.name === 'AbortError' || error.name === 'TimeoutError') return 'No response received. The request may still finish. Refresh saved sources and drafts before retrying.'
  if (error instanceof TypeError) return 'Could not reach the backend. Check your connection and server, then refresh saved sources and drafts before retrying.'
  if (error instanceof ApiError) {
    const code = error.message.split(':')[0]
    if (code.startsWith('demo_') || code === 'public_demo_payment_disabled') return error.serverMessage || error.message
    const actions: Record<string, string> = {
      pdf_ocr_required: 'Use a text-based PDF or run OCR before uploading, or paste the original text instead.',
      unreadable_pdf: 'The PDF could not be read. Export a fresh text-based PDF or paste its text.',
      encrypted_pdf: 'Upload an unencrypted PDF or paste the original text.',
      file_too_large: 'Choose a PDF no larger than 5 MiB.', too_many_pages: 'Choose a PDF with at most 100 pages.',
      text_too_long: 'Keep extracted PDF text within 100,000 characters.',
      unsupported_media_type: 'Choose a PDF document with a .pdf filename.', invalid_filename: 'Use a PDF filename without folder paths, up to 255 characters.',
      invalid_pdf_text: 'Export the PDF again or paste clean text without NUL characters.',
      ai_not_configured: 'AI extraction is not configured. Ask the project maintainer to configure backend Gemini settings.',
      ai_rate_limited: 'Gemini quota is exhausted or rate limited. Wait for quota reset; no retry or fallback was attempted.',
      ai_timeout: 'Gemini timed out. Refresh saved drafts before explicitly retrying.',
      ai_unavailable: 'Gemini is unavailable. Refresh saved drafts before explicitly retrying.',
      ai_invalid_output: 'The AI response failed validation. No draft was accepted. Check the source text before explicitly retrying.',
      ai_invalid_citation: 'The AI returned unsupported evidence references. No draft was accepted.',
      ai_unsupported_value: 'The AI returned a value not supported by its quotation. No draft was accepted.',
      ai_no_draft: 'Gemini did not complete a usable draft. Check saved drafts before explicitly retrying.',
      latest_booking_draft_required: 'A newer saved draft exists. Refresh before opening review.',
      draft_evidence_changed: 'The draft no longer matches its evidence. Refresh and review the saved sources.',
      draft_already_under_review: 'This draft is already under review. Refresh, then open the existing review.',
    }
    if (actions[code]) return [error.serverMessage && code.startsWith('pdf_') ? error.serverMessage : '', actions[code]].filter(Boolean).join(' ')
    if (error.status === 413) return `${error.message} Select fewer sources or reduce the upload/text size.`
  }
  return friendlyError(error.message)
}

export default function EvidenceWorkspace({ bookingId, onReview }: { bookingId: string; onReview: () => void }) {
  const markRead = useContext(WorkspaceReadContext)
  const base = `/bookings/${bookingId}`
  const [sources, setSources] = useState<Summary[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [draft, setDraft] = useState<SavedDraft | null>(null)
  const [reviewedDraft, setReviewedDraft] = useState<string | null>(null)
  const [hasAgreement, setHasAgreement] = useState(false)
  const [sourceType, setSourceType] = useState('quotation')
  const [mode, setMode] = useState<'text' | 'pdf'>('text')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [actor, setActor] = useState('')
  const [busy, setBusy] = useState('Loading saved sources and drafts…')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const mounted = useRef(true)
  const controller = useRef<AbortController | null>(null)
  const acting = useRef(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const textLength = Array.from(text).length
  const unsaved = text.length > 0 || file !== null

  async function load(signal?: AbortSignal) {
    const [saved, drafts, review] = await Promise.all([
      allPages<Summary>(`${base}/sources`, signal), request<SavedDraft[]>(`${base}/drafts?limit=1`, { signal }), request<ReviewState>(`${base}/review`, { signal }),
    ])
    const agreement = review.agreement_id ? await request<Agreement>(`${base}/agreements/${review.agreement_id}`, { signal }) : null
    if (!mounted.current || signal?.aborted) return
    setSources(saved); setDraft(drafts[0] ?? null); setReviewedDraft(agreement?.draft_id ?? null); setHasAgreement(!!agreement)
    setSelected(old => new Set([...old].filter(id => saved.some(s => s.id === id)))); markRead()
  }
  useEffect(() => {
    mounted.current = true; const c = new AbortController(); controller.current = c
    load(c.signal).catch(e => { if (!c.signal.aborted) setError(intakeError(e)) }).finally(() => { if (!c.signal.aborted) setBusy('') })
    return () => { mounted.current = false; controller.current?.abort() }
    // Workspace is keyed by booking; in-flight responses cannot update another booking.
  }, [])
  useEffect(() => {
    if (!unsaved && !busy) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn)
  }, [unsaved, busy])

  async function act(label: string, work: (signal: AbortSignal) => Promise<void>) {
    if (acting.current) return
    acting.current = true; setBusy(label); setError(''); setMessage('')
    const c = new AbortController(); controller.current = c
    try { await work(AbortSignal.any([c.signal, AbortSignal.timeout(90000)])) }
    catch (e) { if (mounted.current) setError(intakeError(e)) }
    finally { acting.current = false; if (mounted.current) setBusy('') }
  }
  async function saveSource(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
    if (mode === 'text' && (!text.trim() || textLength > MAX_TEXT || text.includes('\0'))) { setError('Paste nonblank original text without NUL characters, up to 100,000 characters.'); return }
    if (mode === 'pdf' && (!file || file.size === 0 || file.size > MAX_FILE || !file.name.toLowerCase().endsWith('.pdf') || file.name.length > 255 || (file.type && file.type !== 'application/pdf'))) { setError('Choose a nonempty PDF up to 5 MiB with a .pdf filename of at most 255 characters.'); return }
    await act(mode === 'pdf' ? 'Uploading and validating PDF…' : 'Saving original text…', async signal => {
      let saved: Source
      if (mode === 'text') saved = await request<Source>(`${base}/sources/text`, { method: 'POST', body: JSON.stringify({ source_type: sourceType, original_text: text }), signal })
      else {
        const form = new FormData(); form.append('source_type', sourceType)
        const pdf = file!.type ? file! : new File([file!], file!.name, { type: 'application/pdf' })
        form.append('file', pdf)
        saved = await request<Source>(`${base}/sources/pdf`, { method: 'POST', body: form, signal })
      }
      if (!mounted.current) return
      if (mode === 'text') setText(''); else { setFile(null); if (fileInput.current) fileInput.current.value = '' }
      // A successful response proves persistence even if a later refresh fails.
      setSources(old => [...old.filter(s => s.id !== saved.id), saved])
      setMessage('Source saved. Select it below to include it in an AI draft. Nothing has been generated or confirmed.')
      await load(signal)
    })
  }
  async function generate() {
    if (busy || selected.size === 0 || selected.size > MAX_SOURCES) return
    await act('Generating and validating AI draft… This can take about a minute.', async signal => {
      const saved = await request<SavedDraft>(`${base}/drafts`, { method: 'POST', body: JSON.stringify({ source_ids: [...selected] }), signal })
      if (!mounted.current) return
      setDraft(saved)
      setMessage(`Draft ${saved.version} saved, unconfirmed.${saved.content.needs_clarification ? ' Missing or conflicting terms need review.' : ' Review the terms before confirming.'}`)
    })
  }
  async function loadCameraExample(sourceType: 'quotation' | 'message') {
    if (busy || (unsaved && !window.confirm('Replace unsaved source input with a labelled synthetic camera example? Nothing will be saved automatically.'))) return
    await act('Loading synthetic example into the form…', async signal => {
      const templates = await request<{ key: string; original_text: string }[]>('/demo-templates', { signal })
      const sample = templates.find(t => t.key === (sourceType === 'quotation' ? 'camera-quotation' : 'camera-message'))
      if (!sample?.original_text) throw new Error('Synthetic example unavailable. Paste your own original source instead.')
      setMode('text'); setSourceType(sourceType); setText(sample.original_text); setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      setMessage('Synthetic camera example loaded into the form only. Review it, then explicitly save if wanted. No evidence saved or AI called.')
    })
  }
  async function openReview() {
    if (!draft || busy) return
    // Source inputs remain mounted when opening agreement review.
    await act('Opening saved draft for review…', async signal => {
      const state = await request<ReviewState>(`${base}/review`, { signal })
      if (state.latest_draft_id !== draft.id) throw new Error('A newer saved draft exists. Refresh before opening review.')
      const existing = state.agreement_id ? await request<Agreement>(`${base}/agreements/${state.agreement_id}`, { signal }) : null
      if (existing?.draft_id !== draft.id) {
        if (!actor.trim()) throw new Error('Enter your name / reviewer label to open a new review version.')
        await request<Agreement>(`${base}/agreements/from-draft`, { method: 'POST', body: JSON.stringify({ draft_id: draft.id, customer_label: actor }), signal })
      }
      if (mounted.current) onReview()
    })
  }
  return <section className="workspace" aria-busy={!!busy}>
    <div className="toolbar"><div><h2>Sources & draft</h2><p>Keep the original evidence beside your unconfirmed draft.</p></div><button disabled={!!busy} onClick={() => void act('Refreshing saved sources and drafts…', load)}>Refresh saved</button></div>
    {busy && <p role="status">{busy}</p>}{error && <p className="notice error" role="alert">{error}</p>}{message && <p className="notice success" role="status">{message}</p>}
    <TaskIntro owner="Buyer evidence" title="Original sources → unconfirmed AI draft → your review">Use the actual item names for any rental category. Save sources, select the evidence Gemini may read, then explicitly request a draft.</TaskIntro>
    {hasAgreement && <p className="notice">Adding evidence or generating another draft requires renewed review. Existing versions and receipt history are retained.</p>}
    <div className="source-layout"><section className="source-inbox"><h3><span className="sequence">1</span> Source inbox</h3><details className="source-intake" open={!sources.length || unsaved}><summary>Add quotation or message</summary>
    <section className="panel"><h3>Save original evidence</h3><form onSubmit={event => void saveSource(event)}>
      <fieldset disabled={!!busy}><div className="fields"><label>Source type<select value={sourceType} onChange={e => setSourceType(e.target.value)}><option value="quotation">Quotation</option><option value="message">Message</option></select></label><label>Input method<select value={mode} onChange={e => setMode(e.target.value as 'text' | 'pdf')}><option value="text">Paste original text</option><option value="pdf">Upload PDF</option></select></label></div>
        {mode === 'text' ? <><label>Original quotation or message<textarea rows={8} value={text} onChange={e => setText(e.target.value)} aria-invalid={textLength > MAX_TEXT || text.includes('\0')} placeholder="Paste the original wording. Spacing and line breaks are preserved." /></label><p className={textLength > MAX_TEXT ? 'field-error' : 'hint'}>{textLength.toLocaleString()} / 100,000 characters. Original text is saved unchanged.</p></> : <><label>Text-based PDF<input ref={fileInput} type="file" accept="application/pdf,.pdf" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label><p className="hint">Maximum 5 MiB, 100 pages and 100,000 extracted characters. Encrypted PDFs are unsupported; scanned/image-only PDFs require OCR first.</p></>}
        <Action className="primary" type="submit" disabled={!!busy || (mode === 'text' ? !text.trim() || textLength > MAX_TEXT || text.includes('\0') : !file)} reason={busy ? 'Wait for the current upload or request.' : mode === 'pdf' ? 'Choose a text-based PDF first.' : textLength > MAX_TEXT ? 'Reduce the text to 100,000 characters.' : text.includes('\0') ? 'Remove unsupported NUL characters.' : 'Paste the original quotation or message first.'}>Save source</Action>
      </fieldset></form></section>
    </details><details className="sample-tools source-examples"><summary>Optional synthetic camera example</summary><p>Authored demo sources, not your booking terms. Load into the form only; saving and AI generation stay separate.</p><div className="sample-buttons"><button type="button" disabled={!!busy} onClick={() => void loadCameraExample('quotation')}>Load synthetic quotation · form only</button><button type="button" disabled={!!busy} onClick={() => void loadCameraExample('message')}>Load synthetic message · form only</button></div></details><section className="panel source-selection"><h3>Select sources for your draft</h3><p>Checked sources are sent together only when you click Generate AI draft. Choose what Gemini may read. Source acknowledgement happens separately in agreement review.</p>
      {!sources.length && !busy && <p>No saved sources yet. Paste text or upload a PDF above.</p>}
      {sources.map((s, index) => <SavedSource key={s.id} bookingId={bookingId} source={s} index={index} checked={selected.has(s.id)} disabled={!!busy} onToggle={checked => { setSelected(old => { const next = new Set(old); if (checked) next.add(s.id); else next.delete(s.id); return next }); setMessage('') }} />)}
      <p className={selected.size > MAX_SOURCES ? 'field-error' : 'hint'}>{selected.size} / 20 sources selected. Combined extraction input limit: 200,000 characters.</p>
    </section>
    </section><section className="draft-workspace"><section className="panel ai-panel"><p className="eyebrow ai-label">✦ GEMINI ASSISTANCE · EXPLICIT REQUEST</p><h3><span className="sequence">2</span> Generate a draft</h3><p>Only this action sends selected sources to Gemini. Uses your configured quota; never generates on upload or page load.</p><Action className="primary ai-button" disabled={!!busy || selected.size === 0 || selected.size > MAX_SOURCES} resolve={!busy ? { label: 'Choose saved sources', selector: '.source-selection' } : undefined} reason={busy ? 'Wait for the current request.' : selected.size > MAX_SOURCES ? 'Select at most 20 sources.' : 'Select at least one saved source.'} onClick={() => void generate()}>Generate AI draft</Action><p className="hint">AI drafts remain unconfirmed. Unknowns and conflicting terms must be reviewed; no terms are automatically approved.</p></section>
    <section className="panel"><h3><span className="sequence">3</span> Review extracted terms</h3>{draft ? <><p>Latest saved draft: version {draft.version} · {humanTime(draft.created_at)}{draft.content.needs_clarification ? ' · needs review' : ''}</p><p className="hint">Uses {draft.input_source_ids.length} saved source(s).{sources.some(s => !draft.input_source_ids.includes(s.id)) ? ' Some current sources were not included; review will require acknowledging all current evidence.' : ''}</p>{draft.content.extraction && <details className="draft-summary" open={!hasAgreement}><summary>Read extracted terms · unconfirmed</summary>{Object.entries(draft.content.extraction).map(([category, claims]) => <section className="panel" key={category}><h4>{titles[category as Category]}</h4><CategorySummary category={category as Category} rows={(claims || []).map((c, index) => ({ ...row({ origin: 'source_supported', claim: c }), key: `${draft.id}-${category}-${index}` }))} noItems={false} /></section>)}</details>}<TechnicalDetails data={{ draft_id: draft.id, input_source_ids: draft.input_source_ids }} />{reviewedDraft !== draft.id && <label>Your name / reviewer label<input value={actor} maxLength={100} onChange={e => setActor(e.target.value)} disabled={!!busy} /></label>}<Action className="primary" disabled={!!busy || (reviewedDraft !== draft.id && !actor.trim())} reason={busy ? 'Wait for the current request.' : 'Enter your reviewer name to open this saved draft.'} onClick={() => void openReview()}>Open Agreement review</Action><p className="hint">Open an unconfirmed review or return to the existing version. Saving and confirmation remain separate.</p></> : <p>No saved draft yet. Select evidence and explicitly generate one above.</p>}</section>
    </section></div>
  </section>
}

function SavedSource({ bookingId, source, index, checked, disabled, onToggle }: { bookingId: string; source: Summary; index: number; checked: boolean; disabled: boolean; onToggle: (checked: boolean) => void }) {
  const [open, setOpen] = useState(false)
  return <article className="saved-source"><label className="check"><input type="checkbox" checked={checked} disabled={disabled} onChange={e => onToggle(e.target.checked)} />Use {source.filename || `${source.source_type} ${index + 1}`} for AI draft</label><p className="hint">{source.source_type} · {source.medium === 'pdf' ? 'PDF' : 'Pasted text'} · {humanTime(source.created_at)}</p><details onToggle={e => setOpen(e.currentTarget.open)}><summary>Read saved source</summary>{open && <SourcePreview bookingId={bookingId} sourceId={source.id} />}</details><TechnicalDetails label="Source details" data={{ source_id: source.id }} /></article>
}
function SourcePreview({ bookingId, sourceId }: { bookingId: string; sourceId: string }) {
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const c = new AbortController(); setError('')
    request<Source>(`/bookings/${bookingId}/sources/${sourceId}`, { signal: c.signal }).then(setSource).catch(e => { if (!c.signal.aborted) setError(intakeError(e)) })
    return () => c.abort()
  }, [bookingId, sourceId, retry])
  if (error) return <div><p role="alert" className="error">{error}</p><button onClick={() => setRetry(n => n + 1)}>Retry reading source</button></div>
  if (!source) return <p role="status">Loading original source…</p>
  return source.pages.length ? <>{source.pages.map(p => <div key={p.page_number}><h4>Page {p.page_number}</h4><pre>{p.original_text}</pre></div>)}</> : <pre>{source.original_text}</pre>
}
