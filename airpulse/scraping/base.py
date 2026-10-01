"""Ethical-scraping primitives: robots.txt compliance, rate limiting, source interface.

Design rules (per problem statement: comply with robots.txt / ToS):
  * every live fetch goes through PoliteFetcher (robots.txt check + per-host delay)
  * we do NOT solve or bypass CAPTCHAs. A challenge page aborts that request and
    the quote is recorded as missing.
  * prefer sources with official/permitted access (partner APIs, licensed feeds).
"""
from __future__ import annotations

import time
import urllib.robotparser
from abc import ABC, abstractmethod
from urllib.parse import urlparse

USER_AGENT = "AirpulseBot/0.1 (+contact: airpulse-team@example.org; MoSPI CPI research)"


class CaptchaDetected(Exception):
    pass


class RobotsDisallowed(Exception):
    pass


class PoliteFetcher:
    def __init__(self, min_delay: float = 5.0, user_agent: str = USER_AGENT, _sleep=time.sleep, _clock=time.monotonic):
        self.min_delay = min_delay
        self.user_agent = user_agent
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._sleep, self._clock = _sleep, _clock

    def _rp(self, url: str) -> urllib.robotparser.RobotFileParser:
        u = urlparse(url)
        base = f"{u.scheme}://{u.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
            try:
                rp.read()
            except Exception:
                rp.disallow_all = True  # fail closed
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        return self._rp(url).can_fetch(self.user_agent, url)

    def wait_turn(self, url: str) -> None:
        host = urlparse(url).netloc
        delay = self._rp(url).crawl_delay(self.user_agent) or self.min_delay
        last = self._last.get(host)
        if last is not None:
            gap = delay - (self._clock() - last)
            if gap > 0:
                self._sleep(gap)
        self._last[host] = self._clock()

    def check(self, url: str) -> None:
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        self.wait_turn(url)


class FareSource(ABC):
    name: str

    @abstractmethod
    def collect(self, collected_on: str, routes, windows):
        """Return list[RawQuote] for one collection day."""
