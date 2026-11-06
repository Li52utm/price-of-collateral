"""Download functions. Used ONLY by scripts/refresh_snapshots.py; the dashboard and tests never call them.

Every function returns a pandas Series (or a long DataFrame for MMSR) indexed by observation date.
Each source's quirks, as measured on 2026-11-04:
- ECB Data Portal: no key; occasional 502/504 under load, so requests are retried.
- FRED fredgraph.csv: no key, but browser-like User-Agent headers time out; plain requests work.
- New York Fed Markets API, OFR Short-term Funding Monitor, Treasury Fiscal Data: no key.
- Bank of Japan Time-Series Data Search API (launched February 2026): no key.
- Bundesbank SDMX web service: no key; CSV with a byte-order mark and metadata rows.
"""

from __future__ import annotations

import io
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import requests

import sources

TIMEOUT = 180
RETRIES = 4
START = "2008-01-01"


class DownloadError(RuntimeError):
    """A source could not be downloaded after the retries."""


def _get(url: str, params: dict | None = None, headers: dict | None = None) -> requests.Response:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code in (429, 500, 502, 503, 504):
                raise DownloadError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r
        except Exception as error:  # network errors and retryable statuses
            last = error
            time.sleep(5 * (attempt + 1))
    raise DownloadError(f"{url}: {last}")


# --------------------------------------------------------------------------- #
# ECB
# --------------------------------------------------------------------------- #
ECB = "https://data-api.ecb.europa.eu/service/data/"


def ecb_frame(key: str, start: str = START) -> pd.DataFrame:
    """Raw ECB csvdata for a (possibly wildcarded) key: one row per series and period."""
    r = _get(ECB + key, params={"format": "csvdata", "startPeriod": start[:7] if "/M." in key else start})
    if not r.text.strip():
        raise DownloadError(f"ECB {key}: empty response")
    return pd.read_csv(io.StringIO(r.text))


def ecb_series(key: str, start: str = START) -> pd.Series:
    """One ECB Data Portal series indexed by date (daily, weekly on Fridays, or monthly)."""
    df = ecb_frame(key, start)
    periods = df["TIME_PERIOD"].astype(str)
    if periods.str.contains("-W").any():
        # ISO week "2026-W44": the weekly financial statement refers to the Friday of that week.
        index = pd.to_datetime(periods + "-5", format="%G-W%V-%u")
    elif periods.str.len().max() == 7:
        index = pd.to_datetime(periods, format="%Y-%m")
    else:
        index = pd.to_datetime(periods, format="%Y-%m-%d")
    return pd.Series(df["OBS_VALUE"].to_numpy(dtype=float), index=index).sort_index().dropna()


def ecb_mmsr(start: str = "2018-01-01") -> pd.DataFrame:
    """MMSR secured segment by collateral country, tenor, side and measure (maintenance-period averages).

    Returns a long frame: date (period start), series name 'mmsr_<measure>_<side>_<tenor>_<country>', value.
    """
    countries = "+".join(sources.MMSR_COUNTRIES)
    tenors = "+".join(sources.MMSR_TENORS)
    sides = "+".join(sources.MMSR_SIDES)
    measures = "+".join(sources.MMSR_MEASURES)
    key = f"MMSR/B.U2._X.{countries}.S1ZV._Z.T.{sides}.{measures}._X.{tenors}._Z._Z.EUR._Z"
    df = ecb_frame(key, start)
    parts = df["KEY"].str.split(".")
    names = ("mmsr_" + parts.str[9].map(sources.MMSR_MEASURES) + "_" + parts.str[8].str.lower() + "_"
             + parts.str[11] + "_" + parts.str[4].str.replace("_Z", "ALL"))
    return pd.DataFrame({"date": pd.to_datetime(df["TIME_PERIOD"]), "series": names,
                         "value": df["OBS_VALUE"].astype(float)}).dropna()


def ecb_pspp() -> pd.DataFrame:
    """ECB PSPP monthly net purchases by country (EUR mn) -> long frame of cumulative net purchases."""
    text = _get("https://www.ecb.europa.eu/mopo/pdf/PSPP_breakdown_history.csv").text
    lines = text.splitlines()
    header = lines[2].split(",")
    dates = pd.to_datetime([d for d in header[1:] if "/" in d], format="%d/%m/%Y")
    rows = []
    for line in lines[3:]:
        if line.startswith("Total") or line.startswith("In EUR"):
            break
        cells = next(iter(pd.read_csv(io.StringIO(line), header=None).itertuples(index=False)))
        country = sources.PSPP_COUNTRIES.get(str(cells[0]).strip())
        if country is None:
            continue
        values = pd.to_numeric(pd.Series(list(cells[1:1 + len(dates)])).astype(str).str.replace(",", ""),
                               errors="coerce").to_numpy()
        cumulative = pd.Series(values, index=dates).fillna(0).cumsum()
        rows.append(pd.DataFrame({"date": dates, "series": f"pspp_{country}", "value": cumulative.to_numpy()}))
    if not rows:
        raise DownloadError("PSPP breakdown: no country rows parsed")
    return pd.concat(rows, ignore_index=True)


# --------------------------------------------------------------------------- #
# FRED, New York Fed, OFR, Treasury
# --------------------------------------------------------------------------- #
def fred_series(series_id: str) -> pd.Series:
    """One FRED series from fredgraph.csv, from START."""
    r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id})
    df = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True, na_values=".")
    return df.iloc[:, 0].astype(float).dropna().loc[START:]


def nyfed_rates(start: str = "2018-04-02") -> pd.DataFrame:
    """All NY Fed reference rates (SOFR, TGCR, BGCR, EFFR, OBFR) with percentiles and volumes, long format."""
    end = pd.Timestamp.now().strftime("%Y-%m-%d")
    r = _get("https://markets.newyorkfed.org/api/rates/all/search.csv", params={"startDate": start, "endDate": end})
    df = pd.read_csv(io.StringIO(r.text))
    df["date"] = pd.to_datetime(df["Effective Date"], format="%m/%d/%Y")
    out = []
    for rate in ("SOFR", "TGCR", "BGCR", "EFFR"):
        sub = df[df["Rate Type"] == rate].set_index("date").sort_index()
        name = rate.lower()
        out.append(pd.DataFrame({"date": sub.index, "series": name, "value": sub["Rate (%)"].astype(float)}))
        if rate == "SOFR":
            out.append(pd.DataFrame({"date": sub.index, "series": "sofr_p99",
                                     "value": pd.to_numeric(sub["99th Percentile (%)"], errors="coerce")}))
            out.append(pd.DataFrame({"date": sub.index, "series": "sofr_volume",
                                     "value": pd.to_numeric(sub["Volume ($Billions)"], errors="coerce")}))
    return pd.concat(out, ignore_index=True).dropna()


def nyfed_repo_operations(start: str = "2019-09-17") -> pd.Series:
    """Accepted amounts (USD bn) in Fed repo operations per operation date (standing repo facility from Jul 2021)."""
    end = pd.Timestamp.now().strftime("%Y-%m-%d")
    r = _get("https://markets.newyorkfed.org/api/rp/repo/all/results/search.json",
             params={"startDate": start, "endDate": end})
    ops = r.json().get("repo", {}).get("operations", [])
    if not ops:
        return pd.Series(dtype=float)
    # Several operations can share a date (morning and afternoon standing repo operations): sum them.
    # (Corrected 2026-11-05: a dict keyed by date kept only the last operation of each day.)
    s = pd.Series([float(op.get("totalAmtAccepted", 0) or 0) / 1e9 for op in ops],
                  index=pd.DatetimeIndex([pd.Timestamp(op["operationDate"]) for op in ops]))
    return s.groupby(level=0).sum().sort_index()


def ofr_series(mnemonic: str) -> pd.Series:
    """OFR short-term funding monitor: final values, completed by preliminary values where final is missing."""
    parts = {}
    for suffix in ("-P", "-F"):
        try:
            j = _get("https://data.financialresearch.gov/v1/series/timeseries",
                     params={"mnemonic": mnemonic + suffix}).json()
        except DownloadError:
            j = []
        parts[suffix] = pd.Series({pd.Timestamp(d): v for d, v in j}, dtype=float).dropna()
    # Final values take priority; preliminary values fill the recent months not yet finalised.
    return parts["-F"].combine_first(parts["-P"]).sort_index()


def ofr_term_repo() -> pd.Series:
    """DVP term rate: the <=30-day bucket to 13 Aug 2025, then the 8-30-day bucket (OFR split the bucket)."""
    old = ofr_series("REPO-DVP_AR_LE30")
    new = ofr_series("REPO-DVP_AR_B830")
    return pd.concat([old[old.index < new.index.min()], new]).sort_index()


def treasury_settlements(start: str = "2018-01-01") -> pd.DataFrame:
    """Treasury auction issue (settlement) dates with offering amounts, from Fiscal Data."""
    rows, page = [], 1
    while True:
        j = _get("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
                 params={"fields": "security_type,security_term,issue_date,offering_amt",
                         "filter": f"issue_date:gte:{start}", "page[size]": 10000, "page[number]": page}).json()
        rows += j["data"]
        if page >= j["meta"]["total-pages"]:
            break
        page += 1
    df = pd.DataFrame(rows)
    df["issue_date"] = pd.to_datetime(df["issue_date"])
    df["offering_amt"] = pd.to_numeric(df["offering_amt"], errors="coerce") / 1e9
    return df.rename(columns={"issue_date": "date", "offering_amt": "amount_bn"})


def treasury_tga_daily(start: str = "2018-01-01") -> pd.Series:
    """TGA closing balance (USD mn) from the Daily Treasury Statement."""
    rows, page = [], 1
    while True:
        j = _get("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance",
                 params={"filter": f"record_date:gte:{start}", "page[size]": 10000, "page[number]": page,
                         "fields": "record_date,account_type,close_today_bal,open_today_bal"}).json()
        rows += j["data"]
        if page >= j["meta"]["total-pages"]:
            break
        page += 1
    df = pd.DataFrame(rows)
    df["record_date"] = pd.to_datetime(df["record_date"])
    # The account label changed over time: "Federal Reserve Account" (to Sep 2021), then
    # "Treasury General Account (TGA) Closing Balance" and an "Opening Balance" row whose
    # open_today_bal equals the previous closing balance.
    closing = df[df["account_type"].str.contains("Closing Balance|Federal Reserve Account", regex=True)].copy()
    value = pd.to_numeric(closing["close_today_bal"], errors="coerce")
    fallback = pd.to_numeric(closing["open_today_bal"], errors="coerce")
    closing["v"] = value.fillna(fallback)
    return closing.groupby("record_date")["v"].first().dropna().sort_index()


# --------------------------------------------------------------------------- #
# Bank of Japan, Bundesbank
# --------------------------------------------------------------------------- #
def boj_series(db_code: str, start: str = "200801") -> pd.Series:
    """One Bank of Japan series ('DB/CODE') from the BoJ statistics API."""
    db, code = db_code.split("/")
    j = _get("https://www.stat-search.boj.or.jp/api/v1/getDataCode",
             params={"format": "json", "lang": "en", "db": db, "code": code, "startDate": start}).json()
    if "RESULTSET" not in j:
        raise DownloadError(f"BoJ {db_code}: {j.get('MESSAGE')}")
    values = j["RESULTSET"][0]["VALUES"]
    dates = [str(d) for d in values["SURVEY_DATES"]]
    fmt = "%Y%m%d" if len(dates[0]) == 8 else "%Y%m"
    s = pd.Series(values["VALUES"], index=pd.to_datetime(dates, format=fmt), dtype=float)
    return s.dropna().sort_index()


def bbk_series(key: str) -> pd.Series:
    """One Bundesbank series from its SDMX CSV, from START."""
    flow, rest = key.split("/", 1)
    r = _get(f"https://api.statistiken.bundesbank.de/rest/data/{flow}/{rest}", params={"format": "csv", "lang": "en"})
    text = r.content.decode("utf-8-sig")
    rows = [line.split(",") for line in text.splitlines() if line[:4].isdigit() and line[4] == "-"]
    s = pd.Series({pd.Timestamp(r[0]): r[1] for r in rows})
    return pd.to_numeric(s, errors="coerce").dropna().sort_index().loc[START:]


# --------------------------------------------------------------------------- #
# Bank of England, Eurostat
# --------------------------------------------------------------------------- #
BOE_IADB = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"


def boe_series(code: str, start: str = "01/Jan/2008") -> pd.Series:
    """One Bank of England database (IADB) series by its code. The site refuses requests without a
    browser-like User-Agent, so one is sent (no key, no login)."""
    params = {"csv.x": "yes", "Datefrom": start, "Dateto": "now", "SeriesCodes": code, "CSVF": "TN",
              "UsingCodes": "Y", "VPD": "Y", "VFD": "N"}
    r = _get(BOE_IADB, params=params, headers={"User-Agent": "Mozilla/5.0"})
    df = pd.read_csv(io.StringIO(r.text))
    if df.shape[1] < 2:
        raise DownloadError(f"BoE {code}: unexpected response")
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df.iloc[:, 0], format="%d %b %Y"))
    return s.dropna().sort_index()


EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"


def eurostat_series(key: str) -> pd.Series:
    """One Eurostat series written as 'dataset?dim=value&dim=value' (JSON-stat API, no key).

    Annual periods are dated 31 December, quarterly periods the last day of the quarter.
    """
    dataset, query = key.split("?", 1)
    params = dict(part.split("=", 1) for part in query.split("&"))
    j = _get(EUROSTAT + dataset, params={**params, "lang": "en"}).json()
    times = j["dimension"]["time"]["category"]["index"]          # {period: position}
    if any(n != 1 for d, n in zip(j["id"], j["size"], strict=True) if d != "time"):
        raise DownloadError(f"Eurostat {key}: the query does not select a single series")
    by_pos = {pos: period for period, pos in times.items()}
    values = {by_pos[int(i)]: v for i, v in j["value"].items()}
    index = [pd.Period(p.replace("-Q", "Q"), freq="Q" if "Q" in p else "Y").end_time.normalize() for p in values]
    return pd.Series(list(values.values()), index=pd.DatetimeIndex(index), dtype=float).sort_index()


# --------------------------------------------------------------------------- #
# Banque de France Webstat (needs a free API key; docs/DATA_SOURCES.md)
# --------------------------------------------------------------------------- #
WEBSTAT = "https://webstat.banque-france.fr/api/explore/v2.1/catalog/datasets/"
WEBSTAT_DAILY_QUOTA = 10_000          # requests per day; exceeding it can get the account banned
WEBSTAT_BUDGET = 200                  # this project's own cap per process (far below the quota)
WEBSTAT_CACHE = Path(__file__).resolve().parent.parent / "data" / "webstat"


class WebstatError(DownloadError):
    """Webstat refused the request (bad key, quota, HTTP 429): the refresh stops, nothing is retried."""


def webstat_key() -> str | None:
    """WEBSTAT_API_KEY from the environment, else from the project's .env. Never printed or logged."""
    key = os.environ.get("WEBSTAT_API_KEY")
    if key:
        return key.strip()
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("WEBSTAT_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


class Webstat:
    """Minimal Webstat client: header authentication only, a request counter, no retries on refusal."""

    def __init__(self, key: str | None = None, budget: int = WEBSTAT_BUDGET) -> None:
        self._key = key or webstat_key()
        if not self._key:
            raise WebstatError("WEBSTAT_API_KEY is not set (environment or .env)")
        self.budget = budget
        self.requests = 0

    def get(self, path: str, params: dict) -> requests.Response:
        """One request; HTTP 429 or any refusal stops cleanly with a clear error (no retry)."""
        if self.requests >= self.budget:
            raise WebstatError(f"Webstat request budget of {self.budget} reached; stopping")
        self.requests += 1
        # The key travels ONLY in the Authorization header (never in the URL, never logged).
        r = requests.get(WEBSTAT + path, params=params, timeout=TIMEOUT,
                         headers={"Authorization": f"Apikey {self._key}"})
        if r.status_code == 429:
            raise WebstatError("Webstat HTTP 429 (rate limit or daily quota): stopped without retrying")
        if r.status_code in (401, 403):
            raise WebstatError(f"Webstat HTTP {r.status_code}: the API key was refused")
        if r.status_code == 404 and "NotFoundResource" in r.text:
            raise WebstatError("Webstat NotFoundResource: often a missing or badly formatted key, else a wrong path")
        if r.status_code != 200:
            raise WebstatError(f"Webstat HTTP {r.status_code} on {path}")
        return r

    def series_catalog(self, where: str | None = None, refine: str | None = None) -> pd.DataFrame:
        """Series metadata (key, titles, first and last period) from the `series` dataset."""
        params = {"select": "series_key,dataset_id,title_en,title_long_en,title_fr,title_long_fr,"
                            "first_time_period_date,last_time_period_date"}
        if refine:
            params["refine"] = refine
        if where:
            params["where"] = where
        r = self.get("series/exports/json", params)
        return pd.DataFrame(r.json())

    def observations(self, series_key: str, use_cache: bool = False) -> pd.DataFrame:
        """Full history of one series in one request; raw JSON cached in data/webstat/."""
        cache = WEBSTAT_CACHE / f"{series_key}.json"
        if use_cache and cache.exists():
            rows = json.loads(cache.read_text(encoding="utf-8"))
        else:
            r = self.get("observations/exports/json",
                         {"select": "time_period_start,obs_value,obs_status",
                          "where": f'series_key="{series_key}"', "order_by": "time_period_start"})
            rows = r.json()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(rows), encoding="utf-8")
        return pd.DataFrame(rows)


def webstat_clean(raw: pd.DataFrame) -> tuple[pd.Series, int]:
    """Drop status M (missing); return the series and the number of U (unreliable) observations kept."""
    if raw.empty:
        return pd.Series(dtype=float), 0
    df = raw.copy()
    status = df.get("obs_status", pd.Series("", index=df.index)).fillna("").astype(str)
    df = df[status != "M"]
    n_unreliable = int((status[df.index] == "U").sum())
    values = pd.to_numeric(df["obs_value"], errors="coerce")
    s = pd.Series(values.to_numpy(), index=pd.to_datetime(df["time_period_start"]).dt.tz_localize(None)
                  .dt.normalize())
    return s.dropna().sort_index(), n_unreliable


def webstat_daily_yields(client: Webstat | None = None, log: Callable[..., None] = print) -> pd.DataFrame:
    """Every registered Webstat daily yield (sources.WEBSTAT_YIELDS), one request per series."""
    client = client or Webstat()
    frames = []
    for spec in sources.WEBSTAT_YIELDS:
        s, n_u = webstat_clean(client.observations(spec.key))
        frames.append(_long(spec.name, s))
        log(f"   {spec.name}: {len(s)} observations ({n_u} flagged unreliable)")
    log(f"   Webstat requests used: {client.requests}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "series", "value"])


# --------------------------------------------------------------------------- #
# Everything
# --------------------------------------------------------------------------- #
def _long(name: str, s: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"date": s.index, "series": name, "value": s.to_numpy(dtype=float)})


def download_series(spec: sources.Series) -> pd.Series:
    """One registered series from its source (the dispatcher shared by the full and the add-new refresh)."""
    if spec.source == "ecb":
        start = "1999-01-01" if spec.name == "eonia" else ("1999-01" if spec.freq == "monthly" else START)
        return ecb_series(spec.key, start)
    if spec.source == "fred":
        return fred_series(spec.key)
    if spec.source == "boj":
        return boj_series(spec.key, "199801" if spec.freq == "monthly" else "200801")
    if spec.source == "bbk":
        return bbk_series(spec.key)
    if spec.source == "boe":
        return boe_series(spec.key)
    if spec.source == "eurostat":
        return eurostat_series(spec.key)
    raise DownloadError(f"{spec.name}: no single-series downloader for source {spec.source!r}")


SINGLE_SOURCES = ("ecb", "fred", "boj", "bbk", "boe", "eurostat")


def download_new(names: list[str], log: Callable[..., None] = print) -> pd.DataFrame:
    """Only the named registered series (used to add a new source to the snapshot without a full refresh)."""
    frames = []
    webstat = [s for s in sources.WEBSTAT_YIELDS if s.name in names]
    if webstat:
        client = Webstat()
        for spec in webstat:
            s, n_u = webstat_clean(client.observations(spec.key))
            frames.append(_long(spec.name, s))
            log(f"   {spec.name}: {len(s)} observations ({n_u} flagged unreliable); Webstat requests {client.requests}")
    other = [n for n in names if n not in {s.name for s in webstat}]
    for name in other:
        spec = sources.BY_NAME.get(name)
        if spec is None or spec.source not in SINGLE_SOURCES:
            raise DownloadError(f"adding this source alone is not supported: {name}")
        frames.append(_long(name, download_series(spec)))
        log(f"   {name}: {len(frames[-1])} observations")
    return pd.concat(frames, ignore_index=True)


def download_all(log: Callable[..., None] = print) -> dict[str, pd.DataFrame]:
    """Every series, as {"series": long frame (date, series, value), "settlements": Treasury issues}."""
    frames = []
    for spec in sources.ALL_SERIES:
        if spec.source in SINGLE_SOURCES:
            frames.append(_long(spec.name, download_series(spec)))
        else:
            continue  # Webstat (one client, below) and the bulk sources below
        log(f"   {spec.name}: {len(frames[-1])} observations")
    if sources.WEBSTAT_YIELDS:
        frames.append(webstat_daily_yields(log=log))
    frames.append(nyfed_rates())
    log("   NY Fed reference rates")
    frames.append(_long("repo_dvp_on", ofr_series("REPO-DVP_AR_OO")))
    frames.append(_long("repo_dvp_term", ofr_term_repo()))
    log("   OFR repo rates")
    frames.append(_long("tga_daily", treasury_tga_daily()))
    frames.append(ecb_mmsr())
    log("   MMSR secured segment")
    frames.append(ecb_pspp())
    settlements = treasury_settlements()
    log("   Treasury settlements")
    long = pd.concat(frames, ignore_index=True)
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    long = long.dropna().drop_duplicates(["date", "series"], keep="last").sort_values(["series", "date"])
    return {"series": long.reset_index(drop=True), "settlements": settlements}
