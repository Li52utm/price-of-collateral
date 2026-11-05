"""U1: daily France rules, the Webstat client (offline, with fake responses), and the merged snapshot."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import data
import download
import france as Fr
import france_daily as FD
import sources
import validation
import wording as w


def test_rule1_with_min_run_one_matches_the_monthly_blowout_rule() -> None:
    idx = pd.date_range("2008-01-01", periods=30, freq="MS")
    s = pd.Series([50.0] * 14 + [90, 110, 100, 85, 79, 70, 60] + [55.0] * 9, index=idx)
    base = s.rolling(12).mean().shift(1)
    old = Fr.episodes(s, "XX", threshold=30)
    new = FD.find_episodes(s, base, 30, 1, pd.Timestamp("2008-01-01"))
    assert len(old) == len(new) == 1
    assert new[0]["start"] == old[0]["start"] and new[0]["peak"] == old[0]["peak"]
    assert new[0]["recovery"] == old[0]["recovery"] and new[0]["periods"] == old[0]["duration"]


def test_rule2_needs_a_long_enough_run() -> None:
    idx = pd.date_range("2008-01-01", periods=40, freq="MS")
    base = pd.Series(50.0, index=idx)
    short = pd.Series([50.0] * 14 + [70.0] * 5 + [50.0] * 21, index=idx)   # 5 months above +15
    long_ = pd.Series([50.0] * 14 + [70.0] * 6 + [55.0] * 20, index=idx)   # 6 months, then retraces
    assert FD.find_episodes(short, base, 15, 6) == []
    eps = FD.find_episodes(long_, base, 15, 6)
    assert len(eps) == 1 and eps[0]["start"] == idx[14] and eps[0]["confirmed"] == idx[19]
    # peak 70, baseline 50 -> half retraced at 60; first value <= 60 after confirmation is idx[20]
    assert eps[0]["recovery"] == idx[20] and eps[0]["observed"]


def test_ongoing_episode_is_censored_and_reported() -> None:
    idx = pd.bdate_range("2020-01-01", periods=300)
    s = pd.Series(np.r_[np.full(280, 50.0), np.full(20, 120.0)], index=idx)
    base = s.rolling(250).mean().shift(1)
    eps = FD.find_episodes(s, base, 30, 1)
    st = FD.status(eps, idx[-1], FD.BD_PER_MONTH)
    assert st["in_episode"] and st["start"] == str(idx[280].date()) and st["age_periods"] == 19


def test_daily_event_window_is_centred_on_the_event() -> None:
    idx = pd.bdate_range("2024-12-02", periods=6)
    spread = pd.Series([80, 80, 81, 90, 92, 92], index=idx, dtype=float)
    out = FD.daily_event_study(spread, [{"date": "2024-12-04", "event": "E", "kind": "political"}])
    assert out[0]["event_day"] == "2024-12-04" and out[0]["change_bp"] == pytest.approx(10.0)  # 90 - 80


def test_daily_results_are_consistent_with_their_rule(tmp_path) -> None:
    s = FD.run(out_dir=tmp_path)
    frame = pd.read_csv(tmp_path / "daily_spread.csv", index_col=0, parse_dates=True)
    now = s["rules"]["now"]
    assert now["date"] == str(frame.index[-1].date())
    st = s["rules"]["blowout"]["30"]["status"]
    if st["in_episode"]:
        start = pd.Timestamp(st["start"])
        assert frame.loc[start, "smoothed"] >= frame.loc[start, "baseline"] + 30
    sentence = w.daily_rules_sentence(now["date"], now["spread"], now["smoothed"], now["baseline"], st["in_episode"],
                                      st.get("start"), st.get("peak"), st.get("half_retrace_level"),
                                      st.get("p_recover_next_12m"), False, False)
    assert ("has been in an episode" in sentence) == st["in_episode"]
    assert w.above_or_below(now["smoothed"] - now["baseline"]) in sentence


def test_decomposition_is_exact() -> None:
    d = FD.daily_decomposition()
    assert d["spread_last"] - d["spread_base"] == pytest.approx(d["oat_leg"] + d["bund_contribution"])
    assert d["base_day"] == "2024-06-07"


# --------------------------------------------------------------------------- #
# Webstat client: the key only in the header, no retries, a request budget
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = "") -> None:
        self.status_code, self._payload, self.text = status, payload, text or json.dumps(payload)

    def json(self):
        return self._payload


def test_webstat_sends_the_key_only_in_the_header(monkeypatch, tmp_path) -> None:
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers)
        return FakeResponse(200, [{"time_period_start": "2026-11-02", "obs_value": "4.9", "obs_status": "A"},
                                  {"time_period_start": "2026-11-03", "obs_value": None, "obs_status": "M"},
                                  {"time_period_start": "2026-11-04", "obs_value": "4.8", "obs_status": "U"}])

    monkeypatch.setattr(download.requests, "get", fake_get)
    monkeypatch.setattr(download, "WEBSTAT_CACHE", tmp_path)
    client = download.Webstat(key="secret-test-key", budget=2)
    s, n_u = download.webstat_clean(client.observations("FM.D.FR.X"))
    assert seen["headers"] == {"Authorization": "Apikey secret-test-key"}
    assert "secret-test-key" not in seen["url"] and "secret-test-key" not in json.dumps(seen["params"])
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-11-02", "2026-11-04"] and n_u == 1
    assert client.requests == 1


def test_webstat_stops_on_429_without_retrying(monkeypatch) -> None:
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        return FakeResponse(429, {"error": "quota"})

    monkeypatch.setattr(download.requests, "get", fake_get)
    client = download.Webstat(key="k", budget=5)
    with pytest.raises(download.WebstatError, match="429"):
        client.observations("FM.D.FR.X")
    assert len(calls) == 1


def test_webstat_budget_and_missing_key(monkeypatch) -> None:
    monkeypatch.setattr(download.requests, "get", lambda *a, **k: FakeResponse(200, []))
    client = download.Webstat(key="k", budget=1)
    client.get("series/exports/json", {})
    with pytest.raises(download.WebstatError, match="budget"):
        client.get("series/exports/json", {})
    monkeypatch.delenv("WEBSTAT_API_KEY", raising=False)
    monkeypatch.setattr(download, "webstat_key", lambda: None)
    with pytest.raises(download.WebstatError, match="not set"):
        download.Webstat()


def test_registry_and_snapshot_have_the_daily_oat() -> None:
    spec = sources.BY_NAME["oat10_daily"]
    assert spec.source == "webstat" and spec.lag_bd == 1 and "21:00" in spec.description
    assert set(sources.WEBSTAT_NO_DAILY) == {"DE", "IT", "ES"}
    s = data.get("oat10_daily")
    assert s.index.min() == pd.Timestamp("2004-11-03") and len(s) > 5000
    assert validation.check_oat(data.load_long())["status"] == validation.PASS
