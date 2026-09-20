import {AleaguePlayerVolumeRun,createRun,response,routeRuns} from './run.js';
import {DEPLOY_SOURCE_COMMIT} from './source_commit.generated.js';
export {AleaguePlayerVolumeRun};

const CORS={
  'access-control-allow-origin':'*',
  'access-control-allow-methods':'GET,POST,OPTIONS',
  'access-control-allow-headers':'content-type,authorization',
};
function withCors(res){const headers=new Headers(res.headers);for(const [key,value] of Object.entries(CORS))headers.set(key,value);return new Response(res.body,{status:res.status,headers});}

export default {
  async fetch(request,env){
    try{
      if(request.method==='OPTIONS')return new Response(null,{status:204,headers:CORS});
      const routed=await routeRuns(request,env);if(routed)return withCors(routed);
      const url=new URL(request.url);
      if(request.method==='GET'&&url.pathname==='/health')return withCors(response({ok:true,service:'aleague-player-volume-research-freeze',version:'1.0.0',market_data:false,heads:['PLAYER_SHOTS','PLAYER_SHOTS_ON_TARGET','GOALKEEPER_SAVES'],freeze_storage:Boolean(env?.MATCH_RUNS),source_commit:DEPLOY_SOURCE_COMMIT}));
      if(request.method==='POST'&&url.pathname==='/v1/runs')return withCors(await createRun(request,env));
      return withCors(response({market_data:false,error:'Not found'},404));
    }catch(error){return withCors(response({market_data:false,error:String(error?.message||error)},422));}
  }
};
