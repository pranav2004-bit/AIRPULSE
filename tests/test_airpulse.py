import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from airpulse import cleaning, config, db, index, pipeline
from airpulse.scraping.base import PoliteFetcher, RobotsDisallowed
from airpulse.scraping.simulated import SimulatedSource, lead_multiplier


def raw_row(**kw):
    base = dict(collected_on="2026-09-01", source="airline", origin="DEL", destination="BOM", carrier="IndiGo",
                flight_no="6E101", departure_date="2026-09-08", lead_days=7, fare_class="Eco", base_fare=5000.0,
                taxes=500.0, udf=300.0, convenience_fee=0.0, total_fare=5800.0, status="available")
    base.update(kw)
    return base


# ---- weights / config
def test_weights_sum_to_one():
    assert sum(r.weight for r in config.ROUTES) == pytest.approx(1.0)
    assert sum(index.cell_weights().values()) == pytest.approx(1.0)


# ---- cleaning
def test_cleaning_rules():
    rows = [raw_row(flight_no=f"F{i}", base_fare=5000 + i, total_fare=5800 + i) for i in range(10)]
    rows.append(rows[0].copy())                                   # duplicate
    rows.append(raw_row(flight_no="S", status="sold_out"))         # sold out
    rows.append(raw_row(flight_no="M", base_fare=None, total_fare=None))  # missing
    rows.append(raw_row(flight_no="R", total_fare=None))           # rebuildable -> kept
    rows.append(raw_row(flight_no="X", total_fare=58000.0))        # component mismatch
    clean, qc = cleaning.clean(pd.DataFrame(rows))
    assert (qc["duplicates"], qc["sold_out"], qc["missing"], qc["inconsistent"]) == (1, 1, 1, 1)
    assert "R" in set(clean.flight_no) and "X" not in set(clean.flight_no)


def test_outlier_removed_when_components_consistent():
    rows = [raw_row(flight_no=f"F{i}", base_fare=5000 + 10 * i, total_fare=5800 + 10 * i) for i in range(12)]
    rows.append(raw_row(flight_no="O", base_fare=50000.0, taxes=500.0, total_fare=50800.0))
    clean, qc = cleaning.clean(pd.DataFrame(rows))
    assert qc["outliers"] == 1 and "O" not in set(clean.flight_no)


# ---- index
def _cells(prices_by_day):
    rows = [(d, r, w, p, 1) for d, cells in prices_by_day.items() for (r, w), p in cells.items()]
    return pd.DataFrame(rows, columns=["collected_on", "route", "lead_days", "price", "n"])


def test_index_base_100_and_uniform_10pct_rise():
    w = {("A-B", 1): .5, ("C-D", 1): .5}
    c = _cells({"2026-09-01": {("A-B", 1): 100, ("C-D", 1): 200}, "2026-09-02": {("A-B", 1): 110, ("C-D", 1): 220}})
    d = index.compute_daily(c, w)
    assert d.apix.iloc[0] == 100 and d.apix.iloc[1] == pytest.approx(110)


def test_index_weighting_and_missing_cell_renormalisation():
    w = {("A-B", 1): .75, ("C-D", 1): .25}
    c = _cells({"d1": {("A-B", 1): 100, ("C-D", 1): 100}, "d2": {("A-B", 1): 120, ("C-D", 1): 100}})
    assert index.compute_daily(c, w).apix.iloc[1] == pytest.approx(100 * 1.2 ** .75)
    c = _cells({"d1": {("A-B", 1): 100, ("C-D", 1): 100}, "d2": {("A-B", 1): 120}})  # C-D missing -> A-B only
    assert index.compute_daily(c, w).apix.iloc[1] == pytest.approx(120)


def test_index_unchanged_prices_stay_100():
    c = _cells({f"d{i}": {("A-B", 1): 500.0} for i in range(5)})
    assert np.allclose(index.compute_daily(c, {("A-B", 1): 1}).apix, 100)


# ---- simulator
def test_simulator_deterministic_and_lead_curve():
    a = SimulatedSource().collect("2026-09-01", config.ROUTES, config.WINDOWS)
    b = SimulatedSource().collect("2026-09-01", config.ROUTES, config.WINDOWS)
    assert [q.to_dict() for q in a] == [q.to_dict() for q in b]
    assert lead_multiplier(1) / lead_multiplier(45) > 2.5


# ---- ethics
def test_robots_disallow_blocks_and_rate_limit_waits():
    f = PoliteFetcher(min_delay=5, _sleep=lambda s: slept.append(s), _clock=lambda: 100.0)
    slept = []
    rp = type("RP", (), {"can_fetch": lambda s, ua, u: False, "crawl_delay": lambda s, ua: None})()
    f._robots["https://x.test"] = rp
    with pytest.raises(RobotsDisallowed):
        f.check("https://x.test/search")
    rp.can_fetch = lambda ua, u: True
    f.check("https://x.test/a"); f.check("https://x.test/b")
    assert slept == [5]


# ---- end-to-end + API
@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    with db.connect() as con:
        pipeline.backfill(con, "2026-09-01", 10)
    return path


def test_pipeline_and_api(seeded):
    from airpulse.api import app
    c = TestClient(app)
    assert c.get("/health").json()["clean_rows"] > 1000
    s = c.get("/api/index?freq=D").json()["series"]
    assert len(s) == 10 and s[0]["apix"] == 100
    assert c.get("/api/index?freq=W").status_code == 200
    assert c.get("/api/index?freq=M&fmt=csv").text.startswith("date,apix")
    assert len(c.get("/api/heatmap").json()["routes"]) == len(config.ROUTES)
    el = {e["lead_days"]: e["relative_fare"] for e in c.get("/api/elasticity").json()}
    assert el[1] > el[7] > el[45] * 0.99
    assert "spearman_rank_corr" in c.get("/api/backtest").json()


def test_api_key_enforced(seeded, monkeypatch):
    from airpulse.api import app
    monkeypatch.setenv("AIRPULSE_API_KEY", "secret")
    c = TestClient(app)
    assert c.get("/api/routes").status_code == 401
    assert c.get("/api/routes", headers={"X-API-Key": "secret"}).status_code == 200
