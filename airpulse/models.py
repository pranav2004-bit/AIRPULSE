from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class RawQuote:
    """One fare observation as seen on a source page."""
    collected_on: str          # date the scrape ran (YYYY-MM-DD)
    source: str                # airline / OTA
    origin: str
    destination: str
    carrier: str
    flight_no: str
    departure_date: str
    lead_days: int             # T+n
    fare_class: str            # e.g. Economy Saver / Flex
    base_fare: Optional[float]
    taxes: Optional[float]     # YQ/fuel surcharge, GST, etc.
    udf: Optional[float]       # airport user-development fee
    convenience_fee: Optional[float]
    total_fare: Optional[float]
    status: str = "available"  # available | sold_out | cancelled

    def to_dict(self):
        return asdict(self)
