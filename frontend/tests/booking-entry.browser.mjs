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
async function evaluate(expression) { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 120; i++) { if (await evaluate(`Boolean(${expression})`)) return; await new Promise(r => setTimeout(r, 80)) } throw new Error('Timed out: ' + expression) }
let passes = 0, navigation = 0
function assert(ok, name) { if (!ok) throw new Error(name); passes++; console.log('PASS ' + name) }




const creationFixture = String.raw`
(() => {
 const original=window.fetch;let created=null;
 window.__createRequests=[];window.__holdCreate=false;window.__failCreate=false;
 const holdList=new URLSearchParams(location.search).has('hold-list');let listReleased=false;
 window.fetch=async(input,options={})=>{
  const raw=String(input),url=new URL(raw,location.origin),path=url.pathname;
  if(path==='/api/bookings'&&options.method==='POST'){
   const body=JSON.parse(options.body);window.__createRequests.push(body);window.__writes.push({path,body});
   if(window.__holdCreate)await new Promise(resolve=>window.__releaseCreate=resolve);
   if(window.__failCreate)return Response.json({detail:'Synthetic create outcome uncertain'},{status:503});
   created={id:'new-booking',title:body.title};return Response.json(created,{status:201});
  }
  if(path==='/api/bookings'&&(!options.method||options.method==='GET')){
   if(holdList&&!listReleased){await new Promise(resolve=>window.__releaseList=resolve);listReleased=true}
   const response=await original(input,options);const rows=await response.json();return Response.json(created?[created,...rows]:rows);
  }
  if(path.startsWith('/api/bookings/new-booking/')){
   window.__reads.push(raw);let data=[];
   if(path.endsWith('/review'))data={agreement_id:null,fingerprint:null,source_ids:[],latest_draft_id:null,blockers:[],confirmation_current:false,requires_review:true,confirmation:null};
   else if(path.endsWith('/checkout/eligibility'))data={eligible:false,blockers:['current_confirmation_required'],sandbox_configured:true};
   return Response.json(data);
  }
  return original(input,options);
 };
})();`
async function settle(){await evaluate(`new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))`)}
async function navigate(role,hash='',scenario='ready',hold=false){
 await evaluate(role?`sessionStorage.setItem('beforepay:demo-role','${role}')`:`sessionStorage.removeItem('beforepay:demo-role')`)
 const previous=await evaluate('performance.timeOrigin');await send('Page.navigate',{url:origin+'/?demo-entry=1&case='+scenario+'&bookingqa='+(++navigation)+(hold?'&hold-list=1':'')+hash});await until(`performance.timeOrigin!==${previous}`);await until(`!!document.querySelector('.entry-page,.bookings-page:not([hidden])')`);await settle()
}
async function loginBuyer(){await until(`document.querySelector('.demo-login')?.open`);await evaluate(`fill(document.querySelector('#demo-username'),'buyer.demo');fill(document.querySelector('#demo-password'),'BuyerDemo123!');document.querySelector('.demo-login form').requestSubmit()`);await until(`!document.querySelector('.demo-login')&&visible(document.querySelector('.create-sheet'))`);await until(`!document.querySelector('.list-toolbar').textContent.includes('Loading')`);await settle()}
async function readyForm(){await until(`visible(document.querySelector('.create-sheet'))&&!document.querySelector('.list-toolbar').textContent.includes('Loading')`);await until(`document.activeElement===document.querySelector('.create-sheet input')`)}
async function creation(title='Synthetic buyer-created booking'){
 await readyForm();await evaluate(`window.__holdCreate=true;fill(document.querySelector('.create-sheet input'),${JSON.stringify(title)});document.querySelector('.create-sheet form').requestSubmit();document.querySelector('.create-sheet form').requestSubmit()`);await until(`window.__createRequests.length===1`)
 assert(await evaluate(`window.__createRequests.length===1&&document.querySelector('.create-sheet button').disabled`),'double submit sends one pending creation request')
 await evaluate(`window.__releaseCreate()`);await until(`location.hash==='#bookings/new-booking'&&visible(document.querySelector('.source-inbox'))`)
 assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')==='buyer'&&document.querySelector('.tabs button[aria-current=step]').textContent.includes('Sources & draft')&&document.querySelector('.booking-heading h1').textContent===${JSON.stringify(title)}&&document.querySelector('.booking-session').textContent.includes('Booking created.')`),'success selects returned ID/title and opens Sources & draft with next-step guidance')
 assert(await evaluate(`window.__writes.length===1&&window.__writes[0].path==='/api/bookings'&&window.__unexpected.length===0`),'creation never generates drafts, proposals, approvals or payments')
}
async function shot(name){await settle();const r=await send('Page.captureScreenshot',{captureBeyondViewport:false});await mkdir('/private/tmp/beforepay-booking-entry',{recursive:true});await writeFile('/private/tmp/beforepay-booking-entry/'+name+'.png',Buffer.from(r.data,'base64'))}
try {
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+creationFixture});await send('Page.navigate',{url:origin+'/?demo-entry=1'});await until(`document.querySelector('.entry-page')`)
 for(const [size,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:size==='mobile'})
  await navigate(null);await evaluate(`document.querySelector('.entry-actions .primary').click()`);await until(`document.querySelector('.demo-login')?.open`)
  assert(await evaluate(`document.querySelector('input[value=buyer]').checked&&document.querySelector('input[value=merchant]').disabled&&window.__reads.length===0&&window.__writes.length===0`),size+': visitor starts Buyer-only demo entry without API calls')
  await shot('buyer-entry-'+size);await loginBuyer();await creation();await shot('created-sources-'+size)
  await navigate('buyer');await evaluate(`document.querySelector('.entry-actions .primary').click()`);await readyForm()
  assert(await evaluate(`location.hash==='#bookings/new'&&!document.querySelector('.demo-login')&&window.__writes.length===0`),size+': existing Buyer enters creation directly')
  await navigate('merchant');await evaluate(`document.querySelector('.entry-actions .primary').click()`);await until(`document.querySelector('.demo-login')?.open`)
  assert(await evaluate(`document.querySelector('#demo-login-title').textContent.includes('Switch to Buyer')&&sessionStorage.getItem('beforepay:demo-role')==='merchant'&&!visible(document.querySelector('.create-sheet'))`),size+': Merchant is explicitly offered Buyer switch before creation')
  await evaluate(`document.querySelector('[aria-label="Close demo login"]').click()`);await until(`!document.querySelector('.demo-login')`)
  assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')==='merchant'&&window.__writes.length===0&&!!document.querySelector('.entry-page')`),size+': cancelling leaves Merchant session and public page intact')
  await evaluate(`document.querySelector('.entry-actions .primary').click()`);await until(`document.querySelector('.demo-login')?.open`);await evaluate(`fill(document.querySelector('#demo-username'),'merchant.demo');fill(document.querySelector('#demo-password'),'MerchantDemo123!');document.querySelector('.demo-login form').requestSubmit()`)
  assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')==='merchant'&&!!document.querySelector('#demo-login-error')&&window.__writes.length===0`),size+': Merchant credentials cannot enter Buyer creation')
  await loginBuyer();await readyForm();await shot('create-booking-'+size);await creation('Synthetic switched Buyer rental')
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),size+': created Buyer source workspace fits viewport')
 }
 // Every other creation entry shares the same Buyer intent, including legacy merchant URLs.
 for(const role of ['buyer','merchant']){
  await navigate(role,role==='merchant'?'#merchant/bookings':'#bookings');await until(`!document.querySelector('.list-toolbar').textContent.includes('Loading')`);await evaluate(`document.querySelector('.page-heading > button').click()`)
  if(role==='merchant')await loginBuyer();await readyForm();assert(await evaluate(`location.hash==='#bookings/new'&&sessionStorage.getItem('beforepay:demo-role')==='buyer'`),role+': dashboard Create booking uses Buyer entry')
  await navigate(role,role==='merchant'?'#merchant/bookings':'#bookings','empty');await until(`visible(document.querySelector('.empty-state'))`);await evaluate(`document.querySelector('.empty-state button').click()`)
  if(role==='merchant')await loginBuyer();await readyForm();assert(await evaluate(`location.hash==='#bookings/new'&&sessionStorage.getItem('beforepay:demo-role')==='buyer'`),role+': empty-state creation uses Buyer entry')
 }
 for(const role of [null,'buyer','merchant'])for(const hash of ['#bookings/new','#merchant/bookings/new']){
  await navigate(role,hash);if(role!=='buyer'){await until(`document.querySelector('.demo-login')?.open`);assert(await evaluate(`document.querySelector('input[value=buyer]').checked&&document.querySelector('input[value=merchant]').disabled`),(role||'visitor')+' '+hash+': direct URL requests Buyer entry');await loginBuyer()}
  await readyForm();assert(await evaluate(`location.hash==='#bookings/new'&&window.__writes.length===0`),(role||'visitor')+' '+hash+': canonical Buyer creation route, no write on navigation')
 }
 // Slow initial reads cannot race a new booking out of the selected list.
 await navigate('buyer','#bookings/new','ready',true);await until(`visible(document.querySelector('.create-sheet'))`);await evaluate(`fill(document.querySelector('.create-sheet input'),'Synthetic loading guard');document.querySelector('.create-sheet form').requestSubmit()`)
 assert(await evaluate(`window.__createRequests.length===0&&document.querySelector('.create-sheet button').disabled&&document.querySelector('.create-sheet').textContent.includes('finish loading')`),'creation waits for initial list read; no stale-list overwrite race')
 await evaluate(`window.__releaseList()`);await readyForm()
 // Failed/unknown result needs explicit list reconciliation before another attempt.
 await evaluate(`window.__failCreate=true;document.querySelector('.create-sheet form').requestSubmit()`);await until(`window.__createRequests.length===1&&!document.querySelector('.create-sheet input').disabled`);await evaluate(`document.querySelector('.create-sheet form').requestSubmit()`)
 assert(await evaluate(`window.__createRequests.length===1&&document.querySelector('.create-sheet button').disabled&&document.querySelector('.create-sheet input').value==='Synthetic loading guard'`),'failed creation retains input and blocks duplicate retry until refresh')
 await evaluate(`document.querySelector('.list-toolbar button').click()`);await until(`!document.querySelector('.list-toolbar button').disabled`)
 assert(await evaluate(`!document.querySelector('.create-sheet button').disabled&&window.__createRequests.length===1`),'successful explicit list refresh unlocks creation without automatic retry')
 // Existing saved booking and receipt stay untouched by creating a different booking.
 await navigate('buyer','#bookings','paid');await until(`document.querySelector('.row-action')`);await evaluate(`(async()=>{window.__beforeReceipt=await(await fetch('/api/bookings/b1/checkout/receipt')).json();document.querySelector('.row-action').click()})()`);await until(`document.querySelector('.tabs')`);await evaluate(`document.querySelector('.wordmark').click()`);await until(`document.querySelector('.entry-page')`);await evaluate(`document.querySelector('.entry-actions .primary').click()`);await readyForm();await evaluate(`window.confirm=()=>false;fill(document.querySelector('.create-sheet input'),'Synthetic separate rental');document.querySelector('.create-sheet form').requestSubmit()`)
 assert(await evaluate(`window.__createRequests.length===0&&document.querySelector('.create-sheet input').value==='Synthetic separate rental'`),'rejecting discard warning preserves old booking forms and prevents creation')
 await evaluate(`window.confirm=()=>true`);await creation('Synthetic separate rental');assert(await evaluate(`(async()=>JSON.stringify(await(await fetch('/api/bookings/b1/checkout/receipt')).json())===JSON.stringify(window.__beforeReceipt))()`),'new booking leaves synthetic original receipt snapshot unchanged')
 await navigate(null);await evaluate(`document.querySelector('.global-nav a').click()`);await settle();assert(await evaluate(`!!document.querySelector('.entry-page')&&!document.querySelector('.demo-login')&&window.__reads.length===0&&window.__writes.length===0`),'How it works remains public without demo entry or writes')
 assert(errors.length===0,'no uncaught booking-entry exceptions: '+errors.join('; '));console.log(passes+' Buyer booking-entry assertions passed; all records/providers synthetic.')
}finally{ws.close()}
