"""Back-test APIx-side route fares against DGCA monthly average fares.

Reference file: data/dgca_reference.csv with columns  route,avg_fare  (one reference
month; INR, all-in fare). The shipped data/dgca_reference_SAMPLE.csv is ILLUSTRATIVE only -
replace it with figures from the DGCA monthly domestic traffic / average-fare release.
Metrics: level ratio, MAPE across routes, Spearman rank correlation across routes.
"""
from __future__ import annotations

import pandas as pd

from . import config


def run(clean: pd.DataFrame, ref_path=None) -> dict:
    ref_path = ref_path or (config.DATA_DIR / "dgca_reference.csv")
    if not ref_path.exists():
        ref_path = config.DATA_DIR / "dgca_reference_SAMPLE.csv"
    ref = pd.read_csv(ref_path).set_index("route")["avg_fare"]
    ours = clean.groupby("route")["total_fare"].mean()
    j = pd.concat([ours.rename("apix_avg"), ref.rename("dgca_avg")], axis=1, join="inner").dropna()
    if len(j) < 3:
        return {"error": "fewer than 3 overlapping routes", "reference": str(ref_path)}
    j["ape"] = (j["apix_avg"] - j["dgca_avg"]).abs() / j["dgca_avg"]
    rho = j["apix_avg"].rank().corr(j["dgca_avg"].rank())
    return {
        "reference": ref_path.name,
        "illustrative_reference": "SAMPLE" in ref_path.name,
        "days": int(clean["collected_on"].nunique()),
        "routes_compared": int(len(j)),
        "level_ratio": round(float(j["apix_avg"].sum() / j["dgca_avg"].sum()), 3),
        "mape_pct": round(float(j["ape"].mean() * 100), 1),
        "spearman_rank_corr": round(float(rho), 3),
        "table": j.round(0).reset_index().to_dict("records"),
    }
