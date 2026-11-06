"""D8: what a repo desk sees that this project cannot, and the public proxy (if any) the project uses instead.

General market knowledge only: no figures, no proprietary or non-public information. Rendered in chapter I
(after the glossary), in the research note and in the README. Kept as data so every page shows the same text.
"""

from __future__ import annotations

GAPS: list[dict[str, str]] = [
    {"item": "GC against specials, and bond-level specialness",
     "why": "A bond in demand (a new issue, a futures delivery candidate, a heavily shorted line) lends at a repo rate "
            "well below general collateral; that specialness, not the GC rate, sets the cost of a short or the "
            "pick-up from lending the bond.",
     "proxy": "MMSR secured rates by collateral country (maintenance-period averages, chapter III): a country-level "
              "average that mixes GC and specials. No bond-level data."},
    {"item": "Futures deliveries, cheapest-to-deliver switches and the basis",
     "why": "Deliverable baskets for Bund, OAT and BTP futures concentrate demand on a few bonds around delivery "
            "dates; a switch in the cheapest-to-deliver moves specialness from one bond to another, and the implied "
            "repo rate in the futures basis is a live read of term funding.",
     "proxy": "None. Futures prices, deliverable baskets and implied repo rates are not in free official data."},
    {"item": "Venue differences between cleared GC baskets (LCH RepoClear against Eurex GC Pooling)",
     "why": "Baskets differ in eligible collateral, central bank eligibility and netting, so the same nominal GC trade "
            "prices differently by venue, and the gap tends to widen at quarter-ends and year-ends.",
     "proxy": "€STR (unsecured) and MMSR secured averages across all venues; the venue split is not public."},
    {"item": "Dealer balance-sheet costs: leverage ratio, G-SIB scores, risk-weighted assets, reporting snapshots",
     "why": "Repo is balance-sheet intensive; where ratios are measured on a reporting date rather than on average, "
            "dealers shrink at quarter-ends and the year-end G-SIB snapshot makes 31 December the most expensive day.",
     "proxy": "Calendar effects estimated from rates (chapter V), Fed backstop and ON RRP usage at turns (chapter V), "
              "and the euro against dollar year-end contrast."},
    {"item": "Term repo curves",
     "why": "The price of locking funding over a turn is a term trade (one week, one month, three months), quoted "
            "continuously by desks; it shows when the market starts to pay for the turn.",
     "proxy": "OFR DVP term-rate bucket (dollars, daily) and MMSR one-week and one-month averages (euro, maintenance "
              "periods). No daily euro term repo rate is free."},
    {"item": "Haircut schedules",
     "why": "Haircuts set how much cash a bond raises; clearing houses change them by issuer and maturity, and a "
            "higher haircut on one sovereign tightens funding for everyone holding it.",
     "proxy": "Described qualitatively in chapter I. Clearing houses publish current schedules only, not their "
              "history."},
    {"item": "Equity financing and total return swaps",
     "why": "Equity repo, securities lending and total return swaps compete for the same dealer balance sheet and "
            "have their own seasonality (dividend dates, index rebalances), which can spill into fixed income repo.",
     "proxy": "None. The project covers government bond collateral only."},
]
