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


const advisoryFixture = String.raw`
(()=>{
const original=window.fetch;let saved=[];window.__suggestMode='success';window.__staleSuggestion=false;
window.fetch=async(input,options={})=>{
 const raw=String(input),url=new URL(raw,location.origin),path=url.pathname;
 if(path.endsWith('/clarifications')){
  if(options.method==='POST'){
   const body=JSON.parse(options.body);window.__writes.push({path,body});
   if(window.__suggestMode==='provider_failure')return Response.json({detail:{code:'ai_timeout',message:'Safe mocked timeout'}},{status:504});
   if(window.__suggestMode==='bad_reference')return Response.json({detail:{code:'ai_invalid_output',message:'Unsupported saved-term reference'}},{status:502});
   if(window.__suggestMode==='changed')return Response.json({detail:{code:'clarification_comparison_stale'}},{status:409});
   const comparisons=await(await original('/api/bookings/b1/comparisons?limit=20')).json(),comparison=comparisons[0],result=comparison.results.find(r=>r.category===body.category);
   const terms=['agreement','proposal'].flatMap(side=>result[side+'_terms'].map((t,index)=>({term_id:side+':'+index,side,text:t.value,origin:side==='agreement'?'source_supported':'merchant_entered',citations:side==='agreement'?t.citations:[]})));
   const item={id:'suggestion-'+(saved.length+1),fingerprint:'f'.repeat(64),comparison_id:comparison.id,comparison_fingerprint:comparison.fingerprint,category:body.category,created_at:'2026-11-03T10:00:00Z',stale:false,stale_reasons:[],output:window.__suggestMode==='insufficient'?{status:'needs_more_information',question:null,explanation:'The merchant must provide the missing exception details.'}:{status:'suggested',question:'Can you confirm whether the USD 80 deposit remains refundable under the agreed cancellation terms?',explanation:'The saved buyer and merchant terms give different deposit refund obligations.'},supporting_terms:window.__suggestMode==='insufficient'?[]:terms};saved=[item,...saved];return Response.json(item,{status:201});
  }
  return Response.json(saved.map(x=>({...x,stale:window.__staleSuggestion,stale_reasons:window.__staleSuggestion?['merchant_booking_changed']:[]})));
 }
 if(path.endsWith('/comparisons')&&new URLSearchParams(location.search).has('clarify-stale')){const response=await original(input,options);return Response.json((await response.json()).map(c=>({...c,stale:true,stale_reasons:['merchant_booking_changed']})))}
 return original(input,options);
};
})();`
async function settle(){await evaluate(`new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))`)}
async function navigate(scenario='changed'){
 const before=await evaluate('performance.timeOrigin');await send('Page.navigate',{url:origin+'/?case='+(scenario==='stale'?'changed&clarify-stale=1':scenario)+'&clarifyqa='+(++navigation)+'#bookings'});await until(`performance.timeOrigin!==${before}`);await until(`document.querySelector('.booking-row .state-label')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`);await evaluate(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`);await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes('Compare booking')).click()`);await until(`document.querySelector('.clarification-panel')?.getAttribute('aria-busy')==='false'`);await settle()
}
async function generate(mode='success'){
 await evaluate(`window.__suggestMode=${JSON.stringify(mode)};document.querySelector('.clarification-panel .ai-button').click()`);await until(`window.__writes.length>0&&document.querySelector('.clarification-panel').getAttribute('aria-busy')==='false'`);await settle()
}
async function screenshot(name){await settle();await evaluate(`(()=>{const r=document.querySelector('.clarification-panel').getBoundingClientRect(),header=document.querySelector('.app-header').getBoundingClientRect().height,rail=innerWidth<=1023?document.querySelector('.journey-rail').getBoundingClientRect().height:0;scrollTo({top:scrollY+r.top-header-rail-16,behavior:'instant'})})()`);await new Promise(r=>setTimeout(r,200));const r=await send('Page.captureScreenshot',{captureBeyondViewport:false});await mkdir('/private/tmp/beforepay-clarifications',{recursive:true});await writeFile('/private/tmp/beforepay-clarifications/'+name+'.png',Buffer.from(r.data,'base64'))}
try{
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+advisoryFixture})
 for(const [size,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:size==='mobile'});await navigate()
  assert(await evaluate(`window.__writes.length===0&&!document.querySelector('.saved-clarification')`),size+': discrepancy loads without automatic generation')
  await generate()
  assert(await evaluate(`window.__writes.length===1&&window.__writes[0].body.category==='deposit_conditions'&&window.__writes[0].body.comparison_fingerprint==='c'.repeat(64)&&Object.keys(window.__writes[0].body).length===2`),size+': explicit action sends only saved comparison binding/category')
  assert(await evaluate(`document.querySelector('.saved-clarification').textContent.includes('USD 80 deposit remains refundable')&&document.querySelector('.saved-clarification').textContent.includes('different deposit refund obligations')&&document.querySelector('.clarification-panel').textContent.includes('nothing is resolved, approved or sent')`),size+': question, rationale and advisory boundary visible')
  await evaluate(`document.querySelector('.clarification-support details').open=true;document.querySelector('.clarification-support .evidence-link').click()`);await until(`document.querySelector('.evidence-drawer')?.open&&document.querySelector('.evidence-drawer pre')`)
  assert(await evaluate(`document.querySelector('.evidence-drawer').textContent.includes('Exact quotation')`),size+': supporting buyer term opens original source evidence')
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await until(`!document.querySelector('.evidence-drawer').open`)
  await evaluate(`document.querySelectorAll('.clarification-support details')[1].open=true`)
  assert(await evaluate(`document.querySelectorAll('.clarification-support details')[1].textContent.includes('Merchant-entered saved term')&&!document.querySelectorAll('.clarification-support details')[1].querySelector('.evidence-link')`),size+': merchant support is saved wording, never fabricated document provenance')
  await screenshot('suggestion-'+size)
  assert(await evaluate(`window.__writes.length===1&&window.__unexpected.length===0&&document.documentElement.scrollWidth<=innerWidth&&document.querySelector('.resolution-guide').textContent.includes('Resolve before checkout')`),size+': suggestion leaves discrepancy/checkout block and payment actions unchanged')
  await evaluate(`window.__staleSuggestion=true;window.dispatchEvent(new Event('contextkey:changed'))`);await settle()
  assert(await evaluate(`document.querySelector('.saved-clarification .status').textContent.includes('not current')&&document.querySelector('.clarification-panel .ai-button').disabled`),size+': known saved-input change immediately invalidates current label')
  await evaluate(`clickText('Refresh suggestions')`);await until(`document.querySelector('.clarification-panel').getAttribute('aria-busy')==='false'`)
  assert(await evaluate(`document.querySelector('.saved-clarification .status').textContent.includes('Historical')&&document.querySelector('.clarification-panel .ai-button').disabled`),size+': server-stale history never becomes current on refresh')
  await navigate('stale');assert(await evaluate(`document.querySelector('.clarification-panel .ai-button').disabled&&window.__writes.length===0`),size+': stale comparison cannot generate');
  await navigate();await generate('insufficient');assert(await evaluate(`document.querySelector('.saved-clarification h4').textContent==='Needs more information'&&!document.querySelector('.clarification-question')`),size+': insufficient evidence shows no invented question')
  await screenshot('needs-information-'+size)
 }
 for(const mode of ['provider_failure','bad_reference','changed']){
  await navigate();await generate(mode);assert(await evaluate(`!!document.querySelector('.clarification-panel [role=alert]')&&!document.querySelector('.saved-clarification')&&window.__writes.length===1&&document.querySelector('.clarification-panel .ai-button').disabled`),mode+': safe error, no fake result and no automatic retry')
 }
 await navigate();await evaluate(`clickText('Merchant · edit proposal')`);await until(`visible(document.querySelector('.merchant-view'))`);await evaluate(`fill(field('Merchant name / provisional label'),'Retained clarification test editor');document.querySelector('.sample-tools').open=true;clickText('Copy buyer-confirmed terms into form');clickText('Buyer · review differences')`);await until(`visible(document.querySelector('.buyer-comparison'))`)
 assert(await evaluate(`document.querySelector('.clarification-panel .ai-button').disabled&&window.__writes.length===0`),'unsaved merchant fields block generation and stay unsaved')
 await send('Accessibility.enable');const ax=await send('Accessibility.getFullAXTree');assert(!ax.nodes.some(n=>!n.ignored&&n.role?.value==='button'&&!n.name?.value),'clarification controls have accessible names')
 assert(errors.length===0,'no uncaught clarification browser errors: '+errors.join('; '));console.log(passes+' clarification browser assertions passed; all providers/APIs mocked.')
}finally{ws.close()}
