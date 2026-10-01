# AIRPULSE - Real-time Airfare Price Index (APIx) prototype
SIH 2026 · PS 26056 · Team Hogwarts Techies

Pipeline: **collect -> raw store -> clean -> clean store -> chained Jevons index -> REST API + dashboard**.

```bash
pip install -r requirements.txt
python run.py backfill --days 35     # 35 days of collection/cleaning/index
python run.py backtest               # compare with DGCA reference fares
python run.py serve                  # dashboard http://127.0.0.1:8000 , API docs /docs
python -m pytest -q                  # automated tests
```

## What is real and what is not (read this)
* **Demo data is synthetic.** `airpulse/scraping/simulated.py` generates fares with a realistic
  structure (lead-time curve, weekday/festival demand, fees, sell-outs, duplicates, glitches).
  No live airline/OTA site is scraped by default.
* `scraping/playwright_source.py` is a live-adapter *skeleton*: you must supply the per-portal selectors and
  check each site's ToS/robots.txt. It enforces robots.txt (fail-closed), per-host rate limits, an honest
  User-Agent, optional sanctioned proxy rotation, and **aborts on CAPTCHA instead of bypassing it**.
  Prefer partner/official feeds where available.
* **The back-test is not yet meaningful.** `data/dgca_reference_SAMPLE.csv` is an illustrative placeholder
  I wrote, and the simulator was calibrated near it. Put real DGCA figures (columns `route,avg_fare`) in
  `data/dgca_reference.csv`, replace `data/route_weights.csv` with DGCA city-pair traffic, and run against
  live data for 30+ days for the required validation.

## Index method (`airpulse/index.py`)
Cell = route x window (T+1,7,15,30,45). Cell price = geometric mean of clean total fares. Weights = route traffic
share x equal window weight. Chained Jevons: `I_t = I_{t-1} * prod (P_t/P_{t-1})^w`, over cells seen on both days
(weights renormalised). Base date = 100. Weekly/monthly = mean of daily. Because departure weekday shifts with
collection date, the raw daily series has a weekly cycle; a 7-day mean is provided (`apix_7d`).

## Cleaning (`airpulse/cleaning.py`)
Dedupe -> drop sold-out/cancelled -> rebuild missing total from parts -> drop if total != base+taxes+UDF+convenience
(1%) -> MAD outliers on log fare per route x lead x day. Counts logged in `qc_log`.

## API (`X-API-Key` required if `AIRPULSE_API_KEY` is set; run behind HTTPS)
`/api/index?freq=D|W|M&fmt=json|csv` · `/api/routes` · `/api/fares` · `/api/route-trend` · `/api/heatmap` ·
`/api/elasticity` · `/api/quality` · `/api/backtest` · `/health`

## Deviations from the pitch deck
SQLite instead of PostgreSQL (SQL is portable), a static Chart.js dashboard instead of Next.js, and an Airflow DAG
(`dags/`) and Dockerfile provided but Kubernetes manifests and Scrapy spiders are not included.
