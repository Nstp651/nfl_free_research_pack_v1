export const NBA_PROP_MARKETS = Object.freeze([
  'player_assists',
  'player_assists_alternate',
  'player_rebounds',
  'player_rebounds_alternate',
]);

export function estimatedEventCredits({marketCount=NBA_PROP_MARKETS.length,regions=1}){
  if(!Number.isInteger(marketCount) || marketCount<0) throw new Error('marketCount must be a non-negative integer');
  if(!Number.isInteger(regions) || regions<1) throw new Error('regions must be a positive integer');
  return 10*marketCount*regions;
}

export function estimatedSlateCredits({games,marketCount=NBA_PROP_MARKETS.length,regions=1}){
  if(!Number.isInteger(games) || games<0) throw new Error('games must be a non-negative integer');
  return games*estimatedEventCredits({marketCount,regions});
}

export function budgetSnapshot({monthlyCredits=20000,games,regions=1,marketCount=NBA_PROP_MARKETS.length}){
  if(!Number.isInteger(monthlyCredits) || monthlyCredits<=0) throw new Error('monthlyCredits must be positive');
  const slateCredits=estimatedSlateCredits({games,marketCount,regions});
  return {
    monthly_credits:monthlyCredits,
    games,
    regions,
    market_count:marketCount,
    estimated_slate_credits:slateCredits,
    estimated_full_slates_per_month:slateCredits>0?Math.floor(monthlyCredits/slateCredits):null,
  };
}
