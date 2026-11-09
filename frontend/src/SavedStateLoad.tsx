export default function SavedStateLoad({ title, busy, error, refresh }: { title: string; busy: boolean; error: string; refresh: () => void }) {
  return <section className="workspace" aria-busy={busy}>
    <div className="toolbar"><h2>{title}</h2><button disabled={busy} onClick={refresh}>Refresh saved data</button></div>
    {busy ? <p role="status">Loading saved data…</p> : <div className="notice error" role="alert"><strong>Saved data unavailable</strong><p>{error || 'The load did not complete.'}</p><p>This does not mean no data is saved. Refresh explicitly; do not recreate or regenerate records to work around this error.</p></div>}
  </section>
}
