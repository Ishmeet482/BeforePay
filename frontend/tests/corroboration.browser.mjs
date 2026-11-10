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
 const base=window.fetch;
 window.__activeReads=0;window.__maxReads=0;window.__failLoads=new URLSearchParams(location.search).get('fail')||'';
 window.fetch=async(input,options={})=>{
  const path=new URL(String(input),location.origin).pathname;
  const read=path.startsWith('/api/')&&path!='/api/demo-sessions'&&(!options.method||options.method==='GET');
  const counted=read&&!options.__snapshotFixture;
  if(counted){window.__activeReads++;window.__maxReads=Math.max(window.__maxReads,window.__activeReads)}
  try{
   if(read)await new Promise(r=>setTimeout(r,45));
   if(read&&window.__failLoads&&path.includes('/bookings/b1/')&&path.endsWith('/'+window.__failLoads))return Response.json({detail:{code:'public_setup_required',message:'Sanitised fixture readiness failure'}},{status:503});
   const response=await base(input,options);
   if(read&&path.includes('/agreements')){
    const data=await response.json();
    const duplicate=a=>{for(const [category,entries]of Object.entries(a.content.extraction)){a.content.extraction[category]=entries.flatMap(e=>[e,{...structuredClone(e),claim:{...structuredClone(e.claim),citations:e.claim.citations.map(c=>({...c,source_id:'s2'}))}}])}return a};
    return Response.json(Array.isArray(data)?data.map(duplicate):duplicate(data));
   }
   if(read&&path.endsWith('/sources/s2'))return Response.json({id:'s2',source_type:'message',medium:'pasted_text',original_text:'Synthetic corroborating source',pages:[]});
   return response;
  }finally{if(counted)window.__activeReads--}
 }
})();`
async function nav(fail='',role='buyer') { await send('Page.navigate',{url:origin+'/?case=ready&fail='+fail+'&run='+(++navigation)+'#'+(role==='buyer'?'bookings':'merchant/bookings')});await until(`document.querySelector('.row-action')`);await until(`!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`) }
async function open(){await ev(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`)}
async function tab(name){await ev(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(name)})).click()`);await until(`document.querySelector('.workspace-host:not([hidden]) .workspace')?.getAttribute('aria-busy')==='false'`)}
const directory='/private/tmp/beforepay-corroboration';await mkdir(directory,{recursive:true});
async function screenshot(name){const s=await send('Page.captureScreenshot');await writeFile(directory+'/'+name+'.png',Buffer.from(s.data,'base64'))}
try {
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+extra});
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',820,1180],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<600});await nav();await open();await tab('Agreement');
  assert(await ev(`document.querySelector('#title-equipment').closest('section').querySelectorAll('.item-table tbody tr').length===1`),name+': corroborated item shown once');
  assert(await ev(`document.querySelector('#title-equipment').closest('section').querySelectorAll('.section-editor .claim-row').length===2`),name+': original individually editable claims preserved');
  assert(await ev(`document.querySelector('.workspace-host:not([hidden])').textContent.includes('save a reasoned review revision')`),name+': explicit legacy revision guidance');
  await ev(`document.querySelector('#title-equipment').closest('section').querySelector('.term-summary button').click()`);await until(`document.querySelector('.evidence-drawer[open]')`);
  assert(await ev(`document.querySelector('.evidence-drawer select')?.options.length===2`),name+': both supporting quotations accessible');
  await ev(`document.querySelector('.evidence-drawer').close()`);await screenshot(name+'-agreement');
  assert(await ev(`window.__maxReads<=2&&window.__writes.length===0&&document.documentElement.scrollWidth<=innerWidth+1`),name+': bounded initial GETs, no implicit writes, no overflow');
 }
 await nav('','merchant');await open();await tab('Final proposal');
 await ev(`document.querySelector('.merchant-editor').open=true;clickText('Copy buyer-confirmed terms into form')`);
 assert(await ev(`document.querySelectorAll('.merchant-editor .claim-heading').length===11&&!document.querySelector('.merchant-editor').textContent.includes('Merchant condition 1')`),'merchant copy consolidates exact corroboration with contextual labels');
 assert(await ev(`document.querySelector('.merchant-editor').textContent.includes('Equipment item 1')&&document.querySelector('.merchant-editor').textContent.includes('Charge 1')&&document.querySelector('.merchant-editor').textContent.includes('Deposit clause 1')&&window.__writes.length===0`),'copy is explicit, form-only and labelled by category');
 await screenshot('merchant-copy');
 for(const [failed,screen,empty] of [['review','Agreement','No saved draft available'],['drafts','Sources & draft','No saved draft yet'],['merchant-bookings','Final proposal','No saved comparison yet'],['rules','Cancellation','No agreement version available'],['eligibility','Checkout & receipt','Approve checkout']]){
  await nav(failed,screen==='Final proposal'?'merchant':'buyer');await open();await tab(screen);
  assert(await ev(`document.querySelector('.workspace-host:not([hidden])').textContent.includes('Saved data unavailable')&&!document.querySelector('.workspace-host:not([hidden])').textContent.includes(${JSON.stringify(empty)})`),failed+': failed load is not empty/success');
  await screenshot('failed-'+failed);
  await ev(`window.__failLoads='';clickText('Refresh saved data')`);await until(`!document.querySelector('.workspace-host:not([hidden])').textContent.includes('Saved data unavailable')&&document.querySelector('.workspace-host:not([hidden]) .workspace')?.getAttribute('aria-busy')==='false'`);
  assert(await ev(`window.__writes.length===0`),failed+': explicit refresh restores data without mutations');
 }
 assert(errors.length===0,'no browser runtime exceptions');console.log(passes+' corroboration/loading browser checks passed.');
}finally{ws.close()}
