import {listFixtures,response,routeMatchRuns,NblMatchRun} from './freeze_run_entry.js';
export {NblMatchRun};

const cors={
  'access-control-allow-origin':'*',
  'access-control-allow-methods':'GET,POST,OPTIONS',
  'access-control-allow-headers':'content-type,authorization',
};
function withCors(res){const h=new Headers(res.headers);for(const [k,v] of Object.entries(cors))h.set(k,v);return new Response(res.body,{status:res.status,headers:h});}

export default {
  async fetch(request,env){
    try{
      if(request.method==='OPTIONS')return new Response(null,{status:204,headers:cors});
      const routed=await routeMatchRuns(request,env);if(routed)return withCors(routed);
      const url=new URL(request.url);
      if(request.method==='GET'&&url.pathname==='/health'){
        return withCors(response({ok:true,service:'nbl-player-props-research-freeze',version:'1.0.0',market_data:false,heads:['assists','rebounds'],freeze_storage:Boolean(env.MATCH_RUNS)}));
      }
      if(request.method==='GET'&&url.pathname==='/v1/fixtures'){
        const season=Number(url.searchParams.get('season_start'));const fixtures=await listFixtures(season);const now=Date.now();
        return withCors(response({market_data:false,season_start:season,fixtures:fixtures.filter(f=>Date.parse(f.start_time)>now)}));
      }
      return withCors(response({market_data:false,error:'Not found'},404));
    }catch(e){return withCors(response({market_data:false,error:e.message},422));}
  }
};
