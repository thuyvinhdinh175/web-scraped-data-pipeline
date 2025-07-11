#!/usr/bin/env python3
"""
PySpark Transformation Script

This script transforms raw product data into cleaned and structured format
for the silver data layer using Apache Spark.
"""

import os
import sys
import logging
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, explode, from_json, lit, when, current_timestamp,
    to_timestamp, regexp_replace, split, trim, lower
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, 
    BooleanType, ArrayType, IntegerType, TimestampType
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
INPUT_PATH = os.environ.get("INPUT_PATH")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH")
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"
SPARK_MASTER = os.environ.get("SPARK_MASTER", "spark://spark-master:7077")

# Define schema for the raw product data
product_schema = StructType([
    StructField("url", StringType(), False),
    StructField("scrape_date", StringType(), False),
    StructField("product_id", StringType(), False),
    StructField("title", StringType(), True),
    StructField("name", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("description", StringType(), True),
    StructField("rating", DoubleType(), True),
    StructField("num_reviews", IntegerType(), True),
    StructField("in_stock", BooleanType(), True),
    StructField("brand", StringType(), True),
    StructField("categories", ArrayType(StringType()), True),
    StructField("image_urls", ArrayType(StringType()), True),
    StructField("search_term", StringType(), True)
])

def initialize_spark():
    """Initialize and return a Spark session."""
    spark = (
        SparkSession.builder
        .appName("ProductDataTransformation")
        .master(SPARK_MASTER)  # Explicitly set master URL
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.hadoop.mapreduce.fileoutputcommitter.algorithm.version", "2")
        .config("spark.eventLog.enabled", "true")
        .config("spark.eventLog.dir", "/tmp/spark-events")
        .getOrCreate()
    )
    
    logger.info("Spark session initialized")
    return spark

def load_data(spark, input_path):
    """Load the raw JSON data from the specified path."""
    if USE_S3:
        if not input_path.startswith("s3://"):
            input_path = f"s3a://{S3_BUCKET}/{input_path}"
    
    logger.info(f"Loading data from {input_path}")
    
    # Read the raw JSON file
    df = spark.read.option("multiline", "true").json(input_path, schema=product_schema)
    
    logger.info(f"Loaded {df.count()} records")
    return df

def transform_data(df):
    """Apply transformations to clean and prepare the data."""
    logger.info("Applying transformations")
    
    # Handle the case where we might have either 'name' or 'title' populated
    df = df.withColumn("name", 
                      when(col("name").isNull(), col("title"))
                      .otherwise(col("name")))
    
    # Add timestamp and processing metadata
    df = df.withColumn("processed_at", current_timestamp())
    df = df.withColumn("data_source", lit("web_scraper"))
    
    # Convert string dates to proper timestamps
    df = df.withColumn("scrape_timestamp", to_timestamp(col("scrape_date")))
    
    # Clean up product name (remove extra spaces, special chars)
    df = df.withColumn("name", regexp_replace(trim(col("name")), "\\s+", " "))
    
    # Set default values for missing fields
    df = df.withColumn("brand", 
                      when(col("brand").isNull(), "Unknown")
                      .otherwise(lower(trim(col("brand")))))
    
    # Handle missing price
    df = df.withColumn("price", 
                      when(col("price").isNull(), 0.0)
                      .otherwise(col("price")))
    
    # Handle missing ratings
    df = df.withColumn("rating", 
                      when(col("rating").isNull(), 0.0)
                      .otherwise(col("rating")))
    
    # Handle missing review counts
    df = df.withColumn("num_reviews", 
                      when(col("num_reviews").isNull(), 0)
                      .otherwise(col("num_reviews")))
    
    # Handle missing in_stock
    df = df.withColumn("in_stock", 
                      when(col("in_stock").isNull(), False)
                      .otherwise(col("in_stock")))
    
    # Handle missing categories
    df = df.withColumn("categories", 
                      when(col("categories").isNull(), 
                           when(col("search_term").isNotNull(),
                                split(col("search_term"), " ").getItem(0))
                           .otherwise(array(lit("Uncategorized"))))
                      .otherwise(col("categories")))
    
    # Explode categories into separate rows for better analytics
    exploded_df = df.withColumn("category", explode(col("categories")))
    
    # Handle missing values
    cleaned_df = exploded_df.fillna({
        "description": "No description available",
        "category": "Uncategorized"
    })
    
    # Deduplicate based on product_id and category
    deduplicated_df = cleaned_df.dropDuplicates(["product_id", "category"])
    
    logger.info(f"Transformation complete. {deduplicated_df.count()} records after transformation")
    return deduplicated_df

def save_data(df, output_path):
    """Save the transformed data to the specified path."""
    if USE_S3:
        if not output_path.startswith("s3://"):
            output_path = f"s3a://{S3_BUCKET}/{output_path}"
    
    logger.info(f"Saving transformed data to {output_path}")
    
    # Save as parquet, partitioned by brand and scrape date
    partition_date = datetime.now().strftime("%Y-%m-%d")
    
    (df.write
     .partitionBy("brand", "category")
     .mode("overwrite")
     .parquet(output_path))
    
    logger.info("Data saved successfully")

def main():
    """Main function to orchestrate the transformation process."""
    # Get input and output paths
    if not INPUT_PATH or not OUTPUT_PATH:
        logger.error("INPUT_PATH and OUTPUT_PATH environment variables must be set")
        sys.exit(1)
    
    # Initialize Spark
    spark = initialize_spark()
    
    try:
        # Load data
        df = load_data(spark, INPUT_PATH)
        
        # Transform data
        transformed_df = transform_data(df)
        
        # Save data
        save_data(transformed_df, OUTPUT_PATH)
        
        logger.info("Transformation job completed successfully")
    except Exception as e:
        logger.error(f"Error in transformation job: {e}")
        sys.exit(1)
    finally:
        spark.stop()

if __name__ == "__main__":
    main()
