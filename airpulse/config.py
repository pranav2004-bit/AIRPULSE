"""Basket definition: routes, weights, advance-purchase windows, carriers.

Route weights are proportional to approximate DGCA domestic city-pair passenger
traffic. They are illustrative defaults: replace them with the latest DGCA
city-pair release by editing data/route_weights.csv (columns: origin,destination,weight)
- it is loaded automatically when present.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("AIRPULSE_DB", DATA_DIR / "airpulse.db"))

WINDOWS = (1, 7, 15, 30, 45)  # T+n advance-purchase days
CARRIERS = ("IndiGo", "Air India", "Air India Express", "Akasa Air", "SpiceJet")
SOURCES = ("airline", "makemytrip", "yatra", "easemytrip", "cleartrip", "ixigo")

# Approx. relative traffic share (used as index weights, normalised to 1).
_DEFAULT_ROUTES = [
    ("DEL", "BOM", 100, 1148), ("DEL", "BLR", 85, 1740), ("BOM", "BLR", 70, 842),
    ("DEL", "CCU", 55, 1305), ("BLR", "HYD", 48, 500), ("MAA", "DEL", 45, 1760),
    ("BOM", "HYD", 40, 620), ("DEL", "HYD", 38, 1250), ("BOM", "GOI", 34, 440),
    ("BOM", "MAA", 32, 1030), ("DEL", "PNQ", 30, 1170), ("BLR", "MAA", 28, 290),
]


@dataclass(frozen=True)
class Route:
    origin: str
    destination: str
    weight: float
    distance_km: int

    @property
    def code(self) -> str:
        return f"{self.origin}-{self.destination}"


def load_routes() -> list[Route]:
    routes = [Route(o, d, w, km) for o, d, w, km in _DEFAULT_ROUTES]
    custom = DATA_DIR / "route_weights.csv"
    if custom.exists():
        df = pd.read_csv(custom)
        km = {r.code: r.distance_km for r in routes}
        routes = [
            Route(r.origin, r.destination, float(r.weight), km.get(f"{r.origin}-{r.destination}", 1000))
            for r in df.itertuples()
        ]
    total = sum(r.weight for r in routes)
    return [Route(r.origin, r.destination, r.weight / total, r.distance_km) for r in routes]


ROUTES = load_routes()
