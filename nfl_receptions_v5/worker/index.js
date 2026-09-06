import {NflReceptionsRun, routeRun, reply} from './run.js';
export {NflReceptionsRun};

export default {
  async fetch(request, env = {}) {
    const url = new URL(request.url);
    if (url.pathname === '/health') {
      return reply({
        ok: Boolean(env.NFL_RECEPTIONS_RUNS),
        service: 'NFL_RECEPTIONS_PLATFORM_V5_CONTROL',
        version: '1.1.0',
        market_data: false,
        durable_state: Boolean(env.NFL_RECEPTIONS_RUNS),
        source_lock: 'CONTENT_SHA256',
        note: 'Health is pre-market and never accesses sportsbook data.'
      }, env.NFL_RECEPTIONS_RUNS ? 200 : 503);
    }
    const run = await routeRun(request, env);
    if (run) return run;
    return reply({error: 'Not found', market_data: false}, 404);
  }
};
