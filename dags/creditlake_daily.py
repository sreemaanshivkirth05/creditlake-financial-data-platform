"""Airflow 2.11 integration. Keep the data platform in an isolated interpreter.

DuckDB has one writer. A single end-to-end CLI task owns the candidate release;
Airflow retries it safely, while max_active_runs and the host lock serialize work.
"""

import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="creditlake_daily",
    description="Publish audited SEC financials and verify the release",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    schedule="0 12 * * 1-5",
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,
    default_args={
        "owner": "creditlake",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "execution_timeout": timedelta(minutes=15),
    },
    params={"mode": Param("fixture", type="string", enum=["fixture", "live"])},
    tags=["data-engineering", "finance", "sec"],
) as dag:
    publish = BashOperator(
        task_id="build_test_publish",
        bash_command='"$CREDITLAKE_BINARY" run --mode "$CREDITLAKE_MODE"',
        env={
            "CREDITLAKE_BINARY": os.getenv(
                "CREDITLAKE_BINARY", "/opt/creditlake/.venv/bin/creditlake"
            ),
            "CREDITLAKE_MODE": "{{ params.mode }}",
        },
        append_env=True,
        do_xcom_push=False,
    )
    verify = BashOperator(
        task_id="verify_published_release",
        bash_command='"$CREDITLAKE_PYTHON" "$CREDITLAKE_ROOT/scripts/verify_release.py"',
        env={
            "CREDITLAKE_PYTHON": os.getenv("CREDITLAKE_PYTHON", "/opt/creditlake/.venv/bin/python"),
            "CREDITLAKE_ROOT": os.getenv("CREDITLAKE_ROOT", "/opt/creditlake"),
        },
        append_env=True,
        do_xcom_push=False,
    )
    publish >> verify
