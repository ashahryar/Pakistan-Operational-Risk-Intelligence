"""
aws/glue/scripts/etl_ndma.py

AWS Glue ETL Job — NDMA
Reads parsed NDMA JSON files from S3 and loads them into Redshift.

Glue job parameters (set in create_jobs.py):
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
    StringType, IntegerType, FloatType, DateType, TimestampType,
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

BUCKET      = args["S3_BUCKET"]
RS_URL      = args["REDSHIFT_URL"]
RS_USER     = args["REDSHIFT_USER"]
RS_PASS     = args["REDSHIFT_PASSWORD"]
RS_TMP      = args["REDSHIFT_TMP_DIR"]

RS_PROPS = {
    "url":      RS_URL,
    "user":     RS_USER,
    "password": RS_PASS,
    "tempdir":  RS_TMP,
}


def write_to_redshift(df, table):
    glueContext.write_dynamic_frame.from_options(
        frame=glueContext.create_dynamic_frame.from_catalog(
            database="default", table_name=table
        ) if False else glueContext.create_dynamic_frame.from_dataframe(
            df, glueContext
        ),
        connection_type="redshift",
        connection_options={
            **RS_PROPS,
            "dbtable": table,
            "preactions": f"DELETE FROM {table}",
        },
    )


# ----------------------------------------------------------
# CASUALTIES
# ----------------------------------------------------------

casualties_schema = StructType([
    StructField("report_number", StringType()),
    StructField("report_date",   StringType()),
    StructField("province",      StringType()),
    StructField("deaths",        IntegerType()),
    StructField("injured",       IntegerType()),
])

df_casualties = (
    spark.read
    .schema(casualties_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/casualties.json")
    .withColumn("report_date", F.to_date("report_date", "dd MMMM yyyy"))
)

write_to_redshift(df_casualties, "ndma_casualties")
print(f"ndma_casualties: {df_casualties.count()} rows loaded")

# ----------------------------------------------------------
# DAMAGE
# ----------------------------------------------------------

damage_schema = StructType([
    StructField("report_number", StringType()),
    StructField("report_date",   StringType()),
    StructField("province",      StringType()),
    StructField("roads_km",      FloatType()),
    StructField("bridges",       IntegerType()),
    StructField("houses_total",  IntegerType()),
    StructField("livestock",     IntegerType()),
])

df_damage = (
    spark.read
    .schema(damage_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/damage.json")
    .withColumn("report_date", F.to_date("report_date", "dd MMMM yyyy"))
)

write_to_redshift(df_damage, "ndma_damage")
print(f"ndma_damage: {df_damage.count()} rows loaded")

# ----------------------------------------------------------
# RELIEF
# ----------------------------------------------------------

relief_schema = StructType([
    StructField("report_number", StringType()),
    StructField("report_date",   StringType()),
    StructField("province",      StringType()),
    StructField("item",          StringType()),
    StructField("quantity",      IntegerType()),
])

df_relief = (
    spark.read
    .schema(relief_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/relief.json")
    .withColumn("report_date", F.to_date("report_date", "dd MMMM yyyy"))
)

write_to_redshift(df_relief, "ndma_relief")
print(f"ndma_relief: {df_relief.count()} rows loaded")

# ----------------------------------------------------------
# RESCUE
# ----------------------------------------------------------

rescue_schema = StructType([
    StructField("report_number",     StringType()),
    StructField("report_date",       StringType()),
    StructField("province",          StringType()),
    StructField("rescue_operations", IntegerType()),
    StructField("persons_rescued",   IntegerType()),
])

df_rescue = (
    spark.read
    .schema(rescue_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/rescue.json")
    .withColumn("report_date", F.to_date("report_date", "dd MMMM yyyy"))
)

write_to_redshift(df_rescue, "ndma_rescue")
print(f"ndma_rescue: {df_rescue.count()} rows loaded")

job.commit()
