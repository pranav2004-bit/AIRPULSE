"""SQLite storage (schema is PostgreSQL-compatible; swap the connection for production)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_quotes (
  collected_on TEXT, source TEXT, origin TEXT, destination TEXT, carrier TEXT, flight_no TEXT,
  departure_date TEXT, lead_days INTEGER, fare_class TEXT, base_fare REAL, taxes REAL, udf REAL,
  convenience_fee REAL, total_fare REAL, status TEXT
);
CREATE INDEX IF NOT EXISTS ix_raw_day ON raw_quotes(collected_on);
CREATE TABLE IF NOT EXISTS clean_fares (
  collected_on TEXT, source TEXT, origin TEXT, destination TEXT, route TEXT, carrier TEXT, flight_no TEXT,
  departure_date TEXT, lead_days INTEGER, fare_class TEXT, base_fare REAL, taxes REAL, udf REAL,
  convenience_fee REAL, total_fare REAL,
  UNIQUE(collected_on, source, origin, destination, carrier, flight_no, departure_date, fare_class)
);
CREATE INDEX IF NOT EXISTS ix_clean_day ON clean_fares(collected_on);
CREATE TABLE IF NOT EXISTS apix_daily (date TEXT PRIMARY KEY, apix REAL, n_cells INTEGER, n_quotes INTEGER);
CREATE TABLE IF NOT EXISTS qc_log (collected_on TEXT PRIMARY KEY, raw INTEGER, duplicates INTEGER, sold_out INTEGER,
  missing INTEGER, inconsistent INTEGER, outliers INTEGER, kept INTEGER);
"""


@contextmanager
def connect(path=None):
    path = path or config.DB_PATH
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def replace_day(con, table: str, day: str, df: pd.DataFrame, key: str = "collected_on") -> None:
    con.execute(f"DELETE FROM {table} WHERE {key}=?", (day,))
    if len(df):
        df.to_sql(table, con, if_exists="append", index=False)


def read(con, sql: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params)
