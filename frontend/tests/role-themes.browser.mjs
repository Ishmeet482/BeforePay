import { fixture } from './fixtures/product-fixture.mjs'
import { buyerScreens, merchantScreens } from './role-themes-cases.mjs'
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
function contrast(a,b){const luminance=hex=>{const v=hex.replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};const x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05)}

const noPolicyAction=String.raw`(()=>{const f=window.fetch;window.fetch=(input,options={})=>{if(options.method&&options.method!=='GET'&&String(input).includes('/policy-consistency'))throw Error('Policy consistency action forbidden during this UI audit');return f(input,options)}})();`
async function settle(){await evaluate(`new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))`)}
async function navigate(role='buyer',scenario='ready',home=false){const before=await evaluate('performance.timeOrigin');await send('Page.navigate',{url:origin+'/?case='+scenario+'&themes='+Date.now()+'-'+(++navigation)+(home?'':'#'+(role==='merchant'?'merchant/':'')+'bookings')});await until(`performance.timeOrigin!==${before}`);await until(home?`document.querySelector('.entry-page')`:`document.querySelector('.list-toolbar')&&!document.querySelector('.list-toolbar').textContent.includes('Loading')`);if(!home&&scenario!=='empty')await until(`document.querySelector('.booking-row .state-label')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`);await settle()}
async function open(){await evaluate(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`);await settle()}
async function task(name){await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(name)})).click()`);await until(`!document.querySelector('.workspace-host:not([hidden]) [aria-busy=true]')`);await settle()}
async function shot(name,selector){await evaluate(`scrollTo({top:0,behavior:'instant'})`);await settle();if(selector)await evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});n?.scrollIntoView({block:'center',behavior:'instant'})})()`);await settle();const r=await send('Page.captureScreenshot',{captureBeyondViewport:false});await mkdir('/private/tmp/beforepay-role-themes',{recursive:true});await writeFile('/private/tmp/beforepay-role-themes/'+name+'.png',Buffer.from(r.data,'base64'))}
async function passive(name){assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth&&window.__unexpected.length===0&&window.__writes.length===0`),name+': fits viewport, all reads mocked, no writes or provider actions')}
async function railCheck(name,desktop){assert(await evaluate(`(()=>{const rail=[...document.querySelectorAll('.journey-rail')].find(visible),identity=rail.querySelector('.demo-identity'),buttons=[...identity.querySelectorAll('button')];const a=rail.getBoundingClientRect(),b=identity.getBoundingClientRect();return b.left>=a.left&&b.right<=a.right&&buttons.every(x=>x.getBoundingClientRect().height>=44)&&buttons[0].getBoundingClientRect().right<=buttons[1].getBoundingClientRect().left+1})()`),name+': identity controls stay inside rail with comfortable independent targets');if(desktop)assert(await evaluate(`(()=>{const rail=[...document.querySelectorAll('.journey-rail')].find(visible),a=rail.getBoundingClientRect(),b=rail.querySelector('.demo-identity').getBoundingClientRect();return Math.abs(a.left)<1&&a.width<=252&&a.bottom<=innerHeight+1&&b.bottom<=a.bottom-8&&a.bottom-b.bottom<25})()`),name+': edge-aligned compact sidebar anchors identity at bottom')}
try{
await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+noPolicyAction});
const colours={};
for(const[size,width,height]of[['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]){
 await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:size==='mobile'});
 await navigate('buyer','ready',true);await shot('landing-'+size);await passive('landing '+size);
 for(const role of ['buyer','merchant']){
  await navigate(role,'layoutlist');await shot(role+'-bookings-'+size);await railCheck(role+' dashboard '+size,size==='desktop');
  assert(await evaluate(`document.querySelector('.app-shell').dataset.workspace===${JSON.stringify(role)}&&document.querySelector('.header-role').textContent.toLowerCase().includes(${JSON.stringify(role)})`),role+' '+size+': active role always labelled in sticky header');
  colours[role]=await evaluate(`getComputedStyle(document.querySelector('.app-shell')).getPropertyValue('--accent').trim()`);
  const soft=await evaluate(`getComputedStyle(document.querySelector('.app-shell')).getPropertyValue('--accent-soft').trim()`);assert(contrast(colours[role],'#ffffff')>=4.5&&contrast(colours[role],soft)>=4.5,role+' '+size+': primary and selected-state text meet AA contrast');
  const semantics=await evaluate(`['success','attention','blocked'].map(k=>{const n=document.createElement('span');n.className='status status-'+k;document.querySelector('.app-shell').append(n);const c=getComputedStyle(n).color;n.remove();return c}).join('|')`);colours[role+'Semantics']=semantics;
  assert(await evaluate(`(()=>{const table=document.querySelector('.bookings-table'),hs=[...table.querySelectorAll('thead th')];return getComputedStyle(table.querySelector('tbody tr')).display==='grid'?[...table.querySelector('tbody tr').children].every(c=>!!c.dataset.label):[...table.querySelectorAll('tbody tr')].every(row=>[...row.children].every((c,i)=>Math.abs(c.getBoundingClientRect().left-hs[i].getBoundingClientRect().left)<1))})()`),role+' '+size+': long, missing and paid bookings share aligned columns or labelled stacked rows');await passive(role+' bookings '+size);
  await navigate(role,'changed');await open();
  for(const name of role==='buyer'?buyerScreens:merchantScreens){await task(name);await shot(role+'-'+name.toLowerCase().replaceAll(/[^a-z0-9]+/g,'-')+'-'+size);await passive(role+' '+name+' '+size)}
  await railCheck(role+' booking '+size,size==='desktop');
  assert(await evaluate(`(()=>{const root=document.querySelector('.workspace-host:not([hidden])'),p=[...root.querySelectorAll('p')].find(visible);return !p||parseFloat(getComputedStyle(p).fontSize)>=14})()`),role+' '+size+': supporting prose remains readable');
  await navigate(role,'empty');await passive(role+' empty '+size);await shot(role+'-empty-'+size);
 }
 assert(colours.buyer!==colours.merchant&&colours.buyerSemantics===colours.merchantSemantics,size+': teal/indigo role accents differ while all semantic colours stay identical');
 await navigate('buyer','layoutlong');await open();await task('Agreement');
 assert(await evaluate(`(()=>{const root=document.querySelector('.workspace-host:not([hidden])');return parseFloat(getComputedStyle(root.querySelector('.summary-line p')||root.querySelector('.term-table td')).fontSize)>=16&&[...root.querySelectorAll('.section-editor input:not([type=checkbox]):not([type=radio])')].every(n=>parseFloat(getComputedStyle(n).fontSize)>=16)})()`),size+': agreement values and form inputs use readable sizes');
 await evaluate(`document.querySelector('.section-editor').open=true;fill(document.querySelector('.section-editor input[inputmode=numeric]'),'7');fill(document.querySelector('.condition .reason textarea'),'Retained themed correction reason')`);await task('Sources & draft');await task('Agreement');assert(await evaluate(`document.querySelector('.section-editor input[inputmode=numeric]').value==='7'&&document.querySelector('.condition .reason textarea').value==='Retained themed correction reason'`),size+': unsaved edits and correction reasons retained');await shot('buyer-agreement-long-'+size,'.review-grid');
 await navigate('buyer','stale');await open();await task('Compare booking');await passive('stale comparison '+size);await shot('buyer-stale-'+size,'.comparison-results');
 await navigate('buyer','uncertain');await open();await task('Checkout & receipt');await passive('uncertain payment '+size);await shot('buyer-uncertain-'+size,'.payment-pending');
 await navigate('buyer','paidchanged');await open();await task('Checkout & receipt');await passive('historical receipt '+size);await shot('buyer-receipt-'+size,'.completed-receipt');await shot('buyer-payment-history-'+size,'.payment-history');
 assert(await evaluate(`document.querySelector('.completed-receipt').textContent.includes('USD 200.00')&&!document.querySelector('.completed-receipt').textContent.includes('999.00')`),size+': historical receipt snapshot survives theme changes');
}
await send('Emulation.setDeviceMetricsOverride',{width:1280,height:720,deviceScaleFactor:1,mobile:false});await navigate('merchant');await open();await task('Merchant overview');await railCheck('short desktop',true);await shot('merchant-short-desktop');
assert(await evaluate(`(()=>{const rail=document.querySelector('.booking-session .journey-rail'),tabs=rail.querySelector('.rail-content'),identity=rail.querySelector('.demo-identity');return tabs.getBoundingClientRect().bottom<=identity.getBoundingClientRect().top+1&&rail.scrollHeight<=rail.clientHeight+1})()`),'short desktop: scrolling navigation never overlaps identity');
await send('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});await navigate('merchant','layoutlist');await railCheck('wide desktop',true);await passive('wide dashboard');await shot('merchant-wide-dashboard');
await send('Emulation.setDeviceMetricsOverride',{width:320,height:740,deviceScaleFactor:1,mobile:true});await navigate('buyer');await open();await task('Overview');await passive('narrow 320px overview');await shot('buyer-narrow-overview');
await send('Accessibility.enable');const ax=await send('Accessibility.getFullAXTree');assert(!ax.nodes.some(n=>!n.ignored&&n.role?.value==='button'&&!n.name?.value),'visible controls have accessible names');assert(errors.length===0,'no uncaught browser errors: '+errors.join('; '));console.log(passes+' role-theme browser assertions passed; API/provider fixtures only. Policy-consistency tests/actions excluded.');
}finally{ws.close()}

