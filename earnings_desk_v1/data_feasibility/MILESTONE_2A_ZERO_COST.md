# K&J Earnings Desk — Milestone 2A Zero-Cost Historical Data Feasibility Gate

**Assessment date:** 2026-09-23  
**Scope:** historical reconstruction for the existing Earnings Desk V1.1 `P_MODEL`; no model changes, coefficient fitting, production Worker changes, deployment, subscriptions, or fabricated observations.  
**Required recurring data cost:** $0.

## 1. Executive conclusion

A substantial part of the history can be reconstructed from public primary evidence. SEC filings and company investor-relations archives can support event identity, many AMC/BMO classifications, guidance trajectory, company-specific information, and reported results. Deterministic price-derived features are technically straightforward if a price source with acceptable retention rights is selected. Search-indexed, timestamped earnings previews also materially improve the free-data case: the empirical pass found contemporaneous consensus EPS, consensus revenue, and a 30-day EPS revision measure across several sectors.

The full existing V1.1 feature contract is nevertheless **not reconstructable today at $0 with evidence strong enough to pass its data-quality gates**. Two mandatory inputs remain unproven after testing both API and web-scale routes:

1. `revenue_revision_z`: no tested free source supplied a consistent historical revenue-consensus change over the contract window for the same event and methodology.
2. `consensus_dispersion_z`: no tested free source supplied the complete analyst-level estimate set, or an equivalent sample standard deviation, as of the historical cutoff. Public high/low/count snapshots are not mathematically sufficient to recover standard deviation.

`eps_revision_z` is more promising than a clean-API-only review would suggest. Dated Zacks previews often state the current consensus and its percentage change over the prior 30 days. That can be normalized into a deterministic event record if the article is timestamped before the research cutoff and its use is permitted. It does not solve the two gaps above.

Alpha Vantage does not document an `as_of` or vintage parameter for `EARNINGS_ESTIMATES`. Financial Modeling Prep explicitly describes its estimates API as current consensus rather than versioned history. A historical period row returned today is therefore not proof of what the market knew before an old event. SEC and IR sources cannot supply third-party analyst dispersion.

The result is a stop at the full-model gate, not a rejection of public-web reconstruction. The recommended next zero-cost action is a prospective consensus snapshot collector for future SHADOW events, coupled with the SEC/IR reconstruction pipeline described here. No paid purchase is justified until an ablation or prospective study proves that the unavailable fields are material.

Historical options data is **not required** before validating `P_MODEL`. The option/IV layer can be calibrated prospectively from the existing IBKR SHADOW screenshot contract after the market-blind research record is frozen.

## 2. Gate interpretation

The existing contract requires all ten features and blocks missing or non-auditable inputs. This assessment therefore does not:

- replace missing revisions or dispersion with zero;
- mix consensus values from different vendors as if they formed one time series;
- infer standard deviation from high/low/count;
- use a current API response as an old point-in-time snapshot;
- treat an article's crawl date as its publication timestamp;
- use post-event articles for pre-event features;
- change feature definitions or the approved return horizon; or
- claim that the V1 priors are trained coefficients.

Every reconstructed item must retain the source URL, publisher, publication/acceptance timestamp, retrieval timestamp, extracted text or response hash, period identity, units, transformation version, and any later correction as a new revision rather than an overwrite.

## 3. Pilot universe

The representative pilot is deliberately liquid and spans the requested sectors. Cohorts must be assigned per event using information available at the cutoff; the labels below are only the sampling strata.

| Sector stratum | Tickers | Planned events | Preferred period |
|---|---|---:|---|
| Technology | AAPL, MSFT | 16–24 | 2022 onward |
| Consumer | AMZN, NKE | 16–24 | 2022 onward |
| Financial | JPM, SCHW | 16–24 | 2022 onward |
| Industrial | CAT, HON | 16–24 | 2022 onward |
| Healthcare | JNJ, CVS | 16–24 | 2022 onward |
| **Total planning envelope** | **10 tickers** | **80–120 events** | **8–12 per ticker where evidence exists** |

This is a feasibility envelope, not a claim that 80–120 complete records were downloaded. The empirical work below tested source behavior and individual public observations only; no bulk dataset was created.

## 4. Zero-cost source matrix

### 4.1 Event and universe

| Required field | Preferred zero-cost source and exact interface | Depth / timestamp semantics | PIT validity and provenance | Key, limits, rights | Missingness / leakage risk | Automation | Result |
|---|---|---|---|---|---|---|---|
| Ticker, issuer, CIK | [SEC Submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), `https://data.sec.gov/submissions/CIK##########.json` | Filing history; submissions update in real time | Original accessions and acceptance timestamps are auditable | No key; SEC asks clients to declare a user agent and stay at or below [10 requests/second](https://www.sec.gov/about/webmaster-frequently-asked-questions) | Symbol changes require a versioned identifier map | High | **PASS** |
| Earnings date and AMC/BMO | SEC 8-K filing index and attached release; company IR release/event archive | SEC acceptance timestamp is Eastern Time; IR release/event time is publisher supplied | Valid when an explicit release time exists, or when primary evidence unambiguously places release before 09:30 or after 16:00 America/New_York | No key; public filings/releases; retain URL and hash, respect site terms/robots | 8-K may be filed after the actual release; undated PDFs and ambiguous times must be blocked | Medium | **CONDITIONAL** |
| Confirmation / reliability | Evidence hierarchy: explicit IR event/release time → SEC acceptance plus matching exhibit → two independent contemporaneous sources | Per source | Store evidence tier and conflicts; do not silently resolve conflicts | $0 | Some issuers remove old IR pages; SEC exhibit normally remains | Medium | **PASS** as a method; individual events can fail |
| Sector | Pre-cutoff SEC SIC plus a versioned SIC-to-desk-sector map | SIC recorded in filings/submissions | PIT if taken from a filing available by the cutoff | No key | SIC is not GICS; conglomerates require a documented mapping rule | High | **CONDITIONAL** |
| Market-cap cohort | Latest pre-cutoff SEC shares-outstanding fact × accepted raw close | Shares context/filing acceptance timestamp; close dated to regular session | PIT if the fact was published by cutoff and price source passes | No SEC key; price-source conditions below | Shares can be stale; tags/units vary; buybacks between filing and event | Medium | **CONDITIONAL** |

### 4.2 Approved return horizon and price-derived inputs

The required horizon remains `PRE_EVENT_CLOSE_TO_POST_EVENT_CLOSE_ET_V1` with methodology `earn-return-horizon-v1.0.0`. A daily source date is not itself an exact timestamp: the ingestion record must derive and store 16:00 in `America/New_York`, including EDT/EST, after validating the date against the official exchange calendar.

| Required field | Preferred zero-cost source and exact interface | Depth / timestamp semantics | PIT / corporate-action treatment | Key, limits, rights | Missingness / leakage risk | Request estimate for pilot | Result |
|---|---|---|---|---|---|---:|---|
| Trading session and canonical close time | [NYSE hours and calendars](https://www.nyse.com/markets/hours-calendars) | Current and published holiday calendars; core session closes 16:00 ET | Use IANA `America/New_York`; retain calendar version and early-close flag | No key | Historical exceptional closures need explicit handling | 1 calendar refresh/year | **PASS** |
| Raw pre/post close, 20-day close history, benchmark and sector closes | [FMP historical non-split-adjusted EOD](https://financialmodelingprep.com/stable/historical-price-eod/non-split-adjusted?symbol=AAPL) | Basic plan advertises five years; daily date, not exchange timestamp | Store raw close; apply only intervening split factor; do not use dividend-adjusted close for event return | `FMP_API_KEY`; free Basic advertises 250 calls/day. [Pricing](https://site.financialmodelingprep.com/developer/docs/pricing) and [terms](https://site.financialmodelingprep.com/terms-of-service) restrict use/redistribution; persistent project retention needs written confirmation | Corrections, delistings, and entitlement changes; terms are the main blocker | Roughly 40 batched symbol-series calls plus validation | **CONDITIONAL** |
| Split events | FMP stable `https://financialmodelingprep.com/stable/splits?symbol=AAPL`; cross-check issuer filing/exchange notice | Five-year free-plan envelope | Version every split and source response | Same FMP conditions | Missing/late correction can corrupt return | About 10 calls | **CONDITIONAL** |
| Alternative EOD | [Tiingo EOD](https://www.tiingo.com/documentation/end-of-day), `https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate=...&endDate=...` | Free Starter advertises 30+ years; raw/adjusted OHLC, `divCash`, `splitFactor`; updates after close | Technically adequate | Free key, 50/hour and 1,000/day per [pricing](https://www.tiingo.com/about/pricing); current [terms](https://api.tiingo.com/tos/) prohibit Starter users from persistently retaining raw Tiingo data | Retention prohibition conflicts with the desk's auditable raw-price record | About 40 batched calls | **FAIL** for persistent audit storage |
| Alternative EOD | Alpha Vantage `TIME_SERIES_DAILY` and `TIME_SERIES_DAILY_ADJUSTED` in [official docs](https://www.alphavantage.co/documentation/) | Free compact response covers only the latest 100 observations; full output and adjusted daily history are premium | Insufficient for a 2022+ backtest on the free tier | `ALPHA_VANTAGE_API_KEY`; standard free service advertises 25 requests/day | Coverage truncation; adjusted endpoint entitlement | 40+ series calls | **FAIL** for requested history at $0 |
| Alternative EOD spot-check | Nasdaq historical close/NOCP pages; Stooq downloadable history | Nasdaq states NOCP is its official close; Stooq exposes long daily histories | Suitable for manual cross-checks, not yet a documented bulk source with stable correction, timestamp, and retention semantics | No key observed; site terms and endpoint stability require review | Undocumented interfaces, adjusted/raw ambiguity, and redistribution rights | Manual sample only | **CONDITIONAL** |
| Event return and realised volatility | Local deterministic calculation after source acceptance | Exact pre/post sessions and prior 20 sessions | Recompute from stored raw prices, timestamps, split ledger, and method version | No external cost | Any upstream price/timing failure blocks the observation | No additional calls | **PASS** as calculation |

**Price conclusion:** a private, personal feasibility build appears technically possible with FMP free EOD, but a persistent auditable dataset committed to or served from the project is conditional on written retention/use permission. This is a second gate, independent of the analyst-consensus failure.

### 4.3 Market-blind research features

| Feature | Zero-cost reconstruction path | Point-in-time test | Expected coverage / request volume | Leakage and missingness | Result |
|---|---|---|---|---|---|
| `eps_revision_z` | Prefer a dated pre-event Zacks preview that states both current consensus EPS and the 30-day percentage revision; corroborate period/date with SEC/IR. Alpha Vantage is a secondary test only. | Publication timestamp must precede cutoff; preserve text/hash; derive prior consensus algebraically only when the article explicitly defines the interval and current value | Public-search pass found examples in all five pilot sectors; one search plus one page fetch per event | Coverage and rights are not guaranteed; do not mix publishers or periods | **CONDITIONAL**, materially more feasible via public web than via free APIs |
| `revenue_revision_z` | Look for two same-publisher, same-definition, pre-cutoff consensus-revenue snapshots separated by the contract window, or an article explicitly stating revenue revision | Both timestamps and identical fiscal-period identity required | No consistent pair or explicit revenue-revision field was found in the tested sample | Cross-publisher values differ; a current revenue consensus alone is not a revision | **FAIL** |
| `guidance_trajectory` | Original SEC 8-K/10-Q/10-K exhibits, IR releases, and archived earnings-call materials; extract comparable company guidance with explicit metric/period/unit | Only material published by cutoff; later restatements are new revisions | Usually 2–5 primary documents/event; issuers that do not guide remain missing | No-guidance events cannot be scored as neutral unless contract allows it | **CONDITIONAL** |
| `consensus_dispersion_z` | Complete timestamped analyst estimate set, or a published contemporaneous mean and sample standard deviation | Must represent the full contributing set as of cutoff | Public pages sometimes expose average, high, low, and count; none tested exposed historical sample standard deviation or all analyst estimates | Range/count cannot recover standard deviation; hand-collecting selected broker figures creates selection bias | **FAIL** — hardest feature |
| `peer_readthrough_z` | Compute from prior, horizon-approved peer events only; peer set frozen by versioned sector/cohort map | Every peer event must have occurred before the target cutoff | About 2–6 qualifying peer observations/event after warm-up | Sparse early history; failed peer inputs must not be silently omitted | **CONDITIONAL** |
| `pre_earnings_drift_z` | Deterministic raw-close return over the contract window | All closes at or before cutoff | Included in ticker EOD series | Price-source rights and corrections | **CONDITIONAL** |
| `sector_regime_z` | Deterministic return for a versioned liquid sector ETF proxy | ETF mapping and all closes frozen before event | Roughly 11 series total for pilot, shared across events | ETF inception/sector-map changes; survivorship if current mapping is backfilled | **CONDITIONAL** |
| `index_regime_z` | Deterministic return for the contract benchmark | All closes at or before cutoff | One shared index/ETF series | Price-source conditions | **CONDITIONAL** |
| `company_specific_z` | SEC filings, IR releases, regulator releases, and timestamped material public news; apply existing anchored rules | Evidence must predate cutoff and exclude option-market concepts | 2–10 source documents/event | Search recall is imperfect; restrict the free build to cited, material, independently timestamped facts | **CONDITIONAL** |
| `surprise_reaction_beta_z` | Reported EPS from SEC/IR; contemporaneous pre-event consensus from a dated preview; approved event return; at least four prior pairs | Each consensus must be demonstrably pre-event and each prior event must pass the exact horizon | Four or more prior events after warm-up | Publisher methodology changes and sparse valid consensus snapshots can block the feature | **CONDITIONAL**, with significant attrition |

### 4.4 Estimate APIs tested

| Provider / endpoint | Historical depth claim | Timestamp semantics and PIT finding | Authentication / cost | Result |
|---|---|---|---|---|
| Alpha Vantage [`EARNINGS_ESTIMATES`](https://www.alphavantage.co/documentation/) | Documentation describes annual/quarterly estimates, analyst count, and revision history | Parameters are `function`, `symbol`, and `apikey`; no historical `as_of`, snapshot date, or vintage parameter is documented. Demo access did not return an inspectable IBM payload and requested a free key. A historical fiscal-period row returned today is not sufficient proof of its old pre-event state. | **FREE_KEY_REQUIRED**: `ALPHA_VANTAGE_API_KEY`; $0, 25 requests/day advertised | **FAIL** for strict historical PIT unless the provider supplies vintage semantics and they are empirically verified |
| FMP [`analyst-estimates`](https://financialmodelingprep.com/stable/analyst-estimates?symbol=AAPL&period=annual&page=0&limit=10) | Free Basic advertises five years for included datasets | FMP's own [revision-monitor article](https://site.financialmodelingprep.com/de/education/calendar/build-an-earnings-revision-pressure-signal-estimate-drift-monitor) says the API reflects current consensus rather than versioned history and recommends capturing snapshots locally over time | **FREE_KEY_REQUIRED**: `FMP_API_KEY`; $0, 250 calls/day | **FAIL** for historical PIT; useful for a prospective collector |
| Nasdaq earnings forecast pages | Historical earnings pages and current forecast presentation | Nasdaq notes that some earnings dates are algorithmic; no documented historical-vintage consensus API was identified | No key for pages | **FAIL** as sole PIT source; manual corroboration only |
| Search-indexed Zacks preview articles | Search located 2024 pre-event articles across all five pilot sectors | Article publication date plus explicit “revised X% over 30 days” creates a real PIT EPS-revision observation. Articles expose current revenue consensus but not revenue revision or dispersion standard deviation. | No API key; page availability, terms, robots, and reuse rights must be honored | **CONDITIONAL** for EPS revision/headline consensus; **FAIL** for the missing revenue-revision and dispersion fields |
| Internet Archive / cached dynamic estimate pages | Potentially long | A direct CDX snapshot test could not be completed in this environment. Even if snapshots exist, dynamic tables, robots exclusions, and original-site rights must be verified per source. Archive timestamp would prove capture time, not necessarily the vendor's underlying observation time. | No subscription expected; access and rights unverified | **UNRESOLVED**, not evidence sufficient to pass |

## 5. Empirical public-web findings

This pass deliberately tested whether GPT-led public research can reconstruct structured inputs without a packaged API. It did not merely inspect provider marketing pages.

### 5.1 Primary event-timing evidence

- Microsoft FY24 Q3: [SEC accession 0000950170-24-048268](https://www.sec.gov/Archives/edgar/data/789019/000095017024048268/0000950170-24-048268-index.htm) was accepted 2024-04-25 16:03:19 ET and contains the earnings release exhibit. This supports AMC classification for that event.
- Apple FY24 Q2: [SEC accession 0000320193-24-000067](https://www.sec.gov/Archives/edgar/data/320193/000032019324000067/0000320193-24-000067-index.htm) was accepted 2024-05-02 16:30:34 ET; [Apple's release](https://www.apple.com/newsroom/2024/05/apple-reports-second-quarter-results/) is dated May 2 and links the 17:00 ET call. This supports AMC classification.
- Johnson & Johnson Q1 2024: [SEC accession 0000200406-24-000031](https://www.sec.gov/Archives/edgar/data/200406/000020040624000031/0000200406-24-000031-index.htm) was accepted 2024-04-16 07:06:41 ET. J&J's [IR event notice](https://www.jnj.com/media-center/press-releases/johnson-johnson-to-host-investor-conference-call-on-second-quarter-results-2024) shows the company's normal explicit pre-market release/call scheduling. This demonstrates a viable BMO evidence pattern, while also showing why the IR source should be retained with the filing.

These observations establish that public primary sources can classify at least some events. They do not establish complete coverage; an event with ambiguous or conflicting timing remains blocked.

### 5.2 Search-indexed consensus/revision observations

The following dated public preview observations were found. Values are recorded here only to demonstrate source feasibility; they are not being ingested as a backtest dataset.

| Event | Pre-event source date | Consensus EPS | Consensus revenue | Stated 30-day EPS revision |
|---|---:|---:|---:|---:|
| AAPL, report 2024-05-02 | [2024-04-25](https://www.zacks.com/stock/news/2262315/apple-aapl-expected-to-beat-earnings-estimates-should-you-buy) | $1.51 | $89.99B | -0.38% |
| MSFT, report 2024-10-30 | [2024-10-23](https://www.zacks.com/stock/news/2355909/microsoft-msft-earnings-expected-to-grow-should-you-buy) | $3.08 | $64.41B | -0.10% |
| NKE, report 2024-12-19 | [2024-12-12](https://www.zacks.com/stock/news/2382848/analysts-estimate-nike-nke-to-report-a-decline-in-earnings-what-to-look-out-for) | $0.64 | $12.17B | -1.19% |
| JPM, report 2024-10-11 | [2024-10-04](https://www.zacks.com/stock/news/2346084/jpmorgan-chase-co-jpm-expected-to-beat-earnings-estimates-should-you-buy) | $4.04 | $41.01B | -1.06% |
| CAT, report 2024-10-30 | [2024-10-23](https://www.zacks.com/stock/news/2355871/analysts-estimate-caterpillar-cat-to-report-a-decline-in-earnings-what-to-look-out-for) | $5.33 | $16.35B | +0.22% |
| JNJ, report 2024-10-15 | [2024-10-08](https://www.zacks.com/stock/news/2347550/analysts-estimate-johnson-johnson-jnj-to-report-a-decline-in-earnings-what-to-look-out-for) | $2.19 | $22.19B | +0.07% |
| CVS, report 2024-08-07 | [2024-07-31](https://www.zacks.com/stock/news/2313113/analysts-estimate-cvs-health-%28cvs%29-to-report-a-decline-in-earnings%3A-what-to-look-out-for) | $1.74 | $91.56B | +0.17% |

Observed availability was 7/7 targeted examples across the five sector strata for a headline consensus and stated EPS revision. That is encouraging evidence for an AI research pipeline, but it is not a random coverage estimate and cannot be extrapolated to 100 complete events.

### 5.3 Why headline snapshots do not complete the contract

For AAPL's 2024-05-02 event alone, dated public pages showed revenue consensus values around $89.8B, $89.99B, $90.4B, and $90.608B depending on publisher and timestamp. Those are legitimate contemporaneous observations but are not one homogeneous series. Treating the difference as a “revision” would combine vendor universes, update schedules, and definitions.

The Zacks preview provides a valid same-methodology 30-day EPS change in one record. The tested public pages did not provide the corresponding 30-day revenue change. They also did not provide every analyst observation or sample standard deviation. High, low, and count do not identify the distribution: many different estimate sets have the same range and count but different standard deviation.

Therefore GPT can credibly normalize the public evidence that exists, but cannot manufacture the two missing statistics from prose. Greater research effort improves coverage; it does not make an underdetermined quantity deterministic.

## 6. Point-in-time leakage assessment

| Risk | Control | Residual status |
|---|---|---|
| Current consensus attached to an old fiscal period | Require a publisher timestamp before event cutoff or a versioned `as_of` API response | Controlled for dated articles; failed for AV/FMP historical reconstruction |
| Search result snippet updated after publication | Fetch canonical page; store page timestamp, relevant text, retrieval time, and content hash; never use snippet alone | Conditional on page availability |
| Post-event edit to an old article | Prefer immutable SEC accessions; compare archive/canonical metadata; flag retrieval after event; preserve first captured hash | Cannot always be eliminated retrospectively |
| Fiscal-period mismatch | Join on ticker, fiscal period end, event date, metric basis, currency, and adjusted/GAAP definition | Deterministic if metadata exists |
| Vendor mixing | A revision pair must use the same publisher, metric definition, and analyst universe | Strictly controlled; lowers coverage |
| Event timing leakage | Require primary evidence for AMC/BMO; ambiguous events blocked | Conditional |
| Peer look-ahead | Freeze peer map and include only peer events completed before target cutoff | Deterministic |
| Price/corporate-action leakage | Store raw closes and split ledger; calculate only from sessions available at cutoff; retain provider corrections as revisions | Conditional on price rights/source |
| News hindsight | `company_specific_z` evidence must carry a publication timestamp before cutoff; later summaries are excluded | Conditional on search recall and timestamp quality |

## 7. Expected clean-event count

### Full existing V1.1 contract

**Expected fully usable historical events at $0 under currently verified sources: 0.**

This is not because no public evidence exists. It is because every event would lack at least `revenue_revision_z` and `consensus_dispersion_z`, and the current contract blocks incomplete inputs. Filling either with a neutral score would weaken the gate.

### Partial reconstruction, not valid for full `P_MODEL`

- Event/timing, primary-source research, and many price-derived records: **80–120 events are plausible** for the ten-name 2022+ pilot, subject to price retention permission and timing attrition.
- Headline pre-event EPS/revenue consensus plus stated EPS revision: the seven targeted examples all produced a usable article, but a neutral sampling audit is still required before estimating coverage.
- Four-prior-event surprise/reaction histories will reduce early-period coverage even after consensus is available.

Changing the period or universe cannot solve the missing historical revenue-revision and dispersion statistics. Narrowing to large issuers with strong IR archives improves event timing and guidance. Expanding tickers increases partial records but does not make the missing consensus distribution observable. A prospective collector can solve the future-vintage problem at $0 by storing daily or weekly FMP/current-page snapshots from now onward, but it cannot create a 2022 history retroactively.

## 8. Hardest feature

`consensus_dispersion_z` is the hardest feature. It requires the cross-sectional distribution of analyst estimates at a precise historical cutoff. Public articles usually publish only a mean consensus; some current pages add high, low, and count. Those summary statistics are insufficient to calculate the required sample standard deviation. Collecting a handful of named broker estimates from news articles would be systematically selected, inconsistent across time, and not equivalent to the contributing analyst set.

`revenue_revision_z` is the second terminal gap. Public-web reconstruction can often find multiple revenue consensus numbers, but without a same-provider vintage pair or explicit revision measure their differences cannot be treated as time-series revisions.

## 9. Unresolved gaps and free experiments still worth running

1. Obtain free Alpha Vantage and FMP keys and save raw schemas for a small, non-production sample. This will verify present behavior but is not expected to change the documented PIT conclusion.
2. Ask FMP in writing whether free-plan responses may be retained in an internal audit dataset and whether any endpoint exposes estimate-vintage timestamps.
3. Run a neutral 30-event search audit, selected before searching, to measure dated-preview coverage and page stability rather than relying on successful examples.
4. Test lawful archive availability for static Zacks/Barchart/Nasdaq estimate pages. Treat archive capture time only as provenance; verify that dynamic table contents are actually archived and that reuse is permitted.
5. Search company IR sites for issuer-published analyst-consensus workbooks. These exist for some non-US issuers but were not shown to be systematic for the US pilot.
6. Start a prospective $0 snapshot ledger now: current EPS/revenue mean, analyst count, high, low, and any published standard deviation, captured with response hash and cutoff. This can validate future events but not backfill 2022–2026.

None of these experiments authorizes changing missing mandatory features to zero or proceeding to historical coefficient calibration.

## 10. `P_MODEL` validation design once complete data exists

Milestone 2A does not fit or change coefficients. The V1 weights remain priors, not empirically trained parameters.

### 10.1 Event target and splitting

- First usable round: at least 100 fully gated events, with no ticker contributing more than 15%.
- Preferred calibration round: 200–300 events because ten predictors, tails, sector/cohort checks, and calibration bins are unstable at 100.
- Initial period: 2022-01-01 through 2025-12-31, subject to actual evidence availability.
- Rolling origin: train 2022–2023, validate 2024, and keep 2025 untouched as the final test. Within any expanding-window rerun, standardization parameters, peer histories, and surprise/reaction pairs are calculated only from observations preceding each target event.
- Grouping: report by sector, market-cap cohort, AMC/BMO, and ticker concentration. Do not tune against the final test.

One hundred events is enough for an engineering smoke test and a coarse directional/calibration check. It is not enough to claim stable tail probabilities, reliable sector-specific performance, or trained ten-feature coefficients. Confidence intervals and bootstrap intervals should be reported.

### 10.2 Frozen baselines

**Direction**

1. Constant 50/50 probability.
2. Historical ticker up-rate from the expanding training window, shrunk to the unconditional training-window rate when sparse.
3. Sector × market-cap-cohort × AMC/BMO historical up-rate where the training cell has adequate count; otherwise use a predeclared shrinkage hierarchy.
4. Simple pre-earnings drift sign/probability baseline.

**Expected signed return**

1. Zero return.
2. Historical ticker mean event return, estimated only from the expanding training window.
3. Sector/cohort/AMC-BMO mean event return with the same predeclared sparse-cell shrinkage.

**Absolute move**

1. Historical ticker mean absolute event return.
2. Sector/cohort mean absolute event return.
3. A realised-volatility-only estimate using the frozen conversion rule and the pre-event 20-day realised volatility.

The existing V1-prior `P_MODEL` is frozen before viewing each validation/test block and compared with every applicable baseline.

### 10.3 Metrics

- Brier score and Brier skill score versus the unconditional baseline.
- Log loss with probabilities clipped only by a predeclared numerical epsilon.
- Reliability table/plot and calibration intercept/slope.
- Directional accuracy at 0.50, with class balance shown.
- ROC AUC as a ranking diagnostic, not the primary probability metric.
- Signed expected-return bias, MAE, RMSE, and rank correlation.
- Expected-versus-actual absolute-move bias, MAE, and RMSE, including error relative to the realised-volatility-only baseline.
- Performance by probability bucket, sector, cohort, and AMC/BMO with event counts.
- Tail exceedance calibration for the contract's move thresholds, plus direction diagnostics for `p <= 0.25` and `p >= 0.75`; no tail claim where count is inadequate.
- Comparison of V1 priors against each frozen baseline, with paired bootstrap confidence intervals by event and a ticker-cluster sensitivity check.

Promotion beyond SHADOW requires evidence that the full, leakage-free model improves probability quality out of sample. A positive in-sample result or a fitted coefficient set is insufficient.

## 11. Forward option/IV plan

Free historical option quote history with the required contract-level bid/ask/IV, spot, DTE, and exact observation time was not identified. That does **not** block Stage 1 `P_MODEL` validation.

Public delayed chains, current broker pages, and exchange sample files do not reconstruct old quotes at the desk's entry/exit timestamps. ORATS documents appropriate historical strike-level fields and near-EOD/intraday products, but those are **PAID_FALLBACK** products rather than the default route. No historical option subscription is recommended for this milestone.

Use the existing IBKR screenshot process prospectively in SHADOW:

1. Freeze and hash the market-blind research pack and `P_MODEL` output before viewing option-market information.
2. At the predeclared near-EOD observation time, capture the exact expiry/strike/right, bid, ask, IV, underlying spot, exchange/session, and screenshot timestamp.
3. Capture the same contract and underlying at the defined post-event observation time.
4. Store screenshot hashes, extraction status, manual-review notes, and correction history; never synthesize missing quotes or IV.
5. Accumulate enough clean pairs before calibrating residual IV. Keep CORE/LIVE blocked under existing gates.

This forward plan costs $0 incremental data subscription if the existing IBKR access exposes the required live data. Any exchange-data entitlement already required by the brokerage account is outside this report and must not be assumed.

## 12. Optional paid fallback — not recommended until materiality is proven

The single smallest packaged-data purchase that appears capable of closing the critical analyst-estimate gap is a custom Intrinio/Zacks historical estimates entitlement covering **both EPS Estimates and Sales Estimates**, including the historical archive and revision fields. Intrinio advertises 20+ years of history and revision tracking for [EPS Estimates](https://intrinio.com/products/eps-estimates) and lists EPS/Sales Estimates as enterprise products on its [pricing page](https://intrinio.com/pricing).

This remains **AUTH_REQUIRED**, **QUOTE_REQUIRED**, and **CONDITIONAL** until a sample export proves:

- true observation/vintage timestamps rather than only fiscal-period dates;
- historical mean, analyst count, and standard deviation (or complete analyst estimates) at the research cutoff;
- compatible revenue estimate vintages;
- licensing that permits the desk's storage, derived features, and audit trail.

Public pricing is not disclosed, so a responsible approximate dollar cost cannot be stated from public evidence. The commercial structure is an enterprise subscription plus a one-time historical-data payment. No purchase should be requested yet: first use prospective free snapshots or a lawful vendor sample to test whether the two missing features add material out-of-sample value.

ORATS is not the minimum fallback for this gate. Its paid history is relevant to the later option layer, but it does not solve analyst consensus revisions/dispersion and historical options are not required for Stage 1.

## 13. Required credentials, cost, and audit record

### Free keys

- `ALPHA_VANTAGE_API_KEY`: optional verification only; it does not currently satisfy historical PIT semantics.
- `FMP_API_KEY`: useful for prospective estimate snapshots and a private EOD feasibility sample; retention/use must be cleared before creating the persistent audit dataset.
- SEC/EDGAR, company IR, NYSE/Nasdaq public pages, and search-indexed articles require no API key.

No key is needed to support this gate decision.

### Cost

- **EXPECTED RECURRING DATA COST: $0** for the recommended immediate research and prospective collection path.
- Direct recurring data cost of the recommended immediate work: **$0**.
- AI research/computation, storage, and operator review: internal operating costs, not data subscriptions.
- Paid fallback approximate cost: **not publicly estimable / enterprise quote required**; do not purchase at Milestone 2A.

### Provenance record required for every future observation

`source_id`, canonical URL/endpoint, provider, retrieved timestamp, publisher/SEC timestamp, event cutoff, raw response/text hash, fiscal period, units/basis, extraction method/model version, human-review status, supersedes/revision pointer, and the applicable feature/horizon methodology version.

## 14. Final gate

Public primary research is viable for most qualitative features and event evidence, and dated public earnings previews can recover more EPS history than the free APIs expose. However, the existing deterministic contract cannot admit a historical observation without revenue-consensus revision and analyst-dispersion evidence. Those quantities were not found in a consistent, auditable, historical public source, and inferring them would fabricate data or weaken the gate. A valid 100-event full-model sample therefore cannot be built at $0 from the sources presently verified.

STOP — FREE HISTORICAL DATA NOT SUFFICIENT
