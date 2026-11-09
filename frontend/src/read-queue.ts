// Bound this tab's saved-state fan-out to the existing two-connection backend
// pool. No retry, cache, mutation scheduling or cross-visitor data sharing.
let active = 0
const pending: Array<() => void> = []
export async function boundedRead<T>(signal: AbortSignal, work: () => Promise<T>): Promise<T> {
  const release = await new Promise<() => void>((resolve, reject) => {
    const abort = () => {
      const index = pending.indexOf(start)
      if (index >= 0) pending.splice(index, 1)
      reject(signal.reason)
    }
    const start = () => {
      signal.removeEventListener('abort', abort)
      if (signal.aborted) { reject(signal.reason); drain(); return }
      active++
      resolve(() => { active--; drain() })
    }
    if (signal.aborted) { reject(signal.reason); return }
    signal.addEventListener('abort', abort, { once: true })
    pending.push(start); drain()
  })
  try { return await work() } finally { release() }
}
function drain() { while (active < 2 && pending.length) pending.shift()!() }
