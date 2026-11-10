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
 window.__topReads=[];window.__holdSlow=true;window.__slowFailure=true;
 window.fetch=async(input,options={})=>{
  const path=new URL(String(input),location.origin).pathname;
  if(!options.__snapshotFixture&&(!options.method||options.method==='GET'))window.__topReads.push(path);
  if(path==='/api/bookings')return Response.json([{id:'slow',title:'Synthetic slow status'},{id:'fast',title:'Synthetic fast status'}]);
  if(path==='/api/bookings/slow/saved-state'){
   if(window.__holdSlow)await new Promise(resolve=>window.__releaseSlow=resolve);
   if(window.__slowFailure)return Response.json({detail:{code:'public_setup_required',message:'Sanitised readiness failure'}},{status:503});
  }
  return base(String(input).replace('/bookings/slow/','/bookings/b1/').replace('/bookings/fast/','/bookings/b1/'),options);
 }
})();`
try{
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+extra});
 await send('Page.navigate',{url:origin+'/?case=ready&performance='+Date.now()+'#bookings'});
 await until(`document.querySelectorAll('.booking-row').length===2&&window.__releaseSlow`);
 await until(`[...document.querySelectorAll('.booking-row')][1].textContent.includes('Ready for checkout')`);
 assert(await ev(`document.querySelectorAll('.booking-row')[0].textContent.includes('Checking status')`),'slow optional status does not delay fast row or booking names');
 assert(await ev(`window.__topReads.filter(p=>p.endsWith('/saved-state')).length===2&&window.__topReads.filter(p=>p.includes('/checkout/eligibility')).length===0`),'one actual aggregate read per booking; no dashboard leaf fan-out');
 await ev(`clickText('Create booking')`);await until(`document.querySelector('.create-sheet input')`);await ev(`fill(document.querySelector('.create-sheet input'),'My unsaved recording title')`);
 assert(await ev(`!document.querySelector('.create-sheet .primary').disabled`),'optional status does not block create form');
 await ev(`window.__releaseSlow()`);await until(`document.querySelectorAll('.booking-row')[0].textContent.includes('Status unavailable')`);
 assert(await ev(`document.querySelector('.create-sheet input').value==='My unsaved recording title'&&document.querySelectorAll('.booking-row')[1].textContent.includes('Ready for checkout')&&document.querySelectorAll('.booking-row')[0].textContent.includes('Saved terms unavailable')`),'failure stays local to row; no false absence or lost input');
 assert(await ev(`window.__writes.length===0`),'no automatic retries, bookings, AI or payment writes');
 await ev(`window.__holdSlow=false;window.__slowFailure=false;clickText('Refresh list')`);await until(`document.querySelectorAll('.booking-row')[0].textContent.includes('Ready for checkout')`);
 assert(await ev(`document.querySelector('.create-sheet input').value==='My unsaved recording title'&&window.__topReads.filter(p=>p.endsWith('/saved-state')).length===4`),'explicit refresh updates each row exactly once and retains form input');
 await ev(`document.querySelectorAll('.row-action')[1].click()`);await until(`document.querySelector('.tabs')&&window.__topReads.filter(p=>p==='/api/bookings/fast/saved-state').length===3`);
 await ev(`window.dispatchEvent(new Event('contextkey:changed'))`);await until(`window.__topReads.filter(p=>p==='/api/bookings/fast/saved-state').length===4`);
 await ev(`new Promise(r=>setTimeout(r,120))`);
 assert(await ev(`window.__topReads.filter(p=>p==='/api/bookings/fast/saved-state').length===4&&window.__topReads.filter(p=>p==='/api/bookings/slow/saved-state').length===2`),'one mutation notification refreshes only active booking; hidden dashboard stays quiet');
 assert(errors.length===0,'no browser runtime exceptions');console.log(passes+' saved-state performance browser checks passed; synthetic delays only.');
}finally{ws.close()}
