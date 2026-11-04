# Independent audit

`scratch/audit.py` recomputes the numbers below from the raw snapshot (`results/snapshots/series.csv`) using pandas and numpy only: it imports nothing from `src/`, rebuilds the targets, the BoJ policy rate, the turn days, the blowout episodes and the Kaplan-Meier curve with its own code, and compares them with the project's results files. Tolerance: 0.01 (rounding).

Data as of 2026-11-03.

| Quantity | Audit | Project | Result |
|---|---|---|---|
| USD: median spread to policy, last 250 days (bp) | 0.000 | 0.000 | match |
| EUR: median spread to policy, last 250 days (bp) | -6.800 | -6.800 | match |
| JPY: median spread to policy, last 250 days (bp) | -2.300 | -2.300 | match |
| USD: test turn-day pinball loss of the winner (state) | 1.482 | 1.482 | match |
| EUR: test turn-day pinball loss of the winner (state) | 0.180 | 0.180 | match |
| Kaplan-Meier S(12 months), share of blowouts not yet half-retraced | 0.389 | 0.389 | match |
| Number of blowout episodes (30 bp rule) | 36.000 | 36.000 | match |
| OAT leg of the OAT-Bund change since May 2024 (bp) | 141.000 | 141.000 | match |

8 of 8 match.

## What the audit found

The first run (4 November 2026) matched 7 of 8. The USD turn-day pinball loss differed (audit 1.512, project 1.501) because the two codes disagreed on two turn days. One was an audit bug (the unfinished current month counted as a month-end, now excluded). The other was a project bug: the project's US calendar treated Good Friday as a business day, so the real quarter-end of 28 March 2024 was not flagged. The project was corrected (docs/METHODOLOGY.md, corrections log, with before and after numbers); the frozen Year-End 2026 forecast was left unchanged, as required.
