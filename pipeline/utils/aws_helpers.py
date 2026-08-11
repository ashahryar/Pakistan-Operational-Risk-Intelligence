import boto3
import os
import time

from dotenv import load_dotenv

load_dotenv()


def run_glue_job(job_name):

    glue = boto3.client(

        "glue",

        region_name=os.getenv("AWS_REGION"),

        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),

        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),

    )

    run_id = glue.start_job_run(

        JobName=job_name

    )["JobRunId"]

    print(f"Started {job_name}")

    terminal = {

        "FAILED",

        "ERROR",

        "TIMEOUT",

        "STOPPED",

        "SUCCEEDED"

    }

    while True:

        time.sleep(30)

        state = glue.get_job_run(

            JobName=job_name,

            RunId=run_id

        )["JobRun"]["JobRunState"]

        print(state)

        if state == "SUCCEEDED":

            return

        if state in {

            "FAILED",

            "ERROR",

            "TIMEOUT",

            "STOPPED"

        }:

            raise RuntimeError(state)