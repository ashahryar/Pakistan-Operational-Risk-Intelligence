"""
Shared Airflow default arguments.

Import this file into every DAG.
"""

from datetime import timedelta

DEFAULT_ARGS = {

    "owner": "pakistan-risk",

    "depends_on_past": False,

    "retries": 3,

    "retry_delay": timedelta(minutes=5),

    "email_on_failure": False,

    "email_on_retry": False,

    "email_on_success": False,

    "execution_timeout": timedelta(hours=2),
}