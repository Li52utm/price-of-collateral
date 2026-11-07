"""U4: the challenger forecast v2 (CQR + year-end analogue) and its frozen file."""

from __future__ import annotations

import numpy as np
import pytest

import forecast_v2 as v2


def test_conformal_offset_order_statistics() -> None:
    s = np.arange(1.0, 20.0)                                   # n = 19 scores 1..19
    assert v2.conformal_offset(s, 0.95) == 19.0                # ceil(20 x 0.95) = 19th smallest
    assert v2.conformal_offset(s, 0.9) == 18.0                 # ceil(18) = 18th
    assert v2.conformal_offset(s, 0.5) == 10.0                 # ceil(10) = 10th
    assert v2.conformal_offset(s, 0.05) == 1.0                 # floor(1) = 1st
    assert v2.conformal_offset(np.array([1.0, 2.0]), 0.95) == 2.0   # k > n -> the largest
    assert v2.conformal_offset(np.array([1.0, 2.0]), 0.05) == 1.0   # k = 0 -> the smallest


def test_analogue_quantiles_are_separated() -> None:
    jumps = np.array([61.6, -3.0, -1.8, 0.2, 1.2, 7.4, 16.8, 9.4])
    q = v2.analogue_quantiles(jumps, 0.0)
    assert q[0.05] < q[0.5] < q[0.9] < q[0.95]                 # unlike v1's pinned tails
    assert q[0.95] == pytest.approx(np.quantile(jumps, 0.95))


def test_past_year_ends_jump_definition() -> None:
    t = v2.past_year_ends("USD")
    assert len(t) >= 8 and (t["jump"] - (t["actual"] - t["level_at_origin"])).abs().max() < 1e-9


def test_frozen_v2_exists_and_is_never_overwritten(tmp_path) -> None:
    frozen = v2.load_frozen_v2()
    assert frozen is not None and frozen["model_version"] == "forecast-v2"
    assert "not a clean out-of-sample claim" in frozen["status"]
    before = v2.FROZEN_V2_PATH.read_bytes()
    with pytest.raises(FileExistsError):
        v2.create_frozen_v2()
    assert v2.FROZEN_V2_PATH.read_bytes() == before
    for c in ("USD", "EUR"):
        f = frozen["currencies"][c]
        assert f["q05"] <= f["q50"] <= f["q90"] <= f["q95"]


def test_run_leaves_both_frozen_files_unchanged(tmp_path, monkeypatch) -> None:
    import forecast
    v1_before, v2_before = forecast.FROZEN_PATH.read_bytes(), v2.FROZEN_V2_PATH.read_bytes()
    monkeypatch.setattr(v2, "SUMMARY_PATH", tmp_path / "s.json")
    monkeypatch.setattr(v2, "TURNS_PATH", tmp_path / "t.csv")
    monkeypatch.setattr(v2, "SCORE_V2_PATH", tmp_path / "score.json")   # written from 31 Dec 2026 on
    v2.run()
    assert forecast.FROZEN_PATH.read_bytes() == v1_before and v2.FROZEN_V2_PATH.read_bytes() == v2_before
