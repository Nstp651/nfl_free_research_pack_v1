# A-League Player Volume V1 — Source Policy

## Principle
Use the richest lawful/reliable evidence stack we can support without making production depend on brittle or unapproved scraping.

## Source classes

### `AUTO_APPROVED`
May be used by scheduled GitHub ingestion after parser tests and rate controls pass. Assets must be normalized, hashed and versioned before runtime consumption.

### `RESEARCH_ONLY`
May be consulted during market-blind Layer 1 research, but no unattended GitHub scraper may depend on it. Research must capture source/date/evidence and declare unavailable fields honestly.

### `LICENSED_OPTION`
Architecturally supported if Nick later approves a paid/licensed feed. Credentials must remain in Cloudflare/GitHub secrets as appropriate and raw licensed data must not be committed if licensing forbids it.

### `BLOCKED`
Do not ingest or use until policy/terms/access status changes.

## Initial decisions

### FBref — `AUTO_APPROVED_WITH_GUARDS`
Current public A-League pages expose player/team/opponent shooting and goalkeeper tables useful for historical priors. Automation must be conservative, cache-first, rate-limited and covered by parser/coverage tests. If access controls or terms make unattended retrieval inappropriate, downgrade to `RESEARCH_ONLY` immediately without breaking runtime because published canonical assets are decoupled from retrieval.

### Official A-League / club sources — `AUTO_OR_RESEARCH_BY_ROUTE`
Use stable published fixture/squad/news feeds when technically and policy-safe. Otherwise use as research evidence. Official availability/team news should outrank aggregator inference for current-role decisions.

### FotMob — `RESEARCH_ONLY`
Useful advanced research may include xG/xA, shot maps, box touches and chance creation when visible. Do not create a production scraper dependency. The open-source `soccerdata` project removed FotMob scraping support following a provider request, which is a strong reason to keep FotMob outside unattended ingestion unless a licensed/approved route exists.

### Transfermarkt — `RESEARCH_ONLY` initially
Useful for transfer history, prior clubs and role context. Do not schedule scrape until route/policy and parser durability are separately approved.

### Paid advanced feeds — `LICENSED_OPTION`
Opta/Stats Perform, Wyscout, StatsBomb or similar may materially improve shot-location/quality, pressure and event data, but V1 must not assume a paid subscription. The model must remain functional on the approved free/open stack.

## Market-source separation
Sportsbook/API market sources are prohibited from Layers 0–2. Their data is accepted only by the physically separate post-freeze market service.

## Anti-leakage requirement
Historical QBASE generation must use only information that existed before each target fixture. Retrieval timestamps do not make retrospective season aggregates safe. Builders must reconstruct rolling pre-match features from event-level/match-level history.
