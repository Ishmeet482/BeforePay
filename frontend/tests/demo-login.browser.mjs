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



const out='/private/tmp/beforepay-demo-entry'
async function settle(){await evaluate(`new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))`)}
async function screenshot(name){await settle();await new Promise(r=>setTimeout(r,250));const r=await send('Page.captureScreenshot',{captureBeyondViewport:false});await mkdir(out,{recursive:true});await writeFile(out+'/'+name+'.png',Buffer.from(r.data,'base64'))}
async function navigate(scenario='ready',hash=''){
 const oldOrigin=await evaluate('performance.timeOrigin');await send('Page.navigate',{url:origin+'/?demo-entry=1&case='+scenario+'&qa='+(++navigation)+hash});await until(`performance.timeOrigin!==${oldOrigin}`);await until(`!!document.querySelector('.entry-page,.bookings-page:not([hidden])')`);await settle()
}
async function clearSession(){await evaluate(`sessionStorage.removeItem('beforepay:demo-role')`)}
async function login(role){await until(`document.querySelector('.demo-login')?.open`);await evaluate(`(()=>{const d=document.querySelector('.demo-login');d.querySelector('input[value=${role}]').click();fill(d.querySelector('#demo-username'),'${role}.demo');fill(d.querySelector('#demo-password'),'${role==='buyer'?'BuyerDemo123!':'MerchantDemo123!'}');d.querySelector('form').requestSubmit()})()`);await until(`!document.querySelector('.demo-login')&&sessionStorage.getItem('beforepay:demo-role')==='${role}'`);await settle()}
async function tab(name){await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(name)})).click()`);await until(`document.querySelector('.workspace-host:not([hidden]) .workspace')?.getAttribute('aria-busy')==='false'`);await settle()}
async function switchRole(role){await evaluate(`document.querySelector('.booking-session:not([hidden]) .demo-identity button:first-child, .dashboard-layout:not([hidden]) .demo-identity button:first-child').click()`);await login(role)}
async function keyboard(key,shift=false){await send('Input.dispatchKeyEvent',{type:'keyDown',key,code:key,windowsVirtualKeyCode:key==='Tab'?9:27,modifiers:shift?8:0});await send('Input.dispatchKeyEvent',{type:'keyUp',key,code:key,windowsVirtualKeyCode:key==='Tab'?9:27,modifiers:shift?8:0})}
async function passive(name){assert(await evaluate(`window.__writes.length===0&&window.__unexpected.length===0`),name+': no writes or unmocked API requests');assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),name+': no viewport overflow')}
try {
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture})
 await navigate();await clearSession();await navigate()
 for(const [size,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]) {
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:size==='mobile'});await clearSession();await navigate()
  assert(await evaluate(`[...document.querySelector('.public-header .global-nav').children].map(e=>e.textContent).join('|')==='How it works|Log in'&&document.querySelector('.entry-actions .secondary').textContent==='Log in by role'`),size+': public bar and role entry are concise')
  assert(await evaluate(`window.__reads.length===0&&window.__writes.length===0`),size+': public entry makes no API calls');await screenshot('public-entry-'+size)
  await evaluate(`document.querySelector('.login-entry').focus();document.querySelector('.login-entry').click()`);await until(`document.querySelector('.demo-login')?.open`)
  assert(await evaluate(`document.querySelector('.demo-login').contains(document.activeElement)&&document.querySelector('.demo-login').textContent.includes('Demo login—no real authentication. Use demo credentials only.')&&document.querySelector('.demo-credentials').textContent.includes('merchant.demo')`),size+': modal focuses inside and discloses both demo identities')
  const focused=await evaluate(`document.activeElement.value`);assert(focused==='buyer',size+': role selector receives initial focus')
  for(let i=0;i<18;i++)await keyboard('Tab');assert(await evaluate(`document.querySelector('.demo-login').contains(document.activeElement)`),size+': Tab remains inside native modal')
  await keyboard('Tab',true);assert(await evaluate(`document.querySelector('.demo-login').contains(document.activeElement)`),size+': Shift-Tab remains inside native modal')
  await screenshot('login-modal-'+size)
  await keyboard('Escape');await until(`!document.querySelector('.demo-login')`);assert(await evaluate(`document.activeElement===document.querySelector('.login-entry')`),size+': Escape closes and restores opener focus')
  await evaluate(`document.querySelector('.entry-actions .secondary').click()`);await until(`document.querySelector('.demo-login')?.open`);await evaluate(`document.querySelector('.demo-login form').requestSubmit()`)
  assert(await evaluate(`document.querySelector('#demo-login-error').textContent.includes('Enter the demo username')&&document.activeElement.id==='demo-username'`),size+': required username validation is specific and focused')
  await evaluate(`fill(document.querySelector('#demo-username'),'buyer.demo');document.querySelector('.demo-login form').requestSubmit()`)
  assert(await evaluate(`document.querySelector('#demo-login-error').textContent.includes('demo password')&&document.activeElement.id==='demo-password'`),size+': required password validation is specific and focused')
  await evaluate(`fill(document.querySelector('#demo-password'),'WrongDemoValue');document.querySelector('.demo-password-label button').click()`)
  assert(await evaluate(`document.querySelector('#demo-password').type==='text'&&document.querySelector('.demo-password-label button').getAttribute('aria-pressed')==='true'`),size+': show-password control works')
  await evaluate(`document.querySelector('.demo-password-label button').click();document.querySelector('.demo-login form').requestSubmit()`)
  assert(await evaluate(`document.querySelector('#demo-password').type==='password'&&document.querySelector('#demo-password').value===''&&document.querySelector('#demo-login-error').textContent.includes('do not match')&&sessionStorage.getItem('beforepay:demo-role')===null&&window.__reads.length===0`),size+': invalid credentials clear password and make no request/session')
  await login('buyer');await until(`document.querySelector('.booking-row .state-label')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`)
  assert(await evaluate(`document.querySelector('.bookings-page h1').textContent==='Buyer dashboard'&&document.querySelector('.dashboard-guide').textContent.includes('Evidence and agreement review')&&document.querySelector('.dashboard-sidebar .demo-identity').textContent.includes('Buyer Demo')&&document.querySelector('.bookings-table thead').textContent.includes('Inclusive total')`),size+': Buyer dashboard foregrounds review, payment, actual booking status and identity')
  assert(await evaluate(`JSON.stringify(Object.entries(sessionStorage))==='[["beforepay:demo-role","buyer"]]'&&Object.values(localStorage).every(v=>!String(v).includes('BuyerDemo123!')&&!String(v).includes('WrongDemoValue'))`),size+': tab storage contains selected role only')
  await screenshot('buyer-dashboard-'+size);await passive('buyer dashboard '+size)
  await evaluate(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`);await tab('Agreement');await evaluate(`document.querySelector('.section-editor').open=true;fill(document.querySelector('.section-editor input[inputmode=numeric]'),'8');fill(document.querySelector('.condition .reason textarea'),'Retain demo-switch correction')`)
  await switchRole('merchant');await until(`document.querySelector('.rail-caption').textContent.includes('MERCHANT')`)
  assert(await evaluate(`location.hash==='#merchant/bookings/b1'&&document.querySelector('.booking-session .demo-identity').textContent.includes('Merchant Demo')&&!document.querySelector('.workspace-host:not([hidden]) .confirm-panel')`),size+': role switch preserves booking identity and changes task navigation')
  await tab('Final proposal');await evaluate(`fill(field('Merchant name / provisional label'),'Retained demo merchant');fill(field('Reason / proposal note'),'Demo switch reason')`)
  await switchRole('buyer');await until(`visible(document.querySelector('.conditions'))`)
  assert(await evaluate(`document.querySelector('.section-editor input[inputmode=numeric]').value==='8'&&document.querySelector('.condition .reason textarea').value==='Retain demo-switch correction'`),size+': buyer unsaved correction survives demo role login')
  await switchRole('merchant');assert(await evaluate(`field('Merchant name / provisional label').value==='Retained demo merchant'&&field('Reason / proposal note').value==='Demo switch reason'`),size+': merchant unsaved editor survives return login')
  await evaluate(`document.querySelector('.back-link').click()`);await until(`visible(document.querySelector('.bookings-page'))`)
  assert(await evaluate(`document.querySelector('.bookings-page h1').textContent==='Merchant dashboard'&&document.querySelector('.dashboard-guide').textContent.includes('Merchant policy preparation')&&document.querySelector('.bookings-table thead').textContent.includes('Buyer agreement')&&document.querySelector('.bookings-table thead').textContent.includes('Merchant proposal / rules')`),size+': Merchant dashboard has distinct preparation workflow and saved-state columns')
  await screenshot('merchant-dashboard-'+size);await passive('merchant dashboard '+size)
  await evaluate(`document.querySelector('.dashboard-sidebar .demo-identity button:first-child').click()`);await until(`document.querySelector('.demo-login')?.open`);await evaluate(`document.querySelector('input[value=buyer]').click();fill(document.querySelector('#demo-username'),'merchant.demo');fill(document.querySelector('#demo-password'),'MerchantDemo123!');document.querySelector('.demo-login form').requestSubmit()`)
  assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')==='merchant'&&location.hash==='#merchant/bookings'&&document.querySelector('#demo-login-error').textContent.includes('Buyer demo')`),size+': other-role credentials never change active identity')
  await keyboard('Escape');await until(`!document.querySelector('.demo-login')`)
  await evaluate(`window.confirm=()=>false;document.querySelector('.dashboard-sidebar .demo-identity button:last-child').click()`)
  assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')==='merchant'&&visible(document.querySelector('.bookings-page'))`),size+': rejecting sign-out warning preserves session and forms')
  await evaluate(`window.confirm=()=>true;document.querySelector('.dashboard-sidebar .demo-identity button:last-child').click()`);await until(`document.querySelector('.entry-page')&&!document.querySelector('.booking-session .journey-layout')`)
  await until(`document.activeElement===document.querySelector('.login-entry')`);assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')===null&&location.hash===''&&document.activeElement===document.querySelector('.login-entry')`),size+': sign-out clears demo identity, unmounts warned forms and returns home')
  await passive('sign out '+size)
 }
 // Direct URLs and reloads do not establish real authentication or bypass demo entry.
 await navigate('ready','#merchant/bookings/b1');await until(`document.querySelector('.demo-login')?.open`);assert(await evaluate(`window.__reads.length===0&&document.querySelector('input[value=merchant]').checked`),'direct unauthenticated link requests demo role before any booking reads')
 await login('merchant');await until(`document.querySelector('.merchant-overview')`);const previousOrigin=await evaluate('performance.timeOrigin');await send('Page.reload');await until(`performance.timeOrigin!==${previousOrigin}`);await until(`document.querySelector('.merchant-overview')`)
 assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')==='merchant'&&!document.querySelector('.demo-login')`),'tab reload retains demo identity without password or revalidation')
 await evaluate(`document.querySelector('.wordmark').click()`);await until(`document.querySelector('.entry-page')`);await evaluate(`document.querySelector('.login-entry').click()`);await until(`document.querySelector('.demo-login')?.open`);await evaluate(`fill(document.querySelector('#demo-password'),'TransientOnly');document.querySelector('[aria-label="Close demo login"]').click()`);await evaluate(`document.querySelector('.login-entry').click()`);await until(`document.querySelector('.demo-login')?.open`)
 assert(await evaluate(`document.querySelector('#demo-password').value===''&&document.querySelector('#demo-username').value===''`),'closing/reopening never retains typed credentials')
 await send('Accessibility.enable');const ax=await send('Accessibility.getFullAXTree');assert(!ax.nodes.some(n=>!n.ignored&&['button','textbox','radio','combobox'].includes(n.role?.value)&&!n.name?.value),'modal interactive controls have accessible names')
 await keyboard('Escape');await until(`!document.querySelector('.demo-login')`)
 await navigate('layoutlist','#merchant/bookings');await until(`document.querySelectorAll('.booking-row').length===3&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`)
 assert(await evaluate(`document.querySelectorAll('.booking-row').length===3&&document.documentElement.scrollWidth<=innerWidth&&document.querySelectorAll('.booking-row td[data-label="Merchant proposal / rules"]').length===3`),'long, missing and paid merchant bookings share labelled responsive columns');await evaluate(`(()=>{const r=document.querySelector('.bookings-page .booking-table').getBoundingClientRect();window.scrollTo({top:scrollY+r.top-document.querySelector('.app-header').getBoundingClientRect().height-16,behavior:'instant'})})()`);await screenshot('merchant-long-bookings-mobile')
 await clearSession();await navigate();await evaluate(`document.querySelector('.login-entry').click()`);await until(`document.querySelector('.demo-login')?.open`);await evaluate(`fill(document.querySelector('#demo-password'),'TransientBackdropValue')`)
 await send('Input.dispatchMouseEvent',{type:'mousePressed',x:5,y:5,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:5,y:5,button:'left',clickCount:1});await until(`!document.querySelector('.demo-login')`)
 assert(await evaluate(`sessionStorage.getItem('beforepay:demo-role')===null&&window.__reads.length===0`),'backdrop dismisses without identity, password persistence or requests')
 await evaluate(`document.querySelector('.entry-actions .primary').click()`);await login('buyer');await until(`document.activeElement===document.querySelector('.create-sheet input')`)
 assert(await evaluate(`location.hash==='#bookings/new'&&document.querySelector('.create-sheet input').value===''&&window.__writes.length===0`),'logged-out Start a booking logs into demo then focuses an empty creation form without a write')
 await evaluate(`sessionStorage.setItem('beforepay:demo-role','unsupported')`);await navigate('ready','#bookings');await until(`document.querySelector('.demo-login')?.open`)
 assert(await evaluate(`window.__reads.length===0&&!document.querySelector('.booking-session .journey-layout')`),'unrecognised stored role never opens booking data')
 await evaluate(`sessionStorage.removeItem('beforepay:demo-role');window.__originalStorageSet=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('Synthetic storage disabled')};document.querySelector('input[value=buyer]').click();fill(document.querySelector('#demo-username'),'buyer.demo');fill(document.querySelector('#demo-password'),'BuyerDemo123!');document.querySelector('.demo-login form').requestSubmit()`)
 await until(`!document.querySelector('.demo-login')&&visible(document.querySelector('.bookings-page'))`)
 assert(await evaluate(`document.body.innerText.includes('Tab storage is unavailable')&&sessionStorage.getItem('beforepay:demo-role')===null&&window.__writes.length===0`),'disabled tab storage gives explicit memory-only demo session without passwords or writes')
 await evaluate(`Storage.prototype.setItem=window.__originalStorageSet`)
 assert(errors.length===0,'no uncaught demo-login exceptions: '+errors.join('; '));console.log(passes+' demo entry assertions passed; providers blocked; passwords never persisted or sent.')
}finally{ws.close()}
