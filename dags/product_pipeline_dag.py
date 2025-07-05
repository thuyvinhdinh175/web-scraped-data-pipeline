"""
Product Data Pipeline DAG

This DAG orchestrates the end-to-end data pipeline that:
1. Scrapes product data from an e-commerce website
2. Validates the raw data against schema contracts
3. Transforms the data using PySpark
4. Validates the transformed data
5. Models the data using dbt
6. Updates the Streamlit dashboard
7. Monitors data quality metrics
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator
from airflow.utils.task_group import TaskGroup
from airflow.exceptions import AirflowException

# Default arguments
default_args = {
    'owner': 'data_engineer',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# DAG definition
dag = DAG(
    'product_data_pipeline',
    default_args=default_args,
    description='End-to-end data pipeline for web-scraped product data',
    schedule_interval='0 1 * * *',  # Run daily at 1 AM
    start_date=datetime(2023, 1, 1),
    catchup=False,
    tags=['product', 'e-commerce', 'web-scraping'],
)

# Project base path (will be mounted in Docker container)
PROJECT_PATH = '/opt/airflow/project'

# Variables for file paths
date = "{{ ds }}"  # Execution date in YYYY-MM-DD format
raw_file = f"products_{date}.json"
raw_file_path = f"{PROJECT_PATH}/data/raw/{raw_file}"
s3_raw_key = f"raw/{raw_file}"
s3_silver_path = f"silver/products/dt={date}"
local_silver_path = f"{PROJECT_PATH}/data/silver/products/dt={date}"

# Tasks
with dag:
    # 1. Web Scraping Task
    scrape_task = BashOperator(
        task_id='scrape_products',
        bash_command=f'cd {PROJECT_PATH} && python src/scraper.py',
        env={
            'OUTPUT_DIR': f'{PROJECT_PATH}/data/raw',
            'S3_BUCKET': '{{ var.value.s3_bucket }}',
            'USE_S3': '{{ var.value.use_s3 }}'
        },
    )
    
    # 2. Upload to S3 (only if USE_S3 is False)
    upload_to_s3 = LocalFilesystemToS3Operator(
        task_id='upload_raw_to_s3',
        filename=raw_file_path,
        dest_key=s3_raw_key,
        dest_bucket='{{ var.value.s3_bucket }}',
        aws_conn_id='aws_default',
        replace=True,
    )
    
    # 3. Raw Data Validation with Data Quality Monitoring
    validate_raw = BashOperator(
        task_id='validate_raw_data',
        bash_command=f'cd {PROJECT_PATH} && python src/validate.py {s3_raw_key}',
        env={
            'GE_DIR': f'{PROJECT_PATH}/great_expectations',
            'S3_BUCKET': '{{ var.value.s3_bucket }}',
            'USE_S3': 'True',  # Always use S3 path in Airflow
            'DATA_LAYER': 'raw',
            'CRITICAL_FIELDS': 'product_id,name,price,brand,in_stock',
            'FAIL_ON_ERROR': 'True',
            'SLACK_ENABLED': '{{ var.value.slack_enabled }}',
            'EMAIL_ENABLED': '{{ var.value.email_enabled }}',
            'METRICS_DIR': f'{PROJECT_PATH}/data/metrics'
        },
    )
    
    # 4. Transform Raw to Silver using PySpark
    transform_task = BashOperator(
        task_id='transform_to_silver',
        bash_command=f'cd {PROJECT_PATH} && spark-submit src/transform.py',
        env={
            'INPUT_PATH': s3_raw_key,
            'OUTPUT_PATH': s3_silver_path,
            'S3_BUCKET': '{{ var.value.s3_bucket }}',
            'USE_S3': 'True'  # Always use S3 path in Airflow
        },
    )
    
    # 5. Wait for silver data to be available
    wait_for_silver = S3KeySensor(
        task_id='wait_for_silver_data',
        bucket_key=f's3://{{ var.value.s3_bucket }}/{s3_silver_path}/_SUCCESS',
        bucket_name=None,  # bucket_key contains full S3 URI
        aws_conn_id='aws_default',
        timeout=60 * 60,  # 1 hour
        poke_interval=60,  # 1 minute
    )
    
    # 6. Silver Data Validation with Data Quality Monitoring
    validate_silver = BashOperator(
        task_id='validate_silver_data',
        bash_command=f'cd {PROJECT_PATH} && python src/validate.py {s3_silver_path}',
        env={
            'GE_DIR': f'{PROJECT_PATH}/great_expectations',
            'S3_BUCKET': '{{ var.value.s3_bucket }}',
            'USE_S3': 'True',
            'DATA_LAYER': 'silver',
            'CRITICAL_FIELDS': 'product_id,name,price,brand,in_stock,category',
            'FAIL_ON_ERROR': 'True',
            'SLACK_ENABLED': '{{ var.value.slack_enabled }}',
            'EMAIL_ENABLED': '{{ var.value.email_enabled }}',
            'METRICS_DIR': f'{PROJECT_PATH}/data/metrics'
        },
    )
    
    # 7. Run dbt models (Silver to Gold)
    with TaskGroup(group_id='dbt_models') as dbt_group:
        # Run dbt
        dbt_run = BashOperator(
            task_id='dbt_run',
            bash_command=f'cd {PROJECT_PATH} && dbt run --project-dir dbt_project --profiles-dir dbt_project',
        )
        
        # Test dbt models
        dbt_test = BashOperator(
            task_id='dbt_test',
            bash_command=f'cd {PROJECT_PATH} && dbt test --project-dir dbt_project --profiles-dir dbt_project',
        )
        
        # Generate dbt docs
        dbt_docs = BashOperator(
            task_id='dbt_docs',
            bash_command=f'cd {PROJECT_PATH} && dbt docs generate --project-dir dbt_project --profiles-dir dbt_project',
        )
        
        dbt_run >> dbt_test >> dbt_docs
    
    # 8. Refresh Product Dashboard
    refresh_product_dashboard = BashOperator(
        task_id='refresh_product_dashboard',
        bash_command=f'cd {PROJECT_PATH} && touch streamlit_app/.refresh_trigger',
    )
    
    # 9. Refresh Data Quality Dashboard
    refresh_dq_dashboard = BashOperator(
        task_id='refresh_dq_dashboard',
        bash_command=f'cd {PROJECT_PATH} && streamlit run streamlit_app/dq_dashboard.py --server.port=8502 --server.headless=true &',
    )
    
    # 10. Gold Layer Validation and Monitoring
    validate_gold = BashOperator(
        task_id='validate_gold_data',
        bash_command=f'cd {PROJECT_PATH} && python src/validate.py gold/dim_product',
        env={
            'GE_DIR': f'{PROJECT_PATH}/great_expectations',
            'S3_BUCKET': '{{ var.value.s3_bucket }}',
            'USE_S3': 'True',
            'DATA_LAYER': 'gold',
            'CRITICAL_FIELDS': 'product_id,product_name,brand,rating,is_in_stock',
            'FAIL_ON_ERROR': 'False',  # Don't fail the pipeline if gold validation fails
            'SLACK_ENABLED': '{{ var.value.slack_enabled }}',
            'EMAIL_ENABLED': '{{ var.value.email_enabled }}',
            'METRICS_DIR': f'{PROJECT_PATH}/data/metrics'
        },
    )
    
    # 11. Generate Data Quality Report
    generate_dq_report = BashOperator(
        task_id='generate_dq_report',
        bash_command=f'''
        cd {PROJECT_PATH} && 
        python -c "
import json
import glob
import os
import datetime

# Find the latest metrics files
metrics_dir = './data/metrics'
today = datetime.datetime.now().strftime('%Y-%m-%d')
report = {{'date': today, 'metrics': {{}}}}

for metric_type in ['validation_failure', 'null_counts', 'schema_drift', 'data_arrival', 'record_count']:
    latest_file = None
    latest_time = None
    
    for file in glob.glob(f'{metrics_dir}/{metric_type}/*.json'):
        file_time = os.path.getmtime(file)
        if latest_time is None or file_time > latest_time:
            latest_time = file_time
            latest_file = file
    
    if latest_file:
        with open(latest_file, 'r') as f:
            report['metrics'][metric_type] = json.load(f)

# Save the report
os.makedirs('./data/reports', exist_ok=True)
with open(f'./data/reports/dq_report_{today}.json', 'w') as f:
    json.dump(report, f, indent=2)

print(f'Data quality report generated at ./data/reports/dq_report_{today}.json')
        "
        ''',
    )
    
    # Set task dependencies
    scrape_task >> upload_to_s3 >> validate_raw >> transform_task >> wait_for_silver >> validate_silver >> dbt_group
    dbt_group >> [refresh_product_dashboard, validate_gold]
    validate_gold >> generate_dq_report >> refresh_dq_dashboard
