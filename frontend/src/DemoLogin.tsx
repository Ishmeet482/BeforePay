import { useEffect, useRef, useState } from 'react'
import type { Workspace } from './workspace-state'

const examples = {
  buyer: { username: 'buyer.demo', password: 'BuyerDemo123!' },
  merchant: { username: 'merchant.demo', password: 'MerchantDemo123!' },
}

/** Demo passwords are checked locally; only the isolated session is server-issued. */
export default function DemoLogin({ initialRole, onEnter, onDismiss, requiredRole, currentRole }: { requiredRole?: Workspace; currentRole?: Workspace | null; initialRole: Workspace; onEnter: (role: Workspace) => void | Promise<void>; onDismiss: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const password = useRef<HTMLInputElement>(null)
  const username = useRef<HTMLInputElement>(null)
  const [role, setRole] = useState<Workspace>(initialRole)
  const [shown, setShown] = useState(false)
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  const [error, setError] = useState('')
  const [invalid, setInvalid] = useState<'username' | 'password' | 'both' | null>(null)
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const node = dialog.current!
    node.showModal()
    node.querySelector<HTMLInputElement>('input:checked')?.focus()
    return () => {
      if (password.current) password.current.value = ''
      node.close()
      if (opener?.isConnected && opener.getClientRects().length) opener.focus({ preventScroll: true })
      else document.querySelector<HTMLButtonElement>('.login-entry, .dashboard-link')?.focus({ preventScroll: true })
    }
  }, [])
  function dismiss() { if (submitting.current) return; if (password.current) password.current.value = ''; onDismiss() }
  function select(next: Workspace) {
    setRole(next); setError(''); setInvalid(null); setShown(false)
    if (username.current) username.current.value = ''
    if (password.current) password.current.value = ''
  }
  function trapFocus(e: React.KeyboardEvent) {
    if (e.key !== 'Tab') return
    const fields = [...dialog.current!.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [href], [tabindex="0"]')].filter(el => el.getClientRects().length && (!(el instanceof HTMLInputElement) || el.type !== 'radio' || el.checked))
    if (!fields.length) return
    e.preventDefault()
    const index = fields.indexOf(document.activeElement as HTMLElement)
    fields[(index + (e.shiftKey ? -1 : 1) + fields.length) % fields.length].focus()
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (submitting.current) return
    const user = username.current!.value.trim(), pass = password.current!.value
    if (!user || !pass) {
      setError(!user ? 'Enter the demo username shown below.' : 'Enter the demo password shown below.')
      setInvalid(!user ? 'username' : 'password')
      if (!user) username.current!.focus(); else password.current!.focus()
      password.current!.value = ''; return
    }
    const valid = (!requiredRole || role === requiredRole) && user === examples[role].username && pass === examples[role].password
    password.current!.value = ''
    if (!valid) {
      setError(`Credentials do not match the ${role === 'buyer' ? 'Buyer' : 'Merchant'} demo. Use that role’s displayed demo credentials.`)
      setInvalid('both'); username.current!.focus(); return
    }
    setError(''); submitting.current = true; setBusy(true)
    try { await onEnter(role) } catch (e) { setError(e instanceof Error ? e.message : 'Could not start the demo session. Try explicit entry again.') }
    finally { submitting.current = false; setBusy(false); if (password.current) password.current.value = '' }
  }
  return <dialog className="demo-login" data-workspace={role} ref={dialog} aria-labelledby="demo-login-title" aria-describedby="demo-login-notice" onKeyDown={trapFocus} onCancel={e => { e.preventDefault(); dismiss() }} onClick={e => {
    if (e.target === e.currentTarget) { const r = e.currentTarget.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dismiss() }
  }}>
    <div className="demo-login-heading"><span className="brand-mark" aria-hidden="true">bp</span><button type="button" className="text-button" onClick={dismiss} aria-label="Close demo login">Close ×</button></div>
    <h2 id="demo-login-title">{requiredRole === "buyer" ? currentRole === "merchant" ? "Switch to Buyer to create a booking" : "Start a booking as Buyer" : "Your next step starts here."}</h2>
    <p id="demo-login-notice" className="demo-disclosure"><strong>Demo login—no real authentication. Use demo credentials only.</strong></p>
    <p className="hint">Bookings belong to an expiring, server-issued browser session. Buyer and Merchant are simulated views of that same workspace, not verified people. Signing out ends access; saved records are preserved.</p>
    {requiredRole === "buyer" && <p className="hint" id="booking-entry-note">{currentRole === "merchant" ? "Your Merchant demo remains active until you explicitly enter the Buyer demo. Unsaved work stays in this tab. " : ""}Creating a booking starts in Buyer demo. Merchant demo prepares proposals for existing bookings.</p>}
    <form onSubmit={submit} noValidate autoComplete="off">
      <fieldset className="demo-role-options"><legend>Choose a demo role</legend>{(['buyer','merchant'] as const).map(value => <label key={value} className={role === value ? 'selected' : ''}><input type="radio" name="demo-role" value={value} checked={role === value} disabled={!!requiredRole && value !== requiredRole} aria-describedby={requiredRole ? "booking-entry-note" : undefined} onChange={() => select(value)} /><span><strong>{value === 'buyer' ? 'Buyer' : 'Merchant'}</strong><small>{value === 'buyer' ? 'Review terms, compare and pay' : 'Prepare proposals and policy rules'}</small></span></label>)}</fieldset>
      <label htmlFor="demo-username">Username</label><input id="demo-username" ref={username} autoCapitalize="none" spellCheck={false} autoComplete="off" required maxLength={100} aria-invalid={invalid === 'username' || invalid === 'both' || undefined} aria-describedby={error ? 'demo-login-error demo-credentials' : 'demo-credentials'} onChange={() => { setError(''); setInvalid(null) }} />
      <div className="demo-password-label"><label htmlFor="demo-password">Password</label><button type="button" aria-controls="demo-password" aria-pressed={shown} onClick={() => setShown(v => !v)}>{shown ? 'Hide password' : 'Show password'}</button></div><input id="demo-password" ref={password} type={shown ? 'text' : 'password'} autoComplete="off" required maxLength={100} aria-invalid={invalid === 'password' || invalid === 'both' || undefined} aria-describedby={error ? 'demo-login-error demo-credentials' : 'demo-credentials'} onChange={() => { setError(''); setInvalid(null) }} />
      {error && <p id="demo-login-error" className="notice error" role="alert">{error}</p>}
      <button className="primary demo-submit" type="submit" disabled={busy}>{busy ? 'Opening isolated workspace…' : requiredRole === "buyer" ? "Continue to Create booking →" : `Enter ${role === "buyer" ? "Buyer" : "Merchant"} demo →`}</button>
    </form>
    <section className="demo-credentials" id="demo-credentials" aria-labelledby="demo-credentials-title"><h3 id="demo-credentials-title">Demo credentials</h3><dl>{(['buyer','merchant'] as const).map(value => <div key={value}><dt>{value === 'buyer' ? 'Buyer' : 'Merchant'}</dt><dd><code>{examples[value].username}</code><span aria-hidden="true"> / </span><code>{examples[value].password}</code></dd></div>)}</dl><p>Checked only in this browser. Passwords are cleared after submission or closing. Only the chosen demo role is kept for this tab.</p></section>
  </dialog>
}
