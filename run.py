"""CLI:  python run.py backfill --days 35 | collect [--date D] | index | backtest | serve"""
import argparse
import json
from datetime import date

from airpulse import backtest, db, pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backfill", "collect", "index", "backtest", "serve"])
    ap.add_argument("--start", default="2026-08-25")
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("airpulse.api:app", host="127.0.0.1", port=a.port)
        return
    with db.connect() as con:
        if a.cmd == "backfill":
            d = pipeline.backfill(con, a.start, a.days)
            print(d.tail(3).to_string(index=False), f"\n{len(d)} days loaded")
        elif a.cmd == "collect":
            print(pipeline.collect_day(con, a.date)); con.commit(); pipeline.rebuild_index(con)
        elif a.cmd == "index":
            print(pipeline.rebuild_index(con).tail().to_string(index=False))
        else:
            r = backtest.run(db.read(con, "SELECT * FROM clean_fares"))
            r.pop("table", None)
            print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
