// Isolated API fixtures only. No backend proxy, provider calls or real payments.
import { fixture } from './fixtures/product-fixture.mjs'
import { mkdir, writeFile } from 'node:fs/promises'
const origin = process.env.FRONTEND_URL || 'http://127.0.0.1:5187'
const targets = await (await fetch((process.env.CDP_URL || 'http://127.0.0.1:9228') + '/json')).json()
const ws = new WebSocket(targets.find(t => t.type === 'page' && (!process.env.CDP_TARGET_ID || t.id === process.env.CDP_TARGET_ID)).webSocketDebuggerUrl)
await new Promise(r => { ws.onopen = r })
let serial = 0, passes = 0, navigation = 0
const pending = new Map(), errors = []
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result) } else if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text); if (m.method === 'Page.javascriptDialogOpening' && m.params.type === 'beforeunload') void send('Page.handleJavaScriptDialog', { accept: true }) }
const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++serial; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })) })
async function ev(expression) { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); await send('Runtime.evaluate', { expression: 'window.__enterDemoForRegression?.()', awaitPromise: true, returnByValue: true }); return r.result.value }
async function until(expression) { for (let i = 0; i < 160; i++) { if (await ev(`Boolean(${expression})`)) return; await new Promise(r => setTimeout(r, 70)) } throw Error('Timeout ' + expression) }
function assert(ok, label) { if (!ok) throw Error(label); passes++; console.log('PASS ' + label) }
const extra = String.raw`
(() => {
 const base=window.fetch,flag=new URLSearchParams(location.search).get('flag');let fresh=false;
 const twice=claims=>claims.flatMap(c=>[c,{...structuredClone(c),citations:c.citations.map(q=>({...q,source_id:'s2'}))}]);
 window.fetch=async(input,options={})=>{
  const path=new URL(String(input),location.origin).pathname;
  const response=await base(input,options);
  if(path.includes('/agreements')&&(!options.method||options.method==='GET')){
   const data=await response.json();
   const legacy=a=>{for(const [cat,entries]of Object.entries(a.content.extraction)){a.content.extraction[cat]=entries.flatMap(e=>{const second=structuredClone(e);second.claim.citations=second.claim.citations.map(q=>({...q,source_id:'s2'}));if(cat==='amounts'){second.claim.label=second.claim.kind==='total_payable'?'total':second.claim.label.toLowerCase();second.claim.amount=second.claim.amount.replace(/\.00$/,'')}return[e,second]})}return a};
   return Response.json(Array.isArray(data)?data.map(legacy):legacy(data));
  }
  if(path.endsWith('/eligibility')&&!fresh){const data=await response.json();return Response.json({...data,eligible:false,blockers:['comparison_has_differences_or_clarification']})}
  if(path.endsWith('/comparisons')){
   if(options.method==='POST'&&!flag)fresh=true;
   const data=await response.json();
   const update=c=>{const r=c.results.find(r=>r.category==='included_items');r.agreement_terms=twice(r.agreement_terms);if(flag==='buyer')r.agreement_terms[0].ambiguous=true;if(flag==='merchant')r.proposal_terms[0].ambiguous=true;r.status=fresh&&!flag?'matches':'needs_clarification';r.reason=r.status==='matches'?'typed_values_equal':'missing_or_ambiguous_terms';return c};
   return Response.json(Array.isArray(data)?data.map(update):update(data),{status:options.method==='POST'?201:200});
  }
  return response;
 }
})();`
async function nav(flag='',role='buyer'){await send('Page.navigate',{url:origin+'/?case=ready&flag='+flag+'&run='+(++navigation)+'#'+(role==='buyer'?'bookings':'merchant/bookings')});await until(`document.querySelector('.row-action')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`);await ev(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`)}
async function tab(name){await ev(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(name)})).click()`);await until(`document.querySelector('.workspace-host:not([hidden]) .workspace')?.getAttribute('aria-busy')==='false'`)}
const section=`[...document.querySelectorAll('.difference-section')].find(e=>e.querySelector('h3')?.textContent==='Included items')`;
const directory='/private/tmp/beforepay-comparison-corroboration';await mkdir(directory,{recursive:true});
async function screenshot(name){await ev('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');const s=await send('Page.captureScreenshot');await writeFile(directory+'/'+name+'.png',Buffer.from(s.data,'base64'))}
try{
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+extra});
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',820,1180],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<600});await nav();await tab('Agreement');
  assert(await ev(`document.querySelector('.amount-table tbody').rows.length===3&&document.querySelector('.amount-table').textContent.includes('Total payable / total')`),name+': summary components count once with both original labels');
  await tab('Compare booking');
  assert(await ev(`${section}.textContent.includes('saved source mentions')&&${section}.textContent.includes('Needs clarification')&&window.__writes.length===0`),name+': legacy result is explained without forcing a match');
  await ev(`${section}.scrollIntoView({block:'center'})`);await screenshot(name+'-legacy-result');
  await ev(`clickText('Compare bookings · may use AI')`);await until(`document.querySelector('.comparison-results h2')?.textContent==='Saved terms match'`);
  assert(await ev(`window.__writes.filter(w=>w.path.endsWith('/comparisons')).length===1&&window.__writes.length===1`),name+': only explicit comparison accepts mocked fresh result; no approvals/payments');
  for(const side of ['buyer','merchant']){
   await nav(side);await tab('Compare booking');
   assert(await ev(`${section}.textContent.includes('Saved unresolved flag')&&${section}.textContent.includes('Matching wording does not clear these flags')&&${section}.textContent.includes('Needs clarification')`),name+': '+side+' unresolved flag remains visible and blocking');
   assert(await ev(`document.documentElement.scrollWidth<=innerWidth+1&&window.__writes.length===0`),name+': flags require review without implicit writes or overflow');
   if(name==='desktop')await screenshot(side+'-unresolved');
  }
 }
 await nav('','merchant');await tab('Final proposal');await ev(`document.querySelector('.merchant-editor').open=true;clickText('Copy buyer-confirmed terms into form')`);
 assert(await ev(`document.querySelectorAll('.merchant-editor .claim-heading').length===11&&window.__writes.length===0`),'explicit merchant copy uses three summary charges, no duplicated authored amounts');
 assert(errors.length===0,'no browser runtime exceptions');console.log(passes+' legacy comparison UI checks passed; synthetic API only.');
}finally{ws.close()}
