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
 const base=window.fetch; let created=null;
 window.__previewMode='ready';
 window.fetch=async(input,options={})=>{
  const path=new URL(String(input),location.origin).pathname;
  if(path==='/api/demo-templates')return Response.json([{key:'camera-quotation',original_text:'SYNTHETIC CAMERA EXAMPLE · Camera quantity 1. No invented test pricing.'},{key:'camera-message',original_text:'SYNTHETIC MESSAGE · Camera accessories as explicitly quoted.'}]);
  if(path==='/api/bookings'&&options.method==='POST') {const body=JSON.parse(options.body);window.__writes.push({path,body});created={id:'new-rental',title:body.title};return Response.json(created,{status:201})}
  if(path==='/api/bookings'&&created)return Response.json([created]);
  if(path.startsWith('/api/bookings/new-rental/')){
   if(path.endsWith('/review'))return Response.json({agreement_id:null,confirmation_current:false,blockers:[],source_ids:[],latest_draft_id:null});
   if(path.endsWith('/checkout/eligibility'))return Response.json({eligible:false,blockers:['current_confirmation_required'],sandbox_configured:false});
   return Response.json([]);
  }
  if(path.endsWith('/cancellation/preview')&&window.__previewMode!=='ready'){
   window.__writes.push({path,body:JSON.parse(options.body)});
   if(window.__previewMode==='error')return Response.json({detail:'Synthetic preview unavailable; no result accepted.'},{status:503});
   return Response.json({status:'needs_clarification',blockers:['reviewed_current_rule_approval_required'],cancellation_at:null,previews:[]});
  }
  return base(input,options);
 };
})();`
const directory = '/private/tmp/beforepay-rental-refinements'
async function screenshot(name) { await ev('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))'); await mkdir(directory, { recursive: true }); const r = await send('Page.captureScreenshot', {}); await writeFile(`${directory}/${name}.png`, Buffer.from(r.data, 'base64')) }
async function nav(scenario, workspace = 'buyer') { await send('Page.navigate', { url: `${origin}/?case=${scenario}&refinement=${++navigation}#${workspace === 'buyer' ? 'bookings' : 'merchant/bookings'}` }); await until(`document.querySelector('.row-action')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`) }
async function open() { await ev(`document.querySelector('.row-action').click()`); await until(`document.querySelector('.tabs')`) }
async function tab(name) { await ev(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(name)})).click()`); if (!name.includes('overview') && name !== 'Overview') await until(`document.querySelector('.workspace-host:not([hidden]) .workspace')?.getAttribute('aria-busy')==='false'`); await ev('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))') }
async function viewport(width, height) { await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 }) }
try {
 await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable'); await send('Network.setBlockedURLs', { urls: ['*paypal.com*','*googleapis.com*'] }); await send('Page.addScriptToEvaluateOnNewDocument', { source: fixture + '\n' + extra });
 for (const [category, title] of [['camera','Camera kit · independent shoot'],['audio','Wireless PA · conference'],['lighting','LED panels · exhibition'],['presentation','Projector & screen · workshop'],['custom','Custom kinetic sculpture · gallery']]) {
  await viewport(category==='custom'?390:1440,1000); await nav('ready'); await ev(`clickText('Create booking')`); await until(`document.querySelector('.create-sheet select')`);
  assert(await ev(`(()=>{const s=document.querySelector('.create-sheet select');s.value=${JSON.stringify(category)};s.dispatchEvent(new Event('change',{bubbles:true}));return s.labels.length===1&&s.options.length===6})()`),category+': labelled category choices');
  await ev(`fill(document.querySelector('.create-sheet input'),${JSON.stringify(title)})`);
  if(category==='camera') {
   await ev(`document.querySelector('.create-sheet select').focus()`);
   await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
   assert(await ev(`document.activeElement===document.querySelector('.create-sheet input')&&getComputedStyle(document.activeElement).outlineStyle!=='none'`),'creation controls follow keyboard order with visible focus');
   await ev(`const category=document.querySelector('.create-sheet select');category.value='audio';category.dispatchEvent(new Event('change',{bubbles:true}))`);
   assert(await ev(`document.querySelector('.create-sheet input').value===${JSON.stringify(title)}`),'changing category preserves custom title');
  }
  assert(await ev(`window.__writes.length===0&&document.querySelector('.create-sheet input').value===${JSON.stringify(title)}`),category+': choice/title add no equipment or evidence');
  if(category==='custom'){await ev(`document.querySelector('.create-sheet').scrollIntoView({block:'center'})`);await screenshot('custom-booking-mobile')}
  await ev(`document.querySelector('.create-sheet form').requestSubmit()`);await until(`location.hash.endsWith('/new-rental')&&visible(document.querySelector('.source-inbox'))`);
  assert(await ev(`window.__writes.length===1&&JSON.stringify(window.__writes[0].body)===JSON.stringify({title:${JSON.stringify(title)}})&&document.querySelector('.booking-heading h1').textContent===${JSON.stringify(title)}&&document.querySelector('.source-intake textarea').value===''`),category+': existing API contract, empty evidence and selected new booking');
  if(category==='camera') {
   assert(await ev(`!!(document.querySelector('.source-intake').compareDocumentPosition(document.querySelector('.source-examples'))&Node.DOCUMENT_POSITION_FOLLOWING)`),'own evidence intake precedes optional synthetic sample');
   await ev(`document.querySelector('.source-examples').open=true;clickText('Load synthetic quotation · form only')`);await until(`document.querySelector('.source-intake textarea').value.startsWith('SYNTHETIC CAMERA')`);
   assert(await ev(`window.__writes.length===1&&document.querySelector('.source-inbox').textContent.includes('No saved sources')`),'camera sample loads form only, without saving or AI');
   await ev(`fill(document.querySelector('.source-intake textarea'),'My unsaved original wording');window.confirm=()=>false;clickText('Load synthetic message · form only')`);
   assert(await ev(`document.querySelector('.source-intake textarea').value==='My unsaved original wording'`),'sample replacement respects discard refusal');
  }
 }
 for(const scenario of ['audio','lighting','presentation','custom']) {
  await viewport(1440,1000);await nav(scenario);await open();await tab('Agreement');
  assert(await ev(`document.querySelector('#title-equipment').closest('.condition').textContent.includes(${JSON.stringify({audio:'Wireless PA system',lighting:'LED lighting panel',presentation:'Laser projector',custom:'kinetic sculpture'}[scenario])})&&!document.querySelector('#title-equipment').closest('.condition').textContent.includes('camera')`),scenario+': saved non-camera terms remain authoritative');
 }
 for(const [size,width,height] of [['desktop',1440,1000],['tablet',820,1180],['mobile',390,844]]) {
  await viewport(width,height);await nav('ready');await open();await tab('Cancellation');
  assert(await ev(`!!document.querySelector('.preview-empty')&&window.__writes.length===0`),size+': honest empty preview, no automatic request');
  await ev(`fill(field('Cancellation date & time'),'2026-11-08T09:00');fill(field('Explicit timezone'),'UTC');clickText('Preview refund')`);await until(`document.querySelector('.refund-result')`);
  assert(await ev(width>1023?`Math.abs(document.querySelector('.cancellation-start').getBoundingClientRect().top-document.querySelector('.cancellation-result').getBoundingClientRect().top)<2`:`document.querySelector('.cancellation-start').getBoundingClientRect().bottom<=document.querySelector('.cancellation-result').getBoundingClientRect().top`),size+': matching card tops or logical stacked order');
  await ev(`document.querySelector('.cancellation-result').scrollIntoView({block:'center'})`);await screenshot(size+'-cancellation-single');
  await ev(`document.querySelector('.cancellation-start input[type=checkbox]').click();clickText('Preview refund')`);await until(`document.querySelectorAll('.refund-result').length===2`);
  assert(await ev(`document.documentElement.scrollWidth<=innerWidth+1&&document.querySelectorAll('.refund-result').length===2`),size+': both named previews expand without overflow');await screenshot(size+'-cancellation-side-by-side');
  await ev(`window.__previewMode='error';clickText('Preview refund')`);await until(`document.querySelector('.preview-empty')?.textContent.includes('No new preview')`);
  assert(await ev(`document.querySelectorAll('.refund-result').length===0&&!!document.querySelector('[role=alert]')`),size+': error clears definite results and stays visible');
  await ev(`window.__previewMode='blocked';clickText('Preview refund')`);await until(`document.querySelector('.cancellation-result').textContent.includes('Needs clarification')`);
  assert(await ev(`document.querySelectorAll('.refund-result').length===0`),size+': blocked result never fabricates money');
  await nav('paid');await open();await tab('Checkout & receipt');await until(`document.querySelector('.completed-receipt')`);
  assert(await ev(`document.querySelector('.receipt-brand img').complete&&document.querySelector('.wordmark').textContent==='BeforePay'&&document.documentElement.scrollWidth<=innerWidth+1`),size+': shared accessible wordmark/receipt SVG and no overflow');
  await ev(`document.querySelector('.completed-receipt').scrollIntoView({block:'start'})`);await screenshot(size+'-receipt');
  if(size==='desktop') {await send('Emulation.setEmulatedMedia',{media:'print'});assert(await ev(`getComputedStyle(document.querySelector('.receipt-brand img')).visibility==='visible'`),'receipt logo remains printable');const pdf=await send('Page.printToPDF',{printBackground:true});await writeFile(directory+'/receipt-print.pdf',Buffer.from(pdf.data,'base64'));await send('Emulation.setEmulatedMedia',{media:''})}
  await nav('ready','merchant');await open();await screenshot(size+'-merchant-overview');await tab('Final proposal');await screenshot(size+'-merchant-proposal');await tab('Merchant policy rules');await screenshot(size+'-merchant-rules');
  assert(await ev(`document.documentElement.scrollWidth<=innerWidth+1`),size+': merchant forms retain responsive width');
 }
 const icon = await ev(`document.querySelector('link[rel=icon]').getAttribute('href')`);
 const svg = await (await fetch(new URL(icon,origin))).text();
 assert(svg.includes('BeforePay BP monogram')&&svg.includes('viewBox="0 0 40 40"')&&Buffer.byteLength(svg)<1024,'favicon uses named lightweight vector monogram');
 await viewport(1440,1000);
 await ev('window.scrollTo(0,0)');
 await ev(`(()=>{const proof=document.createElement('div');proof.id='monogram-proof';proof.style='position:fixed;inset:0;z-index:9999;background:#fffefa;color:#18343d;padding:24px;display:flex;gap:32px;align-items:flex-start';const src=document.querySelector('.brand-mark').src;proof.innerHTML=[16,24,32].map(size=>'<div><img src="'+src+'" width="'+size+'" height="'+size+'" alt="BeforePay BP"><p>'+size+' px</p></div>').join('');document.body.append(proof)})()`);
 await ev('Promise.all([...document.querySelectorAll("#monogram-proof img")].map(img=>img.decode()))');
 await ev('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
 const mark=await send('Page.captureScreenshot',{clip:{x:0,y:0,width:350,height:140,scale:1}});await writeFile(directory+'/monogram-sizes.png',Buffer.from(mark.data,'base64'));
 assert(errors.length===0,'no browser runtime exceptions');console.log(passes+' rental refinement browser checks passed. Synthetic fixtures only.');
} finally { ws.close() }
