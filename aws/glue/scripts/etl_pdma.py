"""
aws/glue/scripts/etl_pdma.py

AWS Glue ETL Job — PDMA
Reads parsed PDMA JSON files from S3 and loads them into Redshift.

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
from pyspark.sql.types import (
    StructType, StructField,
    StringType, IntegerType, FloatType, TimestampType,
)

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

BUCKET  = args["S3_BUCKET"]
RS_PROPS = {
    "url":      args["REDSHIFT_URL"],
    "user":     args["REDSHIFT_USER"],
    "password": args["REDSHIFT_PASSWORD"],
    "tempdir":  args["REDSHIFT_TMP_DIR"],
}

DATE_FORMATS = ["dd MMMM yyyy", "dd.MM.yyyy", "MMMM dd, yyyy", "dd MMM yyyy"]


def try_parse_date(col_name):
    """Try multiple date formats, return first non-null."""
    result = F.lit(None).cast("date")
    for fmt in DATE_FORMATS:
        result = F.when(
            F.to_date(F.col(col_name), fmt).isNotNull(),
            F.to_date(F.col(col_name), fmt)
        ).otherwise(result)
    return result


def write_to_redshift(df, table, preaction=None):
    pre = preaction or f"DELETE FROM {table}"
    glueContext.write_dynamic_frame.from_options(
        frame=glueContext.create_dynamic_frame.from_dataframe(df, glueContext),
        connection_type="redshift",
        connection_options={
            **RS_PROPS,
            "dbtable":    table,
            "preactions": pre,
        },
    )


# ----------------------------------------------------------
# DAILY REPORTS
# ----------------------------------------------------------

daily_schema = StructType([
    StructField("source_file",  StringType()),
    StructField("report_date",  StringType()),
    StructField("report_year",  StringType()),
    StructField("forecast",     StringType()),
    StructField("report_time",  StringType()),
])

df_daily = (
    spark.read
    .schema(daily_schema)
    .json(f"s3://{BUCKET}/parsed/pdma/daily/*/*.json")
    .withColumn("report_date", try_parse_date("report_date"))
    .withColumn("report_year", F.col("report_year").cast(IntegerType()))
    .dropDuplicates(["source_file"])
)

write_to_redshift(df_daily, "pdma_daily_reports")
print(f"pdma_daily_reports: {df_daily.count()} rows loaded")

# ----------------------------------------------------------
# RAINFALL READINGS  (explode stations array)
# ----------------------------------------------------------

rainfall_schema = StructType([
    StructField("source_file",  StringType()),
    StructField("report_date",  StringType()),
    StructField("report_year",  StringType()),
    StructField("stations", StructType([
        StructField("station",     StringType()),
        StructField("rainfall_mm", FloatType()),
    ])),
])

df_rainfall_raw = (
    spark.read
    .option("multiline", "true")
    .json(f"s3://{BUCKET}/parsed/pdma/rainfall/*/*.json")
)

df_rainfall = (
    df_rainfall_raw
    .withColumn("station_row", F.explode("stations"))
    .select(
        F.col("source_file"),
        try_parse_date("report_date").alias("report_date"),
        F.col("report_year").cast(IntegerType()).alias("report_year"),
        F.col("station_row.station").alias("station"),
        F.col("station_row.rainfall_mm").alias("rainfall_mm"),
    )
    .dropDuplicates(["source_file", "station"])
)

write_to_redshift(df_rainfall, "pdma_rainfall_readings")
print(f"pdma_rainfall_readings: {df_rainfall.count()} rows loaded")

# ----------------------------------------------------------
# GAUGE READINGS  (explode gauges array)
# ----------------------------------------------------------

df_gauge_raw = (
    spark.read
    .option("multiline", "true")
    .json(f"s3://{BUCKET}/parsed/pdma/gauge/*/*.json")
)

df_gauge = (
    df_gauge_raw
    .withColumn("gauge_row", F.explode("gauges"))
    .select(
        F.col("source_file"),
        F.to_timestamp("report_datetime").alias("report_datetime"),
        F.col("gauge_row.station").alias("station"),
        F.col("gauge_row.river").alias("river"),
        F.col("gauge_row.current_level_ft").cast(FloatType()).alias("current_level_ft"),
        F.col("gauge_row.danger_level_ft").cast(FloatType()).alias("danger_level_ft"),
        F.col("gauge_row.discharge_cusecs").cast(FloatType()).alias("discharge_cusecs"),
        F.col("gauge_row.flow_status").alias("flow_status"),
    )
    .withColumn(
        "report_year",
        F.year("report_datetime").cast(IntegerType())
    )
    .dropDuplicates(["source_file", "station"])
)

write_to_redshift(df_gauge, "pdma_gauge_readings")
print(f"pdma_gauge_readings: {df_gauge.count()} rows loaded")

job.commit()
