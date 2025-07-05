#!/usr/bin/env python3
"""
Data Quality Monitoring and Metrics

This module calculates and tracks data quality metrics for monitoring
pipeline health and data reliability.
"""

import os
import json
import logging
import datetime
import pandas as pd
import numpy as np
import boto3
from botocore.exceptions import ClientError
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"
METRICS_DIR = os.environ.get("METRICS_DIR", "../data/metrics")
SLACK_ENABLED = os.environ.get("SLACK_ENABLED", "False").lower() == "true"
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "False").lower() == "true"
ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "0.05"))  # 5% failure threshold

def calculate_schema_failure_rate(validation_result):
    """
    Calculate percentage of rows that fail schema checks.
    
    Args:
        validation_result: Great Expectations validation result object
        
    Returns:
        float: Percentage of rows that failed validation (0.0 to 1.0)
    """
    try:
        # Extract total rows from the validation result
        total_rows = validation_result.meta.get("batch_spec", {}).get("batch_data", {}).get("row_count", 0)
        if total_rows == 0:
            return 0.0
        
        # Count failed rows from expectation results
        failed_rows = 0
        for expectation_result in validation_result.results:
            if not expectation_result.success:
                # Get the count of unexpected records
                unexpected_count = expectation_result.result.get("unexpected_count", 0)
                failed_rows = max(failed_rows, unexpected_count)
        
        return failed_rows / total_rows
    except Exception as e:
        logger.error(f"Error calculating schema failure rate: {e}")
        return 0.0

def count_nulls_in_critical_fields(df, critical_fields):
    """
    Count nulls in specified critical fields.
    
    Args:
        df: Pandas DataFrame or Spark DataFrame
        critical_fields: List of column names considered critical
        
    Returns:
        dict: Dictionary with column names as keys and null counts as values
    """
    null_counts = {}
    
    try:
        # For Pandas DataFrame
        if isinstance(df, pd.DataFrame):
            for field in critical_fields:
                if field in df.columns:
                    null_counts[field] = df[field].isnull().sum()
        # For Spark DataFrame
        else:
            for field in critical_fields:
                if field in df.columns:
                    null_counts[field] = df.filter(df[field].isNull()).count()
    except Exception as e:
        logger.error(f"Error counting nulls in critical fields: {e}")
    
    return null_counts

def detect_schema_drift(baseline_schema, current_schema):
    """
    Detect schema changes between baseline and current schema.
    
    Args:
        baseline_schema: Dictionary or JSON schema defining the baseline
        current_schema: Dictionary or JSON schema of the current data
        
    Returns:
        dict: Dictionary with added, removed, and modified columns
    """
    # Convert to dictionaries if they are strings
    if isinstance(baseline_schema, str):
        baseline_schema = json.loads(baseline_schema)
    if isinstance(current_schema, str):
        current_schema = json.loads(current_schema)
    
    # Extract properties from schema
    baseline_properties = baseline_schema.get("properties", {})
    current_properties = current_schema.get("properties", {})
    
    # Get column names
    baseline_columns = set(baseline_properties.keys())
    current_columns = set(current_properties.keys())
    
    # Find differences
    added_columns = current_columns - baseline_columns
    removed_columns = baseline_columns - current_columns
    
    # Check for type changes in common columns
    modified_columns = {}
    for col in baseline_columns.intersection(current_columns):
        baseline_type = baseline_properties[col].get("type")
        current_type = current_properties[col].get("type")
        
        if baseline_type != current_type:
            modified_columns[col] = {
                "from_type": baseline_type,
                "to_type": current_type
            }
    
    return {
        "added_columns": list(added_columns),
        "removed_columns": list(removed_columns),
        "modified_columns": modified_columns,
        "has_drift": len(added_columns) > 0 or len(removed_columns) > 0 or len(modified_columns) > 0
    }

def check_data_arrival_delay(file_path, max_delay_hours=24):
    """
    Check if data file is updated within the specified time window.
    
    Args:
        file_path: Path to the data file
        max_delay_hours: Maximum allowed delay in hours
        
    Returns:
        dict: Dictionary with delay status and hours since last update
    """
    try:
        if USE_S3:
            s3_client = boto3.client('s3')
            
            # Extract bucket and key from file_path
            if file_path.startswith('s3://'):
                file_path = file_path[5:]
            
            bucket, key = file_path.split('/', 1)
            
            # Get file metadata from S3
            response = s3_client.head_object(Bucket=bucket, Key=key)
            last_modified = response['LastModified']
        else:
            # Get file stats from local filesystem
            file_stats = os.stat(file_path)
            last_modified = datetime.datetime.fromtimestamp(file_stats.st_mtime, tz=datetime.timezone.utc)
        
        # Calculate hours since last modification
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        hours_since_update = (now - last_modified).total_seconds() / 3600
        
        return {
            "file_path": file_path,
            "last_modified": last_modified.isoformat(),
            "hours_since_update": hours_since_update,
            "is_delayed": hours_since_update > max_delay_hours
        }
    except Exception as e:
        logger.error(f"Error checking data arrival delay: {e}")
        return {
            "file_path": file_path,
            "error": str(e),
            "is_delayed": True  # Assume delayed if we can't check
        }

def detect_record_count_anomaly(current_count, historical_counts, threshold=0.5):
    """
    Detect if current record count has anomalous drop from historical patterns.
    
    Args:
        current_count: Current number of records
        historical_counts: List of historical record counts
        threshold: Threshold for significant drop (0.0 to 1.0)
        
    Returns:
        dict: Dictionary with anomaly status and percentage change
    """
    if not historical_counts:
        return {"is_anomaly": False, "percent_change": 0.0}
    
    # Calculate average of historical counts
    avg_historical = sum(historical_counts) / len(historical_counts)
    
    if avg_historical == 0:
        return {"is_anomaly": current_count == 0, "percent_change": 0.0}
    
    # Calculate percentage change
    percent_change = (current_count - avg_historical) / avg_historical
    
    # Check if drop exceeds threshold
    is_anomaly = percent_change < -threshold
    
    return {
        "is_anomaly": is_anomaly,
        "percent_change": percent_change,
        "current_count": current_count,
        "avg_historical_count": avg_historical
    }

def get_historical_record_counts(data_path, n_days=7):
    """
    Get historical record counts for the past n days.
    
    Args:
        data_path: Base path to the data directory
        n_days: Number of days to look back
        
    Returns:
        list: List of record counts for past n days
    """
    counts = []
    today = datetime.datetime.now()
    
    try:
        for i in range(1, n_days + 1):
            # Calculate date for historical data
            historical_date = today - datetime.timedelta(days=i)
            date_str = historical_date.strftime("%Y-%m-%d")
            
            # Construct path for historical data
            historical_path = data_path.replace(today.strftime("%Y-%m-%d"), date_str)
            
            if USE_S3:
                s3_client = boto3.client('s3')
                
                # Extract bucket and key from file_path
                if historical_path.startswith('s3://'):
                    historical_path = historical_path[5:]
                
                bucket, key = historical_path.split('/', 1)
                
                try:
                    # Use S3 Select to get record count
                    resp = s3_client.select_object_content(
                        Bucket=bucket,
                        Key=key,
                        Expression='SELECT count(*) FROM s3object',
                        ExpressionType='SQL',
                        InputSerialization={'JSON': {'Type': 'DOCUMENT'}},
                        OutputSerialization={'JSON': {}}
                    )
                    
                    for event in resp['Payload']:
                        if 'Records' in event:
                            record_count = json.loads(event['Records']['Payload'].decode('utf-8'))
                            counts.append(record_count['_1'])
                except Exception as e:
                    logger.warning(f"Could not get record count for {historical_path}: {e}")
            else:
                # For local filesystem
                if os.path.exists(historical_path):
                    # Read file and count records
                    with open(historical_path, 'r') as f:
                        data = json.load(f)
                        counts.append(len(data))
    except Exception as e:
        logger.error(f"Error getting historical record counts: {e}")
    
    return counts

def save_metrics(metrics, data_path, metrics_type):
    """
    Save calculated metrics to filesystem or S3.
    
    Args:
        metrics: Dictionary of metrics to save
        data_path: Path to the data being analyzed
        metrics_type: Type of metrics (e.g., 'schema_failure', 'null_counts')
        
    Returns:
        str: Path where metrics were saved
    """
    # Create metrics filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{metrics_type}_{timestamp}.json"
    
    # Add metadata to metrics
    metrics["metadata"] = {
        "timestamp": timestamp,
        "data_path": data_path,
        "metrics_type": metrics_type
    }
    
    if USE_S3:
        s3_client = boto3.client('s3')
        metrics_key = f"metrics/{metrics_type}/{filename}"
        
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=metrics_key,
                Body=json.dumps(metrics, indent=2),
                ContentType='application/json'
            )
            metrics_path = f"s3://{S3_BUCKET}/{metrics_key}"
        except Exception as e:
            logger.error(f"Error saving metrics to S3: {e}")
            metrics_path = None
    else:
        # Create local directory
        os.makedirs(os.path.join(METRICS_DIR, metrics_type), exist_ok=True)
        metrics_path = os.path.join(METRICS_DIR, metrics_type, filename)
        
        try:
            with open(metrics_path, 'w') as f:
                json.dump(metrics, indent=2, fp=f)
        except Exception as e:
            logger.error(f"Error saving metrics locally: {e}")
            metrics_path = None
    
    return metrics_path

def send_slack_alert(message, webhook_conn_id=None):
    """
    Send alert to Slack channel.
    
    Args:
        message: Message text to send
        webhook_conn_id: Airflow connection ID for Slack webhook
        
    Returns:
        bool: True if alert was sent successfully
    """
    if not SLACK_ENABLED:
        logger.info("Slack alerts disabled. Would have sent: " + message)
        return False
    
    try:
        # Get webhook URL from Airflow connection
        if webhook_conn_id:
            hook = BaseHook.get_connection(webhook_conn_id)
            slack_webhook_url = hook.password
        else:
            slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        
        if not slack_webhook_url:
            logger.error("Slack webhook URL not configured")
            return False
        
        # Initialize Slack client
        slack_client = WebClient(token=slack_webhook_url)
        
        # Send message
        response = slack_client.chat_postMessage(
            channel="#data-quality-alerts",
            text=message
        )
        
        return response["ok"]
    except Exception as e:
        logger.error(f"Error sending Slack alert: {e}")
        return False

def send_email_alert(subject, message, smtp_conn_id=None):
    """
    Send alert email.
    
    Args:
        subject: Email subject
        message: Email message body
        smtp_conn_id: Airflow connection ID for SMTP server
        
    Returns:
        bool: True if email was sent successfully
    """
    if not EMAIL_ENABLED:
        logger.info(f"Email alerts disabled. Would have sent: {subject} - {message}")
        return False
    
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Get SMTP settings from Airflow connection
        if smtp_conn_id:
            hook = BaseHook.get_connection(smtp_conn_id)
            smtp_server = hook.host
            smtp_port = hook.port
            smtp_user = hook.login
            smtp_password = hook.password
        else:
            smtp_server = os.environ.get("SMTP_SERVER")
            smtp_port = int(os.environ.get("SMTP_PORT", 587))
            smtp_user = os.environ.get("SMTP_USER")
            smtp_password = os.environ.get("SMTP_PASSWORD")
        
        recipient = os.environ.get("ALERT_EMAIL_RECIPIENT")
        
        if not all([smtp_server, smtp_port, smtp_user, smtp_password, recipient]):
            logger.error("SMTP settings not fully configured")
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        return True
    except Exception as e:
        logger.error(f"Error sending email alert: {e}")
        return False

def handle_validation_failure(validation_result, data_path, raise_exception=True):
    """
    Handle validation failure with appropriate alerts.
    
    Args:
        validation_result: Great Expectations validation result
        data_path: Path to the data being validated
        raise_exception: Whether to raise an AirflowException on failure
        
    Returns:
        bool: True if validation passed, False otherwise
    """
    if validation_result.success:
        return True
    
    # Calculate failure metrics
    failure_rate = calculate_schema_failure_rate(validation_result)
    
    # Create alert message
    message = f"""
DATA QUALITY ALERT: Validation failed for {data_path}
Failure rate: {failure_rate:.2%}
Time: {datetime.datetime.now().isoformat()}

Failed expectations:
"""
    
    # Add details of failed expectations
    for result in validation_result.results:
        if not result.success:
            expectation_type = result.expectation_config.expectation_type
            kwargs = result.expectation_config.kwargs
            message += f"- {expectation_type}: {kwargs}\n"
    
    # Send alerts
    if SLACK_ENABLED:
        send_slack_alert(message)
    
    if EMAIL_ENABLED:
        send_email_alert(
            subject=f"DATA QUALITY ALERT: Validation failed for {os.path.basename(data_path)}",
            message=message
        )
    
    # Log the failure
    logger.error(message)
    
    # Save failure metrics
    save_metrics(
        {
            "validation_success": False,
            "failure_rate": failure_rate,
            "failed_expectations": [
                {
                    "expectation_type": result.expectation_config.expectation_type,
                    "kwargs": result.expectation_config.kwargs
                }
                for result in validation_result.results if not result.success
            ]
        },
        data_path,
        "validation_failure"
    )
    
    # Raise exception if requested
    if raise_exception:
        raise AirflowException(f"Great Expectations validation failed with {failure_rate:.2%} failure rate")
    
    return False

def main():
    """Example usage of the monitoring functions."""
    logger.info("Data Quality Monitoring Module")
    logger.info("Use the functions in this module to track data quality metrics")
    logger.info("Example: handle_validation_failure(validation_result, data_path)")

if __name__ == "__main__":
    main()
