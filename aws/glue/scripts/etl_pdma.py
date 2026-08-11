"""
aws/glue/scripts/etl_pmd.py

AWS Glue ETL Job — PMD
Reads PMD latest.json files from S3 and loads them into Redshift.

Glue job parameters:
  --S3_BUCKET          pakistan-operational-risk-intelligence
  --REDSHIFT_URL       jdbc:redshift://<host>:5439/pakistan_operational_risk
  --REDSHIFT_USER      admin
  --REDSHIFT_PASSWORD  <password>
  --REDSHIFT_TMP_DIR   s3://<bucket>/tmp/glue/
"""

import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F

# ----------------------------------------------------------
# INIT
# ----------------------------------------------------------

args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "S3_BUCKET",
    "REDSHIFT_URL",
    "REDSHIFT_USER",
    "REDSHIFT_PASSWORD",
    "REDSHIFT_TMP_DIR",
])

sc          = SparkContext()
glueContext = GlueContext(sc)
spark       = glueContext.spark_session
job         = Job(glueContext)
job.init(args["JOB_NAME"], args)

BUCKET   = args["S3_BUCKET"]
RS_PROPS = {
    "url":      args["REDSHIFT_URL"],
    "user":     args["REDSHIFT_USER"],
    "password": args["REDSHIFT_PASSWORD"],
    "tempdir":  args["REDSHIFT_TMP_DIR"],
}

REPORT_PATHS = {
    "daily_forecast": f"s3://{BUCKET}/raw/pmd/reports/daily_forecast/all/latest.json",
    "weekly_outlook": f"s3://{BUCKET}/raw/pmd/reports/weekly_outlook/all/latest.json",
    "weather_alerts": f"s3://{BUCKET}/raw/pmd/reports/weather_alerts/all/latest.json",
}


def write_to_redshift(df, table):
    glueContext.write_dynamic_frame.from_options(
        frame=glueContext.create_dynamic_frame.from_dataframe(df, glueContext),
        connection_type="redshift",
        connection_options={
            **RS_PROPS,
            "dbtable":    table,
            "preactions": f"DELETE FROM {table}",
        },
    )


# ----------------------------------------------------------
# PMD REPORTS  (one row per category)
# ----------------------------------------------------------

reports_rows = []
for category, path in REPORT_PATHS.items():
    try:
        df = spark.read.option("multiline", "true").json(path)
        reports_rows.append(
            df.select(
                F.lit(category).alias("category"),
                F.col("source"),
                F.col("url"),
                F.col("forecast"),
                F.to_timestamp("scraped_at").alias("scraped_at"),
            )
        )
    except Exception as e:
        print(f"[WARN] Could not read {path}: {e}")

if reports_rows:
    from functools import reduce
    df_reports = reduce(lambda a, b: a.union(b), reports_rows)
    write_to_redshift(df_reports, "pmd_reports")
    print(f"pmd_reports: {df_reports.count()} rows loaded")

# ----------------------------------------------------------
# PMD WEATHER  (explode tables → rows from daily_forecast)
# ----------------------------------------------------------

df_daily_raw = (
    spark.read
    .option("multiline", "true")
    .json(REPORT_PATHS["daily_forecast"])
)

df_weather = (
    df_daily_raw
    .withColumn("tbl", F.explode("tables"))
    .withColumn("row", F.explode("tbl.rows"))
    .select(
        F.lit("daily_forecast").alias("category"),
        F.to_timestamp("scraped_at").alias("scraped_at"),
        F.col("row")[5].alias("city"),
        F.col("row")[4].alias("humidity"),
        F.col("row")[3].alias("max_temperature"),
        F.col("row")[2].alias("day1_forecast"),
        F.col("row")[1].alias("day2_forecast"),
        F.col("row")[0].alias("day3_forecast"),
    )
    .filter(F.col("city").isNotNull())
)

write_to_redshift(df_weather, "pmd_weather")
print(f"pmd_weather: {df_weather.count()} rows loaded")

# ----------------------------------------------------------
# PMD WEEKLY OUTLOOK  (explode tables → rows)
# ----------------------------------------------------------

df_outlook_raw = (
    spark.read
    .option("multiline", "true")
    .json(REPORT_PATHS["weekly_outlook"])
)

df_outlook = (
    df_outlook_raw
    .withColumn("tbl", F.explode("tables"))
    .withColumn("row", F.explode("tbl.rows"))
    .select(
        F.to_timestamp("scraped_at").alias("scraped_at"),
        F.col("row")[1].alias("forecast_date"),
        F.col("row")[0].alias("weather_description"),
    )
    .filter(F.col("forecast_date").isNotNull())
)

write_to_redshift(df_outlook, "pmd_weekly_outlook")
print(f"pmd_weekly_outlook: {df_outlook.count()} rows loaded")

job.commit()
