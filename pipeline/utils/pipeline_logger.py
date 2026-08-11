from datetime import datetime

from sqlalchemy import text

from config.database import engine


def log_pipeline(

    pipeline,

    task,

    status,

    started,

    finished,

    rows=None,

    message=None,

):

    duration = int(
        (finished - started).total_seconds()
    )

    with engine.begin() as conn:

        conn.execute(

            text("""

            INSERT INTO pipeline_logs(

                pipeline_name,
                task_name,
                status,
                started_at,
                finished_at,
                duration_seconds,
                rows_processed,
                message

            )

            VALUES(

                :pipeline,
                :task,
                :status,
                :started,
                :finished,
                :duration,
                :rows,
                :message

            )

            """),

            {

                "pipeline": pipeline,

                "task": task,

                "status": status,

                "started": started,

                "finished": finished,

                "duration": duration,

                "rows": rows,

                "message": message,

            },

        )