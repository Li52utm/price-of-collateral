"""Independent audit: recompute key numbers WITHOUT importing anything from src/.

Reads results/snapshots/series.csv (the raw published values) with pandas only and recomputes:
1. a headline spread statistic per currency (median spread to policy over the last 250 observations);
2. the test-period turn-day pinball loss of each currency's winning model (actuals rebuilt from raw data);
3. one survival-curve value (Kaplan-Meier S(12 months) for euro spread blowouts, episodes rebuilt);
4. one decomposition number (the OAT leg of the OAT-Bund widening since May 2024).
Writes docs/AUDIT.md. Run: .venv\\Scripts\\python scratch\\audit.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
raw = pd.read_csv(RES / "snapshots" / "series.csv", parse_dates=["date"])


def s(name):
    sub = raw[raw["series"] == name]
    return pd.Series(sub["value"].to_numpy(), index=pd.DatetimeIndex(sub["date"])).sort_index()


def step(policy, days):
    return policy.reindex(policy.index.union(days)).ffill().reindex(days)


# --- targets rebuilt from raw ---------------------------------------------------------------- #
sofr, estr, tona = s("sofr"), s("estr"), s("tona")
ior = pd.concat([s("ioer")[s("ioer").index < "2021-07-29"], s("iorb")])
usd = (sofr - step(ior, sofr.index)) * 100
eur = (estr - step(s("dfr"), estr.index)) * 100
loan = s("boj_loan_rate")
table = pd.Series({pd.Timestamp("2008-01-01"): 0.5, pd.Timestamp("2008-10-31"): 0.3, pd.Timestamp("2008-12-19"): 0.1,
                   pd.Timestamp("2016-02-16"): -0.1, pd.Timestamp("2024-03-21"): 0.1})
pol = step(table, tona.index)
late = tona.index >= "2024-08-01"
pol[late] = step(loan, tona.index[late]) - 0.25
jpy = (tona - pol) * 100

checks = []
corr = json.loads((RES / "corridors" / "summary.json").read_text())
for cur, y in (("USD", usd.loc["2018-04-02":]), ("EUR", eur), ("JPY", jpy.loc["2016-01-04":])):
    mine = float(y.dropna().iloc[-250:].median())
    proj = corr["stats"][cur]["recent_median_bp"]
    checks.append((f"{cur}: median spread to policy, last 250 days (bp)", mine, proj))

# --- pinball loss of the winner on test turn days -------------------------------------------- #
fc = json.loads((RES / "forecast" / "summary.json").read_text())
taus = (0.05, 0.5, 0.9, 0.95)
for cur, y in (("USD", usd), ("EUR", eur)):
    win = fc["currencies"][cur]["winner"]
    pred = pd.read_csv(RES / "forecast" / f"test_predictions_{cur}.csv", index_col=0, parse_dates=True)
    actual = y.reindex(pred.index)
    month = pred.index.to_period("M")
    # turn days rebuilt independently: last observed business day of each month in the target calendar
    all_days = y.index
    last_of_month = pd.Series(all_days, index=all_days).groupby(all_days.to_period("M")).max()
    last_of_month = last_of_month.iloc[:-1]  # the latest month is not finished: its last day is not a turn
    turn = pred.index.isin(last_of_month.values)
    losses = []
    for t in taus:
        q = pred[f"{win}_q{int(t * 100):02d}"]
        d = actual - q
        losses.append(np.where(d >= 0, t * d, (t - 1) * d))
    mean_loss = np.mean(losses, axis=0)
    proj = next(m for m in fc["currencies"][cur]["models"] if m["model"] == win)["pinball_turn"]
    checks.append((f"{cur}: test turn-day pinball loss of the winner ({win})", float(mean_loss[turn].mean()), proj))

# --- survival: rebuild blowouts and KM S(12) ------------------------------------------------- #
de = s("y10_DE")
eps = []
for c in ("IT", "ES", "PT", "FR", "BE", "GR", "IE", "AT", "NL", "FI"):
    sp = ((s(f"y10_{c}") - de) * 100).dropna()
    base = sp.rolling(12).mean().shift(1)
    i, idx = 0, sp.index
    while i < len(sp):
        if idx[i] < pd.Timestamp("2008-01-01") or np.isnan(base.iloc[i]) or sp.iloc[i] < base.iloc[i] + 30:
            i += 1
            continue
        b, peak, j, rec = base.iloc[i], sp.iloc[i], i + 1, None
        while j < len(sp):
            peak = max(peak, sp.iloc[j])
            if sp.iloc[j] <= peak - 0.5 * (peak - b):
                rec = idx[j]
                break
            j += 1
        end = rec if rec is not None else idx[-1]
        eps.append(((end.year - idx[i].year) * 12 + end.month - idx[i].month, rec is not None))
        i = j + 1 if rec is not None else len(sp)
dur = np.array([e[0] for e in eps], float)
obs = np.array([e[1] for e in eps])
surv = 1.0
for t in np.unique(dur):
    if t > 12:
        break
    n, d = (dur >= t).sum(), ((dur == t) & obs).sum()
    surv *= 1 - d / n
fr = json.loads((RES / "france" / "summary.json").read_text())
checks.append(("Kaplan-Meier S(12 months), share of blowouts not yet half-retraced", surv,
               fr["survival"]["at"]["12"]["survival"]))
checks.append(("Number of blowout episodes (30 bp rule)", float(len(eps)), float(fr["survival"]["n_episodes"])))

# --- decomposition: OAT leg -------------------------------------------------------------------- #
frs = s("y10_FR")
oat = float((frs.iloc[-1] - frs.loc["2024-05-01"]) * 100)
checks.append(("OAT leg of the OAT-Bund change since May 2024 (bp)", oat, fr["decomposition"]["oat_leg"]))

# --- report -------------------------------------------------------------------------------------- #
lines = ["# Independent audit", "",
         "`scratch/audit.py` recomputes the numbers below from the raw snapshot (`results/snapshots/series.csv`) "
         "using pandas and numpy only: it imports nothing from `src/`, rebuilds the targets, the BoJ policy rate, "
         "the turn days, the blowout episodes and the Kaplan-Meier curve with its own code, and compares them with "
         "the project's results files. Tolerance: 0.01 (rounding).", "",
         f"Data as of {json.loads((RES / 'snapshots' / 'manifest.json').read_text())['as_of']}.", "",
         "| Quantity | Audit | Project | Result |", "|---|---|---|---|"]
n_match = 0
for name, mine, proj in checks:
    ok = abs(mine - proj) <= 0.01
    n_match += ok
    lines.append(f"| {name} | {mine:.3f} | {proj:.3f} | {'match' if ok else 'MISMATCH'} |")
lines += ["", f"{n_match} of {len(checks)} match.", "",
          "## What the audit found", "",
          "The first run (4 November 2026) matched 7 of 8. The USD turn-day pinball loss differed (audit 1.512, "
          "project 1.501) because the two codes disagreed on two turn days. One was an audit bug (the unfinished "
          "current month counted as a month-end, now excluded). The other was a project bug: the project's US "
          "calendar treated Good Friday as a business day, so the real quarter-end of 28 March 2024 was not "
          "flagged. The project was corrected (docs/METHODOLOGY.md, corrections log, with before and after "
          "numbers); the frozen Year-End 2026 forecast was left unchanged, as required."]
(ROOT / "docs" / "AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
