# The Price of Collateral

A quantitative research dashboard on repo markets, built as a portfolio project for a sales and
trading role on a repo desk. Focus: euro repo, especially Italian BTP and French OAT collateral
against German Bunds, with the United States (SOFR) and Japan as comparisons. Results must be
honest (no look-ahead, out-of-sample tests, publication lags respected) and the code must be easy
to walk through in an interview.

## Goals

1. Explain repo to a non-specialist and show why the collateral handed over changes the price.
2. Measure how tightly the ECB, the Fed and the BoJ hold overnight rates inside their corridors.
3. Decide, from the data, whether the premium on Italian and French collateral is credit risk or
   scarcity, and whether that changed with quantitative tightening.
4. Put the French spread episode in historical context (survival analysis, decomposition, events).
5. Forecast funding spikes around calendar turns, evaluated honestly on a held-out test period.
6. Publish a frozen Year-End 2026 desk note before 31 December 2026 and score it afterwards.

## Conventions (inherited from ../ko-pep-pairs-trading and binding here)

- **No look-ahead.** A model input for day t may only use values published by day t. Every series
  is stored with its publication lag (business days) in `src/sources.py`, and `features.py` lags
  every state variable by that amount before it can be used.
- **Train/test** for anything tested. Split dates, thresholds, episode rules and event lists are
  constants fixed in code with a written rationale BEFORE test results are looked at, and logged
  in `docs/METHODOLOGY.md`.
- **Generated wording.** Every conclusion shown on a page or in the README is built by a pure
  function in `src/wording.py` from the numbers, with conditional wording. Never type a conclusion
  or a parameter value into page text. `tests/test_wording.py` flips each sign.
- **Professional tone**, no slang. Sentence case for every heading, label and chart title.
- **Data validation** (`src/validation.py`): PASS / WARN / FAIL checks; any FAIL stops a refresh.
- **Snapshot + daily pipeline.** Download functions are used ONLY by `scripts/refresh_snapshots.py`.
  Loaders read only the committed snapshots in `results/snapshots/`. The dashboard never downloads
  on page load and no button fetches data.
- **Offline tests.** `tests/conftest.py` makes every network call raise.
- **The frozen forecast** `results/forecasts/yearend_2026.json` is never overwritten by any
  script; only the separate score file is written after the turn.

## Chapter plan

| # | Chapter | Question |
|---|---|---|
| I | The Story | What is repo, and why does the bond you hand over matter? |
| II | Three Corridors | Do the ECB, Fed and BoJ keep overnight rates where they want them, and what happens as balance sheets shrink? |
| III | The Price of Collateral | Italian and French vs German repo: credit risk or scarcity? |
| IV | Italy Then, France Now | Will French OATs bounce back, and what would it take? |
| V | The Calendar | Why do euro year-ends behave differently from US year-ends, and can funding spikes be forecast? |
| VI | Japan | Does Japanese repo follow the BoJ out of negative rates? |
| VII | The Year-End 2026 Desk Note | Euro and dollar funding over 31 December 2026, published before year-end and scored afterwards, plus a France view. |

## Layout

- `src/` – library code (`sources`, `download`, `data`, `validation`, `pipeline`, `features`,
  `forecast`, `corridors`, `collateral`, `france`, `survival`, `japan`, `desk_note`, `wording`,
  `readme_block`, `ui`)
- `app.py` + `chapters/` – Streamlit dashboard (router + one file per chapter; the folder is NOT
  called `pages/`, which would switch on Streamlit's automatic page list)
- `scripts/` – `refresh_snapshots.py` (the only code that downloads), `update_readme.py`,
  `run_all.py` (recomputes every results file from the snapshots)
- `results/` – committed snapshots (`results/snapshots/`), model outputs, `results/forecasts/`
- `docs/` – `DATA_SOURCES.md`, `DATA_VALIDATION.md`, `METHODOLOGY.md`, `AUDIT.md`, `images/`
- `data/` – raw download cache (git-ignored)

## Design: "The Price of Collateral"

Light, calm, editorial (same design system as the KO/PEP project). Tokens in `ui.COLORS` (and
`.streamlit/config.toml`). New palette, Okabe-Ito based and colour-blind safe, each colour used
ONLY for its own series:

- Currencies: EUR `#0072B2`, USD `#009E73`, JPY `#D55E00`.
- Collateral countries: DE `#15213B` (ink, the reference), FR `#56B4E9`, IT `#E69F00`,
  ES `#CC79A7`; others (PT, BE, NL, AT, GR, IE, FI) muted tones in `ui.COUNTRY_COLORS`.
- Fonts: Libre Caslon Text (headings), IBM Plex Sans (body).
- Components: `chapter_heading`, `note`, `kpi_row`, `show_chart` (with source line),
  `answer_box` (the question / the answer), `verdict_box`, `footer` (data-check status and
  "Educational project. Not investment advice.").

## Plan adjustments

Every place where data or tools forced a change to the original plan, with the reason.

- **2026-11-04, lifelines.** lifelines 0.30.3 installs on Python 3.14 but its dependency chain
  (formulaic) forces pandas down to 2.3.3. To keep pandas 3.1.0 (the version the framework was
  built and tested on), Kaplan-Meier with Greenwood confidence bands is implemented in
  `src/survival.py` and tested against hand-computed examples.
- **2026-11-04, daily country yields.** No free official source without registration: the ECB
  Data Portal has only monthly country yields (IRS convergence series), DBnomics mirrors only the
  monthly Banque de France series, and Webstat's daily OAT/BTP series need a (free) API key the
  project cannot register. Substitute: ECB IRS monthly 10-year yields for 11 countries (DE, FR, IT,
  ES, PT, BE, NL, AT, GR, IE, FI) from 1999, plus the daily current 10-year Bund from the
  Bundesbank. Consequence: Chapter IV (decomposition, survival, event study) runs at MONTHLY
  frequency; the "daily France-specific stress series" becomes monthly. Upgrade path: a Webstat
  key would allow daily OAT and BTP yields.
- **2026-11-04, MMSR secured rates are maintenance-period averages**, not daily (69 periods,
  Mar 2018 to Sep 2026, dated at the period end, rounded to 1 bp, published more than six business
  days after the period ends). Chapter III uses them at that frequency. No free daily euro repo rate
  exists (RepoFunds Rate and STOXX/Eurex GC Pooling need a login or offer no download), so the
  "euro repo rate minus DFR" forecasting target is dropped; the euro target is €STR minus DFR.
- **2026-11-04, pre-€STR** is not in the ECB API. Euro history before Oct 2019 is EONIA, kept for
  context only; the euro forecasting target starts with €STR on 1 Oct 2019.
- **2026-11-04, daily excess liquidity** (`ILM.D...EXLIQ`) starts only on 27 Sep 2024. Substitute
  with full history: weekly current accounts + deposit facility - marginal lending (validated:
  it equals excess liquidity plus reserve requirements to within EUR 1 bn on 110 common weeks).
- **2026-11-04, JSDA Tokyo Repo Rate** unavailable (pages moved, HTTP 429; the BoJ's copy ended in
  2012). Substitute: the BoJ collateralized overnight call rate (daily from 2025, monthly average
  since 1960). Chapter VI's pass-through model uses TONA, the daily series with full history.
- **2026-11-04, BoJ policy rate** has no daily series. Built from the BoJ's list of decisions up to
  Jul 2024 and, from 1 Aug 2024, as the daily basic loan rate minus 0.25 (the BoJ's fixed spread),
  validated against TONA (median gap 4.8 bp since Mar 2016).
- **2026-11-04, NY Fed repo-operation search** rejects date ranges; Fed repo operations (including
  the standing repo facility) come from FRED `RPONTSYD` instead. ON RRP from FRED `RRPONTSYD`.
- **2026-11-04, OFR term repo buckets changed**: DVP "<=30 days" ends 13 Aug 2025, replaced by
  "2-7 days" and "8-30 days". The term series splices <=30 days with 8-30 days.
- **2026-11-04, AFT auction results, French CDS and historical haircut schedules**: not available
  free (AFT blocks scripts; no free CDS; clearing houses publish current PDFs only). Dropped as
  model inputs; haircuts are described qualitatively in Chapter I.
- **2026-11-04, event study list.** Only two events could be verified against an official source
  (Assemblée nationale verbatim records of 4 Dec 2024 and 8 Sep 2025, HTTP 200). The dissolution of
  9 Jun 2024 (Élysée and Légifrance unreachable or 403) and every rating action (agency releases not
  found; the AFT ratings page returns 403 to scripts) are excluded and listed in `src/events.py`.
  With monthly yields, the event study measures the event month against all months since 2010.
- **2026-11-04, France and the blowout rule.** By the rule fixed in advance (30 bp above the trailing
  12-month average) France is NOT in an episode: the spread rose steadily (51 bp in May 2024 to 97 bp
  in Sep 2026) and the trailing average rose with it. The rule was not changed. France appears as an
  ongoing, censored episode only under the pre-set 20 bp sensitivity (from Sep 2026), reported beside it.

## Data pipeline

- `scripts/refresh_snapshots.py`: download (`src/download.py`) -> pipeline checks (`src/pipeline.py`) ->
  validation (`src/validation.py`; any FAIL stops before writing) -> write `results/snapshots/` and the
  validation reports -> `scripts/run_all.py` (every results file, plus the forecast score once
  31 Dec 2026 is in the data) -> `scripts/update_readme.py` (README auto-block from `src/findings.py`).
  `--skip-download` recomputes from the committed snapshot.
- `.github/workflows/refresh-data.yml`: weekdays 14:00 UTC (after the previous day's SOFR, 08:00 ET,
  and €STR, 08:00 CET); fails if the frozen forecast changed; commits only if tests pass and files changed;
  never stages the frozen forecast. `.github/workflows/tests.yml`: every push. Actions pinned to
  `actions/checkout@v7.0.1` and `actions/setup-python@v7.1.0` (latest on 4 Nov 2026, node24), ubuntu-24.04.

## The frozen forecast

- `scripts/freeze_forecast.py` wrote `results/forecasts/yearend_2026.json` once (refuses to overwrite;
  `forecast.create_frozen_forecast` opens the file in exclusive mode). It records the model version,
  data as-of date, creation timestamp, git commit (the code commit made just before freezing) and a
  SHA-256 of `src/data.py`, `src/features.py`, `src/forecast.py`, `src/stats_tools.py`.
- `forecast.run` writes `results/forecasts/yearend_2026_score.json` only once the year-end values exist.
  `tests/test_forecast.py` checks that a run leaves the frozen file byte for byte unchanged.

## Dashboard

- `app.py` routes over `chapters/1_story.py` ... `chapters/7_desk_note.py` (`ui.CHAPTERS`). Each page:
  `ui.apply_theme()`, `ui.chapter_heading(...)`, `ui.question_box(key)` (answer from
  `src/findings.py`), charts through `ui.show_chart` (title + source line), `ui.footer()` (data-check
  status and "Educational project. Not investment advice.").
- Pages read only `results/` through `ui.results()` / `ui.csv()` (cached on file modification times);
  a missing results file shows a note, never an error. Chapter VII is built by `src/desk_note.py`
  (pure; the downloadable Markdown note comes from `desk_note.markdown`).
- `tests/test_app.py`: every chapter through the router, the missing-results case and the stale-data warning.

## Environment

- Windows, virtual environment at `.venv` (Python 3.14).
- Run scripts with `.venv\Scripts\python`, e.g. `.venv\Scripts\python scripts\refresh_snapshots.py`.
- Tests: `.venv\Scripts\python -m pytest`.

## Code style

- Clear comments explaining *why*, not just *what*. Type hints on all functions.
- Small, single-purpose functions; beginner-readable pandas.
