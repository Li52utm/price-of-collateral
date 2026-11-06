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

# --- U8: a bootstrap interval (USD reserves slope), rebuilt by the pre-registered recipe -------- #
res = s("reserves") / 1e6
pairs = []
for day, level in res.items():
    nxt = usd[(usd.index > day) & (usd.index <= day + pd.Timedelta(days=7))].dropna()
    if len(nxt) >= 3:
        pairs.append((level, nxt.mean()))
px, py = np.array([a for a, _ in pairs]), np.array([b for _, b in pairs])
rng = np.random.default_rng(42)            # METHODOLOGY U2: seed 42, 1,000 resamples, blocks of 8 weeks
n, block = len(px), 8
starts = rng.integers(0, n - block + 1, size=(1000, int(np.ceil(n / block))))
idx = np.minimum((starts[:, :, None] + np.arange(block)).reshape(1000, -1)[:, :n], n - 1)
slopes = np.array([np.polyfit(px[i], py[i], 1)[0] for i in idx])
boot = json.loads((RES / "inference" / "bootstrap.json").read_text())["reserves_slope"]["USD"]
checks.append(("USD reserves slope, bootstrap 95% lower bound (bp per trillion)", float(np.quantile(slopes, 0.025)),
               boot["lower"]))
checks.append(("USD reserves slope, bootstrap 95% upper bound (bp per trillion)", float(np.quantile(slopes, 0.975)),
               boot["upper"]))

# --- U8: Holm-adjusted Diebold-Mariano p-values on turn days (family F1, six tests) ------------- #
from scipy import stats as sps  # noqa: E402

raw_p = {}
for cur, y in (("USD", usd), ("EUR", eur), ("JPY", jpy)):
    pred = pd.read_csv(RES / "forecast" / f"test_predictions_{cur}.csv", index_col=0, parse_dates=True)
    actual = y.reindex(pred.index)              # actuals rebuilt from the raw snapshot
    turn = pred["day_type"].isin(["me", "qe", "ye"]).to_numpy()

    def loss(model, actual=actual, pred=pred):
        out = []
        for t in taus:
            d = actual - pred[f"{model}_q{int(t * 100):02d}"]
            out.append(np.where(d >= 0, t * d, (t - 1) * d))
        return np.mean(out, axis=0)

    base = loss("baseline")
    for model in ("calendar", "state"):
        d = (loss(model) - base)[turn]
        m = len(d)
        stat = d.mean() / np.sqrt(np.var(d) / m)          # horizon 1 on turn days: no autocovariance terms
        stat *= np.sqrt((m + 1 - 2) / m)                  # Harvey-Leybourne-Newbold correction with h = 1
        raw_p[f"{cur}_{model}"] = float(2 * sps.t.sf(abs(stat), df=m - 1))
order = sorted(raw_p, key=raw_p.get)
holm, running = {}, 0.0
for rank, k in enumerate(order):
    running = max(running, min(1.0, (len(order) - rank) * raw_p[k]))
    holm[k] = running
proj = {x["id"]: x for x in json.loads((RES / "inference" / "tests.json").read_text())["tests"]}
checks.append(("Diebold-Mariano p, USD state vs baseline on turn days (raw)", raw_p["USD_state"],
               proj["dm_turn_USD_state"]["p"]))
checks.append(("Holm-adjusted p of the same test (family of 6)", holm["USD_state"],
               proj["dm_turn_USD_state"]["p_holm"]))
checks.append(("Holm-adjusted p, EUR state vs baseline on turn days", holm["EUR_state"],
               proj["dm_turn_EUR_state"]["p_holm"]))

# --- U8: daily France (Webstat TEC10 minus Bundesbank Bund) ------------------------------------- #
spread = ((s("oat10_daily") - s("bund10_daily")) * 100).dropna()
smooth = spread.rolling(5).mean()
baseline = spread.rolling(250).mean().shift(1)
above = (smooth >= baseline + 30).fillna(False)
start = None
for day in above.index[::-1]:                    # walk back from the last day while the condition holds
    if above[day]:
        start = day
    elif start is not None:
        break
since = smooth.loc[start:]
peak = since.cummax()
recovered = bool((since <= peak - 0.5 * (peak - baseline.loc[start])).iloc[1:].any())
fd = json.loads((RES / "france" / "daily_summary.json").read_text())["rules"]
status = fd["blowout"]["30"]["status"]
checks.append(("Daily OAT-Bund spread on the last day (bp)", float(spread.iloc[-1]), fd["now"]["spread"]))
checks.append(("Daily blowout rule: France in an episode (1 = yes)", float(not recovered),
               float(status["in_episode"])))
checks.append(("Daily blowout start (days since 1 Jan 2024)", float((start - pd.Timestamp("2024-01-01")).days),
               float((pd.Timestamp(status["start"]) - pd.Timestamp("2024-01-01")).days)))

# --- U8: the corrected desk-note verdict, from the frozen file only ----------------------------- #
frozen = json.loads((RES / "forecasts" / "yearend_2026.json").read_text())
tvo = fc["term_vs_overnight"]["USD"]
locks, excess = {}, {}
for cur in ("USD", "EUR"):
    path = frozen["currencies"][cur]["path"]
    days = sorted(pd.Timestamp(d) for d in path)
    start_day = [d for d in days if d <= pd.Timestamp("2026-12-31")][-8]      # 7 business days before
    end_day = start_day + pd.Timedelta(days=14)
    window = [d for d in days if start_day <= d < end_day]
    nights = [(b - a).days for a, b in zip(window, window[1:] + [end_day])]
    med = [path[str(d.date())]["q50"] for d in window]
    excess[cur] = float(np.dot(med, nights) / sum(nights) - frozen["currencies"][cur]["latest_level"])
    hurdle = tvo["latest_premium_bp"] if cur == "USD" and not tvo["term_stale"] else 1.0
    locks[cur] = excess[cur] > hurdle
rule = json.loads((RES / "forecast" / "desk_note_rule.json").read_text())
checks.append(("Desk note: USD expected excess over the turn, night-weighted (bp)", excess["USD"],
               rule["rule"]["USD"]["excess_bp"]))
checks.append(("Desk note: EUR expected excess over the turn, night-weighted (bp)", excess["EUR"],
               rule["rule"]["EUR"]["excess_bp"]))
checks.append(("Desk note verdict (0 = No, 1 = Partly, 2 = Yes)", float(int(locks["USD"]) + int(locks["EUR"])),
               float({"No": 0, "Partly": 1, "Yes": 2}[rule["verdict"]])))

# --- desk upgrade (6 November 2026): runway, Treasury cash, holders, facility table --------------- #
as_of = min(s("estr").index.max(), s("sofr").index.max())
# Euro liquidity proxy rebuilt from the three weekly items (EUR bn); only weeks published by the as-of date
# (observation date + 2 weekday business days).
parts = pd.concat([s("ilm_current_accounts"), s("ilm_deposit_facility"), s("ilm_mlf")], axis=1, sort=True).dropna()
proxy = (parts.iloc[:, 0] + parts.iloc[:, 1] - parts.iloc[:, 2]) / 1e3
avail = pd.DatetimeIndex(np.busday_offset(np.asarray(proxy.index.values, dtype="datetime64[D]"), 2, roll="forward"))
proxy = proxy[avail <= as_of]
drift = (proxy.iloc[-1] - proxy.iloc[-53]) / 52
steps = len(pd.date_range(proxy.index[-1], "2027-12-31", freq="7D")) - 1
base_2027 = proxy.iloc[-1] + drift * steps
corr_sum = json.loads((RES / "corridors" / "summary.json").read_text())["reserves"]["EUR"]
lower = corr_sum["pressure_band"][0] * 1e3
above = proxy[proxy > lower]
run_start = proxy[proxy.index > above.index[-1]].index[0]
rw = json.loads((RES / "desk" / "runway.json").read_text())
checks.append(("Runway, base scenario: liquidity on 31 Dec 2027 (EUR bn)", float(base_2027),
               rw["scenarios"]["base"]["levels_bn"]["2027-12-31"]))
checks.append(("Runway, base scenario: date liquidity fell below the band's lower end (days since 1 Jan 2024)",
               float((run_start - pd.Timestamp("2024-01-01")).days),
               float((pd.Timestamp(rw["scenarios"]["base"]["crossings"]["lower"]["date"])
                      - pd.Timestamp("2024-01-01")).days)))

# Treasury cash, euro, full-sample coefficient (bp per EUR 100 bn), weekly changes, OLS by numpy.
cash = s("ea_resident_liab") / 1e5
liq = proxy_all = (parts.iloc[:, 0] + parts.iloc[:, 1] - parts.iloc[:, 2]) / 1e3 / 100
weeks = cash.index.intersection(proxy_all.index)
weeks = weeks[weeks >= eur.index[0] - pd.Timedelta(days=7)]
rows = {}
for prev, end in zip(weeks[:-1], weeks[1:]):
    days = eur[(eur.index > prev) & (eur.index <= end)]
    if len(days) >= 3:
        rows[end] = days.mean()
wk = pd.DataFrame({"spread": pd.Series(rows)})
wk["cash"], wk["liq"] = cash.reindex(wk.index), liq.reindex(wk.index)
gap = wk.index.to_series().diff().dt.days
d = wk.diff()[gap.between(5, 9)].dropna()
X = np.column_stack([np.ones(len(d)), d["cash"], d["liq"]])
beta = np.linalg.lstsq(X, d["spread"].to_numpy(), rcond=None)[0]
auto = json.loads((RES / "desk" / "autonomous.json").read_text())
checks.append(("Treasury cash, euro: full-sample coefficient (bp per EUR 100 bn)", float(beta[1]),
               auto["currencies"]["EUR"]["full"]["coef"]["cash"]))

# Holder share: non-residents' share of French government debt at the latest year-end (%).
share = (s("hold_FR_S2") / s("hold_FR_S1_S2") * 100).dropna()
holders_csv = pd.read_csv(RES / "desk" / "holders_shares.csv", parse_dates=["date"])
proj_share = holders_csv[(holders_csv["country"] == "FR") & (holders_csv["holder"] == "Non-residents")]
checks.append(("Holders: non-residents' share of French government debt, latest year-end (%)", float(share.iloc[-1]),
               float(proj_share.sort_values("date")["share_pct"].iloc[-1])))

# Facility table: backstop minus floor (bp) for each central bank, and SOFR's headroom below the SRF rate.
def last_on(name):
    x = s(name)
    return float(x[x.index <= as_of].iloc[-1])
fac = {r["bank"]: r for r in json.loads((RES / "desk" / "facilities.json").read_text())["rows"]}
mine = {"ECB": (last_on("mro") - last_on("dfr")) * 100,
        "Federal Reserve": (last_on("fed_upper") - last_on("iorb")) * 100,
        "Bank of England": 0.0,                                      # STR priced at Bank Rate + 0 bp (rule)
        "Bank of Japan": (last_on("boj_loan_rate") - (last_on("boj_loan_rate") - 0.25)) * 100}
for bank, value in mine.items():
    checks.append((f"Facility table: {bank} backstop minus floor (bp)", value, fac[bank]["backstop_minus_floor_bp"]))
checks.append(("Facility table: SOFR headroom below the SRF rate (bp)",
               (last_on("fed_upper") - last_on("sofr")) * 100, fac["Federal Reserve"]["headroom_bp"]))

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
          "numbers); the frozen Year-End 2026 forecast was left unchanged, as required.", "",
          "## Upgrade re-run (5 November 2026)", "",
          "Extended to the upgrade's headline numbers, each rebuilt with independent code from the raw "
          "snapshot or the frozen file: one bootstrap interval (the USD reserves slope, by the pre-registered "
          "recipe: seed 42, 1,000 resamples, 8-week moving blocks), the Diebold-Mariano p-values of family F1 "
          "and their Holm adjustment, the daily France blowout status and start date (Webstat TEC10 minus the "
          "Bundesbank Bund), and the corrected desk-note verdict (night-weighted expected excess against the "
          "term premium, from the frozen file only).", "",
          "## Desk upgrade re-run (6 November 2026)", "",
          "Extended to the desk upgrade, each rebuilt with independent code from the raw snapshot: the euro runway's "
          "base scenario (the liquidity proxy from its three weekly items, the trailing 52-week drift, the level on "
          "31 December 2027 and the week liquidity fell below the pressure band's lower end), the euro Treasury-cash "
          "coefficient (weekly data set and OLS rebuilt with numpy), the non-residents' share of French government "
          "debt, and every row of the facility-pricing table (the Bank of England row by its published rule, the "
          "Bank of Japan row by the BoJ's 25 bp rule)."]
(ROOT / "docs" / "AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
