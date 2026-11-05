# Methodology

Every model, every modelling choice that could be tuned to the results, and every correction.
Fixed choices are written here (and as constants in code) BEFORE the test results are looked at;
the date each block was fixed is given. Changing any of them later requires an entry in the
corrections log with the before and after numbers.

## Phase 2: the forecasting engine (fixed 2026-11-04, before any test-period result was computed)

Code: `src/features.py`, `src/forecast.py`, `src/stats_tools.py`.

### Targets (basis points, daily)

| Currency | Target | First day | Why |
|---|---|---|---|
| USD | SOFR minus interest on reserves (IOER to 28 Jul 2021, IORB afterwards) | 2 Apr 2018 | The Fed's floor system: reserves earn IOR, so repo above IOR signals reserve scarcity |
| EUR | €STR minus the deposit facility rate | 1 Oct 2019 | The ECB's floor system since 2015; €STR is the only daily euro overnight rate that is free |
| JPY | TONA minus the BoJ policy rate (`data.boj_policy`) | 4 Jan 2016 | Comparison only; not in the desk note |

A daily euro repo-minus-DFR target was planned but no free daily euro repo rate exists (see
CLAUDE.md, Plan adjustments).

### Forecast horizon

`HORIZON_BD = 40` business days of the target's calendar. Every state variable enters the model as it
was published 40 business days before the target day (on top of its own publication lag). Why 40:
it is the lead time of the desk note (the snapshot's as-of date, 3 November 2026, is 40 US business
days before 31 December 2026), and a funding decision for a year-end turn is made weeks ahead.
Calendar features are known in advance and enter without a lag.

### Calendar features (`features.calendar_features`)

All dates are business days of the target's calendar.

- `me`: last business day of a month; `me_m1`: the business day before; `me_p1`: the first business day of the next month.
- `qe`: additional effect on the last business day of March, June, September, December (on top of `me`).
- `ye`: additional effect on the last business day of December (on top of `me` and `qe`); `ye_m1`, `ye_p1`: the days either side.
- `us_settle` (USD only): a US Treasury note or bond settles that day (from Fiscal Data issue dates; the settlement calendar is fixed by Treasury's regular schedule, so it is known in advance).
- `us_tax` (USD only): the first business day on or after 15 March, 15 April, 15 June, 15 September and 15 December (corporate and individual tax dates).
- `mp_end`, `mp_start` (EUR only): last and first day of an ECB reserve maintenance period
  (`data.maintenance_period_ends`). For dates after the last known period end the flags are zero;
  31 December is not a period boundary in 2026 (the December period starts after the 17 December meeting).

### State features (point in time at the forecast origin, 40 business days before the target day)

- `level`: the mean of the target over the last 5 published days at the origin (persistence).
- USD: `liq` = reserve balances (USD trillion), `rrp` = ON RRP take-up (USD trillion).
- EUR: `liq` = liquidity proxy (current accounts + deposit facility - marginal lending, EUR trillion), `rrp` absent.
- JPY: `liq` = BoJ current account balances (JPY 100 trillion).
- Interactions: `qe x liq`, `ye x liq` (does scarcity make turns worse?).

### Models (each forecasts the 5th, 50th, 90th and 95th percentiles)

1. **Baseline, "same as the last comparable turn".** The point forecast for day D is the target on the
   most recent day of the same type (year-end, quarter-end, month-end, or ordinary day) that was
   published by the origin. Quantiles = point forecast + the empirical quantiles of this rule's errors
   on the training period.
2. **Calendar-only**: linear quantile regression (`statsmodels.QuantReg`) on the calendar features.
3. **Calendar + state**: quantile regression on calendar and state features.

Quantiles that cross are sorted per day.

### Train / test

- Train: from the first day of each target to **31 December 2022**. Test: **1 January 2023** onward.
  Why: the train period covers both abundant-liquidity regimes and the 2022 hiking cycle; the test
  period is quantitative tightening and the reserve drain to the end of the sample, which is the regime
  the desk note forecasts. The euro target starts in Oct 2019 (no €STR before), so its train period is
  shorter (four year-ends: 2019-2022); the dollar has five (2018-2022).
- Models are fitted ONCE on the train period and evaluated on every test day.

### Evaluation (test period)

- Pinball loss per quantile, averaged over (a) all test days and (b) turn days (`me`, `qe`, `ye` days).
- Coverage: share of test days with the actual below each quantile forecast, and inside the 5-95 interval.
- Diebold-Mariano test of each model against the baseline on the per-day pinball loss averaged over
  the four quantiles; Newey-West variance with `HORIZON_BD - 1` lags and the Harvey, Leybourne and
  Newbold small-sample correction; two-sided p-values.
- **Winner rule (fixed in advance):** the model with the lowest mean pinball loss on test TURN days.
  If the baseline wins, the baseline is reported as the winner.

### Euro vs dollar year-end

Turn effect for each year-end, quarter-end and month-end: target on the turn day minus the mean of the
target over the 10 business days before the turn day (bp). Reported per currency: mean, median and sign.

### Term vs overnight (USD only)

- No free daily euro term repo rate exists (MMSR 1-week and 1-month rates are maintenance-period
  averages; €STR compounded averages are backward-looking), so the euro version is skipped.
- For every month-end in the test period: start day S = 7 business days before the month-end, a
  14-calendar-day borrowing of USD 100m. Overnight cost: the OFR DVP overnight rate on each night
  (ACT/360). Term cost: the OFR DVP term rate on S (<=30-day bucket to 13 Aug 2025, 8-30 days after).
- Decision on S using only data published by S: `premium` = term rate minus overnight rate, both the
  latest published values; `spike` = mean over the window of the winning model's median forecast minus
  the last published target level. **Rule: lock term iff spike > premium.**
- Compare total cost of always-overnight, always-term and the rule (USD per 100m).

### Year-End 2026 forecast

- The winning model (per currency) is refitted on all data to the as-of date and forecasts every
  business day from 21 December 2026 to 8 January 2027; the headline is 31 December 2026.
- Stored in `results/forecasts/yearend_2026.json` with model version, data as-of date, creation
  timestamp, git commit and a SHA-256 of the forecasting code. The file is created once by
  `scripts/freeze_forecast.py`, which refuses to overwrite it. No refresh writes it.
- Scoring (`forecast.score_yearend`): once the snapshot contains 31 December 2026 for a currency,
  the actual target, whether it is inside the 5-95 interval, and the pinball loss per quantile are
  written to `results/forecasts/yearend_2026_score.json` by every refresh.

## Phase 3: Three Corridors (fixed 2026-11-04, before any result was computed)

Code: `src/corridors.py`.

### Corridors and regimes

- ECB: floor DFR, MRO, ceiling MLF; market rate €STR (EONIA before Oct 2019, for context).
- Fed: target range lower and upper bound, IOR (IOER, then IORB); market rates SOFR and EFFR.
- BoJ: policy rate (`data.boj_policy`), ceiling the basic loan rate; market rate TONA.
- Regime annotations are computed from the data, never typed: negative-rate periods (policy rate
  below zero), the US zero lower bound (upper bound <= 0.25%), and hiking / cutting phases (runs of
  policy changes in one direction, from the first to the last change).

### Markov regime switching

- Model: `statsmodels` `MarkovRegression`, two regimes, switching intercept and switching variance,
  on the DAILY spread to policy of each currency (the Phase 2 targets, in bp).
- Fitted on the train period (to 31 Dec 2022). The "stressed" regime is the one with the higher
  variance. Test (2023 onward): the train parameters are held fixed and the model is run forward over
  the full sample, so each day's filtered probability uses only data up to that day.
- Random starting values (`search_reps=20`) are drawn with a fixed seed (`rng=0`) so results are reproducible.
- Evaluation on test: (1) log-likelihood per test day against a one-regime normal fitted on train;
  (2) the share of test days in the stressed regime (filtered probability > 0.5), per year.

### Reserves and liquidity against the spread

- USD: weekly reserve balances (Wednesday, USD trillion) against the mean of SOFR minus IOR over the
  following five business days (Thursday to the next Wednesday). EUR: weekly liquidity proxy (EUR
  trillion) against the mean of €STR minus DFR over the following week. JPY is not modelled: the
  negative-rate tiering system breaks the link between balances and the marginal rate.
- Three fits: linear; piecewise linear with one kink (kink chosen by least squares on a grid of the
  5th-95th percentiles of the training reserves); S-shaped (logistic in reserves, four parameters).
- Chosen out of sample: fitted on weeks to 31 Dec 2022, the model with the lowest root mean squared
  error on weeks from 2023 wins.
- Where pressure starts: for the piecewise fit, the kink; for the logistic, the reserve level at which
  the fitted spread is 2 bp above its abundant-reserve plateau. 95% confidence band from a moving-block
  bootstrap on the full sample (blocks of 8 weeks, 500 resamples, seed 42).

### Case studies

Windows fixed in advance: September 2019 (2 to 30 Sep 2019), March 2020 (2 to 31 Mar 2020), year-end
2025 (1 Dec 2025 to 9 Jan 2026). For each currency with data in the window: peak spread and its date,
the mean over the 10 business days before the window, and the reserve or liquidity level at the start.

## Phase 4: collateral and France (fixed 2026-11-04, before any result was computed)

Code: `src/collateral.py`, `src/france.py`, `src/survival.py`, `src/events.py`.

### III. Credit risk or scarcity?

- Frequency: ECB maintenance periods (MMSR, 69 periods from Mar 2018; dated at the period end).
- Repo rate by collateral country: MMSR secured, **lending** side (cash lent against the collateral),
  **spot-next** tenor (the largest-volume tenor). Spread = country rate minus the German-collateral rate (bp).
- Credit proxy: 10-year yield spread to Germany (ECB IRS, monthly), averaged over the calendar months the
  period covers. Scarcity proxies: euro liquidity (weekly proxy, mean over the period, EUR trillion) and
  Eurosystem PSPP holdings of German bonds (cumulative net purchases, EUR 100 billion, month-end before
  the period end).
- Regression per country (IT, FR): spread = a + b credit + c liquidity + d German holdings, Newey-West
  errors with 3 lags. Comparison on standardised coefficients (coefficient x standard deviation of the
  regressor). **Decision rule:** "credit" if the credit term is significant at 5% and its absolute
  standardised effect exceeds the sum of the two scarcity terms; "scarcity" if at least one scarcity term
  is significant and their sum exceeds the credit term; otherwise "both / unclear".
- Structural break at the start of quantitative tightening, **1 March 2023** (the ECB stopped reinvesting
  part of its APP portfolio from March 2023, the first fall in its bond holdings). Chow test of the full
  regression, split at the first period ending after that date.
- Rolling coefficients: windows of 24 periods (about 2.8 years).

### IV(a). Decomposition and France-specific stress (monthly)

- Exact split: change in (FR - DE) = change in FR (OAT leg) - change in DE (Bund leg).
- Euro-wide vs France-specific: regress the monthly change in the FR-DE spread on the changes in the IT-DE
  and ES-DE spreads, estimated on **Jan 2010 - Dec 2023** (before the French political episode). From
  2024 the out-of-sample residual is the France-specific stress; the fitted part is the euro-wide part.
  Cumulated from **June 2024** (the dissolution of the National Assembly, 9 June 2024).

### IV(b). Survival of spread blowouts

- Spreads to Germany, monthly, for IT, ES, PT, FR, BE, GR, IE, AT, NL, FI; episodes counted from Jan 2008.
- **Blowout start:** the first month in which the spread is at least **X = 30 bp** above its average over
  the previous 12 months (the baseline). Why 30 bp: about two standard deviations of the monthly change in
  core euro spreads, and roughly the size of the widening that euro government bond desks call a
  repricing rather than noise. Sensitivity (fixed in advance, reported but not used for the answer):
  X = 20 bp and X = 50 bp.
- Peak: the running maximum after the start. **Recovery:** the first month in which the spread has
  retraced half the widening: spread <= peak - 0.5 x (peak - baseline). Duration: months from start to
  recovery. Episodes not recovered by the last month are right-censored (France's, if ongoing).
- Kaplan-Meier estimator with Greenwood 95% bands (log-log), implemented in `src/survival.py`.
- What preceded recoveries, over the 6 months before each recovery: (1) the ECB cut the DFR during the
  episode; (2) the average spread of the other countries fell; (3) the Eurosystem was a net buyer of the
  country's bonds (PSPP, from 2015 only). France now: the same three conditions over the latest 6 months.

### IV(c). Is French collateral priced more like Italian?

- Position of French collateral between German (0) and Italian (1): (FR - DE) / (IT - DE), MMSR spot-next
  lending rates, periods with |IT - DE| >= 1 bp only.
- Break test at **9 June 2024** (dissolution): Chow test of a constant mean in the FR-DE repo spread and in
  the FR-IT repo spread, split at the first period ending after that date.

### IV(d). Event study

- Events: only those with an official source URL (government or rating agency) that returned HTTP 200 when
  checked (`src/events.py`, `EVENTS`, with the date checked). Anything not verifiable is excluded.
- Monthly: change in the FR-DE spread from the month before the event to the event month, compared with
  every monthly change since 2010 (percentile and z-score).

## Phase 5: Japan (fixed 2026-11-04, before any result was computed)

Code: `src/japan.py`.

- Policy changes: every change in `data.boj_policy` from 16 Feb 2016 (the start of negative rates) on,
  detected from the data.
- Per change, days to close half the gap: the target after a change is TONA's mean over the 10 business
  days before the change plus the size of the change; day 0 is the effective date; the half-gap day is
  the first business day on which |TONA - target| <= half the size of the change. The same measure is
  computed for the collateralized overnight call rate (daily from 2025, so the 2025-2026 changes only).
- Error-correction model, daily, from 16 Feb 2016 to the latest day (TONA, percent):
  d TONA_t = a + g (TONA_{t-1} - policy_{t-1}) + b d policy_t + e_t, Newey-West errors (10 lags).
  Half-life of a gap in business days: ln(0.5) / ln(1 + g). b is the same-day pass-through.
- Sub-samples: negative-rate period (16 Feb 2016 to 20 Mar 2024) and after the exit (21 Mar 2024 on).

## Phase 6: the desk note's client verdict (fixed 2026-11-04, before the desk note was generated)

Code: `src/desk_note.py`. "Would I advise a client to term out their year-end funding?"

- Turn window: 14 calendar days starting 7 business days before 31 Dec 2026 (the Phase 2 term rule).
- Expected excess overnight cost per currency = mean of the frozen forecast's medians over the window's
  business days minus the latest published level of the target (both from the frozen file).
- USD: term out if the expected excess cost exceeds the latest published term premium (OFR DVP term
  minus overnight). EUR: no free term rate, so term out only if the expected excess cost is positive by
  more than 1 bp (a conservative stand-in for a term premium).
- Verdict: **Yes** if both currencies say term out, **Partly** if one does, **No** if neither.
- The recommendation box: "Term out" / "Stay overnight" per currency from the same rule.

## Upgrade U0: correctness review (fixed 2026-11-05, before the corrected numbers were computed)

### Desk note client rule: what is compared, and in which units

- Both sides are in basis points of an annual rate. The term premium is `term rate - overnight rate`
  (OFR DVP, same segment), so a **negative premium means term funding is cheaper than overnight**.
  The expected excess is the forecast change in SOFR minus IOR over the turn window relative to the
  latest level. Term out iff `expected excess > premium` (equivalently: expected overnight cost >
  term cost). This structure is kept.
- **Change: weight by nights, not business days.** Overnight funding accrues on calendar nights;
  a rate set on a business day applies until the next business day of the currency (Thursday
  24 December covers four nights, Thursday 31 December 2026 covers four nights to 4 January 2027).
  The expected excess (desk note) and the forecast spike (the Phase 2 term-vs-overnight backtest)
  become night-weighted means of the median forecast over the 14-night window. Why: the cost the
  rule compares against is a 14-night term trade; an unweighted business-day mean understates the
  turn (31 December gets 1/8 of the weight instead of 4/14).
- The wording states the premium's sign: with a negative premium the term trade is a discount, so
  "Stay overnight" means the forecast expects overnight funding to fall by more than that discount.
- The desk note shows the 31 December median separately from the window's expected excess, so the
  two are not confused.

### Term premium staleness

- The latest published OFR term rate date is recorded. **Stale if more than 20 business days (US)
  before the as-of date.** Why 20: about one month, the frequency at which OFR's bucket definitions
  have changed and beyond which the premium no longer describes the current market.
- If stale, the USD rule ignores the premium and uses the same 1 bp hurdle as the euro rule, and the
  wording says the premium is stale and gives its date.

### Reserves pressure point: identification

- The kink grid runs from the 5th to the 95th percentile of the sample's reserves (60 points). **The
  kink is "not identified" if the point estimate is within two grid steps of either end of the
  grid, or if more than 10% of the bootstrap kinks are within two grid steps of either end of their
  own grid.** Then no point estimate or band is quoted in words, only that the data cannot place it.
  Why: a least-squares kink at the edge of the grid is the search hitting its limit, not a threshold.

### Degenerate tails of the frozen forecast (diagnosis only; the frozen file is not touched)

- Recorded in `results/forecast/tail_diagnosis.json` by `src/tails.py`: the number of year-ends in
  the fit, the raw (unsorted) 31 December quantiles, whether they cross, and which year-end days the
  90% and 95% fits pass through exactly (zero residual).

### Consistency tests

- `tests/test_consistency.py` checks every generated comparison word ("above", "below", "beats",
  "wider", "Yes"/"No", "Term out"/"Stay overnight", "inside"/"outside") against the numbers, on the
  real results and on sign-flipped inputs.

## Upgrade U1: daily France (fixed 2026-11-05, after downloading the series and BEFORE any daily result was computed)

Code: `src/france_daily.py`. Data: `oat10_daily` (Banque de France Webstat TEC10,
`FM.D.FR.EUR.FR2.BB.FRMOYTEC10.HSTA`, lag 1 business day) minus `bund10_daily` (Bundesbank, lag 1).
Webstat has no daily 10-year series for Germany, Italy or Spain (monthly only), so:

- **Daily:** the OAT-Bund spread, its decomposition into OAT and Bund legs, France's episode status under
  both rules below, and the event study.
- **Monthly, unchanged:** the euro-wide vs France-specific split (needs Italian and Spanish yields) and the
  survival base rates (need the 10-country panel). They are the comparison base for the daily status.
- Both daily yields are constant-maturity 10-year yields (TEC10 is interpolated by the Banque de France;
  the Bundesbank series is read off its fitted yield curve), so the daily spread is like for like.

### Rule 1 (blowout), daily version

- Smoothed spread: the 5-business-day moving average of the daily spread. Why: a single day can move
  10 bp on noise alone; a week's average removes it and still reacts about four times faster than a
  monthly average.
- Baseline: the mean of the daily spread over the previous 250 business days (about 12 months),
  excluding the current day, the daily counterpart of the monthly rule's trailing 12-month mean.
- **Start: the first day the smoothed spread is at least 30 bp above the baseline** (the same 30 bp as
  the monthly rule, so both describe the same economic size of repricing). Peak: running maximum of
  the smoothed spread. **Recovery: the first day the smoothed spread is at or below
  peak - 0.5 x (peak - baseline).** Durations in business days, reported also in months (/21).
- Sensitivity, reported beside it: 20 bp and 50 bp (as monthly).

### Rule 2 (gradual deterioration), new; monthly panel and daily France

France widened gradually (the trailing mean rose with the spread), which Rule 1 is not designed to catch.

- **Monthly: an episode starts in the first month of a run of at least N = 6 consecutive months in which
  the spread is at least X = 15 bp above its trailing 12-month mean (previous 12 months).** Why X = 15:
  half the blowout threshold, about one standard deviation of monthly changes in core euro spreads (the
  same yardstick that set 30 bp at about two). Why N = 6: half a year of persistent excess separates a
  trend from a temporary move; shorter runs are common noise.
- Baseline: the trailing mean in the first month of the run. Peak and recovery as in Rule 1 (half
  retracement), dated from the start month. Episodes from Jan 2008, the 10 countries of IV(b); Kaplan-Meier
  with Greenwood bands for the base rates.
- **Daily France:** the same rule on the smoothed daily spread with the 250-day baseline, X = 15 bp and
  N = 126 consecutive business days (six months).
- Sensitivity: X = 10 and 20 bp; N = 3 and 9 months.

### Event study, daily

- For each event day E (or the next business day if E is not one): change in the daily FR-DE spread from
  the close of the business day before E to the close of the business day after E (a two-day window,
  because some events are announced after the close). Compared with every two-day change since 2010:
  percentile and z-score. The monthly event study is kept as a robustness check.

### Decomposition, daily

- Base: the last business day before the dissolution (7 June 2024); latest: the last day in the data.
  Change in spread = change in OAT yield (OAT leg) - change in Bund yield (Bund leg), exactly.

### Validation

- The monthly mean of the daily TEC10 against the ECB IRS French yield: PASS if the mean absolute
  difference is at most 10 bp, WARN up to 25 bp, FAIL above (the Bund check's yardstick).

## Upgrade U2: uncertainty and multiple testing (fixed 2026-11-05, before any interval or adjusted p-value was computed)

Code: `src/inference.py` (reads the results files, writes `results/inference/`), `stats_tools.holm`,
`stats_tools.block_bootstrap_ci`, `stats_tools.clopper_pearson`.

### Moving-block bootstrap (95% percentile intervals, seed 42, B = 1,000 resamples for every quantity)

| Headline number | Unit resampled | Block length | Why this block |
|---|---|---|---|
| Pinball-loss difference vs the baseline (each model, all test days and turn days) | test day | 40 business days | forecasts 40 days ahead overlap, so errors are correlated up to 39 days |
| 5-95% interval coverage on test days (each model) | test day | 40 business days | same |
| Reserves slope (bp per trillion, linear, full sample) | week | 8 weeks | as the Phase 3 kink bootstrap |
| Credit and scarcity standardised effects and their difference (IT, FR) | maintenance period | 4 periods (about 6 months) | spreads are persistent across neighbouring periods |
| France-specific vs euro-wide split since June 2024 | month of the 2010-2023 fit sample | 6 months | parameter uncertainty of the euro-wide beta; the post-2024 changes are the realised data |
| Japan half-lives (negative-rate and post-exit samples) | business day of the ECM sample | 20 business days | about a month of daily dependence |

The difference between the credit and scarcity effects is `|credit| - (|liquidity| + |German holdings|)`,
the quantity the Phase 4 decision rule compares; positive means credit dominates.

### Multiple testing (Holm, within each family, alpha 5%)

| Family | Tests | Used in wording |
|---|---|---|
| F1 Forecast vs baseline, turn days (Diebold-Mariano) | USD, EUR, JPY x calendar, state = 6 | yes (chapter V, VII) |
| F2 Forecast vs baseline, all days (Diebold-Mariano) | 6 | no (reported) |
| F3 Collateral regression, full sample (HAC t-tests) | IT, FR x credit, liquidity, German holdings = 6 | yes (the decision rule) |
| F4 Collateral regression by sub-period (before / after QT) | 2 countries x 2 periods x 3 = 12 | yes (sub-period verdicts) |
| F5 Structural breaks (Chow) | QT break IT, FR; June 2024 break FR-DE, IT-FR = 4 | yes (chapters III, IV) |
| F6 Euro-wide split betas (HAC) | IT, ES = 2 | no (reported) |
| F7 Japan error correction (HAC t-test on the gap coefficient) | full, negative-rate, exit = 3 | no (reported) |
| F8 Calibration (5-95% coverage = 90%, exact binomial) | USD, EUR, JPY winners = 3 | yes (verdicts use the CI below) |

Event-study percentiles and z-scores are descriptive (no test); the Markov comparison is a likelihood
comparison, not a test. **Every generated sentence that says "significant" uses the Holm-adjusted p-value**;
the decision rule of chapter III uses the adjusted p-values of F3 (full sample) and F4 (sub-periods).
Raw and adjusted p-values are listed in `results/inference/tests.json` and on the pages.

### Calibration (test period, each currency's models)

- Coverage per quantile (share of test days with the actual at or below the forecast) with an exact
  Clopper-Pearson 95% interval, and the 5-95% interval coverage with its interval. The binomial interval
  assumes independent days; the block-bootstrap interval above is shown beside it.
- PIT histogram at the resolution the four quantiles allow: bins below q05, q05-q50, q50-q90, q90-q95,
  above q95, against the expected 5%, 45%, 40%, 5%, 5%.
- **Verdict per currency (winning model):** "well calibrated" if the Clopper-Pearson interval of the 5-95%
  coverage contains 90%; "too narrow" if it lies entirely below 90%; "too wide" if entirely above.

### Credit vs scarcity: "too close to call"

- **If the 95% bootstrap interval of the difference between the credit and scarcity effects includes zero,
  that country's answer reads "too close to call", whatever the point-estimate decision rule says.**

## Upgrade U3: robustness (fixed 2026-11-05, before any alternative specification was computed)

Code: `src/robustness.py`, output `results/robustness/table.json` and `.csv`. Each headline finding is
re-derived under each alternative with everything else unchanged; the finding "holds" if the same
conclusion (the stated test below) is reached. Each chapter shows "Holds in k of n robustness checks",
linked to the table (Appendix page). The baseline specification is not counted among the n.

| # | Chapter | Finding (as generated) | Holds if | Alternatives |
|---|---|---|---|---|
| R1 | V | The winning regression beats the naive baseline on test-period turn days (USD and EUR) | in both currencies a regression has a lower turn-day pinball loss than the baseline | horizon 20 business days; horizon 60; train end 2021 (test 2022 on); train end 2023 (test 2024 on); test period without 2023 Q1 (bank stress, 10-31 Mar 2023 excluded) |
| R2 | V | Dollar year-ends push the spread up, euro year-ends push it down | mean USD year-end effect > 0 and mean EUR effect < 0 | lookback 5 business days; lookback 20; median instead of mean; dropping each series' first year-end |
| R3 | II | SOFR rises relative to IOR as reserves fall (negative slope, interval excludes zero) | slope < 0 and its 95% interval below zero | bootstrap block 4 weeks; block 16 weeks; train weeks only (to 2022); test weeks only (2023 on); spread two weeks ahead instead of one |
| R4 | III | Italy: too close to call; France: neither clearly credit nor scarcity | both countries' final verdicts (after Holm and the U2 rule) are the same | MMSR overnight (O/N) instead of spot-next; borrowing side instead of lending; bootstrap block 2 periods; block 8 periods; Newey-West lags 6 |
| R5 | IV | France is in a blowout now (daily Rule 1) | the main rule's status at the last day is "in an episode" | threshold 20 bp; threshold 50 bp; no smoothing (1 day); 10-day smoothing; baseline 125 business days; the monthly rule (data to the last month) |
| R6 | IV | The widening since June 2024 is mainly France-specific | France-specific part larger in size than the euro-wide part | fit window 2015-2023; fit 2010-2019; regressors IT, ES and PT; start the cumulation in July 2024 |
| R7 | VI | Gaps between TONA and the policy rate close faster after the exit than under negative rates | exit half-life < negative-rate half-life | exit sample from 1 Aug 2024; negative sample from 1 Oct 2016 (after yield-curve control began); no same-day pass-through term; bootstrap block 10 and 40 days (intervals do not overlap) |
| R8 | VII | Client verdict "No" (stay overnight in both currencies) | the same verdict | business-day weights (the pre-U0 rule); window from 5 business days before; from 10; euro hurdle 0 bp; euro hurdle 2 bp |

## Upgrade U4: the challenger forecast v2 (fixed 2026-11-05, before any v2 result was computed)

Code: `src/forecast_v2.py`; frozen file `results/forecasts/yearend_2026_v2.json` (written once by
`scripts/freeze_forecast.py --version v2`, which refuses to overwrite).

**Status of the evidence.** v2 was designed AFTER seeing v1's test-period calibration (USD and JPY ranges
too narrow, EUR too wide; the 90th and 95th year-end percentiles not separately identified). Its
test-period results are therefore NOT a clean out-of-sample claim and are labelled as such everywhere.
Its clean test is the score on 31 December 2026. **v1 stays the pre-registered headline forecast**; v2 is
the challenger shown beside it.

### (a) Conformalised quantile regression (CQR) for every day

- Base model: the v1 "calendar + state" quantile regression (same features, same 40-business-day
  horizon, same publication lags), fitted on days up to **31 December 2021**.
- Calibration set: **1 January to 31 December 2022**. For each quantile tau and each day class (turn days =
  month-, quarter- and year-ends; ordinary days), the conformity scores are s = y - q_tau(x) and the
  adjustment is their empirical quantile with the finite-sample correction of Romano, Patterson and Candès
  (2019) applied one quantile at a time: for tau >= 0.5 the ceil((n+1) tau)-th smallest score (the largest
  if that exceeds n), for tau < 0.5 the floor((n+1) tau)-th smallest (the smallest if that is 0).
  Separate classes because turn days are where v1's tails failed. Adjusted quantiles are sorted per day.
- Test: **1 January 2023 onward**, the same test days as v1: pinball loss (all days and turn days), the
  5-95% coverage with its exact binomial interval, and the calibration verdict rule of U2.
- For the 2026 forecast: the base model is fitted on all days to 31 December 2025 and calibrated on
  1 January 2026 to the as-of date (the year after the fit, as in the test design).

### (b) "History of year-ends" analogue for the turn itself

- For each past year-end D of the target: jump(D) = y(D) - level(D), where level(D) is the 5-day mean of the
  target published at D's forecast origin (40 business days before, the v1 `level` feature).
- The forecast quantiles for 31 December 2026 = the latest level + the empirical quantiles of all past
  jumps (numpy linear interpolation), USD 8 year-ends (2018-2025), EUR 7 (2019-2025).
- v2's 31 December numbers are the analogue's; every other day of the path is CQR.
- Test (labelled as above): expanding window over the 2023, 2024 and 2025 year-ends, each forecast with
  only the year-ends before it: pinball loss and whether the actual fell inside the 5-95% range. Three
  points per currency: a description, not a test.

### Scoring

- After 31 December 2026 the refresh scores BOTH frozen files: v1 in `yearend_2026_score.json`, v2 in
  `yearend_2026_v2_score.json` (actual, inside the 5-95% range, pinball loss per quantile).

## Corrections log

- **2026-11-04, Phase 2 sample filter.** Wrong: `forecast.dataset` dropped every day on which the
  baseline had no earlier comparable day, so the two regressions lost the first (2018 for USD, 2019
  for EUR, 2016 for JPY) year-end and quarter-ends, although they do not use the baseline. Found
  when the preview of the 2026 forecast showed a USD year-end median below the neighbouring days:
  with only seven year-ends, the year-end x reserves interaction took the wrong sign. Fix: drop
  those days only for the baseline's own fit; evaluate every model on the same test days (all have
  a baseline). No other choice was changed, and the result was accepted whatever it showed.
  Before -> after (test period, mean pinball loss over the four quantiles):

  | Currency | Model | All days | Turn days | 5-95 coverage | Turn-day DM p vs baseline | Winner |
  |---|---|---|---|---|---|---|
  | USD | calendar | 1.233 -> 1.217 | 2.402 -> 2.069 | 94.4% -> 94.6% | 0.373 -> 0.885 | |
  | USD | state | 0.826 -> 0.811 | 1.831 -> 1.501 | 85.4% -> 85.7% | 0.558 -> 0.043 | state -> state |
  | EUR | calendar | 0.440 -> 0.442 | 0.505 -> 0.548 | 70.8% -> 70.9% | <0.001 -> <0.001 | |
  | EUR | state | 0.103 -> 0.102 | 0.212 -> 0.180 | 98.7% -> 99.4% | 0.546 -> 0.180 | state -> state |
  | JPY | state | 1.790 -> 1.805 | 1.714 -> 1.725 | 24.7% -> 24.7% | <0.001 -> <0.001 | baseline -> baseline |

  Baselines are unchanged (same fit). Term-vs-overnight rule unchanged (9 of 42 windows locked,
  USD 14.9k saved per 100m against always-overnight). Preview of the USD 31 Dec 2026 median:
  -1.8 bp -> +6.2 bp (EUR -6.8 -> -6.7 bp). The forecast was frozen only after this fix.

- **2026-11-04, US calendar missed Good Friday (found by the independent audit, docs/AUDIT.md).** Wrong:
  the USD business-day calendar was the US federal holiday calendar, which treats Good Friday as a
  business day, but the bond market closes and SOFR is not published (no SOFR on any Good Friday
  2018-2026). So Thursday 28 March 2024, the real quarter-end turn, was not flagged as a turn day
  (Good Friday 29 March 2024 was), and publication lags spanning Good Friday were one day short. Fix:
  `data.USRepoCalendar` = federal holidays + Good Friday. Before -> after (USD test period): turn days
  45 -> 46; turn-day pinball loss baseline 2.016 -> 1.985, calendar 2.069 -> 2.071, state 1.501 -> 1.482;
  state DM p on turns 0.043 -> 0.043; winner unchanged (state); mean quarter-end effect +5.39 -> +5.29 bp;
  term rule 42 -> 43 windows, 9 locked, USD 14.9k saved vs overnight (unchanged), 36.3k -> 37.0k vs term.
  EUR and JPY unchanged. **The frozen forecast was NOT regenerated** (it must never change): it was made
  with the earlier calendar. For transparency, the corrected code would give USD 31 Dec 2026 q05/q50/q90/q95
  of -5.65 / +6.19 / +31.58 / +31.76 bp against the frozen -5.64 / +6.21 / +31.68 / +31.76 (EUR identical).

- **2026-11-05, U0 correctness review: the desk note's client rule.** Checked: units (both sides in bp of an
  annual rate), the sign convention (premium = OFR DVP term minus overnight; the latest is -2.0 bp, so term
  funding is 2.0 bp CHEAPER than overnight) and the comparison (term out iff expected excess overnight cost >
  premium, i.e. expected overnight cost > term cost) are correct. The "+6.2 bp" quoted in the desk note is
  the 31 December MEDIAN LEVEL, not the quantity the rule uses; the rule used the window's expected excess,
  -5.3 bp, and "-5.3 below -2.0" was arithmetically right. Two real faults: (1) the window mean weighted
  each business day equally although overnight cost accrues per night (24 and 31 December each carry four
  of the 14 nights); (2) the client sentence ("neither forecast spike is large enough to pay for term
  funding") is wrong when the premium is negative: there is nothing to pay for, term is a discount. Fix:
  night-weighted means (desk note and the Phase 2 backtest), premium sign stated in the wording, the
  31 December median shown next to the window's expected excess. Before -> after: USD expected excess
  -5.30 -> -4.08 bp, EUR +0.08 -> -0.04 bp; USD hurdle -2.0 bp, EUR 1 bp: **verdict No -> No (Stay
  overnight in both)**, with the corrected sentence. Backtest (43 month-end windows, 2023 on): mean spike
  -0.17 -> -0.09 bp, lock decisions changed in 0 of 43 windows, 9 locked, USD 14.9k saved vs overnight and
  37.0k vs term (unchanged).
- **2026-11-05, U0: term premium staleness.** Latest OFR term rate: 2 November 2026, 1 US business day before
  the as-of date (3 November): not stale (limit 20). Rule and wording added; no number changed.
- **2026-11-05, U0: reserves pressure point.** Before: "USD pressure starts at 1.57 trillion, 95% band
  1.52 to 2.89". Diagnosis: the kink grid runs 1.525 to 3.982; the point estimate is the second grid point
  (one step from the lower edge), and 77% of bootstrap kinks are within two steps of their grid's edges.
  The upper band end (2.89) is the 97.5% bootstrap quantile, which happens to equal the latest reserves
  (2.89), not the grid boundary. After: **USD kink not identified** (no point or band quoted). EUR: point
  3.19 trillion, 1% of bootstrap kinks at an edge: identified, unchanged (band 2.43 to 4.09). The linear
  slope (USD -6.41 bp per trillion) and the out-of-sample winner (linear, both currencies) are unchanged.
- **2026-11-05, U0: degenerate tails (diagnosis; the frozen file is unchanged).** Refitting the winning
  model on the same data: the raw 31 December quantiles CROSS (USD q90 +31.76 > q95 +31.58; EUR q90 -4.83 >
  q95 -4.85) and the per-day sort swaps them. Root cause: the year-end effect has two year-end-only
  parameters (`ye`, `ye_liq`) fitted on 8 USD / 7 EUR year-ends; a quantile above (n-1)/n (87.5% / 85.7%)
  leaves no year-end above the fit, so the 90% and 95% fits pass exactly through the SAME two year-ends
  (USD 31 Dec 2018 and 30 Dec 2021; EUR 31 Dec 2019 and 30 Dec 2022). Collinearity is not the cause (the
  two parameters are pinned by the data, not unstable). The 90th and 95th percentiles on the turn are
  therefore not separately identified; chapter VII says so. v2 (U4) addresses it.
- **2026-11-05, U0: sign-unsafe wording.** Three sentences printed a magnitude with a fixed "more"
  (collateral cost, the story answer, the repo treatment premium); they now say "more"/"less" or print
  signed values. No current number had the wrong sign, so no displayed conclusion changed.

- **2026-11-05, U1: chapter IV's headline moves to the daily rules.** Not a correction of the monthly rule
  (unchanged, kept as the robustness check) but a change of which result answers the question. Before
  (monthly, data to Sep 2026): "France is not in a blowout" (97 bp, 12-month average 69 bp + 30 bp not
  reached). After (daily, data to 3 Nov 2026): France has been in a blowout since **28 September 2026**
  (5-day average 158 bp against a trailing-year average of 81 bp; peak 164 bp on 27 October; half
  retraced at 119 bp). The gradual-deterioration rule (15 bp x 6 months) is NOT met: the excess built up
  within weeks. Base rate: of past euro blowouts that had lasted about one month, 59% retraced half the
  widening within the next 12 months. Daily decomposition since 7 June 2024: spread 49 -> 162 bp; OAT
  yields +187 bp, Bund yields +74 bp. Daily event study: both verified events moved the spread by -1 bp
  over two days (26th and 28th percentile of two-day windows).
- **2026-11-05, U2: significance now uses Holm-adjusted p-values (a change to existing choices).**
  (1) Chapter III decision rule: before, raw HAC p-values; after, Holm within F3/F4. Italy: liquidity term
  p 0.023 -> 0.113 (credit stays significant, p < 0.001), so **Italy: scarcity -> both / unclear**; France
  unchanged (both / unclear). Sub-periods unchanged (IT after QT stays scarcity: liquidity p < 0.001
  adjusted). (2) Chapter V: USD state model vs baseline on turn days, DM p 0.043 -> **0.130 (no longer
  significant)**; EUR 0.180 -> 0.360. Chapter V answer: "Partly: reliably in dollars" -> "Partly: the
  models beat a naive rule, but not significantly". Note: the block-bootstrap interval of the USD turn-day
  loss difference (-1.14 to -0.06) excludes zero; the two methods disagree and the wording reports both,
  with the pre-registered Holm-adjusted DM deciding "significant". (3) Chow tests (F5): QT break IT 0.035 ->
  0.035, FR < 0.001; June 2024 FR-DE 0.006 -> 0.011, IT-FR < 0.001: no conclusion changes.
- **2026-11-05, U2: wording correction, "too close to call".** Italy's credit-minus-scarcity difference is
  -2.2 bp with a 95% interval of -12.7 to +1.5 bp (includes zero), so Italy's answer reads **"too close to
  call"** (before: "mainly scarcity of German collateral"; after the Holm change alone it would have read
  "neither clearly credit nor scarcity"). France: -3.0 bp (-9.1 to -0.7): the interval excludes zero (the
  scarcity effects are larger in size), but no scarcity coefficient is significant after Holm, so France
  stays "neither clearly credit nor scarcity". Chapter III answer: "Scarcity for Italy; no clear driver for
  France" -> **"Too close to call"**.
- **2026-11-05, U3: one pre-registered alternative could not be computed.** R8 "window from 10 business
  days before" needs the frozen medians from 16 December 2026, but the frozen path starts on 21 December
  (Phase 2 window). It is listed in the table as "not computable" and excluded from n; no substitute
  alternative was added after seeing the results. Results: R1 3 of 5 (fails at horizon 20 for EUR, a tie
  at 0.21, and with train end 2021 for EUR); R2 4/4; R3 5/5; R4 4/5 (fails with MMSR overnight: France
  reads as scarcity); R5 5/6 (fails only under the monthly rule, whose data end in September 2026);
  R6 4/4; R7 5/5; R8 4/4.
- **2026-11-05, U4: v2 frozen.** `results/forecasts/yearend_2026_v2.json`, created 2026-11-05 19:29:42 UTC,
  code commit c9e81af, data as of 3 November 2026. 31 December 2026: USD median +8.5 bp, 5-95% +1.6 to +50.1
  (90th +34.4); EUR median -7.5 bp, 5-95% -8.5 to -5.2 (90th -5.9). Test period (NOT a clean out-of-sample
  claim): CQR turn-day pinball USD 1.93 (v1 1.48, baseline 1.98), EUR 0.34 (v1 0.18, baseline 0.23); 5-95%
  coverage USD 91.6% (well calibrated; v1 85.8%), EUR 62.5% (too narrow; v1 99.4%). The analogue range
  contained all three 2023-2025 year-ends in both currencies. v1 remains the headline.
