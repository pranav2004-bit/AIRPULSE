"""Simulated fare source - deterministic synthetic market for demo/tests/back-test.

Live airline/OTA sites restrict or actively block automated access, so the prototype
ships with a generator that reproduces the *structure* of Indian dynamic pricing
(lead-time curve, weekday/festival demand, fuel-surcharge drift, sell-outs, noise,
outliers, duplicates, missing fields). All output is SYNTHETIC.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

import numpy as np

from ..models import RawQuote
from .base import FareSource

CARRIER_FACTOR = {"IndiGo": 1.00, "Air India": 1.12, "Air India Express": 0.95, "Akasa Air": 0.96, "SpiceJet": 0.93}
FESTIVE = [(date(2026, 10, 18), date(2026, 10, 25), 1.30), (date(2026, 11, 5), date(2026, 11, 10), 1.35),
           (date(2026, 12, 22), date(2027, 1, 2), 1.40)]


def lead_multiplier(lead: int) -> float:
    # ~2.6x at T+1 falling to ~0.85x by T+45 -> 200-400% intra-sector spread
    return 0.85 + 1.75 * math.exp(-lead / 9.0)


def demand_multiplier(dep: date) -> float:
    m = {4: 1.12, 5: 1.10, 6: 1.15, 0: 1.05}.get(dep.weekday(), 0.95)  # Fri/Sat/Sun/Mon
    for a, b, f in FESTIVE:
        if a <= dep <= b:
            m *= f
    return m


class SimulatedSource(FareSource):
    def __init__(self, name: str = "airline", seed: int = 7, dirty: bool = True, fuel_trend_per_day: float = 0.0006):
        self.name, self.seed, self.dirty, self.trend = name, seed, dirty, fuel_trend_per_day
        self.origin_day = date(2026, 8, 1)

    def _rng(self, *keys) -> np.random.Generator:
        h = hashlib.sha256("|".join(map(str, (self.seed, self.name, *keys))).encode()).digest()
        return np.random.default_rng(int.from_bytes(h[:8], "little"))

    def collect(self, collected_on, routes, windows):
        today = date.fromisoformat(collected_on)
        rng = self._rng(collected_on)
        drift = 1 + self.trend * (today - self.origin_day).days
        out: list[RawQuote] = []
        for r in routes:
            base_route = 1200 + 2.0 * r.distance_km
            for lead in windows:
                dep = today + timedelta(days=lead)
                for carrier in CARRIER_FACTOR:
                    if rng.random() < 0.15:  # carrier does not operate / not listed
                        continue
                    base = (base_route * lead_multiplier(lead) * demand_multiplier(dep)
                            * CARRIER_FACTOR[carrier] * drift * rng.lognormal(0, 0.05))
                    tax = round(base * 0.05 + 350 + rng.uniform(0, 60), 2)
                    udf = round(150 + rng.uniform(0, 400), 2)
                    conv = 0.0 if self.name == "airline" else round(rng.uniform(150, 399), 2)
                    base = round(base, 2)
                    status = "sold_out" if (lead <= 7 and rng.random() < 0.06) else "available"
                    total = round(base + tax + udf + conv, 2)
                    q = RawQuote(collected_on, self.name, r.origin, r.destination, carrier,
                                 f"{carrier[:2].upper()}{int(rng.integers(100, 999))}", dep.isoformat(), lead,
                                 "Economy Saver", base, tax, udf, conv, total, status)
                    if self.dirty:
                        x = rng.random()
                        if x < 0.01:
                            q.total_fare = round(total * float(rng.choice([6.0, 0.08])), 2)  # glitch outlier
                        elif x < 0.02:
                            q.base_fare = q.total_fare = None  # missing
                        elif x < 0.03:
                            out.append(q)  # exact duplicate
                    out.append(q)
        return out
