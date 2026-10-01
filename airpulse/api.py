"""REST API for NSO / RBI consumption.  Run:  uvicorn airpulse.api:app
Set AIRPULSE_API_KEY to require an `X-API-Key` header on /api/* (recommended behind HTTPS)."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, backtest, config, db, index

app = FastAPI(title="AIRPULSE APIx", version=__version__,
              description="Real-time Airfare Price Index (base = first collection date = 100). Demo data is synthetic.")
STATIC = Path(__file__).resolve().parent.parent / "static"


def auth(x_api_key: str | None = Header(default=None)):
    key = os.environ.get("AIRPULSE_API_KEY")
    if key and x_api_key != key:
        raise HTTPException(401, "invalid or missing X-API-Key")


def _clean(con):
    return db.read(con, "SELECT * FROM clean_fares")


@app.get("/health")
def health():
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM clean_fares").fetchone()[0]
    return {"status": "ok", "clean_rows": n, "version": __version__}


@app.get("/api/routes", dependencies=[Depends(auth)])
def routes():
    return [{"route": r.code, "weight": round(r.weight, 4), "distance_km": r.distance_km} for r in config.ROUTES]


@app.get("/api/index", dependencies=[Depends(auth)])
def apix(freq: str = Query("D", pattern="^[DWM]$"), fmt: str = Query("json", pattern="^(json|csv)$")):
    with db.connect() as con:
        daily = db.read(con, "SELECT * FROM apix_daily ORDER BY date")
    out = index.aggregate(daily, freq)
    if fmt == "csv":
        return Response(out.to_csv(index=False), media_type="text/csv")
    return {"freq": freq, "base": 100, "series": out.round(3).astype(object).where(out.notna(), None).to_dict("records")}


@app.get("/api/quality", dependencies=[Depends(auth)])
def quality():
    with db.connect() as con:
        return db.read(con, "SELECT * FROM qc_log ORDER BY collected_on").to_dict("records")


@app.get("/api/fares", dependencies=[Depends(auth)])
def fares(route: str | None = None, date: str | None = None, lead_days: int | None = None, limit: int = Query(500, le=5000)):
    sql, p = "SELECT * FROM clean_fares WHERE 1=1", []
    for col, v in (("route", route), ("collected_on", date), ("lead_days", lead_days)):
        if v is not None:
            sql += f" AND {col}=?"
            p.append(v)
    with db.connect() as con:
        return db.read(con, sql + " ORDER BY collected_on DESC LIMIT ?", (*p, limit)).to_dict("records")


@app.get("/api/route-trend", dependencies=[Depends(auth)])
def route_trend(route: str):
    with db.connect() as con:
        df = db.read(con, "SELECT collected_on AS date, AVG(total_fare) AS avg_fare, MIN(total_fare) AS min_fare "
                          "FROM clean_fares WHERE route=? GROUP BY collected_on ORDER BY collected_on", (route,))
    return df.round(0).to_dict("records")


@app.get("/api/heatmap", dependencies=[Depends(auth)])
def heatmap():
    with db.connect() as con:
        h = index.heatmap(_clean(con))
    return {"routes": list(h.index), "leads": [int(c) for c in h.columns], "values": h.where(h.notna(), None).values.tolist()}


@app.get("/api/elasticity", dependencies=[Depends(auth)])
def elasticity():
    with db.connect() as con:
        e = index.elasticity(_clean(con))
    return e.round(3).to_dict("records")


@app.get("/api/backtest", dependencies=[Depends(auth)])
def bt():
    with db.connect() as con:
        return backtest.run(_clean(con))


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(STATIC / "index.html")
