from airflow.utils.state import State


def task_success(context):

    task = context["task_instance"]

    print("=" * 60)

    print(f"SUCCESS : {task.task_id}")

    print("=" * 60)


def task_failed(context):

    task = context["task_instance"]

    print("=" * 60)

    print(f"FAILED : {task.task_id}")

    print("=" * 60)


def dag_success(context):

    print("=" * 60)

    print("Pipeline completed successfully.")

    print("=" * 60)