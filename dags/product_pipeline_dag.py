"""
Product Data Pipeline DAG

This DAG orchestrates the end-to-end data pipeline that:
1. Scrapes product data from e-commerce websites
2. Validates the raw data against schema contracts
3. Transforms the data using PySpark
4. Models the data using dbt
5. Updates the dashboard
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

# Default arguments
default_args = {
    'owner': 'data_engineer',
    'depends_on_past': False,
    'email_on_failure': False,
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

# Tasks
with dag:
    # 1. Web Scraping Task
    scrape_task = BashOperator(
        task_id='scrape_products',
        bash_command=f'cd {PROJECT_PATH} && python src/scraper.py',
        env={
            'OUTPUT_DIR': f'{PROJECT_PATH}/data/raw',
            'S3_BUCKET': 'web-scraped-data-pipeline',
            'USE_S3': 'false'
        },
    )
    
    # 2. Raw Data Validation
    validate_raw = BashOperator(
        task_id='validate_raw_data',
        bash_command=f'cd {PROJECT_PATH} && python src/validate.py',
        env={
            'GE_DIR': f'{PROJECT_PATH}/great_expectations',
            'S3_BUCKET': 'web-scraped-data-pipeline',
            'USE_S3': 'false',
            'DATA_LAYER': 'raw'
        },
    )
    
    # 3. Transform Raw to Silver using PySpark
    transform_task = BashOperator(
        task_id='transform_to_silver',
        bash_command=f'cd {PROJECT_PATH} && python src/transform.py',
        env={
            'INPUT_PATH': f'{PROJECT_PATH}/data/raw',
            'OUTPUT_PATH': f'{PROJECT_PATH}/data/silver',
            'S3_BUCKET': 'web-scraped-data-pipeline',
            'USE_S3': 'false'
        },
    )
    
    # 4. Silver Data Validation
    validate_silver = BashOperator(
        task_id='validate_silver_data',
        bash_command=f'cd {PROJECT_PATH} && python src/validate.py',
        env={
            'GE_DIR': f'{PROJECT_PATH}/great_expectations',
            'S3_BUCKET': 'web-scraped-data-pipeline',
            'USE_S3': 'false',
            'DATA_LAYER': 'silver'
        },
    )
    
    # 5. Run dbt models (Silver to Gold)
    with TaskGroup(group_id='dbt_models') as dbt_group:
        # Run dbt
        dbt_run = BashOperator(
            task_id='dbt_run',
            bash_command=f'cd {PROJECT_PATH}/dbt_project && dbt run',
        )
        
        # Test dbt models
        dbt_test = BashOperator(
            task_id='dbt_test',
            bash_command=f'cd {PROJECT_PATH}/dbt_project && dbt test',
        )
        
        dbt_run >> dbt_test
    
    # 6. Gold Layer Validation
    validate_gold = BashOperator(
        task_id='validate_gold_data',
        bash_command=f'cd {PROJECT_PATH} && python src/validate.py',
        env={
            'GE_DIR': f'{PROJECT_PATH}/great_expectations',
            'S3_BUCKET': 'web-scraped-data-pipeline',
            'USE_S3': 'false',
            'DATA_LAYER': 'gold'
        },
    )
    
    # 7. Success notification
    success_task = BashOperator(
        task_id='pipeline_success',
        bash_command='echo "Product data pipeline completed successfully!"',
    )
    
    # Set task dependencies
    scrape_task >> validate_raw >> transform_task >> validate_silver >> dbt_group >> validate_gold >> success_task
