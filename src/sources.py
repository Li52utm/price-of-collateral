"""Registry of every data series: where it comes from, its frequency and its publication lag.

Measured on 2026-11-04 by downloading each series (see docs/DATA_SOURCES.md). The publication
lag is in BUSINESS DAYS after the observation date: a value dated d may be used by a model on day
t only if d + lag business days <= t (data.point_in_time enforces this). Lags are conservative:
where a series is published late on day d+1 (e.g. the Daily Treasury Statement at 16:00 ET), the
lag is set so that the value is usable from the morning after publication.

Rates are in percent per annum; amounts in the units stated.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Series:
    name: str          # column name used throughout the project
    source: str        # ecb, fred, nyfed, ofr, boj, bbk
    key: str           # series key / mnemonic / endpoint id at the source
    freq: str          # daily, weekly, monthly, maintenance_period
    lag_bd: int        # publication lag in business days after the observation date
    unit: str
    description: str


# --------------------------------------------------------------------------- #
# Euro area
# --------------------------------------------------------------------------- #
EUR = [
    Series("estr", "ecb", "EST/B.EU000A2X2A25.WT", "daily", 1, "%", "Euro short-term rate (published 08:00 CET on T+1)"),
    Series("estr_p25", "ecb", "EST/B.EU000A2X2A25.R25", "daily", 1, "%", "€STR 25th volume percentile"),
    Series("estr_p75", "ecb", "EST/B.EU000A2X2A25.R75", "daily", 1, "%", "€STR 75th volume percentile"),
    Series("estr_volume", "ecb", "EST/B.EU000A2X2A25.TT", "daily", 1, "EUR mn", "€STR total volume"),
    Series("eonia", "ecb", "EON/D.EONIA_TO.RATE", "daily", 1, "%", "EONIA (discontinued 3 Jan 2022; €STR + 8.5 bp from Oct 2019)"),
    Series("dfr", "ecb", "FM/D.U2.EUR.4F.KR.DFR.LEV", "daily", 0, "%", "Deposit facility rate (announced in advance)"),
    Series("mro", "ecb", "FM/D.U2.EUR.4F.KR.MRR_FR.LEV", "daily", 0, "%", "Main refinancing operations fixed rate (announced in advance)"),
    Series("mlf", "ecb", "FM/D.U2.EUR.4F.KR.MLFR.LEV", "daily", 0, "%", "Marginal lending facility rate"),
    Series("excess_liquidity", "ecb", "ILM/D.U2.C.EXLIQ.U2.EUR", "daily", 1, "EUR mn", "Eurosystem excess liquidity"),
    Series("min_reserves", "ecb", "ILM/D.U2.C.MRR.U2.EUR", "daily", 1, "EUR mn",
           "Minimum reserve requirements (constant within a maintenance period; changes mark period starts)"),
    Series("ilm_current_accounts", "ecb", "ILM/W.U2.C.L020100.U2.EUR", "weekly", 2, "EUR mn",
           "Credit institutions' current accounts with the Eurosystem (weekly financial statement)"),
    Series("ilm_deposit_facility", "ecb", "ILM/W.U2.C.L020200.U2.EUR", "weekly", 2, "EUR mn",
           "Deposit facility (weekly financial statement)"),
    Series("ilm_mlf", "ecb", "ILM/W.U2.C.A050500.U2.EUR", "weekly", 2, "EUR mn", "Marginal lending facility (weekly)"),
    Series("mp_securities", "ecb", "ILM/W.U2.C.A070100.U2.EUR", "weekly", 2, "EUR mn",
           "Securities held for monetary policy purposes (APP + PEPP), weekly financial statement"),
    Series("bund10_daily", "bbk", "BBSSY/D.REN.EUR.A630.000000WT1010.A", "daily", 1, "%",
           "Daily yield of the current 10-year Bund (Bundesbank)"),
]

# Monthly 10-year yields for convergence purposes (ECB IRS): the only free official source with
# every euro country on one basis. Published about four to five weeks after the month.
YIELD_COUNTRIES = ("DE", "FR", "IT", "ES", "PT", "BE", "NL", "AT", "GR", "IE", "FI")
YIELDS = [Series(f"y10_{c}", "ecb", f"IRS/M.{c}.L.L40.CI.0000.EUR.N.Z", "monthly", 25, "%",
                 f"Long-term interest rate for convergence purposes, {c} (monthly average)")
          for c in YIELD_COUNTRIES]

# MMSR secured segment: maintenance-period averages, by collateral issuer country.
MMSR_COUNTRIES = ("DE", "FR", "IT", "ES", "BE", "NL", "_Z")  # _Z = all collateral
MMSR_TENORS = {"KS": "S/N", "KT": "T/N", "MA": "O/N", "TA": "1W", "TC": "1M"}
MMSR_SIDES = {"LE": "lending", "BO": "borrowing"}
MMSR_MEASURES = {"WR": "rate", "TT": "volume"}

# --------------------------------------------------------------------------- #
# United States
# --------------------------------------------------------------------------- #
USD = [
    Series("sofr", "nyfed", "SOFR", "daily", 1, "%", "Secured overnight financing rate (08:00 ET on T+1)"),
    Series("sofr_p99", "nyfed", "SOFR:p99", "daily", 1, "%", "SOFR 99th volume percentile"),
    Series("sofr_volume", "nyfed", "SOFR:volume", "daily", 1, "USD bn", "SOFR volume"),
    Series("tgcr", "nyfed", "TGCR", "daily", 1, "%", "Tri-party general collateral rate"),
    Series("bgcr", "nyfed", "BGCR", "daily", 1, "%", "Broad general collateral rate"),
    Series("effr", "nyfed", "EFFR", "daily", 1, "%", "Effective federal funds rate"),
    Series("iorb", "fred", "IORB", "daily", 0, "%", "Interest on reserve balances (from 29 Jul 2021)"),
    Series("ioer", "fred", "IOER", "daily", 0, "%", "Interest on excess reserves (to 28 Jul 2021)"),
    Series("fed_upper", "fred", "DFEDTARU", "daily", 0, "%", "Fed funds target range, upper"),
    Series("fed_lower", "fred", "DFEDTARL", "daily", 0, "%", "Fed funds target range, lower"),
    Series("onrrp", "fred", "RRPONTSYD", "daily", 1, "USD bn", "Overnight reverse repo, Treasury collateral, accepted"),
    Series("reserves", "fred", "WRESBAL", "weekly", 1, "USD mn", "Reserve balances with Federal Reserve Banks (Wednesday level, H.4.1 Thursday)"),
    Series("tga_weekly", "fred", "WTREGEN", "weekly", 1, "USD mn", "Treasury General Account (Wednesday level)"),
    Series("fed_securities", "fred", "WSHOSHO", "weekly", 1, "USD mn", "Fed securities held outright"),
    Series("fed_repo_ops", "fred", "RPONTSYD", "daily", 1, "USD bn",
           "Fed overnight repo operations accepted, Treasury collateral (standing repo facility from Jul 2021)"),
    Series("repo_dvp_on", "ofr", "REPO-DVP_AR_OO", "daily", 1, "%", "DVP overnight/open average rate (preliminary where final is missing)"),
    Series("repo_dvp_term", "ofr", "REPO-DVP_AR_LE30|REPO-DVP_AR_B830", "daily", 1, "%",
           "DVP term average rate: <=30 days to 13 Aug 2025, 8-30 days afterwards (OFR changed the buckets)"),
    Series("tga_daily", "fiscal", "dts/operating_cash_balance", "daily", 2, "USD mn",
           "Treasury General Account closing balance, Daily Treasury Statement (16:00 ET on T+1)"),
]

# --------------------------------------------------------------------------- #
# Japan
# --------------------------------------------------------------------------- #
JPY = [
    Series("tona", "boj", "FM01/STRDCLUCON", "daily", 2, "%", "Uncollateralized overnight call rate (TONA), average"),
    Series("call_collat_on", "boj", "FM02/STRDCLCOON", "daily", 2, "%", "Collateralized overnight call rate (daily from 2025)"),
    Series("call_collat_on_m", "boj", "FM02/STRACLCOON", "monthly", 3, "%", "Collateralized overnight call rate, monthly average"),
    Series("boj_loan_rate", "boj", "IR01/MADR1Z@D", "daily", 0, "%", "Basic discount rate and basic loan rate"),
    Series("boj_current_accounts", "boj", "MD01/MABS1AN113", "monthly", 3, "JPY 100 mn", "Current account balances, monthly average"),
]

# Daily 10-year yields from Banque de France Webstat (U1, discovered 2026-11-05 in the `series` catalogue).
# Webstat publishes updates at 09:00, 13:00 and 21:00 Paris time; the TEC10 of day d appears in the 21:00
# update of day d at the earliest, so it is usable from the next business day (lag 1).
WEBSTAT_UPDATE_TIMES_PARIS = ("09:00", "13:00", "21:00")
WEBSTAT_YIELDS: list[Series] = [
    Series("oat10_daily", "webstat", "FM.D.FR.EUR.FR2.BB.FRMOYTEC10.HSTA", "daily", 1, "%",
           "French 10-year constant-maturity government yield (TEC10), Banque de France; "
           "updates 09:00, 13:00 and 21:00 Paris time"),
]
# No daily 10-year benchmark on Webstat for these countries (FM has monthly series only, e.g.
# FM.M.IT.EUR.FR2.BB.IT10YT_RR.YLD); the project keeps the ECB IRS monthly series for them.
# Germany has a daily series from the Bundesbank (bund10_daily).
WEBSTAT_NO_DAILY = {"DE": "monthly only on Webstat (FM.M.DE.EUR.FR2.BB.DE10YT_RR.YLD); daily from the Bundesbank",
                    "IT": "monthly only on Webstat (FM.M.IT.EUR.FR2.BB.IT10YT_RR.YLD); ECB IRS monthly kept",
                    "ES": "monthly only on Webstat (FM.M.ES.EUR.FR2.BB.ES10YT_RR.YLD); ECB IRS monthly kept"}

ALL_SERIES: list[Series] = [*EUR, *YIELDS, *USD, *JPY, *WEBSTAT_YIELDS]
BY_NAME: dict[str, Series] = {s.name: s for s in ALL_SERIES}


def lag(name: str) -> int:
    """Publication lag in business days for a registered series (MMSR series: see MMSR_LAG_BD)."""
    if name.startswith("mmsr_"):
        return MMSR_LAG_BD
    if name == "boj_policy":
        return 0
    if name.startswith("pspp_"):
        return PSPP_LAG_BD
    return BY_NAME[name].lag_bd


# MMSR maintenance-period averages are dated at the period END (the day before the next period
# starts: each MMSR date is one day before a change in minimum reserve requirements, and the rates
# match the DFR in force during the period that ends on that date). The period ending 27 Oct 2026
# was not yet published on 4 Nov 2026, so the lag is more than six business days; 10 is used.
MMSR_LAG_BD = 10
# ECB PSPP country breakdown: monthly, published in the following month's update.
PSPP_LAG_BD = 25
PSPP_COUNTRIES = {"Germany": "DE", "France": "FR", "Italy": "IT", "Spain": "ES", "Portugal": "PT",
                  "Belgium": "BE", "Netherlands": "NL", "Austria": "AT", "Ireland": "IE", "Finland": "FI",
                  "Greece": "GR"}
