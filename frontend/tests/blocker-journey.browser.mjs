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

// One continuous synthetic booking. Saved state changes only after explicit UI writes.
const journeyFixture = String.raw`
(() => {
 const base = window.fetch; let fresh = false, corrected = false, question = null, replies = [], reviews = [], reports = [], approvedKinds = new Set();
 window.__extraBlockers = [];
 const get = async path => (await base('/api/bookings/b1' + path)).json();
 const proposal = async () => (await get('/merchant-bookings'))[0];
 const comparison = async () => { const cmp = (await get('/comparisons'))[0]; return {...cmp, stale: corrected && !fresh, stale_reasons: corrected && !fresh ? ['merchant_booking_changed'] : []}; };
 const terms = async () => { const cmp = await comparison(); return cmp.results.find(r => r.category === 'deposit_conditions'); };
 const ruleStates = async () => (await get('/cancellation/rules')).map(r=>({...r,approved_current:approvedKinds.has(r.target.kind)}));
 const blocked = async () => [!fresh ? corrected ? 'comparison_stale' : 'comparison_has_differences_or_clarification' : null, ...['agreement','proposal'].filter(kind=>!approvedKinds.has(kind)).map(kind=>kind+'_cancellation_rules_unapproved_stale_or_inconsistent'), ...window.__extraBlockers].filter(Boolean);
 const context = async () => {
  const p = await proposal(), cmp = await comparison();
  return {eligible: fresh && !!replies.length, blockers: !replies.length ? ['saved_merchant_reply_required'] : fresh ? [] : ['all_comparison_terms_must_match'], bindings: {suggestion_id:'q1',suggestion_fingerprint:'f'.repeat(64),original_comparison_id:'c1',original_comparison_fingerprint:'c'.repeat(64),agreement_id:'a1',agreement_fingerprint:'a'.repeat(64),confirmation_id:'confirm1',original_proposal_id:'p1',original_proposal_fingerprint:'b'.repeat(64),proposal_id:p.id,proposal_fingerprint:p.fingerprint,comparison_id:cmp.id,comparison_fingerprint:cmp.fingerprint,reply_id:replies[0]?.id,reply_fingerprint:'e'.repeat(64)},context_fingerprint:'9'.repeat(64),category:'deposit_conditions',original:{question:question?.output,supporting_terms:question?.supporting_terms||[],comparison:window.__originalComparison,proposal_version:1},selected_reply_id:replies[0]?.id,replies,corrected_proposal:p,comparison:cmp};
 };
 window.fetch = async (input, options={}) => {
  const url = new URL(String(input), location.origin), path=url.pathname, write=options.method==='POST';
  if(path.endsWith('/clarifications')) {
   if(write) { const t=await terms(); window.__originalComparison=await comparison(); question={id:'q1',comparison_id:'c1',comparison_fingerprint:'c'.repeat(64),proposal_id:'p1',proposal_fingerprint:'b'.repeat(64),fingerprint:'f'.repeat(64),category:'deposit_conditions',created_at:'2026-11-04T10:00:00Z',output:{status:'suggested',question:'Will you restore the agreed refundable USD 80 deposit?',explanation:'The saved deposit obligations differ.'},supporting_terms:[...t.agreement_terms.map(t=>({term_id:'agreement:0',side:'agreement',text:t.value,origin:'source_supported',citations:t.citations})),...t.proposal_terms.map(t=>({term_id:'proposal:0',side:'proposal',text:t.value,origin:'merchant_entered',citations:[]}))]}; window.__writes.push({path,body:JSON.parse(options.body)}); return Response.json(question,{status:201}); }
   return Response.json(question?[{...question,stale:corrected,stale_reasons:corrected?['merchant_booking_changed']:[]}]:[]);
  }
  if(path.endsWith('/replies')) { if(write) {const body=JSON.parse(options.body);window.__writes.push({path,body});replies=[{id:'reply1',fingerprint:'e'.repeat(64),...body,created_at:'2026-11-04T10:01:00Z',identity_provisional:true}];} return Response.json(write?replies[0]:replies); }
  if(path.endsWith('/correction')) return Response.json(await context());
  if(path.endsWith('/correction-reviews')) { if(write) {const body=JSON.parse(options.body),c=await context();if(!c.eligible)throw Error('Mock correction guard');window.__writes.push({path,body});reviews=[{id:'review1',context:c,context_fingerprint:c.context_fingerprint,reviewer_label:body.reviewer_label,note:body.note,created_at:'2026-11-04T10:02:00Z',identity_provisional:true,fingerprint:'8'.repeat(64),stale:false,stale_reasons:[]}];} return Response.json(write?reviews[0]:reviews); }
  if(path.endsWith('/cancellation/rules') && !write) return Response.json(await ruleStates());
  if(path.endsWith('/confirm') && write) {const r=(await get('/cancellation/rules')).find(r=>path.endsWith('/'+r.id+'/confirm'));approvedKinds.add(r.target.kind);return base(input,options);}
  if(path.endsWith('/policy-consistency/state')) {const p=await proposal();return Response.json({proposal_id:p.id,proposal_fingerprint:p.fingerprint,blockers:window.__extraBlockers.filter(b=>b==='merchant_policy_consistency_requires_clarification')});}
  if(path.endsWith('/policy-consistency')) { if(window.__extraBlockers.includes('merchant_policy_consistency_requires_clarification')) {const p=await proposal(),clauses=['deposit_conditions','cancellation_conditions'].flatMap(category=>p.content[category].map((c,i)=>({clause_id:category+':'+i,category,text:c.value,ambiguous:false})));reports=[{id:'saved-policy-check',proposal_id:p.id,proposal_version:p.version,proposal_fingerprint:p.fingerprint,status:'needs_clarification',created_at:'2026-11-04T10:03:00Z',fingerprint:'7'.repeat(64),model_metadata:null,stale:false,stale_reasons:[],clauses,output:{findings:[{status:'needs_clarification',explanation:'Synthetic saved uncertainty for navigation verification only.',references:clauses.map(c=>({clause_id:c.clause_id,quotation:c.text}))}]}}];} return Response.json(reports); }
  if(path.endsWith('/checkout/eligibility')) { const b=await blocked(),p=await proposal(),cmp=await comparison(),r=await base(input,options),e=await r.json();return Response.json({...e,eligible:!b.length,blockers:b,context:b.length?null:{...e.context,proposal_id:p.id,proposal_version:p.version,proposal_fingerprint:p.fingerprint,comparison_id:cmp.id,comparison_fingerprint:cmp.fingerprint}}); }
  if(path.endsWith('/checkout/approvals') && write && (await blocked()).length) throw Error('Mock checkout guard');
  if(path.endsWith('/merchant-bookings') && write) { const response=await base(input,options);corrected=true;fresh=false;return response; }
  if(path.endsWith('/comparisons')) {
   if(write) {const body=JSON.parse(options.body),p=await proposal();if(body.proposal_id!==p.id)throw Error('Mock exact proposal guard');await base(input,options);fresh=true;}
   const raw=await base(input,write?{}:options),rows=await raw.json();
   const current=rows.map(c=>({...c,stale:corrected&&!fresh,stale_reasons:corrected&&!fresh?['merchant_booking_changed']:[],results:c.results.map(r=>fresh?{...r,status:'matches',proposal_terms:r.agreement_terms}:r)}));
   return Response.json(write?current[0]:current);
  }
  if(write && (/\/orders$|\/capture$|\/rules\/propose$/.test(path))) throw Error('Payment/live AI actions forbidden in this fixture');
  return base(input,options);
 };
})();`
async function task(name) { await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.toLowerCase().includes(${JSON.stringify(name.toLowerCase())})).click()`); await new Promise(r=>setTimeout(r,180)) }
async function click(label) { await evaluate(`clickText(${JSON.stringify(label)})`); await new Promise(r=>setTimeout(r,140)) }
async function role(name) {
 const opened=await send('Runtime.evaluate',{expression:"clickText('Switch role');new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(!!document.querySelector('.demo-login')?.open))))",awaitPromise:true,returnByValue:true});
 assert(opened.result.value,'role handoff opens explicit demo-login modal');
 await evaluate(`document.querySelector('input[name=demo-role][value=${name}]').click()`);
 await until(`sessionStorage.getItem('beforepay:demo-role')===${JSON.stringify(name)}`)
}
async function shot(name) { const r=await send('Page.captureScreenshot',{captureBeyondViewport:false});await mkdir('/private/tmp/beforepay-blocker-journey',{recursive:true});await writeFile('/private/tmp/beforepay-blocker-journey/'+name+'.png',Buffer.from(r.data,'base64')) }
try {
await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*','*generativelanguage*']});
await send('Page.addScriptToEvaluateOnNewDocument',{source:fixture+'\n'+journeyFixture});
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
await send('Page.navigate',{url:origin+'/?case=changed#bookings'});await until(`document.querySelector('.row-action')&&!document.querySelector('.booking-row .state-label').textContent.includes('Checking')`);await evaluate(`document.querySelector('.row-action').click()`);await until(`document.querySelector('.tabs')`);
assert(await evaluate(`(async()=>{const {blockerAction:a}=await import('/src/blocker-actions.ts');return a('comparison_stale','merchant').destination.workspace==='buyer'&&a('proposal_reviewed_cancellation_rules_required','buyer').destination.kind==='proposal'&&a('agreement_reviewed_cancellation_rules_required','merchant').destination.kind==='agreement'&&a('merchant_unknown_policy','buyer').destination===null&&a('reviewed_current_rule_approval_required','buyer').destination===null})()`),'shared mapping preserves roles, source kinds and unknown-source honesty');
await task('Compare booking');await until(`document.querySelector('.clarification-panel')?.getAttribute('aria-busy')==='false'`);await click('Suggest clarification');await until(`document.querySelector('.clarification-result')||document.querySelector('.clarification-panel').textContent.includes('Will you restore')`);
assert(await evaluate(`window.__writes.length===1&&document.querySelector('.clarification-panel').textContent.includes('USD 80')`),'explicit saved-discrepancy suggestion retains exact support');
await role('merchant');await task('Clarification replies');await until(`document.querySelector('.merchant-reply-form')`);await evaluate(`fill(field('Merchant label (provisional)'),'Demo rental desk');fill(field('Response text'),'I will restore the buyer-agreed deposit in a new saved proposal.')`);await click('Save merchant response');await until(`document.querySelector('.merchant-response')`);
assert(await evaluate(`window.__writes.length===2`),'merchant response saved without comparison/rule/checkout approval');
await task('Final proposal');await until(`document.querySelector('.merchant-editor')`);await click('Copy buyer-confirmed terms into form');await evaluate(`fill(field('Merchant name / provisional label'),'Demo rental desk');fill(field('Reason / proposal note'),'Restore the agreed refundable deposit.')`);await click('Save as new merchant version');await until(`window.__writes.some(w=>w.path.endsWith('/merchant-bookings'))`);
await task('Overview');await until(`document.querySelector('.merchant-overview .blocker-list')`);await evaluate(`document.querySelector('.merchant-overview details').open=true`);
assert(await evaluate(`document.querySelector('.merchant-overview').textContent.includes('Switch to Buyer demo view')`),'merchant stale comparison offers explicit Buyer switch');
// Use actual blocker action, not a direct test route.
await evaluate(`[...document.querySelectorAll('.merchant-overview .blocker-list button')].find(b=>b.textContent.includes('Review saved comparison')).click()`);await until(`sessionStorage.getItem('beforepay:demo-role')==='buyer'`);await until(`document.querySelector('.buyer-comparison')&&visible(document.querySelector('.buyer-comparison'))`);
await click('Refresh');await until(`document.querySelector('.comparison-workspace')?.getAttribute('aria-busy')==='false'||!document.querySelector('.toolbar > button').disabled`);
await evaluate(`[...document.querySelectorAll('button')].find(b=>visible(b)&&b.textContent.includes('Compare bookings')).click()`);await until(`document.querySelector('.comparison-results')?.textContent.includes('Saved terms match')`);
await click('Review correction');await until(`document.querySelector('.correction-review-content')`);await evaluate(`fill(field('Reviewer label (provisional)'),'Demo buyer');fill(field('Review note'),'Reviewed exact saved correction and matching comparison.')`);await click('Record correction reviewed');await until(`document.querySelector('.correction-record')`);
await task('Checkout & receipt');await until(`document.querySelector('.checkout-readiness')`);
assert(await evaluate(`!window.__writes.some(w=>w.path.endsWith('/checkout/approvals'))&&document.querySelector('.blocker-list').textContent.includes('agreement')`),'matching comparison and correction review do not approve checkout');
// Add already-saved unapproved rule fixtures via explicit authoring; Buyer first.
await click('Review buyer agreement rules →');await until(`document.querySelector('.rule-workbench')?.open`);assert(await evaluate(`field('Policy source version').value==='agreement'`),'agreement approval blocker selects buyer agreement rule review');await evaluate(`document.querySelector('.rule-workbench').open=true;fill(field('Your name / reviewer label'),'Demo buyer')`);await click('Load 48-hour example · form only');await evaluate(`const cb=[...document.querySelectorAll('.rule-authoring input[type=checkbox]')][0];if(cb.checked)cb.click();fill(field('Reason for this rule version'),'Reviewed source-linked rules.')`);await click('Save rules for review');await until(`document.querySelector('.rule-confirmation')`);
await evaluate(`document.querySelectorAll('.rule-confirmation input[type=checkbox]').forEach(c=>{if(!c.checked)c.click()});fill(document.querySelector('.rule-confirmation textarea'),'Checked exact source and cutoff.')`);await click('Confirm reviewed rules');await evaluate(`fill(field('Cutoff hours'),'47')`);
await task('Checkout & receipt');await click('Refresh');await until(`document.querySelector('.checkout-readiness')`);await click('Switch to Merchant demo view · Review merchant policy rules →');await until(`sessionStorage.getItem('beforepay:demo-role')==='merchant'&&document.querySelector('.workspace-host:not([hidden]) .rule-workbench')?.open`);assert(await evaluate(`field('Policy source version').value==='proposal'`),'merchant approval blocker explicitly switches role and opens proposal rule review');await evaluate(`document.querySelector('.workspace-host:not([hidden]) .rule-workbench').open=true;fill(field('Your name / reviewer label'),'Demo merchant')`);await click('Load 48-hour example · form only');await evaluate(`document.querySelector('.workspace-host:not([hidden]) .rule-authoring input[type=checkbox]').click();fill(field('Reason for this rule version'),'Reviewed corrected merchant policy.')`);await click('Save rules for review');await until(`document.querySelector('.workspace-host:not([hidden]) .rule-confirmation')`);await evaluate(`document.querySelectorAll('.workspace-host:not([hidden]) .rule-confirmation input[type=checkbox]').forEach(c=>{if(!c.checked)c.click()});fill(document.querySelector('.workspace-host:not([hidden]) .rule-confirmation textarea'),'Checked exact merchant source.')`);await click('Confirm reviewed merchant rules');
await role('buyer');await task('Checkout & receipt');await click('Refresh');await until(`document.querySelector('.checkout-readiness').textContent.includes('Backend checks passed')`);
assert(await evaluate(`window.__writes.filter(w=>w.path.endsWith('/confirm')).length===2&&!window.__writes.some(w=>w.path.endsWith('/checkout/approvals'))`),'both source rule approvals remain separate from checkout approval');
await evaluate(`fill(field('Your name / reviewer label'),'Demo buyer');document.querySelector('.checkout-approval input[type=checkbox]').click()`);await click('Approve sandbox checkout');await until(`window.__writes.some(w=>w.path.endsWith('/checkout/approvals'))`);
assert(await evaluate(`!window.__writes.some(w=>w.path.endsWith('/orders')||w.path.endsWith('/capture'))&&window.__unexpected.length===0`),'explicit checkout approval only; no orders/captures or unmocked calls');
await shot('checkout-desktop');
// Existing saved consistency blocker must lead to findings; unknown code gets no link.
await evaluate(`window.__extraBlockers=['merchant_policy_consistency_requires_clarification','unknown_backend_requirement'];window.dispatchEvent(new Event('contextkey:changed'))`);await click('Refresh');await until(`document.querySelector('.blocker-list')?.textContent.includes('unknown_backend_requirement')`);
assert(await evaluate(`!document.querySelector('.blocker-list li:last-child button')&&document.querySelector('.blocker-list').textContent.includes('Merchant proposal version 2')`),'unknown code remains explicit without guessed action; saved proposal version shown');
await click('Open merchant policy findings →');await until(`visible(document.querySelector('.workspace-host:not([hidden]) .policy-consistency'))`);
assert(await evaluate(`document.activeElement.classList.contains('policy-consistency')&&document.querySelector('.workspace-host:not([hidden]) .consistency-report')?.textContent.includes('Synthetic saved uncertainty')`),'policy blocker focuses relevant saved findings rather than comparison');
assert(await evaluate(`field('Cutoff hours').value==='47'`),'unsaved buyer rule edits survive blocker navigation and both role switches');
await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await evaluate(`document.querySelector('.workspace-host:not([hidden]) .policy-consistency').scrollIntoView({block:'start'})`);await shot('policy-mobile');assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),'mobile blocker destination does not overflow');
// Different source in the same mounted calculator: cancellation must retain edits.
await evaluate(`const s=field('Policy source version');s.value='proposal';s.dispatchEvent(new Event('change',{bubbles:true}))`);
await evaluate(`fill(field('Cutoff hours'),'46');window.__extraBlockers=['agreement_cancellation_rules_unapproved_stale_or_inconsistent'];window.confirm=()=>{window.__confirms++;return false}`);
await task('Checkout & receipt');await click('Refresh');await until(`document.querySelector('.blocker-list')?.textContent.includes('Review buyer agreement rules')`);const beforeDiscard=await evaluate('window.__confirms');
await click('Review buyer agreement rules →');await until(`visible(document.querySelector('.workspace-host:not([hidden]) .rule-workbench'))`);
assert(await evaluate(`field('Policy source version').value==='proposal'&&field('Cutoff hours').value==='46'&&window.__confirms===${beforeDiscard+1}`),'cancelled source-specific navigation keeps unsaved proposal rule fields');
await evaluate(`window.confirm=()=>{window.__confirms++;return true}`);await task('Checkout & receipt');await click('Review buyer agreement rules →');await until(`field('Policy source version')?.value==='agreement'&&field('Cutoff hours')?.value==='48'`);
assert(await evaluate(`window.__confirms===${beforeDiscard+2}&&window.__writes.filter(w=>w.path.endsWith('/checkout/approvals')).length===1`),'explicit discard selects saved agreement rules without any additional approval');
assert(errors.length===0,'no uncaught browser exceptions: '+errors.join('; '));console.log(passes+' connected blocker journey assertions passed; synthetic APIs/providers only.');
} finally { ws.close() }

