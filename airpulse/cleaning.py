"""Cleaning pipeline: dedupe -> drop sold-out/cancelled -> repair missing -> component
consistency -> robust outlier removal (MAD on log fare within route x lead x day).
Returns (clean_df, qc_dict)."""
from __future__ import annotations

import numpy as np
import pandas as pd

KEY = ["collected_on", "source", "origin", "destination", "carrier", "flight_no", "departure_date", "fare_class"]
PARTS = ["base_fare", "taxes", "udf", "convenience_fee"]


def clean(raw: pd.DataFrame, mad_z: float = 3.5, tol: float = 0.01):
    qc = dict(raw=len(raw), duplicates=0, sold_out=0, missing=0, inconsistent=0, outliers=0, kept=0)
    if raw.empty:
        return raw.assign(route=[]), qc
    df = raw.copy()

    n = len(df)
    df = df.drop_duplicates(subset=KEY, keep="first")
    qc["duplicates"] = n - len(df)

    n = len(df)
    df = df[df["status"] == "available"]
    qc["sold_out"] = n - len(df)

    # Missing: rebuild total from components when possible, else drop.
    df = df.copy()
    df[["taxes", "udf", "convenience_fee"]] = df[["taxes", "udf", "convenience_fee"]].fillna(0.0)
    can_rebuild = df["total_fare"].isna() & df["base_fare"].notna()
    df.loc[can_rebuild, "total_fare"] = df.loc[can_rebuild, PARTS].sum(axis=1)
    n = len(df)
    df = df[df["total_fare"].notna() & df["base_fare"].notna() & (df["total_fare"] > 0)]
    qc["missing"] = n - len(df)

    # Total must equal base + taxes + UDF + convenience within tolerance.
    n = len(df)
    parts_sum = df[PARTS].sum(axis=1)
    df = df[(df["total_fare"] - parts_sum).abs() <= tol * parts_sum]
    qc["inconsistent"] = n - len(df)

    df["route"] = df["origin"] + "-" + df["destination"]

    # Robust outliers within (route, lead) for the day.
    n = len(df)
    lf = np.log(df["total_fare"])
    g = lf.groupby([df["route"], df["lead_days"]])
    med = g.transform("median")
    mad = (lf - med).abs().groupby([df["route"], df["lead_days"]]).transform("median")
    z = 0.6745 * (lf - med).abs() / mad.replace(0, np.nan)
    keep = ~(z > mad_z).fillna(False)
    df = df[keep]
    qc["outliers"] = n - len(df)

    qc["kept"] = len(df)
    cols = ["collected_on", "source", "origin", "destination", "route", "carrier", "flight_no", "departure_date",
            "lead_days", "fare_class", *PARTS, "total_fare"]
    return df[cols].reset_index(drop=True), qc
