import { fixture } from './fixtures/product-fixture.mjs'
// Entire product journey uses synthetic in-browser API fixtures. No backend proxy.
// Run with FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228.
import process from 'node:process'
import { writeFile, mkdir } from 'node:fs/promises'
const origin = process.env.FRONTEND_URL || 'http://127.0.0.1:5187'
const targets = await (await fetch(`${process.env.CDP_URL || 'http://127.0.0.1:9228'}/json`)).json()
const target = targets.find(t => t.type === 'page' && (!process.env.CDP_TARGET_ID || t.id === process.env.CDP_TARGET_ID))
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise(resolve => { ws.onopen = resolve })
let serial = 0
const pending = new Map(), errors = [], started = Date.now()
ws.onmessage = event => { const m = JSON.parse(event.data); if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p?.reject(new Error(m.error.message)) : p?.resolve(m.result) } else if (m.method === 'Runtime.exceptionThrown' && m.params.timestamp >= started) errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text) }
function send(method, params = {}) { return new Promise((resolve, reject) => { const id = ++serial; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); await send('Runtime.evaluate',{expression:'window.__enterDemoForRegression?.()',awaitPromise:true,returnByValue:true});return r.result.value }
async function until(expression) { for (let i = 0; i < 120; i++) { if (await evaluate(`Boolean(${expression})`)) return; await new Promise(r => setTimeout(r, 80)) } throw new Error('Timed out: ' + expression) }
let passes = 0, navigation = 0
function assert(ok, name) { if (!ok) throw new Error(name); passes++; console.log('PASS ' + name) }


const out = '/private/tmp/beforepay-workspaces'
async function settle() { await evaluate(`new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))`) }
async function navigate(scenario, workspace='buyer', direct=false) {
  await send('Page.navigate',{url:`${origin}/?case=${scenario}&workspaceqa=${++navigation}#${workspace==='merchant'?'merchant/':''}bookings${direct?'/b1':''}`})
  await until(direct?`document.querySelector('.next-action')`:`document.querySelector('.booking-row .state-label')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`)
  if(!direct){await evaluate(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`)}
  await settle()
}
async function tab(label){await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(label)})).click()`);await until(`document.querySelector('.workspace-host:not([hidden]) .workspace')?.getAttribute('aria-busy')==='false'||!!document.querySelector('.merchant-overview')||!!document.querySelector('.workspace-host:not([hidden]) [role=alert]')`);await settle()}
async function view(workspace){await evaluate(`document.querySelector('.workspace-view-switch button:nth-child(${workspace==='buyer'?1:2})').click()`);await until(`document.querySelector('.rail-caption').textContent.includes(${JSON.stringify(workspace.toUpperCase())})`);await settle()}
async function shot(name){await settle();await new Promise(r=>setTimeout(r,150));const r=await send('Page.captureScreenshot',{captureBeyondViewport:false});await mkdir(out,{recursive:true});await writeFile(`${out}/${name}.png`,Buffer.from(r.data,'base64'))}
async function passive(name){assert(await evaluate(`window.__writes.length===0&&window.__unexpected.length===0`),name+': no writes or unmocked reads');assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),name+': fits viewport')}
try {
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture})
 for(const [size,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]) {
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:size==='mobile'})
  await navigate('awaiting')
  await tab('Agreement');await evaluate(`document.querySelector('.section-editor').open=true;fill(document.querySelector('.section-editor input[inputmode=numeric]'),'9');fill(document.querySelector('.condition .reason textarea'),'Retained across workspaces')`)
  await view('merchant');await until(`document.querySelector('.merchant-overview')`)
  assert(await evaluate(`document.querySelector('.merchant-overview').textContent.includes('Buyer review needed')&&document.querySelector('.workspace-view-switch').textContent.includes('Prototype views—not authenticated accounts')`),size+': merchant overview explains buyer handoff and prototype identity')
  assert(await evaluate(`[...document.querySelectorAll('.tabs button')].map(b=>b.textContent).join('|').includes('Buyer reference')&&!document.querySelector('.tabs').textContent.includes('Sources & draft')`),size+': merchant navigation contains merchant tasks')
  await shot('merchant-overview-'+size);await passive('merchant overview '+size)
  await tab('Buyer reference')
  assert(await evaluate(`!document.querySelector('.buyer-reference input,.buyer-reference textarea')&&document.querySelector('.buyer-reference').textContent.includes('not currently confirmed')`),size+': read-only baseline never mislabels unconfirmed terms')
  await shot('buyer-reference-'+size);await passive('reference '+size)
  await view('buyer');assert(await evaluate(`document.querySelector('.section-editor input[inputmode=numeric]').value==='9'&&document.querySelector('.condition .reason textarea').value==='Retained across workspaces'`),size+': buyer correction and reason survive prototype switching')
  await navigate('ready','merchant',true)
  assert(await evaluate(`location.hash==='#merchant/bookings/b1'&&document.querySelector('.merchant-overview')&&document.querySelector('.booking-heading h1').textContent==='Cinema kit · November shoot'`),size+': direct merchant route reads same booking')
  await tab('Final proposal');await evaluate(`fill(field('Merchant name / provisional label'),'Retained merchant editor');fill(field('Reason / proposal note'),'Retained reason')`)
  await view('buyer');await tab('Compare booking');assert(await evaluate(`visible(document.querySelector('.buyer-comparison'))&&!visible(document.querySelector('.merchant-view'))`),size+': buyer navigation opens comparison review')
  await view('merchant');assert(await evaluate(`field('Merchant name / provisional label').value==='Retained merchant editor'&&field('Reason / proposal note').value==='Retained reason'`),size+': proposal editor survives workspace and task navigation')
  assert(await evaluate(`document.querySelector('.booking-heading').getBoundingClientRect().bottom<=document.querySelector('.workspace-host:not([hidden]) .toolbar').getBoundingClientRect().top`),size+': workspace title and task heading never overlap');await shot('merchant-proposal-'+size);await passive('proposal '+size)
  await tab('Merchant policy rules')
  assert(await evaluate(`field('Policy source version').value==='proposal'&&field('Policy source version').disabled&&!visible(document.querySelector('.cancellation-start'))&&document.querySelector('.rule-confirmation h3').textContent.includes('merchant')`),size+': merchant rules scoped to proposal; agreement approval remains separate')
  await evaluate(`fill(field('Your name / reviewer label'),'Retained merchant reviewer');fill(field('Reason for this rule version'),'Retained policy reason');fill(field('Cutoff hours'),'36')`)
  await view('buyer');await tab('Cancellation');assert(await evaluate(`field('Policy source version').value==='agreement'&&field('Your name / reviewer label').value===''`),size+': buyer calculator retains independent agreement-rule editor')
  await view('merchant');assert(await evaluate(`field('Your name / reviewer label').value==='Retained merchant reviewer'&&field('Cutoff hours').value==='36'`),size+': unsaved merchant rules survive switching')
  await shot('merchant-rules-'+size);await passive('policy '+size)
  await tab('Payment status');assert(await evaluate(`document.querySelector('.merchant-payment').textContent.includes('No payment recorded')&&!document.querySelector('.merchant-payment input')`),size+': merchant payment view read-only and unpaid explicit');await shot('merchant-payment-'+size);await passive('payment '+size)
  await navigate('uncertain','merchant');await tab('Payment status');assert(await evaluate(`document.querySelector('.merchant-payment').textContent.includes('capture uncertain')&&!document.querySelector('.merchant-payment').textContent.includes('Capture recorded · sandbox')`),size+': uncertain attempt never treated as captured');await passive('uncertain '+size)
  await navigate('paid','merchant');await tab('Payment status');assert(await evaluate(`document.querySelector('.merchant-payment').textContent.includes('USD 200.00')&&document.querySelector('.merchant-payment').textContent.includes('Capture recorded · sandbox')`),size+': same captured amount visible to merchant')
  await evaluate(`clickText('View receipt in Buyer workspace →')`);await until(`visible(document.querySelector('#payment-receipt'))`);assert(await evaluate(`location.hash==='#bookings/b1'&&document.querySelector('#payment-receipt').textContent.includes('CAPTURE_FIXTURE')`),size+': receipt handoff preserves booking and provider reference');await passive('receipt '+size)
  await send('Accessibility.enable');const ax=await send('Accessibility.getFullAXTree');assert(!ax.nodes.some(n=>!n.ignored&&['button','link','textbox','combobox'].includes(n.role?.value)&&!n.name?.value),size+': named interactive controls')
 }
 for(const [scenario,status] of [['merchantneeded','Merchant proposal needed'],['changed','Resolve booking differences'],['stale','Buyer review needed']]) {
  await navigate(scenario,'merchant',true);assert(await evaluate(`document.querySelector('.next-action').textContent.includes(${JSON.stringify(status)})`),scenario+': handoff derived from saved state');await passive(scenario)
 }
 await navigate('ready','merchant',true);await tab('Final proposal')
 await evaluate(`fill(field('Merchant name / provisional label'),'Synthetic shared editor');fill(field('Reason / proposal note'),'Explicit shared-version test');clickText('Save as new merchant version')`)
 await until(`window.__writes.length===1&&!document.querySelector('.workspace-host:not([hidden]) .workspace').matches('[aria-busy=true]')`)
 assert(await evaluate(`window.__writes[0].path==='/api/bookings/b1/merchant-bookings'&&window.__writes[0].body.expected_latest_id==='p1'`),'merchant revision uses existing booking and optimistic version guard')
 await view('buyer');await tab('Compare booking');assert(await evaluate(`document.querySelector('.version-meta').textContent.includes('Agreement version 1')&&document.querySelector('.merchant-editor select').value==='p2'`),'buyer sees same newly saved proposal; agreement remains original')
 await view('merchant');await tab('Buyer reference');assert(await evaluate(`document.querySelector('.buyer-reference').textContent.includes('Buyer-confirmed agreement · version 1')`),'proposal revision leaves buyer confirmation intact')
 await evaluate(`document.querySelector('.back-link').click()`);await until(`visible(document.querySelector('.bookings-page'))`);const merchantCount=await evaluate(`document.querySelectorAll('.booking-row').length`)
 await evaluate(`document.querySelector('.dashboard-sidebar .demo-identity button:first-child').click()`);await until(`visible(document.querySelector('.bookings-page'))&&location.hash==='#bookings'`);assert(await evaluate(`document.querySelectorAll('.booking-row').length===${merchantCount}&&document.querySelector('.booking-row').textContent.includes('Cinema kit')`),'Buyer and Merchant lists share booking count and title without duplication')
 await navigate('paid','merchant',true)
 await evaluate(`window.__baseFetch=window.fetch;window.fetch=async(i,o={})=>String(i).includes('/checkout/eligibility')?Response.json({detail:'Synthetic saved-state outage'},{status:503}):window.__baseFetch(i,o);window.dispatchEvent(new CustomEvent('contextkey:changed'))`)
 await until(`document.querySelector('.rail-next').textContent.includes('Saved state unavailable')`);await tab('Payment status')
 assert(await evaluate(`!document.querySelector('.merchant-payment')&&document.querySelector('.workspace-host:not([hidden]) [role=alert]').textContent.includes('Saved state unavailable')`),'saved-state outage hides previous payment summary and offers retry')
 // Explicit merchant rule creation/approval must target the proposal only.
 await navigate('missingrules','merchant',true);await tab('Merchant policy rules')
 await evaluate(`fill(field('Your name / reviewer label'),'Synthetic merchant reviewer');clickText('Load 48-hour example · form only');fill(field('Reason for this rule version'),'Checked exact merchant clauses');document.querySelector('.rule-authoring fieldset .check input').click();clickText('Save rules for review')`)
 await until(`window.__writes.length===1&&!document.querySelector('.workspace-host:not([hidden]) .workspace').matches('[aria-busy=true]')`)
 assert(await evaluate(`window.__writes[0].path.endsWith('/rules')&&window.__writes[0].body.target.kind==='proposal'&&window.__writes[0].body.target.id==='p1'&&window.__writes[0].body.target.fingerprint==='b'.repeat(64)&&!window.__writes[0].path.endsWith('/confirm')`),'merchant manual rule save binds exact proposal and stays unapproved')
 await evaluate(`fill(field('Review note'),'Checked merchant policy coverage');document.querySelectorAll('.rule-confirmation .check input').forEach(e=>{if(!e.checked)e.click()});clickText('Confirm reviewed merchant rules')`)
 await until(`window.__writes.length===2&&!document.querySelector('.workspace-host:not([hidden]) .workspace').matches('[aria-busy=true]')`)
 assert(await evaluate(`window.__writes[1].path.endsWith('/rules/new-rule/confirm')&&window.__writes[1].body.expected_fingerprint==='e'.repeat(64)&&window.__writes.every(w=>!w.path.includes('/agreements/')&&!w.path.includes('/checkout/')&&!w.path.endsWith('/propose'))`),'separate merchant rule approval never confirms agreement, calls AI or approves checkout')
 await view('buyer');await tab('Cancellation');assert(await evaluate(`field('Policy source version').value==='agreement'&&document.querySelector('.policy-status').textContent.includes('Rule approval required')`),'merchant approval leaves buyer-agreement rules unapproved')
 // Fresh viewport captures avoid stale compositor tiles after deep form switches.
 for(const [size,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]) {
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:size==='mobile'})
  for(const [name,label,scenario] of [['merchant-overview','Merchant overview','awaiting'],['buyer-reference','Buyer reference','awaiting'],['merchant-proposal','Final proposal','ready'],['merchant-rules','Merchant policy rules','ready'],['merchant-payment','Payment status','paid']]) {
   await navigate(scenario,'merchant',true)
   if(label!=='Merchant overview')await tab(label)
   await evaluate(`window.scrollTo({top:0,behavior:'instant'})`);await new Promise(r=>setTimeout(r,300));await shot(name+'-'+size)
  }
 }
 assert(errors.length===0,'no uncaught browser errors: '+errors.join('; '));console.log(passes+' workspace assertions passed; synthetic API only; providers blocked.')
} finally {ws.close()}
