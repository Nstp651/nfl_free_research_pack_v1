const SUPPORTED_HEADS = new Set(['assists','rebounds']);
const SUPPORTED_SIDES = new Set(['over','under']);

function need(ok,message){ if(!ok) throw new Error(message); }
function finite(x){ return Number.isFinite(Number(x)); }

export function exactMarketKey(row){
  need(row && typeof row==='object','market row required');
  const gameId=String(row.game_id||'').trim();
  const playerId=String(row.player_id||'').trim();
  const head=String(row.stat_type||'').toLowerCase();
  const side=String(row.side||'').toLowerCase();
  const threshold=Number(row.threshold);
  need(gameId && playerId,'game_id/player_id required');
  need(SUPPORTED_HEADS.has(head),'unsupported stat_type');
  need(SUPPORTED_SIDES.has(side),'unsupported side');
  need(finite(threshold) && threshold>=0,'invalid threshold');
  need(Math.abs(threshold*2-Math.round(threshold*2))<=1e-9,'threshold must be integer or half-point');
  return `${gameId}|${playerId}|${head}|${side}|${threshold}`;
}

export function chooseBestExactPrices(rows){
  need(Array.isArray(rows),'market rows required');
  const best=new Map();
  for(const original of rows){
    const row={...original,decimal_price:Number(original.decimal_price),threshold:Number(original.threshold)};
    need(finite(row.decimal_price) && row.decimal_price>1,'invalid decimal_price');
    need(Number.isFinite(Date.parse(String(row.captured_at||''))),'invalid captured_at');
    need(String(row.bookmaker||'').trim(),'bookmaker required');
    const key=exactMarketKey(row), old=best.get(key);
    const tie=`${row.captured_at}\0${String(row.bookmaker).toLowerCase()}`;
    const oldTie=old?`${old.captured_at}\0${String(old.bookmaker).toLowerCase()}`:'';
    if(!old || row.decimal_price>old.decimal_price || (row.decimal_price===old.decimal_price && tie>oldTie)) best.set(key,row);
  }
  return [...best.values()];
}

export function findExactFrozenLine(probabilityGrid,threshold){
  const line=Number(threshold);
  need(finite(line),'invalid threshold');
  const isInteger=Math.abs(line-Math.round(line))<=1e-9;
  const rows=isInteger?probabilityGrid?.integer_push_grid:probabilityGrid?.half_point_grid;
  need(Array.isArray(rows),'frozen probability grid missing');
  const found=rows.filter(r=>Math.abs(Number(r.line)-line)<=1e-9);
  need(found.length===1,`Exact frozen threshold ${line} unavailable`);
  return found[0];
}

export function evaluateExactMarket(row,probabilityGrid){
  const normalized={...row,stat_type:String(row.stat_type||'').toLowerCase(),side:String(row.side||'').toLowerCase(),threshold:Number(row.threshold),decimal_price:Number(row.decimal_price)};
  exactMarketKey(normalized);
  need(finite(normalized.decimal_price) && normalized.decimal_price>1,'invalid decimal_price');
  const line=findExactFrozenLine(probabilityGrid,normalized.threshold);
  const other=normalized.side==='over'?'under':'over';
  const pWin=Number(line[normalized.side]), pPush=Number(line.push||0), pLoss=Number(line[other]);
  need([pWin,pPush,pLoss].every(Number.isFinite),'invalid probability partition');
  need(Math.min(pWin,pPush,pLoss)>=-1e-12 && Math.abs(pWin+pPush+pLoss-1)<=1e-8,'probability partition failed');
  const nonPush=pWin+pLoss;
  const conditionalWin=nonPush>0?pWin/nonPush:null;
  const marketBreakEven=1/normalized.decimal_price;
  const ev=pWin*(normalized.decimal_price-1)-pLoss;
  return {
    ...normalized,
    p_win:pWin,
    p_push:pPush,
    p_loss:pLoss,
    conditional_win_probability:conditionalWin,
    market_break_even_probability:marketBreakEven,
    probability_edge:conditionalWin===null?null:conditionalWin-marketBreakEven,
    fair_decimal_price:pWin>0?nonPush/pWin:null,
    ev_per_unit:ev,
    positive_ev:ev>0,
  };
}

export function rankPositiveEdges(rows){
  const positives=rows.filter(r=>r.positive_ev).slice().sort((a,b)=>
    b.ev_per_unit-a.ev_per_unit ||
    String(a.stat_type).localeCompare(String(b.stat_type)) ||
    String(a.player_name||a.player_id).localeCompare(String(b.player_name||b.player_id)) ||
    a.threshold-b.threshold ||
    String(a.bookmaker).localeCompare(String(b.bookmaker))
  );
  return positives.map((row,index)=>({...row,positive_edge_rank:index+1}));
}
