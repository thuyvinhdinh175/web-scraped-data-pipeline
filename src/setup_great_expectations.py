#!/usr/bin/env python3
"""
Great Expectations Setup Script

This script initializes the Great Expectations configuration, 
datasources, and expectation suites for the data pipeline.
"""

import os
import sys
import logging
import json
import great_expectations as ge
from great_expectations.core.batch import BatchRequest
from great_expectations.checkpoint import SimpleCheckpoint
from great_expectations.data_context.types.base import (
    DataContextConfig, FilesystemStoreBackendDefaults
)
from great_expectations.data_context import BaseDataContext

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
GE_DIR = os.environ.get("GE_DIR", "./great_expectations")
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
LOCAL_DATA_DIR = os.environ.get("LOCAL_DATA_DIR", "./data")

def create_data_context_config():
    """Create Great Expectations data context configuration."""
    return DataContextConfig(
        store_backend_defaults=FilesystemStoreBackendDefaults(root_directory=GE_DIR),
        datasources={
            "local_data": {
                "class_name": "Datasource",
                "execution_engine": {
                    "class_name": "PandasExecutionEngine",
                },
                "data_connectors": {
                    "default_inferred_data_connector_name": {
                        "class_name": "InferredAssetFilesystemDataConnector",
                        "base_directory": LOCAL_DATA_DIR,
                        "default_regex": {
                            "group_names": ["data_asset_name"],
                            "pattern": "(.*)\\.json",
                        },
                    },
                },
            },
            "s3_data": {
                "class_name": "Datasource",
                "execution_engine": {
                    "class_name": "PandasExecutionEngine",
                },
                "data_connectors": {
                    "default_inferred_data_connector_name": {
                        "class_name": "InferredAssetS3DataConnector",
                        "bucket": S3_BUCKET,
                        "prefix": "",
                        "default_regex": {
                            "group_names": ["data_asset_name"],
                            "pattern": "(.*)\\.json",
                        },
                    },
                },
            },
        },
    )

def setup_ge_context():
    """Initialize and configure the Great Expectations context."""
    os.makedirs(GE_DIR, exist_ok=True)
    
    if not os.path.exists(os.path.join(GE_DIR, "great_expectations.yml")):
        logger.info("Initializing Great Expectations configuration")
        context_config = create_data_context_config()
        context = BaseDataContext(project_config=context_config)
        context.build_data_docs()
        return context
    else:
        logger.info("Loading existing Great Expectations configuration")
        return ge.get_context()

def create_expectation_suite(context, suite_name):
    """Create an expectation suite if it doesn't already exist."""
    try:
        suite = context.get_expectation_suite(suite_name)
        logger.info(f"Expectation suite '{suite_name}' already exists")
        return suite
    except:
        logger.info(f"Creating expectation suite '{suite_name}'")
        return context.create_expectation_suite(suite_name)

def load_expectation_suite_from_json(context, suite_name, json_path):
    """Load an expectation suite from a JSON file."""
    try:
        with open(json_path, 'r') as f:
            suite_config = json.load(f)
        
        # Create the suite if it doesn't exist
        if not context.list_expectation_suites(suite_name=suite_name):
            context.create_expectation_suite(suite_name)
        
        # Load expectations into the suite
        suite = context.get_expectation_suite(suite_name)
        for expectation in suite_config.get('expectations', []):
            suite.add_expectation(expectation)
        
        # Save the updated suite
        context.save_expectation_suite(suite)
        logger.info(f"Loaded expectation suite '{suite_name}' from {json_path}")
        return suite
    except Exception as e:
        logger.error(f"Error loading expectation suite from {json_path}: {e}")
        return None

def setup_validation_suites(context):
    """Set up all validation suites for the pipeline."""
    # Raw data validation suites
    raw_suites = [
        "raw_product_suite",
        "raw_product_completeness_suite",
        "raw_product_uniqueness_suite", 
        "raw_product_consistency_suite"
    ]
    
    for suite_name in raw_suites:
        json_path = os.path.join(GE_DIR, "expectations", "raw", f"{suite_name}.json")
        if os.path.exists(json_path):
            load_expectation_suite_from_json(context, suite_name, json_path)
        else:
            create_expectation_suite(context, suite_name)
    
    # Silver data validation suites
    silver_suites = [
        "silver_product_suite",
        "silver_product_completeness_suite",
        "silver_product_consistency_suite"
    ]
    
    for suite_name in silver_suites:
        json_path = os.path.join(GE_DIR, "expectations", "silver", f"{suite_name}.json")
        if os.path.exists(json_path):
            load_expectation_suite_from_json(context, suite_name, json_path)
        else:
            create_expectation_suite(context, suite_name)
    
    # Gold data validation suites
    gold_suites = [
        "gold_product_suite"
    ]
    
    for suite_name in gold_suites:
        json_path = os.path.join(GE_DIR, "expectations", "gold", f"{suite_name}.json")
        if os.path.exists(json_path):
            load_expectation_suite_from_json(context, suite_name, json_path)
        else:
            create_expectation_suite(context, suite_name)

def main():
    """Main function to set up Great Expectations."""
    logger.info("Setting up Great Expectations")
    
    # Set up GE context
    context = setup_ge_context()
    
    # Set up validation suites
    setup_validation_suites(context)
    
    # Build data docs
    context.build_data_docs()
    
    logger.info("Great Expectations setup complete")
    logger.info(f"Data docs available at: {context.get_docs_sites_urls()[0]}")

if __name__ == "__main__":
    main()
