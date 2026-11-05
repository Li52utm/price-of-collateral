"""Download parsers, offline: every source's response format is faked, so no request leaves the machine."""

from __future__ import annotations

import json

import pandas as pd
import pytest

import download as D
import sources


class Fake:
    """A stand-in for requests.Response."""

    def __init__(self, text: str = "", payload=None, status: int = 200) -> None:
        self.text, self._payload, self.status_code = text, payload, status
        self.content = text.encode("utf-8-sig")

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def route(monkeypatch, responses: dict) -> list:
    """Patch download._get: the first key contained in the URL (plus params) picks the response."""
    calls = []

    def fake_get(url, params=None, headers=None):
        calls.append((url, params))
        probe = url + json.dumps(params or {})
        for key, resp in responses.items():
            if key in probe:
                return resp(params) if callable(resp) else resp
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(D, "_get", fake_get)
    return calls


def test_get_retries_then_raises(monkeypatch) -> None:
    attempts = []
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: attempts.append(1) or Fake(status=503))
    with pytest.raises(D.DownloadError):
        D._get("https://example.org")
    assert len(attempts) == D.RETRIES
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: Fake("ok"))
    assert D._get("https://example.org").text == "ok"


def test_ecb_series_daily_weekly_monthly(monkeypatch) -> None:
    route(monkeypatch, {
        "EST": Fake("KEY,TIME_PERIOD,OBS_VALUE\nx,2026-11-02,1.93\nx,2026-11-03,1.92\n"),
        "ILM": Fake("KEY,TIME_PERIOD,OBS_VALUE\nx,2026-W44,100\n"),
        "IRS": Fake("KEY,TIME_PERIOD,OBS_VALUE\nx,2026-09,3.1\n"),
        "EMPTY": Fake("  ")})
    s = D.ecb_series("EST/B.EU000A2X2A25.WT")
    assert list(s.values) == [1.93, 1.92]
    assert D.ecb_series("ILM/W.U2.C.L020100.U2.EUR").index[0] == pd.Timestamp("2026-10-30")   # Friday of week 44
    assert D.ecb_series("IRS/M.FR.L.L40.CI.0000.EUR.N.Z").index[0] == pd.Timestamp("2026-09-01")
    with pytest.raises(D.DownloadError):
        D.ecb_frame("EMPTY/x")


def test_ecb_mmsr_names(monkeypatch) -> None:
    key = "MMSR.B.U2._X.IT.S1ZV._Z.T.LE.WR._X.KS._Z._Z.EUR._Z"
    route(monkeypatch, {"MMSR": Fake(f"KEY,TIME_PERIOD,OBS_VALUE\n{key},2026-09-15,1.95\n")})
    df = D.ecb_mmsr()
    assert df["series"].iloc[0] == "mmsr_rate_le_KS_IT" and df["value"].iloc[0] == 1.95


def test_ecb_pspp_cumulates(monkeypatch) -> None:
    text = ("title\nunits\nCountry,31/03/2015,30/04/2015\nGermany,\"1,000\",500\nFrance,200,300\n"
            "Narnia,1,1\nTotal,0,0\n")
    route(monkeypatch, {"PSPP": Fake(text)})
    df = D.ecb_pspp()
    de = df[df["series"] == "pspp_DE"]["value"].tolist()
    assert de == [1000.0, 1500.0] and "pspp_FR" in set(df["series"])
    route(monkeypatch, {"PSPP": Fake("a\nb\nCountry,31/03/2015\nTotal,0\n")})
    with pytest.raises(D.DownloadError):
        D.ecb_pspp()


def test_fred_nyfed_ofr(monkeypatch) -> None:
    nyfed = ("Effective Date,Rate Type,Rate (%),99th Percentile (%),Volume ($Billions)\n"
             "11/03/2026,SOFR,3.97,4.10,2900\n11/03/2026,TGCR,3.95,,\n11/03/2026,BGCR,3.95,,\n11/03/2026,EFFR,3.88,,\n")
    route(monkeypatch, {
        "fredgraph": Fake("DATE,IORB\n2026-11-02,3.90\n2026-11-03,.\n"),
        "rates/all": Fake(nyfed),
        "rp/repo": Fake(payload={"repo": {"operations": [
            {"operationDate": "2026-10-31", "totalAmtAccepted": 5e9},
            {"operationDate": "2026-10-31", "totalAmtAccepted": 1e9}]}}),
        "LE30-F": Fake(payload=[["2025-08-12", 4.4]]), "LE30-P": Fake(payload=[["2025-08-13", 4.5]]),
        "B830-F": Fake(payload=[]), "B830-P": Fake(payload=[["2025-08-14", 4.3], ["2026-11-02", 3.94]]),
        "OO-F": Fake(payload=[["2026-11-01", 3.9]]), "OO-P": Fake(payload=[["2026-11-01", 3.8], ["2026-11-02", 3.96]])})
    assert list(D.fred_series("IORB").values) == [3.90]
    rates = D.nyfed_rates()
    assert set(rates["series"]) == {"sofr", "tgcr", "bgcr", "effr", "sofr_p99", "sofr_volume"}
    assert D.nyfed_repo_operations().iloc[0] == pytest.approx(6.0)
    on = D.ofr_series("REPO-DVP_AR_OO")
    assert on[pd.Timestamp("2026-11-01")] == 3.9 and on[pd.Timestamp("2026-11-02")] == 3.96   # final wins
    term = D.ofr_term_repo()
    assert list(term.index.strftime("%Y-%m-%d")) == ["2025-08-12", "2025-08-13", "2025-08-14", "2026-11-02"]


def test_treasury_boj_bbk(monkeypatch) -> None:
    def auctions(params):
        page = params["page[number]"]
        return Fake(payload={"data": [{"security_type": "Note", "security_term": "2-Year",
                                       "issue_date": f"2026-11-0{page}", "offering_amt": "69000000000"}],
                             "meta": {"total-pages": 2}})

    tga = {"data": [{"record_date": "2026-11-03", "account_type": "Treasury General Account (TGA) Closing Balance",
                     "close_today_bal": "null", "open_today_bal": "850000"},
                    {"record_date": "2026-11-03", "account_type": "Treasury General Account (TGA) Opening Balance",
                     "close_today_bal": "1", "open_today_bal": "1"}], "meta": {"total-pages": 1}}
    route(monkeypatch, {
        "auctions_query": auctions, "operating_cash_balance": Fake(payload=tga),
        "FM01": Fake(payload={"RESULTSET": [{"VALUES": {"SURVEY_DATES": [20261102, 20261104],
                                                        "VALUES": [0.727, None]}}]}),
        "MD01": Fake(payload={"RESULTSET": [{"VALUES": {"SURVEY_DATES": [202609], "VALUES": [5000000]}}]}),
        "BAD": Fake(payload={"MESSAGE": "no data"}),
        "bundesbank": Fake("title\n2026-11-03,3.31\n2026-11-04,.\n")})
    s = D.treasury_settlements()
    assert len(s) == 2 and s["amount_bn"].iloc[0] == 69.0
    assert D.treasury_tga_daily().iloc[0] == 850000.0
    assert len(D.boj_series("FM01/STRDCLUCON")) == 1
    assert D.boj_series("MD01/MABS1AN113").index[0] == pd.Timestamp("2026-09-01")
    with pytest.raises(D.DownloadError):
        D.boj_series("BAD/x")
    assert list(D.bbk_series("BBSSY/D.REN").values) == [3.31]


def test_download_all_and_new(monkeypatch) -> None:
    original_webstat_yields = D.webstat_daily_yields
    one = pd.Series([1.0], index=pd.DatetimeIndex(["2026-11-03"]))
    long = lambda name: pd.DataFrame({"date": [pd.Timestamp("2026-11-03")], "series": [name], "value": [1.0]})  # noqa: E731
    for f in ("ecb_series", "fred_series", "boj_series", "bbk_series", "ofr_series", "ofr_term_repo",
              "treasury_tga_daily"):
        monkeypatch.setattr(D, f, lambda *a, **k: one)
    monkeypatch.setattr(D, "webstat_daily_yields", lambda **k: long("oat10_daily"))
    monkeypatch.setattr(D, "nyfed_rates", lambda: long("sofr"))
    monkeypatch.setattr(D, "ecb_mmsr", lambda: long("mmsr_rate_le_KS_IT"))
    monkeypatch.setattr(D, "ecb_pspp", lambda: long("pspp_DE"))
    monkeypatch.setattr(D, "treasury_settlements", lambda: pd.DataFrame({"date": [pd.Timestamp("2026-11-03")]}))
    out = D.download_all(log=lambda *a: None)
    names = set(out["series"]["series"])
    assert {"estr", "oat10_daily", "sofr", "pspp_DE"} <= names and len(out["settlements"]) == 1

    class Client:
        requests = 0

        def observations(self, key):
            self.requests += 1
            return pd.DataFrame({"time_period_start": ["2026-11-03"], "obs_value": ["4.9"], "obs_status": ["A"]})

    monkeypatch.setattr(D, "Webstat", Client)
    new = D.download_new(["oat10_daily"], log=lambda *a: None)
    assert new["series"].tolist() == ["oat10_daily"]
    with pytest.raises(D.DownloadError):
        D.download_new(["estr"], log=lambda *a: None)
    assert len(original_webstat_yields(Client(), log=lambda *a: None)) == len(sources.WEBSTAT_YIELDS)


def test_webstat_key_from_env_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEBSTAT_API_KEY", " abc ")
    assert D.webstat_key() == "abc"
    monkeypatch.delenv("WEBSTAT_API_KEY")
    fake_root = tmp_path / "src"
    fake_root.mkdir()
    (tmp_path / ".env").write_text('OTHER=1\nWEBSTAT_API_KEY="xyz"\n', encoding="utf-8")
    monkeypatch.setattr(D, "__file__", str(fake_root / "download.py"))
    assert D.webstat_key() == "xyz"


def test_webstat_errors_and_catalog(monkeypatch, tmp_path) -> None:
    responses = iter([Fake(payload=[{"series_key": "FM.D.X"}]), Fake(status=403), Fake(text="NotFoundResource",
                                                                                       status=404),
                      Fake(status=500)])
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: next(responses))
    c = D.Webstat(key="k", budget=10)
    assert c.series_catalog(where="x", refine="dataset_id:FM")["series_key"].tolist() == ["FM.D.X"]
    for match in ("refused", "NotFoundResource", "HTTP 500"):
        with pytest.raises(D.WebstatError, match=match):
            c.get("x", {})
    monkeypatch.setattr(D, "WEBSTAT_CACHE", tmp_path)
    (tmp_path / "K.json").write_text(json.dumps([{"time_period_start": "2026-11-03", "obs_value": "1"}]))
    assert len(c.observations("K", use_cache=True)) == 1
    assert D.webstat_clean(pd.DataFrame())[0].empty
