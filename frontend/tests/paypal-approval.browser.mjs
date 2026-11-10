// Run with Vite and headless Chrome debugging on port 9225.
// All backend traffic is mocked; all PayPal hosts are blocked.
// No actual orders, approvals or captures are created.
import process from 'node:process'
const targets = await (await fetch(`${process.env.CDP_URL || 'http://127.0.0.1:9225'}/json`)).json()
const target = targets.find(t => t.type === 'page' && (!process.env.CDP_TARGET_ID || t.id === process.env.CDP_TARGET_ID))
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise(r => ws.onopen = r)
let id = 0
const pending = new Map()
const exceptions = []
const started = Date.now()
ws.onmessage = e => { const m = JSON.parse(e.data); if(m.id) { const p=pending.get(m.id); pending.delete(m.id); m.error?p?.reject(new Error(m.error.message)):p?.resolve(m.result) } else if(m.method==='Runtime.exceptionThrown') { if (m.params.timestamp >= started) exceptions.push(m.params.exceptionDetails.exception?.description?.split('\n')[0] || m.params.exceptionDetails.text) } }
function send(method, params={}) { return new Promise((resolve,reject) => { const n=++id; pending.set(n,{resolve,reject}); ws.send(JSON.stringify({id:n,method,params})) }) }
async function evaluate(expression) { const result = await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}); if(result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value }
async function until(expression) { for(let n=0;n<80;n++) { if(await evaluate(`Boolean(${expression})`)) return; await new Promise(r=>setTimeout(r,100)) } throw new Error('Browser condition timed out: '+expression) }
function assert(ok,name) { if(!ok) throw new Error(name); console.log('PASS '+name) }
const fixtures = String.raw`
if(!new URLSearchParams(location.search).has('demo-entry'))sessionStorage.setItem('beforepay:demo-role','buyer');
(() => {
window.confirm=()=>true;
window.__writes=[];window.__sdk={};
const context={environment:'sandbox',agreement_id:'a1',agreement_version:1,agreement_fingerprint:'a'.repeat(64),proposal_id:'p1',proposal_version:1,proposal_fingerprint:'b'.repeat(64),comparison_id:'c1',comparison_fingerprint:'c'.repeat(64),amount:'200.00',currency:'USD'};
const append=Element.prototype.append;
Element.prototype.append=function(...nodes){for(const n of nodes){
 if(n.tagName==='SCRIPT'&&n.src.includes('paypal.com')){
  window.__sdk.url=n.src;
  window.paypal={createInstance:async options=>{window.__sdk.options=options;return {
   findEligibleMethods:async options=>{window.__sdk.eligibility=options;return {isEligible:method=>method==='paypal'}},
   createPayPalOneTimePaymentSession:()=>({start:async(options,promise)=>{
    window.__sdk.startOptions=options;window.__sdk.order=await promise;
    // Deliberately never invoke onApprove: this regression cannot capture.
   }})
  }}};
  queueMicrotask(()=>n.onload(new Event('load')));
 }else append.call(this,n);
}};
window.fetch=async(input,options={})=>{
 const url=String(input);let data;
 if(url==='/api/demo-sessions')return Response.json({active:true,csrf_token:'f'.repeat(64),expires_at:new Date(Date.now()+2700000).toISOString()});
 if(options.method==='POST'){
  const body=JSON.parse(options.body);window.__writes.push({url,body});
  if(url.endsWith('/checkout/approvals'))return Response.json({id:'LOCAL_APPROVAL_UUID',fingerprint:'e'.repeat(64),context},{status:201});
  if(url.endsWith('/checkout/orders'))return Response.json({id:'LOCAL_ATTEMPT_UUID',approval_id:'LOCAL_APPROVAL_UUID',order_id:'PAYPALORDER123',status:'awaiting_buyer',amount:'200.00',currency:'USD',capture_id:null,error_code:null});
  throw new Error('Unexpected mutation: '+url);
 }
 if(url.startsWith('/api/bookings?'))data=[{id:'b1',title:'Synthetic existing-order regression'}];
 else if(url.endsWith('/saved-state'))data={review:{agreement_id:null,fingerprint:null,source_ids:[],latest_draft_id:null,blockers:['agreement_missing'],confirmation_current:false,requires_review:true,confirmation:null},agreement:null,proposal:null,comparison:null,rules:[],attempts:[],receipt:null,eligible:true,blockers:[],sandbox_configured:true};
 else if(url.endsWith('/checkout/eligibility'))data={eligible:true,blockers:[],context,fingerprint:'e'.repeat(64),sandbox_configured:true};
 else if(url.endsWith('/checkout/config'))data={environment:'sandbox',configured:true,client_id:'SANDBOX_APP_FROM_BACKEND',sdk_url:'https://www.sandbox.paypal.com/web-sdk/v6/core'};
 else if(url.endsWith('/checkout/attempts'))data=[];
 else if(url.endsWith('/review'))data={agreement_id:null,fingerprint:null,source_ids:[],latest_draft_id:null,blockers:['agreement_missing'],confirmation_current:false,requires_review:true,confirmation:null};
 else if(url.includes('/agreements?')||url.includes('/drafts?')||url.includes('/sources?'))data=[];
 else return Response.json({detail:'Unexpected synthetic read'},{status:404});
 return Response.json(data);
};
})();`
try {
  await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable')
  await send('Network.setBlockedURLs', { urls: ['*paypal.com*'] })
  await send('Page.addScriptToEvaluateOnNewDocument', { source: fixtures })
  await send('Page.navigate', { url: (process.env.FRONTEND_URL || 'http://127.0.0.1:5173')+'/?regression=sdk-'+Date.now()+'#bookings' })
  await until(`document.querySelector('.row-action')`)
  await evaluate(`document.querySelector('.row-action').click()`)
  await until(`document.querySelector('.tabs button:last-child')`)
  await evaluate(`document.querySelector('.tabs button:last-child').click()`)
  await until(`document.querySelector('.workspace-host:not([hidden]) .workspace h2')?.textContent==='Sandbox checkout'&&!document.querySelector('.workspace-host:not([hidden]) .workspace').matches('[aria-busy=true]')`)
  await evaluate(`window.clickText=text=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text).click()`)
  await evaluate(`(()=>{const input=document.querySelector('.workspace-host:not([hidden]) .workspace label input:not([type=checkbox])');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'Test buyer');input.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await evaluate(`document.querySelector('.workspace-host:not([hidden]) .workspace .check input').click()`)
  await evaluate(`clickText('Approve sandbox checkout')`)
  await until(`window.__writes.length===1&&!document.querySelector('.workspace-host:not([hidden]) .workspace').matches('[aria-busy=true]')`)
  await evaluate(`clickText('Load PayPal sandbox button')`)
  await until(`document.querySelector('paypal-button')&&!document.querySelector('.workspace-host:not([hidden]) .workspace').matches('[aria-busy=true]')`)
  assert(await evaluate(`window.__writes.length===1`), 'SDK initialization does not create an order')
  await evaluate(`document.querySelector('paypal-button').click()`)
  await until(`window.__sdk.order`)
  assert(await evaluate(`typeof window.__sdk.order.orderId==='string'&&window.__sdk.order.orderId==='PAYPALORDER123'`), 'v6 receives the actual PayPal order ID as a string')
  assert(await evaluate(`JSON.stringify(Object.keys(window.__sdk.order))==='["orderId"]'&&window.__sdk.order.orderId!=='LOCAL_ATTEMPT_UUID'`), 'v6 envelope is not a bare string, local attempt ID or whole API response')
  assert(await evaluate(`window.__sdk.url==='https://www.sandbox.paypal.com/web-sdk/v6/core'&&window.__sdk.options.clientId==='SANDBOX_APP_FROM_BACKEND'`), 'sandbox SDK uses backend app identifier')
  assert(await evaluate(`window.__sdk.eligibility.currencyCode==='USD'&&window.__sdk.eligibility.amount==='200.00'&&window.__sdk.options.components[0]==='paypal-payments'`), 'SDK uses stored currency/amount and one-time PayPal component')
  assert(await evaluate(`window.__writes.length===2&&!window.__writes.some(w=>w.url.endsWith('/capture'))`), 'regression never approves/captures a payment')
  assert(exceptions.length === 0, 'no new browser runtime exceptions')
} finally { ws.close() }
