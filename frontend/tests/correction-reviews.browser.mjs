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
async function evaluate(expression) { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); await send('Runtime.evaluate',{expression:'window.__enterDemoForRegression?.()',awaitPromise:true,returnByValue:true});return r.result.value }
async function until(expression) { for (let i = 0; i < 120; i++) { if (await evaluate(`Boolean(${expression})`)) return; await new Promise(r => setTimeout(r, 80)) } throw new Error('Timed out: ' + expression) }
let passes = 0, navigation = 0
function assert(ok, name) { if (!ok) throw new Error(name); passes++; console.log('PASS ' + name) }

const correctionFixture=String.raw`
(()=>{
const original=window.fetch;let reviews=[];window.__correctionMode='ready';window.__contextOutdated=false;window.__correctionReads=0;
const sourceCmp=async()=>(await(await original('/api/bookings/b1/comparisons')).json())[0];
const question=async()=>{const cmp=await sourceCmp(),r=cmp.results.find(r=>r.category==='deposit_conditions');return{id:'q1',fingerprint:'f'.repeat(64),comparison_id:'oldc',comparison_fingerprint:'1'.repeat(64),proposal_id:'oldp',proposal_fingerprint:'3'.repeat(64),category:'deposit_conditions',created_at:'2026-11-04T09:00:00Z',stale:true,stale_reasons:['merchant_booking_changed'],output:{status:'suggested',question:'Will the merchant restore the refundable USD 80 deposit?',explanation:'The original saved merchant proposal changed refundability.'},supporting_terms:[{term_id:'agreement:0',side:'agreement',text:r.agreement_terms[0].value,origin:'source_supported',citations:r.agreement_terms[0].citations},{term_id:'proposal:0',side:'proposal',text:'The USD 80 deposit is non-refundable.',origin:'merchant_entered',citations:[]}]}};
const replies=()=>[{id:'reply1',fingerprint:'e'.repeat(64),merchant_label:'Demo merchant desk',response:'I have saved a corrected proposal. Please review its exact terms.',created_at:'2026-11-04T09:10:00Z',identity_provisional:true,stale:true,stale_reasons:['merchant_booking_changed']},...(window.__correctionMode==='ambiguous'?[{id:'reply2',fingerprint:'d'.repeat(64),merchant_label:'Second merchant statement',response:'The newer proposal is the proposed correction, not this statement.',created_at:'2026-11-04T09:12:00Z'}]:[])];
const context=async(replyId)=>{
const q=await question(),cmp=structuredClone(await sourceCmp());cmp.id='c2';cmp.proposal_id='p2';cmp.proposal_fingerprint='2'.repeat(64);cmp.stale=window.__contextOutdated;
const old=structuredClone(cmp);old.id='oldc';old.proposal_id='oldp';old.fingerprint='1'.repeat(64);old.results.find(r=>r.category==='deposit_conditions').status='differs';old.results.find(r=>r.category==='deposit_conditions').proposal_terms=[{value:'The USD 80 deposit is non-refundable.',ambiguous:false,citations:[]}];
const selected=replyId|| (window.__correctionMode==='ambiguous'?null:'reply1');const blockers=window.__contextOutdated?['merchant_booking_changed']:window.__correctionMode==='blocked'?['all_comparison_terms_must_match']:!selected?['select_one_saved_merchant_reply']:[];
return{eligible:!blockers.length,blockers,bindings:{suggestion_id:q.id,suggestion_fingerprint:q.fingerprint,original_comparison_id:'oldc',original_comparison_fingerprint:'1'.repeat(64),agreement_id:'a1',agreement_fingerprint:'a'.repeat(64),confirmation_id:'confirm1',original_proposal_id:'oldp',original_proposal_fingerprint:'3'.repeat(64),proposal_id:'p2',proposal_fingerprint:'2'.repeat(64),comparison_id:'c2',comparison_fingerprint:'c'.repeat(64),reply_id:selected,reply_fingerprint:selected==='reply2'?'d'.repeat(64):'e'.repeat(64)},context_fingerprint:'9'.repeat(64),category:q.category,selected_reply_id:selected,replies:replies(),original:{question:q.output,supporting_terms:q.supporting_terms,comparison:old,proposal_version:1},corrected_proposal:{id:'p2',version:2,content:Object.fromEntries(cmp.results.map(r=>[r.category,r.proposal_terms]))},comparison:cmp};
};
window.fetch=async(input,options={})=>{
const url=new URL(String(input),location.origin),path=url.pathname;
if(path.endsWith('/correction-reviews')){
 if(options.method==='POST'){
  const body=JSON.parse(options.body);window.__writes.push({path,body});await new Promise(r=>setTimeout(r,80));
  if(window.__correctionMode==='stale'||window.__contextOutdated)return Response.json({detail:{code:'correction_review_context_changed'}},{status:409});
  const c=await context(body.bindings.reply_id);if(!c.eligible)return Response.json({detail:{code:'correction_review_blocked',blockers:c.blockers}},{status:409});
  const record={id:'review1',context:c,context_fingerprint:body.context_fingerprint,reviewer_label:body.reviewer_label,note:body.note,identity_provisional:true,fingerprint:'8'.repeat(64),created_at:'2026-11-04T10:00:00Z',stale:false,stale_reasons:[]};if(!reviews.length)reviews=[record];return Response.json(reviews[0],{status:201});
 }
 return Response.json(reviews.map(r=>({...r,stale:window.__contextOutdated,stale_reasons:window.__contextOutdated?['merchant_booking_changed']:[]})));
}
if(path.endsWith('/correction')){window.__correctionReads++;return Response.json(await context(url.searchParams.get('reply_id')))}
if(path.endsWith('/clarifications')){if(options.method==='POST')throw Error('No AI generation in correction review tests');return Response.json([await question()])}
if(path.endsWith('/replies'))return Response.json(replies());
if(options.method&&options.method!=='GET')throw Error('Unexpected correction workflow mutation '+path);
return original(input,options);
};
})();`
async function settle(){await evaluate(`new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))`)}
async function openTask(name){await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes(${JSON.stringify(name)})).click()`);await settle()}
async function navigate(){const before=await evaluate('performance.timeOrigin');await send('Page.navigate',{url:origin+'/?case=missingrules&correctionqa='+Date.now()+'-'+(++navigation)+'#bookings'});await until(`performance.timeOrigin!==${before}`);await until(`document.querySelector('.row-action')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`);await evaluate(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`);await openTask('Compare booking');await until(`document.querySelector('.correction-inbox')?.getAttribute('aria-busy')==='false'`);await settle()}
async function review(mode='ready'){await evaluate(`window.__correctionMode=${JSON.stringify(mode)};clickText('Review correction')`);await until(`document.querySelector('.correction-review-content')&&document.querySelector('.correction-review').getAttribute('aria-busy')==='false'`);await settle()}
async function fillReview(){await evaluate(`fill(field('Reviewer label (provisional)'),'Demo buyer reviewer');fill(field('Review note'),'Reviewed exact supporting terms, corrected proposal and saved comparison.')`);await settle()}
async function screenshot(name){await evaluate(`scrollTo({top:0,behavior:'instant'})`);await settle();const m=await send('Page.getLayoutMetrics'),r=await send('Page.captureScreenshot',{captureBeyondViewport:true,clip:{x:0,y:0,width:m.cssContentSize.width,height:m.cssContentSize.height,scale:1}});await mkdir('/private/tmp/beforepay-correction-reviews',{recursive:true});await writeFile('/private/tmp/beforepay-correction-reviews/'+name+'.png',Buffer.from(r.data,'base64'))}
try{
await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+correctionFixture});
for(const[size,width,height]of[['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]){
 await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:size==='mobile'});await navigate();
 assert(await evaluate(`window.__writes.length===0&&window.__correctionReads===0&&!!document.querySelector('.correction-inbox')`),size+': matching comparison retains original question; no automatic review or generation');
 await review();assert(await evaluate(`['Original discrepancy','Merchant response—not verified resolution','Corrected proposal','Fresh saved comparison'].every(t=>document.querySelector('.correction-context').textContent.includes(t))&&document.querySelector('.correction-context').textContent.includes('non-refundable')&&document.querySelector('.correction-context').textContent.includes('refunded on cancellation')`),size+': review shows exact original, reply, correction and fresh comparison together');
 assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>visible(b)&&b.textContent==='Record correction reviewed').disabled`),size+': explicit reviewer and note required');
 await fillReview();await openTask('Sources & draft');await openTask('Compare booking');assert(await evaluate(`field('Review note').value.startsWith('Reviewed exact')&&field('Reviewer label (provisional)').value==='Demo buyer reviewer'`),size+': unsaved review survives normal navigation');
 await evaluate(`document.querySelector('.correction-review-form').requestSubmit();document.querySelector('.correction-review-form').requestSubmit()`);await until(`document.querySelector('.correction-record')&&document.querySelector('.correction-review').getAttribute('aria-busy')==='false'`);await settle();
 assert(await evaluate(`window.__writes.length===1&&window.__writes[0].body.bindings.suggestion_id==='q1'&&window.__writes[0].body.bindings.comparison_id==='c2'&&window.__writes[0].body.bindings.original_comparison_id==='oldc'&&window.__writes[0].body.bindings.reply_id==='reply1'&&window.__writes[0].body.context_fingerprint==='9'.repeat(64)`),size+': one explicit save carries exact context, no duplicate click');
 assert(await evaluate(`document.querySelector('.correction-record').textContent.includes('Correction reviewed for these versions—not checkout approval.')&&document.querySelector('.correction-record').textContent.includes('provisional label')&&[...document.querySelectorAll('button')].find(b=>visible(b)&&b.textContent==='Record correction reviewed').disabled`),size+': immutable outcome distinguished from approval; repeat save disabled');
 await screenshot('buyer-'+size);
 await evaluate(`clickText('Switch role');new Promise(r=>setTimeout(()=>{document.querySelector('input[name=demo-role][value=merchant]').click();r()},80))`);await until(`sessionStorage.getItem('beforepay:demo-role')==='merchant'`);await openTask('Clarification replies');await until(`document.querySelector('.merchant-question')`);await evaluate(`document.querySelector('.merchant-question').open=true`);await until(`!!document.querySelector('.merchant-clarifications .correction-record')`);
 assert(await evaluate(`!!document.querySelector('.merchant-clarifications .correction-record')&&!document.querySelector('.merchant-clarifications .correction-review-form')`),size+': same review visible read-only in Merchant workspace');await screenshot('merchant-'+size);
 await evaluate(`window.__contextOutdated=true;window.dispatchEvent(new Event('contextkey:changed'))`);await settle();assert(await evaluate(`document.querySelector('.merchant-clarifications .correction-record .status').textContent.includes('Outdated')`),size+': saved-input change removes current label without rewriting history');
 await evaluate(`clickText('Refresh correction history')`);await until(`document.querySelector('.merchant-clarifications .correction-review').getAttribute('aria-busy')==='false'`);assert(await evaluate(`document.querySelector('.merchant-clarifications .correction-record .status').textContent.includes('Outdated')&&window.__writes.length===1&&window.__unexpected.length===0&&document.documentElement.scrollWidth<=innerWidth`),size+': server stale history retained; no approvals/payments or overflow');
}
await navigate();await review('blocked');assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>visible(b)&&b.textContent==='Record correction reviewed').disabled&&document.querySelector('.correction-review-content').textContent.includes('Resolve remaining differences')&&window.__writes.length===0`),'remaining discrepancies block review with concrete explanation');
await navigate();await review('ambiguous');assert(await evaluate(`field('Merchant reply reviewed').value===''&&[...document.querySelectorAll('button')].find(b=>visible(b)&&b.textContent==='Record correction reviewed').disabled`),'multiple replies require explicit selection');await evaluate(`const s=field('Merchant reply reviewed');s.value='reply2';s.dispatchEvent(new Event('change',{bubbles:true}))`);await until(`document.querySelector('.correction-context').textContent.includes('Second merchant statement')`);assert(await evaluate(`field('Merchant reply reviewed').value==='reply2'`),'selected exact reply shown in context');
await navigate();await review();await fillReview();await evaluate(`window.__correctionMode='stale';document.querySelector('.correction-review-form').requestSubmit()`);await until(`!!document.querySelector('.correction-review [role=alert]')`);assert(await evaluate(`field('Review note').value.startsWith('Reviewed exact')&&!document.querySelector('.correction-record')&&window.__writes.length===1`),'stale submission retains note and shows no invented success or retry');
await send('Accessibility.enable');const ax=await send('Accessibility.getFullAXTree');assert(!ax.nodes.some(n=>!n.ignored&&n.role?.value==='button'&&!n.name?.value),'correction controls have accessible names');assert(errors.length===0,'no uncaught browser errors: '+errors.join('; '));console.log(passes+' correction-review browser assertions passed; APIs/providers mocked.');
}finally{ws.close()}

