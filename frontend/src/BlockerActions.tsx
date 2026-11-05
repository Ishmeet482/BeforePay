import { createContext, useContext } from 'react'
import type { Snapshot, Step } from './booking-state'
import type { Workspace } from './workspace-state'
import { blockerAction, type BlockerScope, type Destination } from './blocker-actions'

export const BlockerContext = createContext<{ workspace: Workspace; step?: Step; snapshot: Snapshot | null; navigate: (to: Destination) => void; findingsSerial?: number; ruleRequest?: { serial: number; kind: 'agreement' | 'proposal'; workspace: Workspace } }>({ workspace: 'buyer', snapshot: null, navigate: () => {} })
export function BlockerList({ codes, scope = {} }: { codes: string[]; scope?: BlockerScope }) {
  const { workspace, snapshot, navigate } = useContext(BlockerContext)
  return <ul className="blocker-list">{[...new Set(codes)].map(code => {
    const action = blockerAction(code, workspace, snapshot, scope)
    return <li key={code}><p>{action.explanation}</p><small>{action.affected}</small>{action.destination && <button type="button" className="resolve-link" onClick={() => navigate(action.destination!)}>{action.label} →</button>}</li>
  })}</ul>
}
export function BlockerNext({ fallback, codes }: { fallback: React.ReactNode; codes: string[] }) {
  const { workspace, snapshot, navigate } = useContext(BlockerContext)
  const first = codes.map(code => blockerAction(code, workspace, snapshot)).sort((a, b) => a.priority - b.priority).find(a => a.destination)
  return first ? <><p>{first.explanation}</p><small>{first.affected}</small><button className="primary" onClick={() => navigate(first.destination!)}>{first.label} →</button></> : fallback
}
