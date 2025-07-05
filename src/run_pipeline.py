#!/usr/bin/env python3
"""
Pipeline Runner

This script orchestrates the entire ETL pipeline, calling each component
in the correct order with appropriate parameters.
"""

import os
import sys
import logging
import argparse
import subprocess
import datetime
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run the data pipeline")
    parser.add_argument(
        "--stage", 
        choices=["scrape", "validate_raw", "transform", "validate_silver", "dbt", "all"],
        default="all",
        help="Pipeline stage to run"
    )
    parser.add_argument(
        "--date", 
        default=datetime.datetime.now().strftime("%Y-%m-%d"),
        help="Processing date (YYYY-MM-DD)"
    )
    return parser.parse_args()

def run_command(cmd, env=None):
    """Run a shell command and log its output."""
    logger.info(f"Running command: {' '.join(cmd)}")
    
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    
    try:
        process = subprocess.run(
            cmd,
            env=merged_env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        logger.info(process.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with code {e.returncode}")
        logger.error(e.stdout)
        logger.error(e.stderr)
        return False

def run_scraper(date):
    """Run the web scraper component."""
    logger.info("Starting web scraping process")
    
    cmd = ["python", os.path.join(PROJECT_ROOT, "src", "scraper.py")]
    env = {
        "OUTPUT_DIR": os.path.join(DATA_DIR, "raw"),
        "S3_BUCKET": S3_BUCKET,
        "USE_S3": str(USE_S3)
    }
    
    success = run_command(cmd, env)
    if not success:
        logger.error("Scraping failed")
        return None
    
    filename = f"products_{date}.json"
    file_path = os.path.join(DATA_DIR, "raw", filename)
    s3_key = f"raw/{filename}"
    
    logger.info(f"Scraping completed successfully: {file_path}")
    return {"local_path": file_path, "s3_key": s3_key}

def run_validation(layer, file_info):
    """Run Great Expectations validation for a data layer."""
    logger.info(f"Starting {layer} data validation")
    
    if USE_S3:
        file_path = file_info["s3_key"]
    else:
        file_path = file_info["local_path"]
    
    cmd = [
        "python", 
        os.path.join(PROJECT_ROOT, "src", "validate.py"),
        file_path
    ]
    env = {
        "GE_DIR": os.path.join(PROJECT_ROOT, "great_expectations"),
        "S3_BUCKET": S3_BUCKET,
        "USE_S3": str(USE_S3),
        "DATA_LAYER": layer
    }
    
    success = run_command(cmd, env)
    if not success:
        logger.error(f"{layer.capitalize()} data validation failed")
        return False
    
    logger.info(f"{layer.capitalize()} data validation completed successfully")
    return True

def run_transformation(raw_file_info, date):
    """Run the PySpark transformation component."""
    logger.info("Starting data transformation process")
    
    if USE_S3:
        input_path = raw_file_info["s3_key"]
        output_path = f"silver/products/dt={date}"
    else:
        input_path = raw_file_info["local_path"]
        output_path = os.path.join(DATA_DIR, "silver", f"products/dt={date}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    cmd = ["spark-submit", os.path.join(PROJECT_ROOT, "src", "transform.py")]
    env = {
        "INPUT_PATH": input_path,
        "OUTPUT_PATH": output_path,
        "S3_BUCKET": S3_BUCKET,
        "USE_S3": str(USE_S3)
    }
    
    success = run_command(cmd, env)
    if not success:
        logger.error("Transformation failed")
        return None
    
    logger.info(f"Transformation completed successfully: {output_path}")
    return {"local_path": output_path, "s3_key": output_path}

def run_dbt():
    """Run dbt models to transform silver to gold."""
    logger.info("Starting dbt model execution")
    
    cmd = [
        "dbt", "run",
        "--project-dir", os.path.join(PROJECT_ROOT, "dbt_project"),
        "--profiles-dir", os.path.join(PROJECT_ROOT, "dbt_project")
    ]
    
    success = run_command(cmd)
    if not success:
        logger.error("dbt model execution failed")
        return False
    
    logger.info("dbt model execution completed successfully")
    return True

def main():
    """Main function to run the pipeline."""
    args = parse_args()
    stage = args.stage
    date = args.date
    
    logger.info(f"Starting pipeline at stage '{stage}' for date {date}")
    
    # Create data directories if needed
    os.makedirs(os.path.join(DATA_DIR, "raw"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "silver"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "gold"), exist_ok=True)
    
    # Run appropriate stages
    if stage in ["scrape", "all"]:
        raw_file_info = run_scraper(date)
        if not raw_file_info:
            sys.exit(1)
    else:
        # If not running scraper, assume raw data exists
        filename = f"products_{date}.json"
        raw_file_info = {
            "local_path": os.path.join(DATA_DIR, "raw", filename),
            "s3_key": f"raw/{filename}"
        }
    
    if stage in ["validate_raw", "all"]:
        if not run_validation("raw", raw_file_info):
            sys.exit(1)
    
    if stage in ["transform", "all"]:
        silver_file_info = run_transformation(raw_file_info, date)
        if not silver_file_info:
            sys.exit(1)
    else:
        # If not running transform, assume silver data exists
        silver_path = f"silver/products/dt={date}"
        silver_file_info = {
            "local_path": os.path.join(DATA_DIR, silver_path),
            "s3_key": silver_path
        }
    
    if stage in ["validate_silver", "all"]:
        if not run_validation("silver", silver_file_info):
            sys.exit(1)
    
    if stage in ["dbt", "all"]:
        if not run_dbt():
            sys.exit(1)
    
    logger.info(f"Pipeline completed successfully at stage '{stage}' for date {date}")

if __name__ == "__main__":
    main()
