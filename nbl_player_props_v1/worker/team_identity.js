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
  ['thehawks','illawarrahawks'],
  ['semelbournephoenix','southeastmelbournephoenix'],
]);
export const normTeamName=value=>{const key=normName(value);return TEAM_NAME_ALIASES.get(key)||key;};
export const canonicalTeamName=value=>{const raw=String(value||'').trim(),key=normTeamName(raw);return CANONICAL_BY_KEY.get(key)||raw;};
export const sameTeam=(a,b)=>normTeamName(a)===normTeamName(b);
