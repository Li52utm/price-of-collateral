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
