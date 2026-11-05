import { createContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

export const WorkspaceReadContext = createContext<() => void>(() => {})

/** Preserve form state; disclose cross-workspace writes instead of silently reloading it. */
export default function WorkspaceFrame({ active, children }: { active: boolean; children: ReactNode }) {
  const [changed, setChanged] = useState(false)
  const frame = useRef<HTMLDivElement>(null)
  const read = useCallback(() => setChanged(false), [])
  useEffect(() => {
    const update = () => { if (!active) setChanged(true) }
    window.addEventListener('contextkey:changed', update)
    return () => window.removeEventListener('contextkey:changed', update)
  }, [active])
  return <WorkspaceReadContext.Provider value={read}><div className="workspace-host" hidden={!active} ref={frame}>
    {changed && <div className="notice attention workspace-refresh" role="status"><strong>Saved inputs changed in another task.</strong><p>This workspace keeps your current fields. Refresh its saved inputs before continuing; existing discard warnings still apply.</p><button onClick={() => frame.current?.querySelector<HTMLButtonElement>('.toolbar > button')?.click()}>Refresh saved inputs</button></div>}
    {children}
  </div></WorkspaceReadContext.Provider>
}
