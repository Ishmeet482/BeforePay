// Pure offline projections and read scheduling; no API/provider requests.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'
const module = async name => {
  const source = await readFile(new URL(`../src/${name}.ts`, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
  return import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'))
}
const { row, corroboratedRows, merchantLabels } = await module('conditions')
const item = (source, changes = {}) => row({ origin: 'source_supported', claim: { name: 'Camera', quantity: 1, ambiguous: false, citations: [{ source_id: source, quotation: 'Camera quantity 1', page_number: null }], ...changes } })
const input = [item('s1'), item('s2')], before = JSON.stringify(input)
const combined = corroboratedRows('equipment', input)
assert.equal(combined.length, 1)
assert.deepEqual(combined[0].original.claim.citations.map(c => c.source_id), ['s1', 's2'])
assert.equal(JSON.stringify(input), before)
for (const change of [{ quantity: 2 }, { name: 'Tripod' }, { ambiguous: true }]) assert.equal(corroboratedRows('equipment', [item('s1'), item('s2', change)]).length, 2)
assert.equal(corroboratedRows('equipment', [item('s1'), item('s1')]).length, 2)
const correction = item('s2'); correction.original.origin = 'customer_entered'; correction.original.reason = 'Explicit correction'
assert.equal(corroboratedRows('equipment', [item('s1'), correction]).length, 2)
const invalid = item('s1'); invalid.quantity = 'invalid'
assert.equal(corroboratedRows('equipment', [invalid, item('s2')]).length, 2)
assert.equal(merchantLabels.pickup, 'Pickup option')
assert.equal(merchantLabels.amounts, 'Charge')
const { boundedRead } = await module('read-queue')
let active = 0, maximum = 0, calls = 0
const work = async () => { active++; maximum = Math.max(maximum, active); calls++; await new Promise(r => setTimeout(r, 15)); active--; return calls }
await Promise.all(Array.from({ length: 12 }, () => boundedRead(AbortSignal.timeout(1000), work)))
assert.equal(maximum, 2); assert.equal(calls, 12)
let release
const held = new Promise(r => { release = r })
const first = boundedRead(AbortSignal.timeout(1000), () => held)
const second = boundedRead(AbortSignal.timeout(1000), () => held)
const controller = new AbortController()
const queued = boundedRead(controller.signal, () => { throw Error('Aborted queued read ran') })
controller.abort(new DOMException('Cancelled', 'AbortError'))
await assert.rejects(queued, { name: 'AbortError' })
release(); await Promise.all([first, second])
let failures = 0
await assert.rejects(boundedRead(AbortSignal.timeout(1000), async () => { failures++; throw Error('Read failed') }), /Read failed/)
assert.equal(failures, 1) // No retry, and slot released for subsequent work.
assert.equal(await boundedRead(AbortSignal.timeout(1000), async () => 'recovered'), 'recovered')
console.log('Offline corroboration and read-queue checks passed; no API calls.')
