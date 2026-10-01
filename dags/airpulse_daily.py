"""Airflow DAG: daily collect -> clean -> index (retries on failure). Requires apache-airflow."""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from airpulse import db, pipeline


def _run(ds, **_):
    with db.connect() as con:
        pipeline.collect_day(con, ds)
        con.commit()
        pipeline.rebuild_index(con)


with DAG("airpulse_daily", start_date=datetime(2026, 9, 1), schedule="0 2 * * *", catchup=False,
         default_args={"retries": 3, "retry_delay": timedelta(minutes=15)}) as dag:
    PythonOperator(task_id="collect_clean_index", python_callable=_run)
