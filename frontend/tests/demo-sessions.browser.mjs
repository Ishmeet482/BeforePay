// Session lifecycle is mocked here; cookie/DB enforcement is tested by pytest.
import { fixture } from './fixtures/product-fixture.mjs'
const origin = process.env.FRONTEND_URL || 'http://127.0.0.1:5187'
const cdp = process.env.CDP_URL || 'http://127.0.0.1:9228'
if (![origin, cdp].every(url => ['localhost', '127.0.0.1'].includes(new URL(url).hostname))) throw Error('Local QA only')
const targets = await (await fetch(cdp + '/json')).json()
const target = targets.find(t => t.type === 'page' && (!process.env.CDP_TARGET_ID || t.id === process.env.CDP_TARGET_ID))
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise(resolve => { ws.onopen = resolve })
let serial = 0, passed = 0
const pending = new Map()
ws.onmessage = event => { const m = JSON.parse(event.data); if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result) } }
function send(method, params = {}) { return new Promise((resolve, reject) => { const id = ++serial; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let n = 0; n < 120; n++) { if (await evaluate(`Boolean(${expression})`)) return; await new Promise(r => setTimeout(r, 80)) } throw Error('Timed out: ' + expression) }
function check(value, message) { if (!value) throw Error(message); passed++; console.log('PASS ' + message) }
const sessionFixture = String.raw`
(() => {
 sessionStorage.removeItem('beforepay:demo-role');
 let active=false, generation=0;
 const base=window.fetch;window.__sessionCalls=[];window.__denySessions=false;window.__expireSession=()=>{active=false};window.__csrfSeen=[];
 const description=()=>({active:true,csrf_token:(generation%2?'a':'b').repeat(64),expires_at:new Date(Date.now()+2592000000).toISOString()});
 const missing=()=>Response.json({detail:{code:'demo_session_required',message:'Demo session expired. Unsaved inputs are retained. Enter the demo explicitly.'}},{status:401});
 window.fetch=async(input,options={})=>{
  if(String(input)==='/api/demo-sessions'){
   const method=options.method||'GET';window.__sessionCalls.push({method,body:options.body??null,headers:Object.fromEntries(new Headers(options.headers))});
   if(window.__denySessions)return Response.json({detail:'Synthetic session outage'},{status:503});
   if(method==='DELETE'){active=false;return new Response(null,{status:204})}
   if(method==='POST'){if(!active)generation++;active=true;return Response.json(description(),{status:201})}
   return active?Response.json(description()):missing();
  }
  if(!active)return missing();
  if(options.method&&options.method!=='GET')window.__csrfSeen.push(new Headers(options.headers).get('X-BeforePay-CSRF'));
  return base(input,options);
 };
})();`
async function login(role='buyer') {
  await until(`document.querySelector('.demo-login')?.open`)
  await evaluate(`(()=>{const d=document.querySelector('.demo-login');d.querySelector('input[value=${role}]').click();fill(d.querySelector('#demo-username'),'${role}.demo');fill(d.querySelector('#demo-password'),'${role==='buyer'?'BuyerDemo123!':'MerchantDemo123!'}');d.querySelector('form').requestSubmit()})()`)
}
try {
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable')
 await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']})
 await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+sessionFixture})
 await send('Page.navigate',{url:origin+'/?demo-entry=1&case=firsttime'})
 await until(`document.querySelector('.entry-page')`)
 check(await evaluate(`window.__sessionCalls.length===0`),'public page never issues a session automatically')
 await evaluate(`document.querySelector('.entry-actions .primary').click()`);await login()
 await until(`!document.querySelector('.demo-login')&&document.querySelector('.create-sheet input')&&document.querySelector('.list-toolbar span')?.textContent.includes('0 saved')`)
 check(await evaluate(`window.__sessionCalls.map(c=>c.method).join(',')==='GET,POST'`),'explicit demo entry creates exactly one isolated session')
 check(await evaluate(`window.__sessionCalls.every(c=>c.body===null)&&Object.keys(sessionStorage).join(',')==='beforepay:demo-role'`),'credentials and opaque tokens never sent or persisted by frontend')
 await evaluate(`fill(document.querySelector('.create-sheet input'),'Retain this unsaved title');window.__expireSession();window.__denySessions=true;document.querySelector('.dashboard-sidebar .demo-identity button:first-child').click()`)
 await login('merchant');await until(`document.querySelector('#demo-login-error')`)
 check(await evaluate(`document.querySelector('.create-sheet input').value==='Retain this unsaved title'&&sessionStorage.getItem('beforepay:demo-role')==='buyer'`),'session outage keeps current role and unsaved input')
 check(await evaluate(`document.querySelector('#demo-password').value===''`),'session error clears password')
 await evaluate(`window.__denySessions=false;window.confirm=()=>false`);await login('merchant')
 await until(`document.querySelector('#demo-login-error')?.textContent.includes('cancelled')`)
 check(await evaluate(`window.__sessionCalls.filter(c=>c.method==='POST').length===1&&document.querySelector('.create-sheet input').value==='Retain this unsaved title'`),'declining session renewal preserves input and issues no new cookie')
 await evaluate(`window.confirm=()=>true`);await login('buyer')
 await until(`!document.querySelector('.demo-login')&&document.querySelector('.create-sheet input')?.value===''`)
 check(await evaluate(`window.__sessionCalls.filter(c=>c.method==='POST').length===2`),'confirmed renewal opens a new empty workspace')
 await evaluate(`fill(document.querySelector('.create-sheet input'),'Synthetic session-owned booking');document.querySelector('.create-sheet form').requestSubmit()`)
 await until(`location.hash==='#bookings/b1'&&document.querySelector('.tabs button[aria-current=step]')?.textContent.includes('Sources')`)
 check(await evaluate(`window.__csrfSeen.length===1&&window.__csrfSeen[0]==='b'.repeat(64)&&window.__writes.length===1`),'booking creation attaches current session CSRF token exactly once')
 await evaluate(`document.querySelector('.booking-session .demo-identity button:first-child').click()`);await login('merchant')
 await until(`!document.querySelector('.demo-login')&&location.hash==='#merchant/bookings/b1'`)
 check(await evaluate(`window.__sessionCalls.filter(c=>c.method==='POST').length===2&&window.__writes.length===1`),'role switching retains same server session, booking and saved actions')
 await evaluate(`document.querySelector('.booking-session .demo-identity button:first-child').click()`);await login('buyer')
 await until(`!document.querySelector('.demo-login')&&location.hash==='#bookings/b1'`)
 check(await evaluate(`window.__sessionCalls.filter(c=>c.method==='POST').length===2&&window.__writes.length===1`),'switching back to Buyer retains booking without replacing the session')
 await evaluate(`window.__expireSession();document.querySelector('.workspace-host:not([hidden]) .toolbar > button')?.click();window.dispatchEvent(new Event('contextkey:changed'))`)
 await until(`document.body.innerText.includes('Demo session expired')`)
 check(await evaluate(`window.__sessionCalls.filter(c=>c.method==='POST').length===2&&window.__writes.length===1`),'expired API requests never create sessions or retry writes automatically')
 await evaluate(`window.confirm=()=>true;document.querySelector('.booking-session .demo-identity button:last-child').click()`)
 await until(`sessionStorage.getItem('beforepay:demo-role')===null&&location.hash===''`)
 check(await evaluate(`window.__sessionCalls.at(-1).method==='DELETE'&&window.__unexpected.length===0`),'explicit sign-out clears expired cookie without provider or payment calls')
 console.log(`${passed} session lifecycle assertions passed; synthetic providers only.`)
} finally { ws.close() }
