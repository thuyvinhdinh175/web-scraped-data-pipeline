#!/usr/bin/env python3
"""
Data Validation with Great Expectations

This script runs Great Expectations validations against the raw and transformed data
to ensure data quality and adherence to schema contracts. It also tracks data quality
metrics for monitoring and alerting.
"""

import os
import sys
import logging
import json
import datetime
import pandas as pd
import great_expectations as ge
from great_expectations.datasource.types import S3BatchKwargs
from great_expectations.core.batch import BatchRequest
from great_expectations.checkpoint import SimpleCheckpoint
from airflow.exceptions import AirflowException

# Import monitoring metrics module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.monitoring.metrics import (
    calculate_schema_failure_rate, 
    count_nulls_in_critical_fields,
    detect_schema_drift,
    check_data_arrival_delay,
    detect_record_count_anomaly,
    get_historical_record_counts,
    save_metrics,
    send_slack_alert,
    send_email_alert,
    handle_validation_failure
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
GE_DIR = os.environ.get("GE_DIR", "../great_expectations")
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"
DATA_LAYER = os.environ.get("DATA_LAYER", "raw")  # raw, silver, or gold
EXPECTATION_SUITE = f"{DATA_LAYER}_product_suite"
CRITICAL_FIELDS = os.environ.get("CRITICAL_FIELDS", "product_id,name,price,brand").split(",")
FAIL_ON_ERROR = os.environ.get("FAIL_ON_ERROR", "True").lower() == "true"
SLACK_ENABLED = os.environ.get("SLACK_ENABLED", "False").lower() == "true"
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "False").lower() == "true"

def get_context():
    """Initialize and return the Great Expectations context."""
    context = ge.get_context()
    logger.info(f"Initialized Great Expectations context from {GE_DIR}")
    return context

def validate_local_data(context, data_path):
    """Validate a local JSON data file against expectations."""
    batch_request = BatchRequest(
        datasource_name="local_data",
        data_connector_name="default_inferred_data_connector_name",
        data_asset_name=os.path.basename(data_path),
        batch_spec_passthrough={"reader_method": "read_json", "reader_options": {"lines": False}}
    )
    
    checkpoint = SimpleCheckpoint(
        name=f"{DATA_LAYER}_validation_checkpoint",
        run_name=f"{DATA_LAYER}_validation_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        expectation_suite_name=EXPECTATION_SUITE,
        batch_request=batch_request
    )
    
    checkpoint_result = checkpoint.run(context)
    logger.info(f"Validation completed with success: {checkpoint_result.success}")
    return checkpoint_result

def validate_s3_data(context, s3_key):
    """Validate a JSON data file in S3 against expectations."""
    batch_request = BatchRequest(
        datasource_name="s3_data",
        data_connector_name="default_inferred_data_connector_name",
        data_asset_name=os.path.basename(s3_key),
        batch_spec_passthrough={
            "s3": S3BatchKwargs(
                bucket=S3_BUCKET,
                key=s3_key,
                reader_method="read_json",
                reader_options={"lines": False}
            )
        }
    )
    
    checkpoint = SimpleCheckpoint(
        name=f"{DATA_LAYER}_validation_checkpoint",
        run_name=f"{DATA_LAYER}_validation_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        expectation_suite_name=EXPECTATION_SUITE,
        batch_request=batch_request
    )
    
    checkpoint_result = checkpoint.run(context)
    logger.info(f"Validation completed with success: {checkpoint_result.success}")
    return checkpoint_result

def load_data(data_path):
    """Load data from file for additional metrics calculation."""
    try:
        if USE_S3:
            import boto3
            s3_client = boto3.client('s3')
            
            # Extract bucket and key from file_path
            if data_path.startswith('s3://'):
                data_path = data_path[5:]
                if '/' in data_path:
                    bucket, key = data_path.split('/', 1)
                else:
                    bucket, key = data_path, ""
            else:
                bucket, key = S3_BUCKET, data_path
            
            # Get file from S3
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            data = json.loads(content)
        else:
            # Load from local file
            with open(data_path, 'r') as f:
                data = json.load(f)
        
        # Convert to DataFrame for easier processing
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame([data])
        else:
            df = pd.DataFrame()
            
        return df
    except Exception as e:
        logger.error(f"Error loading data from {data_path}: {e}")
        return pd.DataFrame()

def load_schema(schema_name):
    """Load JSON schema from file."""
    try:
        schema_path = f"../contracts/{schema_name}.json"
        with open(schema_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading schema {schema_name}: {e}")
        return {}

def calculate_additional_metrics(data_path, validation_result):
    """Calculate additional data quality metrics beyond GE validation."""
    metrics = {}
    
    try:
        # Load data
        df = load_data(data_path)
        if df.empty:
            logger.warning(f"Could not load data from {data_path} for metrics calculation")
            return metrics
        
        # 1. Count nulls in critical fields
        null_counts = count_nulls_in_critical_fields(df, CRITICAL_FIELDS)
        save_metrics(null_counts, data_path, "null_counts")
        metrics["null_counts"] = null_counts
        
        # 2. Check for schema drift
        if DATA_LAYER == "raw":
            # Load expected schema from contract
            schema = load_schema("product_schema")
            if schema:
                # Infer schema from data
                inferred_schema = {
                    "type": "object",
                    "properties": {}
                }
                
                for col in df.columns:
                    if df[col].dtype == 'object':
                        inferred_schema["properties"][col] = {"type": "string"}
                    elif pd.api.types.is_numeric_dtype(df[col]):
                        if pd.api.types.is_integer_dtype(df[col]):
                            inferred_schema["properties"][col] = {"type": "integer"}
                        else:
                            inferred_schema["properties"][col] = {"type": "number"}
                    elif pd.api.types.is_bool_dtype(df[col]):
                        inferred_schema["properties"][col] = {"type": "boolean"}
                    else:
                        inferred_schema["properties"][col] = {"type": "string"}
                
                # Detect drift
                drift_result = detect_schema_drift(schema, inferred_schema)
                save_metrics(drift_result, data_path, "schema_drift")
                metrics["schema_drift"] = drift_result
                
                # Alert on schema drift if detected
                if drift_result.get("has_drift", False):
                    drift_message = f"""
SCHEMA DRIFT ALERT: Schema changes detected in {data_path}
Added columns: {drift_result.get('added_columns', [])}
Removed columns: {drift_result.get('removed_columns', [])}
Modified columns: {drift_result.get('modified_columns', {})}
"""
                    if SLACK_ENABLED:
                        send_slack_alert(drift_message)
                    
                    if EMAIL_ENABLED:
                        send_email_alert(
                            subject=f"SCHEMA DRIFT ALERT: {os.path.basename(data_path)}",
                            message=drift_message
                        )
        
        # 3. Check data arrival delay
        arrival_status = check_data_arrival_delay(data_path)
        save_metrics(arrival_status, data_path, "data_arrival")
        metrics["data_arrival"] = arrival_status
        
        # Alert on data delay if detected
        if arrival_status.get("is_delayed", False):
            delay_message = f"""
DATA DELAY ALERT: Data in {data_path} is delayed
Last modified: {arrival_status.get('last_modified', 'unknown')}
Hours since update: {arrival_status.get('hours_since_update', 0):.2f} hours
"""
            if SLACK_ENABLED:
                send_slack_alert(delay_message)
            
            if EMAIL_ENABLED:
                send_email_alert(
                    subject=f"DATA DELAY ALERT: {os.path.basename(data_path)}",
                    message=delay_message
                )
        
        # 4. Check for record count anomalies
        record_count = len(df)
        historical_counts = get_historical_record_counts(data_path)
        anomaly_result = detect_record_count_anomaly(record_count, historical_counts)
        anomaly_result["current_count"] = record_count
        
        save_metrics(anomaly_result, data_path, "record_count")
        metrics["record_count"] = anomaly_result
        
        # Alert on record count anomaly if detected
        if anomaly_result.get("is_anomaly", False):
            anomaly_message = f"""
RECORD COUNT ANOMALY ALERT: Unusual record count in {data_path}
Current count: {record_count}
Average historical count: {anomaly_result.get('avg_historical_count', 0):.2f}
Percent change: {anomaly_result.get('percent_change', 0) * 100:.2f}%
"""
            if SLACK_ENABLED:
                send_slack_alert(anomaly_message)
            
            if EMAIL_ENABLED:
                send_email_alert(
                    subject=f"RECORD COUNT ANOMALY ALERT: {os.path.basename(data_path)}",
                    message=anomaly_message
                )
    
    except Exception as e:
        logger.error(f"Error calculating additional metrics: {e}")
    
    return metrics

def main():
    """Main function to run validations and calculate metrics."""
    # Get file path from arguments
    if len(sys.argv) < 2:
        logger.error("Please provide the file path to validate")
        sys.exit(1)
    
    file_path = sys.argv[1]
    logger.info(f"Starting validation for {file_path}")
    
    # Initialize GE context
    context = get_context()
    
    # Run validation
    if USE_S3:
        s3_key = file_path if file_path.startswith(f"{DATA_LAYER}/") else f"{DATA_LAYER}/{file_path}"
        result = validate_s3_data(context, s3_key)
        data_path = f"s3://{S3_BUCKET}/{s3_key}"
    else:
        result = validate_local_data(context, file_path)
        data_path = file_path
    
    # Calculate additional metrics regardless of validation result
    additional_metrics = calculate_additional_metrics(data_path, result)
    logger.info(f"Additional metrics calculated: {list(additional_metrics.keys())}")
    
    # Handle validation failure with appropriate alerts
    if not result.success:
        handle_validation_failure(
            result, 
            data_path, 
            raise_exception=FAIL_ON_ERROR
        )
    
    # Exit with appropriate status code
    sys.exit(0 if result.success else 1)

if __name__ == "__main__":
    main()
