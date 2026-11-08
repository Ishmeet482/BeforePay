// Synthetic API fixture only. Never contacts a backend or provider.
export const fixture = String.raw`
(() => {
 const scenario = new URLSearchParams(location.search).get('case') || 'ready';
 // Legacy workflow tests start with a demo role; entry tests exercise login from empty storage.
 const entryTest = new URLSearchParams(location.search).has('demo-entry');
 if(!entryTest)sessionStorage.setItem('beforepay:demo-role',location.hash.startsWith('#merchant/')?'merchant':'buyer');
 let hasBooking=scenario!=='firsttime',hasAgreement=scenario!=='firsttime',hasDraft=scenario!=='firsttime',hasProposal=!['firsttime','merchantneeded'].includes(scenario),hasComparison=!['firsttime','merchantneeded'].includes(scenario),bookingTitle=scenario==='layoutlong'?'Synthetic rental · a long booking title covering camera, audio, lighting and supporting accessories for an extended production schedule':'Cinema kit · November shoot',draftSources=['s1'];
 window.__writes=[]; window.__unexpected=[]; window.__reads=[]; window.__confirms=0; window.__rejectNextRevision=false;
 window.__copied=[];window.__prints=0;window.print=()=>{window.__prints++};Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.__copied.push(value)}}});
 window.confirm=()=>{window.__confirms++;return true};
 window.visible = el => !!el && !!el.getClientRects().length;
 window.clickText=text=>{const b=[...document.querySelectorAll('button')].find(b=>visible(b)&&b.textContent.trim()===text);if(!b)throw Error('No visible button '+text);b.click()};
 window.fill=(el,value)=>{if(!el)throw Error('Input missing');Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}))};
 window.field=label=>[...document.querySelectorAll('label')].find(l=>visible(l)&&l.textContent.startsWith(label))?.querySelector('input,textarea,select');
 window.__enterDemoForRegression=async()=>{if(entryTest)return false;const d=document.querySelector('.demo-login');if(!d?.open)return false;const role=d.querySelector('input[name=demo-role]:checked').value;window.fill(d.querySelector('#demo-username'),role+'.demo');window.fill(d.querySelector('#demo-password'),role==='buyer'?'BuyerDemo123!':'MerchantDemo123!');d.querySelector('form').requestSubmit();for(let n=0;n<100;n++){await new Promise(r=>setTimeout(r,10));if(!d.isConnected||!d.open)return true;if(d.querySelector('#demo-login-error'))throw Error(d.querySelector('#demo-login-error').textContent)}throw Error('Mocked demo session did not finish')};
 const cats=['equipment','pickup','return_time','currency','amounts','deposit_conditions','cancellation_conditions','included_items'];
 const early='Cancellation at least 48 hours before pickup gives a full refund of USD 200.';
 const late='Cancellation less than 48 hours before pickup refunds the deposit USD 80 and retains the rental fee USD 120.';
 const deposit='The USD 80 deposit is refunded on cancellation according to the cancellation clauses.';
 const c=values=>({...values,ambiguous:false,citations:[{source_id:'s1',quotation:JSON.stringify(values),page_number:scenario==='firsttime'?null:1}]});
 const extraction={equipment:[c({name:'Cinema camera kit',quantity:1})],included_items:[c({name:'Battery',quantity:2})],pickup:[c({value:{local_datetime:'2026-11-10T09:00:00',timezone:'UTC'}})],return_time:[c({value:{local_datetime:'2026-11-12T10:00:00',timezone:'UTC'}})],currency:[c({value:'USD'})],amounts:[c({kind:'rental_total',label:'Rental fee',amount:'120.00',currency:'USD'}),c({kind:'deposit',label:'Deposit',amount:'80.00',currency:'USD'}),c({kind:'total_payable',label:'Total payable',amount:'200.00',currency:'USD'})],deposit_conditions:[c({value:deposit})],cancellation_conditions:[c({value:early}),c({value:late})]};
 const nonCamera={audio:'Wireless PA system',lighting:'Bi-colour LED lighting panel',presentation:'Laser projector & custom screen',custom:'Handmade kinetic sculpture rig'}[scenario];
 if(nonCamera){bookingTitle='SYNTHETIC · '+nonCamera;extraction.equipment=[c({name:nonCamera,quantity:1})];extraction.included_items=[];}
 if(scenario==='layoutlong') {
   extraction.equipment=[c({name:'Cinema camera kit with a long descriptive model, mounting accessories and protective transport case',quantity:2}),c({name:'Wireless microphone system',quantity:4}),c({name:'Tripod',quantity:null})];
   extraction.included_items=[c({name:'Rechargeable battery packs',quantity:6}),c({name:'Power supply and original charging cables',quantity:2}),c({name:'Carry bag',quantity:1})];
   extraction.amounts[0].label='Rental fee for camera kit, audio equipment and the agreed rental period';
   extraction.deposit_conditions=[c({value:deposit+' Return arrangements and the recorded condition of each item must be reviewed against the original quotation. '+deposit})];
   extraction.cancellation_conditions=[c({value:early+' '+late+' '+early+' '+late}),c({value:'Any unclear exception remains unresolved until the original source and exact wording are reviewed. No extra fee or policy is implied by this illustrative long-text fixture.'})];
 }
 if(scenario==='layoutempty')for(const category of cats)extraction[category]=[];
 let agreement={id:'a1',draft_id:'d1',version:1,fingerprint:'a'.repeat(64),created_at:'2026-11-02T09:00:00Z',content:{extraction:Object.fromEntries(cats.map(cat=>[cat,extraction[cat].map(claim=>({origin:'source_supported',claim}))])),explicit_none_categories:[]},audit:{customer_label:'Synthetic reviewer',kind:'ai_draft_review',changes:[]}};
 let confirmed=!['awaiting','journey','firsttime','layoutempty','layoutlong'].includes(scenario);
 let proposal={id:'p1',version:1,fingerprint:'b'.repeat(64),created_at:'2026-11-02T09:10:00Z',audit:{merchant_label:'Synthetic prototype editor',reason:'Fixture'},content:{...structuredClone(extraction),included_items_none:false}};
 if(scenario==='changed')proposal.content.deposit_conditions=[{value:'The USD 80 deposit is non-refundable.',ambiguous:false,citations:[]}];
 let comparisons=[{id:'c1',agreement_id:'a1',agreement_fingerprint:'a'.repeat(64),proposal_id:'p1',proposal_fingerprint:'b'.repeat(64),fingerprint:'c'.repeat(64),stale:scenario==='stale',stale_reasons:scenario==='stale'?['merchant_booking_changed']:[],results:cats.map(category=>({category,status:scenario==='changed'&&category==='deposit_conditions'?'differs':'matches',basis:category.includes('conditions')?'gemini_policy':'python',reason:scenario==='changed'&&category==='deposit_conditions'?'policy_meaning_differs':'values_match',agreement_terms:extraction[category],proposal_terms:proposal.content[category],agreement_quote:null,proposal_quote:null}))}];
 const ruleData={cutoff_hours:'48',early_includes_boundary:true,early:{rental_refund:{mode:'percent',value:'100'},deposit_refund:{mode:'percent',value:'100'},clause:early},late:{rental_refund:{mode:'percent',value:'0'},deposit_refund:{mode:'percent',value:'100'},clause:late},deposit_clause:deposit,needs_clarification:false,clarification_note:''};
 let rules=['agreement','proposal'].map((kind,i)=>({id:'r'+i,target:{kind,id:kind==='agreement'?'a1':'p1',fingerprint:kind==='agreement'?'a'.repeat(64):'b'.repeat(64)},source_version:1,version:1,fingerprint:'d'.repeat(64),rules:ruleData,origin:'human',blockers:[],approved_current:true,approval:{id:'ra'+i},audit:{reason:'Synthetic reviewed fixture'}}));
 if(['missingrules','awaiting','journey','firsttime'].includes(scenario))rules=[];
 let attempts=scenario.startsWith('paid')?[{id:'attempt1',approval_id:'approval1',status:'completed',amount:'200.00',currency:'USD',order_id:'ORDER_FIXTURE',capture_id:'CAPTURE_FIXTURE',error_code:null}]:scenario==='uncertain'?[{id:'attempt1',approval_id:'approval1',status:'capture_uncertain',amount:'200.00',currency:'USD',order_id:'ORDER_FIXTURE',capture_id:null,error_code:'paypal_timeout'}]:[];
 const context={environment:'sandbox',agreement_id:'a1',agreement_version:1,agreement_fingerprint:'a'.repeat(64),proposal_id:'p1',proposal_version:1,proposal_fingerprint:'b'.repeat(64),comparison_id:'c1',comparison_fingerprint:'c'.repeat(64),amount:'200.00',currency:'USD'};
 const receipt={id:'11111111-1111-4111-8111-111111111111',booking_id:'b1',attempt_id:'attempt1',approval_id:'22222222-2222-4222-8222-222222222222',context:{...context,confirmation_id:'33333333-3333-4333-8333-333333333333',cancellation_rules:[{id:'44444444-4444-4444-8444-444444444444',fingerprint:'d'.repeat(64),approval_id:'55555555-5555-4555-8555-555555555555'}]},amount:'200.00',currency:'USD',order_id:'ORDER_FIXTURE',capture_id:'CAPTURE_FIXTURE',created_at:'2026-11-02T09:20:00Z'};
 if(scenario==='paidchanged'){agreement={...agreement,id:'current-agreement-9',version:9,content:{...agreement.content,extraction:{...agreement.content.extraction,amounts:[{origin:'customer_entered',reason:'Synthetic later change',claim:{kind:'rental_total',label:'Current rental fee',amount:'999.00',currency:'USD',ambiguous:false,citations:[]}}]}}}};
 const source={id:'s1',created_at:'2026-11-02T08:00:00Z',source_type:'quotation',medium:'pdf',filename:'Synthetic quotation.pdf',original_text:'Synthetic evidence only. '+deposit+' '+early+' '+late,pages:[{page_number:1,original_text:'Synthetic evidence only. '+deposit+' '+early+' '+late}]};
 if(nonCamera){source.original_text='SYNTHETIC · '+extraction.equipment[0].citations[0].quotation+' '+source.original_text;source.pages[0].original_text=source.original_text;}
 if(scenario==='firsttime'){source.medium='pasted_text';source.filename=null;source.pages=[];source.original_text='Synthetic quotation only. '+Object.values(extraction).flatMap(items=>items.flatMap(c=>c.citations.map(q=>q.quotation))).join('\n')};window.__syntheticQuotation=source.original_text;
 let sources=scenario==='firsttime'?[]:[source];
 window.fetch=async(input,options={})=>{
   const raw=String(input);if(!raw.startsWith('/api/')){window.__unexpected.push(raw);throw Error('Blocked nonfixture fetch '+raw)};
   const url=new URL(raw,location.origin),path=url.pathname;
   if(path==='/api/demo-sessions')return options.method==='DELETE'?new Response(null,{status:204}):Response.json({active:true,csrf_token:'f'.repeat(64),expires_at:new Date(Date.now()+2700000).toISOString()});
   if(options.method&&options.method!=='GET'){
     const body=options.body instanceof FormData?null:JSON.parse(options.body||'{}');window.__writes.push({path,body});
     if(path==='/api/bookings'){hasBooking=true;bookingTitle=body.title;return Response.json({id:'b1',title:bookingTitle},{status:201})}
     if(path.endsWith('/agreements/from-draft')){hasAgreement=true;return Response.json(agreement,{status:201})}
     if(path.endsWith('/revisions')){if(window.__rejectNextRevision)return Response.json({detail:{code:'stale_agreement'}},{status:409});const next=structuredClone(agreement);next.id='a2';next.version=2;next.fingerprint='2'.repeat(64);for(const change of body.changes)next.content.extraction[change.category]=change.items.map(claim=>({origin:'customer_entered',reason:change.reason,claim:{...claim,citations:[]}}));agreement=next;confirmed=false;return Response.json(next,{status:201})}
     if(path.endsWith('/confirmations')){confirmed=true;return Response.json({id:'confirm2'},{status:201})}
     if(path.endsWith('/rules/propose')||path.endsWith('/rules')){const rule={id:['journey','firsttime'].includes(scenario)?'new-rule-'+body.target.kind:'new-rule',target:body.target,source_version:['journey','firsttime'].includes(scenario)?2:1,version:2,fingerprint:'e'.repeat(64),rules:body.rules||ruleData,origin:path.endsWith('/propose')?'gemini':'human',blockers:[],approved_current:false,approval:null,audit:{reason:body.reason||'Explicit AI proposal'}};rules=[rule,...rules.filter(r=>r.target.kind!==body.target.kind)];return Response.json(rule,{status:201})}
     if(path.endsWith('/confirm')){rules=rules.map(r=>path.endsWith('/'+r.id+'/confirm')?{...r,approved_current:true,approval:{id:'synthetic-rule-approval'}}:r);return Response.json(rules[0])}
     if(path.endsWith('/preview')){const isEarly=body.cancellation.local_datetime==='2026-11-08T09:00';return Response.json({status:'ready',blockers:[],cancellation_at:body.cancellation.local_datetime+'Z',previews:body.rule_ids.map(id=>{const r=rules.find(r=>r.id===id);return {target:r.target,source_version:1,cancellation_at:body.cancellation.local_datetime+'Z',pickup_at:'2026-11-10T09:00:00Z',cutoff_at:'2026-11-08T09:00:00Z',early_includes_boundary:true,band:isEarly?'early':'late',currency:'USD',refund:isEarly?'200.00':'80.00',retained:isEarly?'0.00':'120.00',rental_refund:isEarly?'120.00':'0.00',deposit_refund:'80.00',applied_clause:isEarly?early:late,deposit_clause:deposit}})})}
     if(path.endsWith('/sources/text')){const saved={...source,id:scenario==='firsttime'&&sources.length===0?'s1':'s2',source_type:body.source_type,medium:'pasted_text',filename:null,original_text:body.original_text,pages:[]};sources=[...sources,saved];return Response.json(saved,{status:201})}
     if(path.endsWith('/sources/pdf')){const file=options.body.get('file');window.__writes.at(-1).file={name:file.name,type:file.type};const saved={...source,id:'s3',filename:file.name};sources=[...sources,saved];return Response.json(saved,{status:201})}
     if(path.endsWith('/drafts')){hasDraft=true;draftSources=body.source_ids;return Response.json({id:'d1',version:1,created_at:'2026-11-02T08:30:00Z',input_source_ids:body.source_ids,content:{needs_clarification:false,extraction}},{status:201})};
     if(path.endsWith('/checkout/approvals'))return Response.json({id:'approval1',fingerprint:'f'.repeat(64),context},{status:201});
     if(path.endsWith('/reconcile'))return Response.json(attempts[0]);
     if(path.endsWith('/comparisons')){hasComparison=true;comparisons=[{...comparisons[0],...body,id:'new-comparison',stale:false,stale_reasons:[]}];return Response.json(comparisons[0],{status:201})}
     if(path.endsWith('/merchant-bookings')){hasProposal=true;proposal={...proposal,...body,content:{...body.content,...Object.fromEntries(cats.map(cat=>[cat,body.content[cat].map(claim=>({...claim,citations:[]}))]))},id:'p2',version:2,fingerprint:'2'.repeat(64)};return Response.json(proposal,{status:201})}
     window.__unexpected.push(raw);throw Error('Unexpected synthetic mutation '+path);
   }
   window.__reads.push(raw);let data;
   if(path==='/api/bookings')data=scenario==='empty'||!hasBooking?[]:[{id:'b1',title:bookingTitle}];
   else if(path.endsWith('/review'))data={agreement_id:hasAgreement?agreement.id:null,fingerprint:hasAgreement?agreement.fingerprint:null,source_ids:sources.map(s=>s.id),latest_draft_id:hasDraft?'d1':null,blockers:scenario==='layoutempty'?cats.map(c=>c+'_missing'):[],confirmation_current:confirmed,requires_review:!confirmed,confirmation:confirmed?{customer_label:'Synthetic reviewer',created_at:'2026-11-02T09:05:00Z'}:null};
   else if(path.endsWith('/agreements'))data=hasAgreement?[agreement]:[];
   else if(path.includes('/agreements/'))data=agreement;
   else if(path.endsWith('/merchant-bookings'))data=hasProposal?[proposal]:[];
   else if(path.endsWith('/policy-consistency/state'))data={proposal_id:hasProposal?proposal.id:null,proposal_fingerprint:hasProposal?proposal.fingerprint:null,blockers:[]};
   else if(path.endsWith('/policy-consistency'))data=[];
   else if(path.endsWith('/correction-reviews'))data=[];
   else if(path.endsWith('/replies'))data=[];
   else if(path.endsWith('/clarifications'))data=[];
   else if(path.endsWith('/comparisons'))data=hasComparison?comparisons:[];
   else if(path.endsWith('/cancellation/rules'))data=rules;
   else if(path.endsWith('/drafts'))data=hasDraft?[{id:'d1',version:1,created_at:'2026-11-02T08:30:00Z',input_source_ids:draftSources,content:{needs_clarification:false,extraction}}]:[];
   else if(path.endsWith('/sources'))data=sources;
   else if(path.includes('/sources/'))data=sources.find(s=>path.endsWith('/'+s.id));
   else if(path.endsWith('/checkout/attempts'))data=attempts;
   else if(path.endsWith('/checkout/receipt'))data=receipt;
   else if(path.endsWith('/checkout/eligibility')){const eligible=['ready','uncertain'].includes(scenario)||(['journey','firsttime'].includes(scenario)&&confirmed&&hasComparison&&comparisons[0].agreement_id===agreement.id&&comparisons[0].proposal_id===proposal.id&&['agreement','proposal'].every(kind=>rules.some(r=>r.target.kind===kind&&r.target.id===(kind==='agreement'?agreement.id:proposal.id)&&r.approved_current)));data={eligible,blockers:scenario.startsWith('paid')?['sandbox_payment_already_completed']:eligible?[]:scenario==='missingrules'?['agreement_reviewed_cancellation_rules_required','proposal_reviewed_cancellation_rules_required']:[scenario==='stale'?'comparison_stale':scenario==='changed'?'comparison_has_differences_or_clarification':scenario==='awaiting'?'current_confirmation_required':'reviewed_current_rule_approval_required'],context:scenario==='awaiting'?null:['journey','firsttime'].includes(scenario)?{...context,agreement_id:agreement.id,agreement_version:agreement.version,agreement_fingerprint:agreement.fingerprint,proposal_id:proposal.id,proposal_version:proposal.version,proposal_fingerprint:proposal.fingerprint,comparison_id:comparisons[0].id,comparison_fingerprint:comparisons[0].fingerprint}:context,fingerprint:'f'.repeat(64),sandbox_configured:true}}
   else{window.__unexpected.push(raw);throw Error('Unexpected synthetic read '+raw)}
   if(scenario==='layoutlist') {
     if(path==='/api/bookings')data=[{id:'b1',title:'Synthetic short rental'},{id:'b2',title:'Synthetic rental with an exceptionally long booking name that wraps across several readable lines without shifting dates, prices, status labels or action controls'},{id:'b3',title:'Synthetic paid booking · historical receipt'}];
     if(path.includes('/bookings/b2/')) {
       if(path.endsWith('/review'))data={agreement_id:null,fingerprint:null,source_ids:[],latest_draft_id:null,blockers:['agreement_missing'],confirmation_current:false,requires_review:true,confirmation:null};
       else if(['/merchant-bookings','/comparisons','/cancellation/rules','/checkout/attempts'].some(suffix=>path.endsWith(suffix)))data=[];
       else if(path.endsWith('/checkout/eligibility'))data={eligible:false,blockers:['current_confirmation_required'],context:null,fingerprint:null,sandbox_configured:true};
     }
     if(path.includes('/bookings/b3/')) {
       if(path.endsWith('/checkout/attempts'))data=[{id:'layout-completed',approval_id:'approval1',status:'completed',amount:'200.00',currency:'USD',order_id:'ORDER_LAYOUT',capture_id:'CAPTURE_LAYOUT',error_code:null}];
       if(path.endsWith('/checkout/receipt'))data={...receipt,booking_id:'b3',order_id:'ORDER_LAYOUT',capture_id:'CAPTURE_LAYOUT'};
     }
   }
   if(scenario==='layouthistory'&&path.endsWith('/checkout/attempts'))data=[{...attempts[0],id:'history-complete',approval_id:'approval1',status:'completed',amount:'200.00',currency:'USD',order_id:'ORDER_FIXTURE',capture_id:'CAPTURE_FIXTURE',error_code:null},{id:'history-failed',approval_id:'approval1',status:'failed',amount:'200.00',currency:'USD',order_id:'ORDER_DECLINED',capture_id:null,error_code:'paypal_declined'},{id:'history-cancelled',approval_id:'approval1',status:'cancelled',amount:'200.00',currency:'USD',order_id:null,capture_id:null,error_code:null}];
   return Response.json(data);
 };
})();`
