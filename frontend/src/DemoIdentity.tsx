import { demoNames } from './demo-session'
import type { Workspace } from './workspace-state'
export default function DemoIdentity({ role, onSwitch, onSignOut }: { role: Workspace; onSwitch: () => void; onSignOut: () => void }) {
  return <section className="demo-identity" aria-label="Demo identity"><p className="eyebrow">DEMO IDENTITY</p><strong>{demoNames[role]}</strong><p>{role === 'buyer' ? 'Buyer' : 'Merchant'} <span>· no real authentication</span></p><div><button onClick={onSwitch}>Switch role</button><button onClick={onSignOut}>Sign out</button></div></section>
}
