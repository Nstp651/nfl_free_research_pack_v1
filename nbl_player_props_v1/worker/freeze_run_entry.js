import {NblMatchRun as BaseNblMatchRun,listFixtures,response,routeMatchRuns} from './freeze_run.js';

/**
 * Stable Cloudflare entry class.
 *
 * The base implementation persists the initialized run before its generic route
 * fall-through. This wrapper turns that already-successful initialization into a
 * 200 response instead of exposing the internal fall-through as a 422. All other
 * errors remain fail-closed. Keeping the compatibility shim isolated lets the
 * persistent storage format stay unchanged while V1 is under acceptance testing.
 */
export class NblMatchRun extends BaseNblMatchRun {
  async handle(request) {
    try {
      return await super.handle(request);
    } catch (error) {
      const url=new URL(request.url);
      const parts=url.pathname.split('/').filter(Boolean);
      const tail=parts.slice(3);
      if(request.method==='POST'&&tail.length===0&&error?.message==='Unknown run operation'){
        const meta=await this.storage.get('meta');
        if(meta) return response({market_data:false,status:meta.status,lock:meta.lock});
      }
      throw error;
    }
  }
}
export {listFixtures,response,routeMatchRuns};
