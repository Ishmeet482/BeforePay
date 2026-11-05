// Every API/provider response below is synthetic; no development API proxy.
import { fixture } from './fixtures/product-fixture.mjs'
const origin = process.env.FRONTEND_URL || 'http://127.0.0.1:5187'
const cdp = process.env.CDP_URL || 'http://127.0.0.1:9228'
if (![origin,cdp].every(url=>['127.0.0.1','localhost'].includes(new URL(url).hostname))) throw Error('Local QA only')
const targets=await(await fetch(cdp+'/json')).json()
const target=targets.find(t=>t.type==='page'&&(!process.env.CDP_TARGET_ID||t.id===process.env.CDP_TARGET_ID))
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>{ws.onopen=r})
let serial=0,passed=0;const pending=new Map()
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}}
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value}
async function until(expression){for(let n=0;n<120;n++){if(await evaluate(`Boolean(${expression})`))return;await new Promise(r=>setTimeout(r,80))}throw Error('Timed out: '+expression)}
function check(value,label){if(!value)throw Error(label);passed++;console.log('PASS '+label)}
const publicFixture=String.raw`
(()=>{const base=window.fetch;window.__publicActions=[];window.fetch=async(input,options={})=>{
const path=new URL(String(input),location.origin).pathname;
if(path.endsWith('/checkout/eligibility')){const r=await base(input,options),data=await r.json();return Response.json({...data,payment_execution_allowed:false,sandbox_configured:false,payment_notice:'Payments and provider reconciliation are disabled in the public demo. Existing receipts are historical captures only.'})}
if(options.method==='POST'&&['/drafts','/comparisons','/clarifications','/policy-consistency','/rules/propose'].some(s=>path.endsWith(s))){window.__publicActions.push(path);return Response.json({detail:{code:'demo_ai_budget_exhausted',message:'Shared daily AI allowance exhausted. Continue manual review; no automatic retry or fallback. Saved work remains available.'}},{status:429})}
return base(input,options)};})();`
async function navigate(scenario='ready'){
 const before=await evaluate('performance.timeOrigin');await send('Page.navigate',{url:origin+'/?case='+scenario+'&publicqa='+Date.now()+'#bookings/b1'});await until(`performance.timeOrigin!==${before}&&document.querySelector('.tabs')`)
 await until(`document.querySelector('.next-action')`)
}
async function tab(name){await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(name)})).click()`);await until(`document.querySelector('.workspace-host:not([hidden]) .workspace')?.getAttribute('aria-busy')==='false'`)}
async function quota(label){const before=await evaluate('window.__publicActions.length');await evaluate(`clickText(${JSON.stringify(label)})`);await until(`window.__publicActions.length===${before+1}&&document.querySelector('.workspace-host:not([hidden]) [role=alert]')?.textContent.includes('Shared daily AI allowance exhausted')`);await evaluate(`new Promise(r=>setTimeout(r,180))`);check(await evaluate(`window.__publicActions.length===${before+1}`),label+': readable quota explanation, no automatic retry')}
try{
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+publicFixture})
 for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:name==='mobile'});await navigate();await tab('Checkout & receipt')
  await until(`document.querySelector('.checkout-workspace')?.getAttribute('aria-busy')==='false'`)
  check(await evaluate(`document.querySelector('.checkout-workspace').textContent.includes('disabled in the public demo')&&!document.querySelector('.checkout-workspace').textContent.includes('Set backend sandbox credentials')`),name+': public payment policy shown without credential setup instruction')
  check(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Load PayPal sandbox button')?.disabled&&!document.querySelector('script[src*=paypal]')&&!document.querySelector('.completed-receipt')`),name+': SDK disabled, no fabricated receipt')
  check(await evaluate(`document.documentElement.scrollWidth<=innerWidth&&window.__writes.length===0`),name+': no overflow or automatic writes')
  await navigate('uncertain');await tab('Checkout & receipt')
  check(await evaluate(`[...document.querySelectorAll('.payment-attempt-actions button')].filter(b=>b.textContent.includes('PayPal status')||b.textContent.includes('Retry capture')).every(b=>b.disabled)&&document.querySelector('.payment-attempt').textContent.includes('not paid')`),name+': uncertain result stays visible, provider reconciliation/retry disabled')
  await navigate('paid');await tab('Checkout & receipt')
  check(await evaluate(`!!document.querySelector('.completed-receipt')&&document.querySelector('.completed-receipt').textContent.includes('200.00')&&window.__writes.length===0`),name+': existing synthetic historical receipt preserved, no new capture')
 }
 await navigate('changed');await tab('Sources & draft');await evaluate(`document.querySelectorAll('.saved-source .check input').forEach(e=>e.click())`);await quota('Generate AI draft')
 await tab('Compare booking');await quota('Compare bookings · may use AI');await quota('Suggest clarification')
 await tab('Cancellation');await evaluate(`document.querySelector('.rule-workbench').open=true;fill(field('Your name / reviewer label'),'Retained synthetic reviewer')`);await quota('Propose rules with AI');await quota('Check policy consistency')
 check(await evaluate(`field('Your name / reviewer label').value==='Retained synthetic reviewer'&&window.__writes.length===0&&window.__unexpected.length===0`),'quota failures retain reviewer input and never save/approve/payment implicitly')
 console.log(`${passed} public-demo UI assertions passed; providers mocked/blocked.`)
}finally{ws.close()}
