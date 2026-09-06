import {NflReceptionsRun, routeRun, reply} from './run.js';
export {NflReceptionsRun};

export default {
  async fetch(request, env = {}) {
    const url = new URL(request.url);
    if (url.pathname === '/health') {
      return reply({ok: Boolean(env.NFL_RECEPTIONS_RUNS), service: 'NFL_RECEPTIONS_PLATFORM_V5_CONTROL', version: '1.0.0', market_data: false,
        durable_state: Boolean(env.NFL_RECEPTIONS_RUNS), note: 'Health is pre-market and never accesses sportsbook data.'}, env.NFL_RECEPTIONS_RUNS ? 200 : 503);
    }

    const run = await routeRun(request, env);
    if (run) {
      // The Durable Object initializes POST /v1/runs state before its generic
      // dispatcher reaches the terminal Unknown-run-operation branch. Normalize
      // that one successful initialization path into the authoritative GET
      // receipt so Actions receive the created run instead of a false failure.
      if (request.method === 'POST' && url.pathname === '/v1/runs' && run.status === 422) {
        let payload = null;
        try { payload = await run.clone().json(); } catch {}
        if (payload?.run_id && payload?.error === 'Unknown run operation') {
          const created = await routeRun(new Request(`${url.origin}/v1/runs/${payload.run_id}`, {method: 'GET'}), env);
          if (created) return created;
        }
      }
      return run;
    }
    return reply({error: 'Not found', market_data: false}, 404);
  }
};
