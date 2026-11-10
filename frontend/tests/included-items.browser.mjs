// Run with Vite and headless Chrome debugging on port 9225.
// Agreement-review regression: all API reads/writes are synthetic.
// No real records, AI requests, PayPal SDK downloads or payments are accessed.
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
window.confirm=()=>true;window.__writes=[];
const supported=(name,quantity)=>({origin:'source_supported',claim:{name,quantity,ambiguous:false,citations:[{source_id:'s1',quotation:name+' quantity '+quantity,page_number:null}]}});
const extraction=Object.fromEntries(['equipment','pickup','return_time','currency','amounts','deposit_conditions','cancellation_conditions','included_items'].map(c=>[c,[]]));extraction.included_items=[supported('batteries',2),supported('microphone',1)];
let agreement={id:'a1',draft_id:'d1',version:1,fingerprint:'a'.repeat(64),created_at:'2026-11-01T12:00:00Z',content:{extraction,explicit_none_categories:[]},audit:{customer_label:'Synthetic reviewer',kind:'from_draft',changes:[]}};
window.fetch=async(url,options={})=>{url=String(url);if(url==='/api/demo-sessions')return Response.json({active:true,csrf_token:'f'.repeat(64),expires_at:new Date(Date.now()+2700000).toISOString()});if(options.method==='POST'){
 const body=JSON.parse(options.body);window.__writes.push({url,body});
 if(!url.endsWith('/revisions'))throw new Error('Unexpected mutation');
 const next=structuredClone(agreement);next.id='a'+(agreement.version+1);next.version++;next.fingerprint=String(next.version).repeat(64);
 for(const change of body.changes)next.content.extraction[change.category]=change.items.map(claim=>({origin:'customer_entered',reason:change.reason,claim:{...claim,citations:[]}}));
 agreement=next;return Response.json(next,{status:201});
};let data;
if(url.startsWith('/api/bookings?'))data=[{id:'b1',title:'Synthetic included-items regression'}];
else if(url.endsWith('/saved-state'))data={review:{agreement_id:agreement.id,fingerprint:agreement.fingerprint,source_ids:['s1'],latest_draft_id:'d1',blockers:['equipment_missing'],confirmation_current:false,requires_review:true,confirmation:null},agreement,proposal:null,comparison:null,rules:[],attempts:[],receipt:null,eligible:false,blockers:['equipment_missing'],sandbox_configured:false};
else if(url.includes('/agreements?'))data=[agreement];
else if(url.includes('/drafts?'))data=[{id:'d1',version:1}];
else if(url.endsWith('/review'))data={agreement_id:agreement.id,fingerprint:agreement.fingerprint,source_ids:['s1'],latest_draft_id:'d1',blockers:['equipment_missing'],confirmation_current:false,requires_review:true,confirmation:null};
else if(url.includes('/sources?'))data=[{id:'s1'}];
else if(url.endsWith('/sources/s1'))data={id:'s1',source_type:'quotation',medium:'text',filename:null,original_text:'batteries quantity 2; microphone quantity 1',pages:[]};else throw new Error('Unexpected read '+url);return Response.json(data)};
`;
try {
await send('Runtime.enable');await send('Page.enable');await send('Network.enable');
await send('Network.setBlockedURLs',{urls:['*paypal.com*','*googleapis.com*']});
await send('Page.addScriptToEvaluateOnNewDocument',{source:fixtures});
await send('Page.navigate',{url:(process.env.FRONTEND_URL || 'http://127.0.0.1:5173')+'/?regression=items-'+Date.now()+'#bookings'});
await until(`document.querySelector('.row-action')`);
await evaluate(`document.querySelector('.row-action').click()`);
await until(`document.querySelector('.tabs')`);
await evaluate(`[...document.querySelectorAll('.tabs button')].find(b=>b.textContent.includes('Agreement')).click()`);
await until(`document.querySelector('#title-included_items')&&!document.querySelector('.workspace').matches('[aria-busy=true]')`);
await evaluate(`document.querySelector('#title-included_items').closest('section').querySelector('.section-editor').open=true`);
await evaluate(`window.included=()=>document.querySelector('#title-included_items').closest('section');window.quantity=()=>included().querySelector('input[inputmode=numeric]');window.saveButton=()=>document.querySelector('.save-panel button');window.fill=(el,value)=>{Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}))}`);
assert(await evaluate(`included().querySelector('.badge').textContent==='Saved'&&included().querySelectorAll('.claim-row').length===2&&!included().querySelector('.reason')`),'fresh source-supported batteries 2 and microphone 1 remain unchanged');
assert(await evaluate(`Array.from(included().querySelectorAll('input[inputmode=numeric]'),el=>el.value).join(',')==='2,1'&&included().querySelectorAll('.citation').length===2`),'initialization preserves both quantities and evidence quotations');
assert(await evaluate(`(async()=>{const {row,rowsChanged}=await import('/src/conditions.ts');const saved=[{origin:'source_supported',claim:{name:'batteries',quantity:2,ambiguous:false,citations:[]}},{origin:'source_supported',claim:{name:'microphone',quantity:null,ambiguous:false,citations:[]}}];const form=saved.map(row);return form[0].quantity==='2'&&form[1].quantity===''&&!rowsChanged('included_items',form,saved)&&rowsChanged('included_items',[{...form[0],quantity:'invalid'},form[1]],saved)})()`),'normalization ignores UI keys, preserves unknown quantities and detects invalid edits');
await evaluate(`fill(document.querySelector('.identity input'),'Synthetic reviewer');fill(document.querySelector('.save-panel textarea'),'Reviewed unchanged source-supported items.');document.querySelector('.source .check input').click()`);
assert(await evaluate(`!saveButton().disabled&&document.querySelector('.save-panel .hint').textContent.includes('0 changed')`),'untouched review can save with overall reason and source acknowledgement only');
await evaluate(`saveButton().click()`);
await until(`window.__writes.length===1&&!document.querySelector('.workspace').matches('[aria-busy=true]')`);
assert(await evaluate(`window.__writes[0].body.changes.length===0&&window.__writes[0].body.expected_fingerprint==='a'.repeat(64)`),'untouched save sends no corrections and retains exact-version fingerprint');
await evaluate(`fill(document.querySelector('.save-panel textarea'),'Review quantity correction.');document.querySelector('.source .check input').click();fill(quantity(),'3')`);
assert(await evaluate(`included().querySelector('.badge').textContent==='Unsaved correction'&&!!included().querySelector('.reason textarea[required]')&&saveButton().disabled`),'actual quantity edit requires a category correction reason');
await evaluate(`fill(quantity(),'2')`);
assert(await evaluate(`included().querySelector('.badge').textContent==='Saved'&&!included().querySelector('.reason')&&!saveButton().disabled`),'restoring original quantities clears the false correction and reason blocker');
await evaluate(`fill(quantity(),'3');fill(included().querySelector('.reason textarea'),'   ')`);
assert(await evaluate(`saveButton().disabled`),'whitespace-only correction reason remains blocked');
await evaluate(`fill(included().querySelector('.reason textarea'),'Explicitly reviewed battery quantity correction.')`);
assert(await evaluate(`!saveButton().disabled&&document.querySelector('.confirm-panel button').disabled`),'reason permits saving corrected version without auto-confirmation');
await evaluate(`saveButton().click()`);
await until(`window.__writes.length===2&&!document.querySelector('.workspace').matches('[aria-busy=true]')`);
assert(await evaluate(`(()=>{const b=window.__writes[1].body,c=b.changes[0];return b.changes.length===1&&c.category==='included_items'&&!!c.reason.trim()&&c.items[0].name==='batteries'&&c.items[0].quantity===3&&c.items[1].name==='microphone'&&c.items[1].quantity===1&&!c.items.some(i=>'citations'in i)&&b.expected_fingerprint==='2'.repeat(64)})()`),'real correction keeps complementary item, reason and fingerprint without fabricated citations');
assert(await evaluate(`window.__writes.every(w=>w.url.endsWith('/revisions'))`),'regression never generates AI, confirms terms or accesses payments');
assert(exceptions.length===0,'no browser runtime exceptions');
}finally{ws.close()}
