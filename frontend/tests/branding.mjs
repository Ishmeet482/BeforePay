// Static branding coverage. No app startup, database or provider calls.
import { readFile, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const root = fileURLToPath(new URL('../../', import.meta.url))
let checks = 0
function assert(ok, message) { if (!ok) throw Error(message); console.log('PASS ' + message); checks++ }
const read = path => readFile(root + path, 'utf8')
const app = await read('frontend/src/App.tsx'), html = await read('frontend/index.html'), readme = await read('README.md')
assert(app.includes('BeforePay') && !app.includes('ContextKey'), 'frontend display name BeforePay')
assert(html.includes('<title>BeforePay | Know what you’re agreeing to, before you pay.</title>') && html.includes('content="BeforePay.'), 'page title and description carry new brand/tagline')
assert(readme.startsWith('# BeforePay\n') && readme.includes('Know what you’re agreeing to, before you pay.'), 'README display brand/tagline')
for (const file of await readdir(root + 'docs')) if (file.endsWith('.md')) {
  const s = await read('docs/' + file)
  assert(!s.replaceAll('ContextKey - Book with confidence.pdf', '').includes('ContextKey'), 'guide brand coverage: ' + file)
}
assert((await read('backend/app/main.py')).includes('title="BeforePay API"'), 'API documentation display title')
assert((await read('frontend/package.json')).includes('"name": "contextkey-frontend"') && (await read('backend/pyproject.toml')).includes('name = "contextkey-backend"'), 'technical distribution identifiers retained')
assert((await read('frontend/src/review-api.ts')).includes("'contextkey:changed'") && (await read('frontend/src/paypal-sdk.ts')).includes('data-contextkey-sandbox'), 'internal event and SDK marker retained')
assert((await read('backend/app/payments/provider.py')).includes('contextkey-{attempt.id}') && (await read('backend/app/payments/service.py')).includes('contextkey-{attempt.id}'), 'payment invoice creation/verification prefix retained')
assert((await read('compose.yaml')).includes('contextkey') && (await read('backend/app/core/config.py')).includes('/contextkey'), 'database/Docker compatibility names retained')
console.log(checks + ' static branding checks passed.')
