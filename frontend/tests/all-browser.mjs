// Each existing feature suite owns a fresh tab. No shared injected scripts/storage.
import { readdir } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
const cdp = process.env.CDP_URL || 'http://127.0.0.1:9228'
const origin = process.env.FRONTEND_URL || 'http://127.0.0.1:5187'
if (!['127.0.0.1', 'localhost'].includes(new URL(cdp).hostname) || !['127.0.0.1', 'localhost'].includes(new URL(origin).hostname)) throw Error('Use local isolated QA services only')
const available = (await readdir(new URL('.', import.meta.url))).filter(file => file.endsWith('.browser.mjs')).sort()
const suites = process.argv.length > 2 ? process.argv.slice(2) : available
if (suites.some(suite => !available.includes(suite))) throw Error('Unknown browser feature suite')
for (const suite of suites) {
  const response = await fetch(`${cdp}/json/new?about:blank`, { method: 'PUT' })
  if (!response.ok) throw Error('Could not create isolated QA tab')
  const target = await response.json()
  try {
    console.log(`\nRunning ${suite}`)
    const exitCode = await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [fileURLToPath(new URL(suite, import.meta.url))], { stdio: 'inherit', env: { ...process.env, CDP_URL: cdp, FRONTEND_URL: origin, CDP_TARGET_ID: target.id } })
      const timeout = setTimeout(() => child.kill(), 180000)
      child.on('error', error => { clearTimeout(timeout); reject(error) })
      child.on('exit', code => { clearTimeout(timeout); resolve(code) })
    })
    if (exitCode !== 0) throw Error(`${suite} failed (${exitCode}); remaining suites not run`)
  } finally { await fetch(`${cdp}/json/close/${target.id}`) }
}
console.log(`${suites.length} browser feature suites passed; synthetic fixtures only.`)
