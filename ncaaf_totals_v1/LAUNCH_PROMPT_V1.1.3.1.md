NEW NCAA FOOTBALL TOTALS MODEL RUN — V1.1.3.1

Season: 2026
Target Week: [WEEK]
Australia/Sydney Run Window: [DATES]
Timing Mode: MATCHDAY

Run the complete V1.1.3.1 workflow automatically across the eligible FBS-v-FBS slate through Layers 1–4.

Use the server-enforced runtime loop: retrieve only the next at-most-two pending games, complete full current research for those games, checkpoint them immediately, verify progress, then request the next batch. Never research or preload later games before the current batch is persisted. On any message timeout, resume the SAME run_id and pending set; do not silently start over.

Maintain strict market blindness until the complete atomic P_model freeze. Require exact game_id/QBASE identity binding, all hashes and audits PASS, then retrieve the AU totals board post-freeze and rank BEST SINGLE + Top 10 positive edges, or fewer if fewer qualify. Do not force a bet.

End exactly:
FINAL_NCAAF_TOTALS_SLATE_RANKING_COMPLETE
