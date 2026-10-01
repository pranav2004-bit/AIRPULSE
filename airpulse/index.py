"""APIx construction: chained Jevons (geometric-mean) price index.

Cell = (route, advance-purchase window). Cell price on a day = geometric mean of clean
total fares across carriers/sources. Weights = route traffic weight x window weight
(equal by default), renormalised over cells observed on both consecutive days.
    I_t = I_{t-1} * prod_c (P_c,t / P_c,t-1) ^ w_c        (base date = 100)
Weekly/monthly APIx = mean of the daily index over the period.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def cell_prices(clean: pd.DataFrame, field: str = "total_fare") -> pd.DataFrame:
    g = clean.assign(_l=np.log(clean[field])).groupby(["collected_on", "route", "lead_days"])
    out = g.agg(_l=("_l", "mean"), n=("_l", "size")).reset_index()
    out["price"] = np.exp(out.pop("_l"))
    return out


def cell_weights(routes=None, windows=None) -> dict:
    routes = routes or config.ROUTES
    windows = windows or config.WINDOWS
    return {(r.code, w): r.weight / len(windows) for r in routes for w in windows}


def compute_daily(cells: pd.DataFrame, weights: dict | None = None, base: float = 100.0) -> pd.DataFrame:
    weights = weights or cell_weights()
    if cells.empty:
        return pd.DataFrame(columns=["date", "apix", "n_cells", "n_quotes"])
    piv = cells.pivot_table(index="collected_on", columns=["route", "lead_days"], values="price").sort_index()
    cnt = cells.groupby("collected_on")["n"].sum()
    w = pd.Series({c: weights.get(c, 0.0) for c in piv.columns})
    rows, level, prev = [], base, None
    for day, row in piv.iterrows():
        if prev is None:
            rows.append((day, level, int(row.notna().sum()), int(cnt[day])))
        else:
            ok = row.notna() & prev.notna() & (w > 0)
            if ok.any():
                ww = w[ok] / w[ok].sum()
                level *= float(np.exp((ww * np.log(row[ok] / prev[ok])).sum()))
            rows.append((day, level, int(ok.sum()), int(cnt[day])))
        prev = row.where(row.notna(), prev)  # carry last seen price for cells that drop out
    return pd.DataFrame(rows, columns=["date", "apix", "n_cells", "n_quotes"])


def aggregate(daily: pd.DataFrame, freq: str) -> pd.DataFrame:
    """freq: 'D' | 'W' | 'M'"""
    if daily.empty:
        return daily[["date", "apix"]].copy()
    if freq == "D":
        out = daily[["date", "apix"]].copy()
        # departure weekday shifts with collection date under fixed lead windows, so the
        # raw daily series carries a weekly cycle; the 7-day trailing mean removes it.
        out["apix_7d"] = out["apix"].rolling(7, min_periods=7).mean()
        return out
    s = daily.assign(date=pd.to_datetime(daily["date"])).set_index("date")["apix"]
    r = s.resample("W-SUN" if freq == "W" else "MS").mean().dropna().reset_index()
    r["date"] = r["date"].dt.strftime("%Y-%m-%d")
    return r


def heatmap(clean: pd.DataFrame, by: str = "lead_days") -> pd.DataFrame:
    return clean.pivot_table(index="route", columns=by, values="total_fare", aggfunc="mean").round(0)


def elasticity(clean: pd.DataFrame, ref_lead: int = 45) -> pd.DataFrame:
    """Mean fare by lead window relative to the ref_lead window (per route-normalised)."""
    m = clean.pivot_table(index="route", columns="lead_days", values="total_fare", aggfunc="mean")
    rel = m.div(m[ref_lead], axis=0) if ref_lead in m.columns else m
    out = rel.mean().rename("relative_fare").reset_index()
    out["mean_fare"] = m.mean().values
    return out
