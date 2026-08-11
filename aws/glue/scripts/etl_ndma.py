import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import *

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

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

job = Job(glueContext)
job.init(args["JOB_NAME"], args)

BUCKET = args["S3_BUCKET"]

RS_PROPS = {
    "url": args["REDSHIFT_URL"],
    "user": args["REDSHIFT_USER"],
    "password": args["REDSHIFT_PASSWORD"],
    "tempdir": args["REDSHIFT_TMP_DIR"],
}


def write_to_redshift(df, table):
    glueContext.write_dynamic_frame.from_options(
        frame=glueContext.create_dynamic_frame.from_dataframe(df, glueContext),
        connection_type="redshift",
        connection_options={
            **RS_PROPS,
            "dbtable": table,
            "preactions": f"DELETE FROM {table}",
        },
    )


# ==========================================================
# CASUALTIES
# ==========================================================

casualties_schema = StructType([
    StructField("report_number", StringType(), True),
    StructField("report_date", StringType(), True),
    StructField("province", StringType(), True),
    StructField("deaths", StringType(), True),
    StructField("injured", StringType(), True),
])

df = (
    spark.read
    .schema(casualties_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/casualties.json")
)

df = (
    df.withColumn(
        "report_date",
        F.to_date("report_date", "d MMMM yyyy")
    )
    .withColumn(
        "deaths",
        F.regexp_replace(F.col("deaths"), "[^0-9]", "").cast("int")
    )
    .withColumn(
        "injured",
        F.regexp_replace(F.col("injured"), "[^0-9]", "").cast("int")
    )
)

write_to_redshift(df, "ndma_casualties")

print(f"Loaded ndma_casualties : {df.count()}")


# ==========================================================
# DAMAGE
# ==========================================================

damage_schema = StructType([
    StructField("report_number", StringType(), True),
    StructField("report_date", StringType(), True),
    StructField("province", StringType(), True),
    StructField("roads_km", StringType(), True),
    StructField("bridges", StringType(), True),
    StructField("houses_total", StringType(), True),
    StructField("livestock", StringType(), True),
])

df = (
    spark.read
    .schema(damage_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/damage.json")
)

df = (
    df.withColumn(
        "report_date",
        F.to_date("report_date", "d MMMM yyyy")
    )
    .withColumn(
        "roads_km",
        F.when(
            F.col("roads_km") == "-", None
        ).otherwise(
            F.col("roads_km").cast("double")
        )
    )
    .withColumn(
        "bridges",
        F.when(
            F.col("bridges") == "-", None
        ).otherwise(
            F.col("bridges").cast("int")
        )
    )
    .withColumn(
        "houses_total",
        F.col("houses_total").cast("int")
    )
    .withColumn(
        "livestock",
        F.col("livestock").cast("int")
    )
)

write_to_redshift(df, "ndma_damage")

print(f"Loaded ndma_damage : {df.count()}")


# ==========================================================
# RELIEF
# ==========================================================

relief_schema = StructType([
    StructField("report_number", StringType(), True),
    StructField("report_date", StringType(), True),
    StructField("province", StringType(), True),
    StructField("item", StringType(), True),
    StructField("quantity", IntegerType(), True),
])

df = (
    spark.read
    .schema(relief_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/relief.json")
)

df = df.withColumn(
    "report_date",
    F.to_date("report_date", "d MMMM yyyy")
)

write_to_redshift(df, "ndma_relief")

print(f"Loaded ndma_relief : {df.count()}")


# ==========================================================
# RESCUE
# ==========================================================

rescue_schema = StructType([
    StructField("report_number", StringType(), True),
    StructField("report_date", StringType(), True),
    StructField("province", StringType(), True),
    StructField("operations", StringType(), True),
    StructField("rescued", StringType(), True),
])

df = (
    spark.read
    .schema(rescue_schema)
    .json(f"s3://{BUCKET}/analytics/ndma/rescue.json")
)

df = (
    df.withColumn(
        "report_date",
        F.to_date("report_date", "d MMMM yyyy")
    )
    .withColumn(
        "rescue_operations",
        F.regexp_replace(
            F.col("operations"),
            "[^0-9]",
            ""
        ).cast("int")
    )
    .withColumn(
        "persons_rescued",
        F.regexp_replace(
            F.col("rescued"),
            "[^0-9]",
            ""
        ).cast("int")
    )
    .drop(
        "operations",
        "rescued"
    )
)

write_to_redshift(df, "ndma_rescue")

print(f"Loaded ndma_rescue : {df.count()}")

job.commit()