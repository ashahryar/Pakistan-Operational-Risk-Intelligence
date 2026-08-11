"""
airflow/utils/task_callbacks.py

Reusable Airflow Callbacks

Features

✓ Task Success
✓ Task Failure
✓ DAG Success
✓ DAG Failure

Notifications

✓ Email
✓ Slack (Future)
✓ Teams (Future)
✓ SNS (Future)
"""

import logging
from datetime import datetime

from pipeline.helpers.email_helper import send_email

logger = logging.getLogger(__name__)


# ==========================================================
# HELPERS
# ==========================================================

def line():
    logger.info("=" * 80)


def title(text):
    line()
    logger.info(text)
    line()


def get_duration(context):

    task = context["task_instance"]

    if task.start_date and task.end_date:
        return task.end_date - task.start_date

    return None


def print_common(context):

    task = context["task_instance"]
    dag = context["dag"]

    logger.info(f"DAG            : {dag.dag_id}")
    logger.info(f"Task           : {task.task_id}")
    logger.info(f"Run ID         : {context.get('run_id')}")
    logger.info(f"Execution Date : {context.get('execution_date')}")
    logger.info(f"Try Number     : {task.try_number}")
    logger.info(f"Start Time     : {task.start_date}")
    logger.info(f"End Time       : {task.end_date}")
    logger.info(f"Duration       : {get_duration(context)}")


# ==========================================================
# FUTURE PLACEHOLDERS
# ==========================================================

def send_slack(message):
    logger.info(f"[Slack] {message}")


def send_teams(message):
    logger.info(f"[Teams] {message}")


def send_sns(message):
    logger.info(f"[SNS] {message}")

# ==========================================================
# TASK SUCCESS
# ==========================================================

def task_success(context):

    task = context["task_instance"]
    dag = context["dag"]

    title("TASK COMPLETED SUCCESSFULLY")

    print_common(context)

    logger.info("Status         : SUCCESS")

    line()

    subject = f"✅ Airflow Task Success | {dag.dag_id}"

    message = f"""
Task completed successfully.

DAG            : {dag.dag_id}
Task           : {task.task_id}
Run ID         : {context.get('run_id')}
Execution Date : {context.get('execution_date')}
Duration       : {get_duration(context)}
Finished       : {datetime.now()}
"""

    send_email(subject, message)

    send_slack(
        f"Task Success : {dag.dag_id} -> {task.task_id}"
    )


# ==========================================================
# TASK FAILURE
# ==========================================================

def task_failure(context):

    task = context["task_instance"]
    dag = context["dag"]

    title("TASK FAILED")

    print_common(context)

    exception = context.get("exception")

    logger.error(f"Exception      : {exception}")

    line()

    subject = f"❌ Airflow Task Failed | {dag.dag_id}"

    message = f"""
Task execution failed.

DAG            : {dag.dag_id}
Task           : {task.task_id}
Run ID         : {context.get('run_id')}
Execution Date : {context.get('execution_date')}
Duration       : {get_duration(context)}
Exception      : {exception}
Finished       : {datetime.now()}
"""

    send_email(subject, message)

    send_slack(
        f"Task Failed : {dag.dag_id} -> {task.task_id}"
    )

# ==========================================================
# DAG SUCCESS
# ==========================================================

def dag_success(context):

    dag = context["dag"]

    title("DAG COMPLETED SUCCESSFULLY")

    logger.info(f"DAG            : {dag.dag_id}")
    logger.info(f"Run ID         : {context.get('run_id')}")
    logger.info(f"Execution Date : {context.get('execution_date')}")
    logger.info(f"Finished       : {datetime.now()}")

    line()

    subject = f"✅ Airflow DAG Success | {dag.dag_id}"

    message = f"""
DAG execution completed successfully.

DAG            : {dag.dag_id}
Run ID         : {context.get('run_id')}
Execution Date : {context.get('execution_date')}
Finished       : {datetime.now()}

All pipeline tasks completed successfully.
"""

    send_email(subject, message)

    send_slack(
        f"DAG Success : {dag.dag_id}"
    )


# ==========================================================
# DAG FAILURE
# ==========================================================

def dag_failure(context):

    dag = context["dag"]

    title("DAG FAILED")

    logger.error(f"DAG            : {dag.dag_id}")
    logger.error(f"Run ID         : {context.get('run_id')}")
    logger.error(f"Execution Date : {context.get('execution_date')}")
    logger.error(f"Finished       : {datetime.now()}")
    logger.error(f"Exception      : {context.get('exception')}")

    line()

    subject = f"❌ Airflow DAG Failed | {dag.dag_id}"

    message = f"""
DAG execution failed.

DAG            : {dag.dag_id}
Run ID         : {context.get('run_id')}
Execution Date : {context.get('execution_date')}
Finished       : {datetime.now()}

Exception:
{context.get('exception')}
"""

    send_email(subject, message)

    send_slack(
        f"DAG Failed : {dag.dag_id}"
    )


# ==========================================================
# EXPORTS
# ==========================================================

__all__ = [

    "task_success",
    "task_failure",
    "dag_success",
    "dag_failure",

]