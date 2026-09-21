/** Deterministic NBL team identity canonicalisation. No fuzzy matching. */
export const normName=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const CANONICAL_BY_KEY=new Map([
  ['adelaide36ers','Adelaide 36ers'],
  ['brisbanebullets','Brisbane Bullets'],
  ['cairnstaipans','Cairns Taipans'],
  ['illawarrahawks','Illawarra Hawks'],
  ['melbourneunited','Melbourne United'],
  ['newzealandbreakers','New Zealand Breakers'],
  ['perthwildcats','Perth Wildcats'],
  ['southeastmelbournephoenix','South East Melbourne Phoenix'],
  ['sydneykings','Sydney Kings'],
  ['tasmaniajackjumpers','Tasmania JackJumpers'],
]);
const TEAM_NAME_ALIASES=new Map([
  ['nzbreakers','newzealandbreakers'],
  ['semelbournephoenix','southeastmelbournephoenix'],
]);
const HISTORICAL_SOURCE_ALIASES=new Map([
  ['thehawks','illawarrahawks'],
]);
export const normTeamName=value=>{const key=normName(value);return TEAM_NAME_ALIASES.get(key)||key;};
export const canonicalTeamName=value=>{const raw=String(value||'').trim();let key=normTeamName(raw);key=HISTORICAL_SOURCE_ALIASES.get(key)||key;return CANONICAL_BY_KEY.get(key)||raw;};
export const sameTeam=(a,b)=>normTeamName(a)===normTeamName(b);
