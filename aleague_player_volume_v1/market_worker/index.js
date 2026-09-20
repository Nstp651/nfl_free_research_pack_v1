import {evaluateMarkets,normalizeRows} from './evaluate.js';

const CORS={'access-control-allow-origin':'*','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,authorization'};
function response(body,status=200){return new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store'}});}
function withCors(res){const headers=new Headers(res.headers);for(const [k,v] of Object.entries(CORS))headers.set(k,v);return new Response(res.body,{status:res.status,headers});}
function requireThat(condition,message){if(!condition)throw new Error(message);}

export default {
  async fetch(request,env){
    try{
      if(request.method==='OPTIONS')return new Response(null,{status:204,headers:CORS});
      const url=new URL(request.url);
      if(request.method==='GET'&&url.pathname==='/health')return withCors(response({ok:true,service:'aleague-player-volume-market',version:'1.0.0',post_freeze_only:true,research_service_binding:Boolean(env?.RESEARCH_FREEZE)}));
      if(request.method==='POST'&&url.pathname==='/v1/evaluate'){
        requireThat(env?.RESEARCH_FREEZE,'RESEARCH_FREEZE service binding missing');const input=await request.json();requireThat(input&&typeof input==='object'&&!Array.isArray(input),'JSON object body required');const allowed=new Set(['run_id','records','default_source_type','captured_at','selection_sides']),extra=Object.keys(input).filter(k=>!allowed.has(k));requireThat(extra.length===0,`unexpected fields: ${extra.join(', ')}`);const runId=String(input.run_id||'').trim();requireThat(/^[0-9a-f]{64}$/.test(runId),'valid run_id required');requireThat(Array.isArray(input.records)&&input.records.length>0,'records required');
        const frozenRes=await env.RESEARCH_FREEZE.fetch(new Request(`https://research.internal/v1/runs/${runId}/frozen`,{method:'GET'}));requireThat(frozenRes.ok,`research freeze unavailable ${frozenRes.status}`);const payload=await frozenRes.json();requireThat(payload.status==='FROZEN'&&payload.lock?.run_id===runId,'research service returned wrong run');requireThat(payload.frozen?.freeze_receipt_sha256===payload.freeze_receipt_sha256,'research freeze receipt mismatch');const records=normalizeRows(payload.frozen.fixture_id,input.records,{defaultSourceType:input.default_source_type||'MANUAL',defaultCapturedAt:input.captured_at||null});const result=await evaluateMarkets(payload.frozen,records,{selectionSides:input.selection_sides||['AT_LEAST','OVER']});return withCors(response({run_id:runId,...result}));
      }
      return withCors(response({error:'Not found'},404));
    }catch(error){return withCors(response({error:String(error?.message||error)},422));}
  }
};
