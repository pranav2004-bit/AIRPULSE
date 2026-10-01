"""Live-collection adapter skeleton (Playwright). Not used by default.

Requires: pip install playwright && playwright install chromium
Each portal needs its own selector map (parse_cards). Verify the portal's Terms of
Service and robots.txt first, prefer official/partner APIs, keep rate limits
conservative. No CAPTCHA solving or fingerprint spoofing is implemented by design:
a challenge page aborts that request and the quote is simply missing.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..models import RawQuote
from .base import CaptchaDetected, FareSource, PoliteFetcher


class PlaywrightSource(FareSource):
    def __init__(self, name: str, search_url_tpl: str, parse_cards, proxies: list[str] | None = None,
                 fetcher: PoliteFetcher | None = None):
        """search_url_tpl: 'https://host/search?from={o}&to={d}&date={dt}'
        parse_cards(page, ctx) -> list[dict] with keys carrier, flight_no, base_fare,
        taxes, udf, convenience_fee, total_fare.
        proxies: optional egress proxies you are authorised to use (round-robin).
        """
        self.name, self.tpl, self.parse_cards = name, search_url_tpl, parse_cards
        self.proxies = proxies or []
        self.fetcher = fetcher or PoliteFetcher()

    def collect(self, collected_on, routes, windows):
        from playwright.sync_api import sync_playwright  # lazy import

        today = date.fromisoformat(collected_on)
        out: list[RawQuote] = []
        i = 0
        with sync_playwright() as p:
            for r in routes:
                for lead in windows:
                    dep = (today + timedelta(days=lead)).isoformat()
                    url = self.tpl.format(o=r.origin, d=r.destination, dt=dep)
                    try:
                        self.fetcher.check(url)
                    except Exception:
                        continue
                    proxy = {"server": self.proxies[i % len(self.proxies)]} if self.proxies else None
                    i += 1
                    browser = p.chromium.launch(proxy=proxy)
                    page = browser.new_context(user_agent=self.fetcher.user_agent).new_page()
                    try:
                        page.goto(url, wait_until="networkidle", timeout=45000)
                        if page.locator("iframe[src*='captcha'], #captcha").count():
                            raise CaptchaDetected(url)
                        for c in self.parse_cards(page, {"route": r, "lead": lead}):
                            out.append(RawQuote(collected_on, self.name, r.origin, r.destination, c["carrier"],
                                                c.get("flight_no", ""), dep, lead, c.get("fare_class", "Economy"),
                                                c.get("base_fare"), c.get("taxes"), c.get("udf"),
                                                c.get("convenience_fee"), c.get("total_fare")))
                    except CaptchaDetected:
                        pass  # back off; never bypass
                    finally:
                        browser.close()
        return out
