"""Orchestration: collect -> store raw -> clean -> store clean -> rebuild APIx."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import cleaning, config, db, index
from .scraping.simulated import SimulatedSource


def default_sources():
    return [SimulatedSource("airline", seed=7), SimulatedSource("makemytrip", seed=11),
            SimulatedSource("cleartrip", seed=13)]


def collect_day(con, day: str, sources=None) -> dict:
    sources = sources or default_sources()
    quotes = []
    for s in sources:
        try:
            quotes += s.collect(day, config.ROUTES, config.WINDOWS)
        except Exception as e:  # one failing source must not stop the run (Airflow retries the task)
            print(f"[warn] source {s.name} failed on {day}: {e}")
    raw = pd.DataFrame([q.to_dict() for q in quotes])
    db.replace_day(con, "raw_quotes", day, raw)
    clean, qc = cleaning.clean(raw) if len(raw) else (raw, dict(raw=0, duplicates=0, sold_out=0, missing=0, inconsistent=0, outliers=0, kept=0))
    db.replace_day(con, "clean_fares", day, clean)
    db.replace_day(con, "qc_log", day, pd.DataFrame([{"collected_on": day, **qc}]))
    return qc


def rebuild_index(con) -> pd.DataFrame:
    clean = db.read(con, "SELECT * FROM clean_fares")
    daily = index.compute_daily(index.cell_prices(clean))
    con.execute("DELETE FROM apix_daily")
    if len(daily):
        daily.to_sql("apix_daily", con, if_exists="append", index=False)
    return daily


def backfill(con, start: str, days: int, sources=None) -> pd.DataFrame:
    d0 = date.fromisoformat(start)
    for i in range(days):
        collect_day(con, (d0 + timedelta(days=i)).isoformat(), sources)
    con.commit()
    return rebuild_index(con)
