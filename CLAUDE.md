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

## Environment

- Windows, virtual environment at `.venv` (Python 3.14).
- Run scripts with `.venv\Scripts\python`, e.g. `.venv\Scripts\python scripts\refresh_snapshots.py`.
- Tests: `.venv\Scripts\python -m pytest`.

## Code style

- Clear comments explaining *why*, not just *what*. Type hints on all functions.
- Small, single-purpose functions; beginner-readable pandas.
