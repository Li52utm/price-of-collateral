# Data sources

Every source below was downloaded on **4 November 2026** (not assumed). Series keys, coverage and
publication lags are as measured that day. The registry in `src/sources.py` holds the same keys and
lags; `results/snapshots/manifest.json` records the coverage of the committed snapshot at each
refresh. Lags are in business days after the observation date, set conservatively.

## Summary

| Source | Series (key) | Key needed | Frequency | Coverage | Publication lag | Model input |
|---|---|---|---|---|---|---|
| ECB Data Portal | €STR `EST/B.EU000A2X2A25.WT` (+ percentiles, volume) | No | Daily | 1 Oct 2019 → | T+1 08:00 CET (1) | Yes (target) |
| ECB Data Portal | Pre-€STR | — | — | Not in the API | — | No |
| ECB Data Portal | EONIA `EON/D.EONIA_TO.RATE` | No | Daily | 1999 → 31 Dec 2021 | 1 | History only |
| ECB Data Portal | DFR `FM/D.U2.EUR.4F.KR.DFR.LEV`, MRO `...MRR_FR.LEV`, MLF `...MLFR.LEV` | No | Daily | 2008 → | Known in advance (0) | Yes |
| ECB Data Portal | Excess liquidity `ILM/D.U2.C.EXLIQ.U2.EUR`, reserve requirements `ILM/D.U2.C.MRR.U2.EUR` | No | Daily | 27 Sep 2024 → | 1 | Check only (short) |
| ECB Data Portal | Current accounts `ILM/W...L020100`, deposit facility `...L020200`, MLF `...A050500` | No | Weekly (Friday) | 1999 → | 2 | Yes (liquidity proxy) |
| ECB Data Portal | Monetary policy securities (APP + PEPP) `ILM/W.U2.C.A070100.U2.EUR` | No | Weekly | Jul 2009 → | 2 | Yes |
| ECB Data Portal | MMSR secured: rate and volume by collateral country (DE, FR, IT, ES, BE, NL, all), tenor (S/N, T/N, O/N, 1W, 1M), lending/borrowing `MMSR/B.U2._X.<cty>.S1ZV._Z.T.<LE/BO>.<WR/TT>._X.<tenor>._Z._Z.EUR._Z` | No | **Maintenance period** (69 periods), dated at the period end, rates to 1 bp | Mar 2018 → Sep 2026 | > 6 business days after the period end (10 used) | Chapter III (not daily) |
| ECB Data Portal | 10-year yields for convergence purposes `IRS/M.<cty>.L.L40.CI.0000.EUR.N.Z`, 11 countries | No | **Monthly** average | 1990s → Sep 2026 | about 25 | Chapters III-IV |
| ECB website | PSPP net purchases by country (`PSPP_breakdown_history.csv`) | No | Monthly | Mar 2015 → | about 25 | Chapter III (scarcity) |
| Bundesbank | Current 10-year Bund `BBSSY/D.REN.EUR.A630.000000WT1010.A` | No | Daily | Oct 2001 → | Same day (1 used) | Chapter IV |
| Banque de France Webstat | French 10-year constant maturity (TEC10) `FM.D.FR.EUR.FR2.BB.FRMOYTEC10.HSTA` | **Yes** (free; header `Authorization: Apikey <key>`) | Daily | 3 Nov 2004 → | Updates 09:00, 13:00, 21:00 Paris; day d usable from d+1 (1) | Chapter IV (daily, U1) |
| Banque de France Webstat | Germany, Italy, Spain 10-year `FM.M.<cty>.EUR.FR2.BB.<cty>10YT_RR.YLD` | Yes | **Monthly only** (no daily series in any dataset, searched 5 Nov 2026) | — | — | Not used (ECB IRS kept; daily Bund from the Bundesbank) |
| DBnomics (BdF mirror) | `BDF/FM/M.<cty>.EUR.FR2.BB.<cty>10YT_RR.YLD` | No | Monthly only | — | — | Not used (ECB IRS preferred) |
| RepoFunds Rate, STOXX/Eurex GC Pooling | Daily euro GC repo | Login / no download | — | — | — | Not used |
| AFT | Auction results | Blocked (Cloudflare challenge) | — | — | — | Not used |
| French CDS | — | No free source | — | — | — | Not used |
| LCH SA, Euronext Clearing, Eurex | Haircut schedules | Current PDFs only | — | No history | — | Not used |
| NY Fed Markets API | SOFR, TGCR, BGCR, EFFR with percentiles and volumes (`/api/rates/all/search.csv`) | No | Daily | 2 Apr 2018 → | T+1 08:00 ET (1) | Yes (target) |
| NY Fed Markets API | ON RRP propositions, repo operation results (`/api/rp/...`) | No | Daily | `last/N` works; date search rejects ranges | Same day | Via FRED instead |
| FRED | IOER, IORB, `DFEDTARU/L`, `RRPONTSYD` (ON RRP), `RPONTSYD` (Fed repo incl. SRF) | No (plain requests; browser User-Agent times out) | Daily | 2008 → | 0-1 | Yes |
| FRED | Reserves `WRESBAL`, TGA `WTREGEN`, securities `WSHOSHO` | No | Weekly (Wednesday, H.4.1 Thursday) | 2002 → | 1 | Yes |
| FRED | Country 10-year yields `IRLTLT01..M156N` | No | Monthly | — | — | Not used (ECB IRS) |
| OFR Short-term Funding Monitor | DVP O/N `REPO-DVP_AR_OO`, DVP term `REPO-DVP_AR_LE30` (to 13 Aug 2025) then `REPO-DVP_AR_B830` | No | Daily | 8 May 2018 → | Preliminary T+1; final about 4 months | Yes (term vs overnight) |
| Treasury Fiscal Data | Auction issue (settlement) dates and sizes `auctions_query`; TGA `dts/operating_cash_balance` | No | Daily | 2018 → | Issues known in advance; DTS 16:00 ET T+1 (2) | Yes |
| Bank of Japan API | TONA `FM01/STRDCLUCON` | No | Daily | 1998 → | 2 (holiday 3 Nov: data to 30 Oct on 4 Nov) | Yes |
| Bank of Japan API | Collateralized O/N call `FM02/STRDCLCOON` | No | Daily | 2025 → (monthly average 1960 →) | 2 | Chapter VI |
| Bank of Japan API | Basic loan rate `IR01/MADR1Z@D`; current accounts `MD01/MABS1AN113` | No | Daily; monthly | 1882 →; 1981 → | 0; 3 | Yes |
| JSDA | Tokyo Repo Rate | Site returned 404 and HTTP 429 | — | BoJ copy discontinued 2012 | — | Not used |

Tools: statsmodels 0.15.0 provides `QuantReg`, `MarkovRegression`, HAC (Newey-West) covariance,
OLS-based CUSUM tests and `VECM`; structural breaks are tested with a Chow test at a date fixed in
advance (implemented in `src/stats_tools.py`). lifelines 0.30.3 installs on Python 3.14 but forces
pandas 2.3.3, so Kaplan-Meier is implemented in-house (`src/survival.py`).

## Feasibility by chapter

| Chapter | Verdict | Data |
|---|---|---|
| I The Story | Feasible | All of the below, simplified |
| II Three Corridors | Feasible | €STR/DFR/MRO/MLF, SOFR/EFFR/IORB/target range/ON RRP, TONA/BoJ policy; reserves (weekly), euro liquidity (weekly), BoJ current accounts (monthly) |
| III The Price of Collateral | Feasible at **maintenance-period frequency** | MMSR repo by collateral country (69 periods) against monthly yield spreads and PSPP holdings |
| IV Italy Then, France Now | **Daily** for France (OAT-Bund), monthly for the cross-country parts | Webstat TEC10 + Bundesbank daily Bund (from Nov 2004); ECB IRS monthly yields for 11 countries since 1999 |
| V The Calendar | Feasible for USD and EUR unsecured (€STR); no daily euro repo | €STR from Oct 2019, SOFR from Apr 2018, OFR term repo, Treasury settlements |
| VI Japan | Feasible for TONA; repo only via collateralized call (daily from 2025) | BoJ API |
| VII Desk note | Feasible | Built on V and IV |

## France: what the data supports

- **(a) Bund-driven vs France-driven moves; France-specific vs euro-wide stress.** Supported at
  monthly frequency: the OAT-Bund spread change splits exactly into the OAT leg and minus the Bund
  leg, and a regression of French spread changes on Italian (and Spanish) spread changes separates a
  euro-wide component from a France-specific residual. Since U1 the OAT-Bund split is also daily (Webstat
  TEC10 against the Bundesbank Bund); the euro-wide split stays monthly (no daily Italian or Spanish yield).
- **(b) Survival analysis of spread blowouts.** Supported: monthly 10-year spreads against Germany for
  IT, ES, PT, FR, BE, GR, IE, NL, AT, FI since 1999 (episodes counted from 2008).
- **(c) Is French collateral priced more like Italian in repo?** Supported at maintenance-period
  frequency (MMSR by collateral country, 69 periods from 2018), with a break test at a fixed date.
  Small sample; rates are rounded to 1 bp.
- **(d) Event study.** Daily since U1 (two-day window around each event, against every two-day window
  since 2010); the monthly version is kept as a robustness check. Events are restricted
  to ones with an official source URL that resolved when checked.

## Webstat (Banque de France), added 5 November 2026 (U1)

- Base URL `https://webstat.banque-france.fr/api/explore/v2.1/catalog/datasets/`. Authentication ONLY with
  the header `Authorization: Apikey <WEBSTAT_API_KEY>`; a missing or badly formatted key returns a
  misleading `NotFoundResource`. The key is read from the environment or the git-ignored `.env`
  (`download.webstat_key`), never printed, logged, written or put in a URL. In GitHub Actions it comes
  from the repository secret `WEBSTAT_API_KEY`.
- Discovery: `series/exports/json?select=series_key,title_en,...&refine=dataset_id:FM`, then a search of
  `title_long_en`/`title_long_fr` and `series_key` for "10-year", "10 ans", "OAT", "TEC10", "benchmark",
  "10YT", "yield"/"rendement". The only daily 10-year government yield is France's TEC10 (constant
  maturity, interpolated by the Banque de France). Germany, Italy and Spain have monthly series only.
- Download: `observations/exports/json?select=time_period_start,obs_value,obs_status&where=series_key="<key>"&order_by=time_period_start`,
  one request per series (full history). Observations with status `M` (missing) are dropped (2,403 of
  8,037 rows: weekends and holidays); status `U` (unreliable) would be kept and counted (none so far).
- Quota: 10,000 requests a day; exceeding it can get the account banned. The client (`download.Webstat`)
  counts requests, stops at a budget of 200 per process, never loops day by day, caches raw JSON in
  `data/webstat/`, and stops on HTTP 429 with a clear error (no retries). Discovery and the first
  download used 6 requests in total.
- Validation: the monthly mean of the daily TEC10 differs from the ECB IRS French yield by 1.8 bp on
  average over 263 months (PASS); monthly changes of the daily-based OAT-Bund spread correlate 0.93 with
  the ECB-based spread.
- Added to the committed snapshot with `scripts/refresh_snapshots.py --add-new-series`, capped at what
  was published by the snapshot's fetch time (last observation 3 November 2026), so no other series
  changed.

## Coverage of the committed snapshot

`results/snapshots/manifest.json` lists the first and last date, number of observations and
publication lag of every series in the snapshot. `docs/DATA_VALIDATION.md` holds the validation
report from the latest refresh.
