# Data Quality Monitoring & Alerting

This project implements comprehensive data quality monitoring and alerting throughout the pipeline to ensure data reliability, correctness, and consistency.

## 🔍 Key Metrics Tracked

The monitoring system tracks these critical data quality dimensions:

### 1. Schema Validation
- **Metric**: Percentage of rows that fail schema checks
- **Implementation**: Great Expectations validation against JSON schema contracts
- **Alert Trigger**: Any validation failures

### 2. Null Values in Critical Fields
- **Metric**: Count of nulls in business-critical fields (product_id, name, price, brand, etc.)
- **Implementation**: Custom null counting function per field
- **Alert Trigger**: Nulls in required fields

### 3. Schema Drift Detection
- **Metric**: Detection of schema changes (added/removed/modified columns)
- **Implementation**: Comparison between expected schema and actual data schema
- **Alert Trigger**: Any schema changes detected

### 4. Data Arrival Delay
- **Metric**: Hours since last data update
- **Implementation**: Timestamp comparison with expected schedule
- **Alert Trigger**: File not updated in last 24 hours

### 5. Record Count Anomalies
- **Metric**: Unexpected changes in record volume
- **Implementation**: Statistical comparison with historical patterns
- **Alert Trigger**: 50% or greater drop/increase from historical average

## 🔔 Alerting System

Alerts are configured to notify of data quality issues through multiple channels:

### Airflow Integration
```python
if not validation_result["success"]:
    raise AirflowException("Great Expectations validation failed")
```

This configuration automatically:
- Fails the DAG if critical validation checks fail
- Triggers Airflow's built-in alerting mechanisms (email, etc.)
- Creates detailed error logs with validation results

### Notification Channels
- **Email Alerts**: Configurable email notifications for DQ issues
- **Slack Alerts**: Real-time Slack messages on validation failures
- **Logging**: Detailed logs of all data quality checks

## 📊 Data Quality Dashboard

A dedicated Streamlit dashboard provides visualization and monitoring of data quality metrics:

- **Schema Validation**: Track validation success rates over time
- **Critical Field Nulls**: Monitor null counts by field over time
- **Schema Drift**: Visualize schema changes across pipeline stages
- **Data Arrival**: Track data freshness and timeliness
- **Record Counts**: Monitor for anomalous changes in volume

![Data Quality Dashboard](https://example.com/dq-dashboard.png)

## 🛠️ Implementation

### Great Expectations Suite Structure
```
great_expectations/
├── expectations/
│   ├── raw/
│   │   ├── product_completeness_suite.json
│   │   ├── product_uniqueness_suite.json
│   │   └── product_consistency_suite.json
│   └── silver/
│       ├── product_completeness_suite.json
│       └── product_advanced_quality_suite.json
```

### Validation Workflow
The pipeline executes these validation checks at multiple stages:

1. **Raw Data Validation**: 
   - Schema contract validation
   - Completeness checks
   - Uniqueness constraints
   - Consistency rules

2. **Post-Transformation Validation**:
   - Silver layer quality checks
   - Business rule validation
   - Referential integrity

3. **Gold Layer Validation**:
   - Business KPI validation
   - Dimensional model integrity

### Metrics Storage
All data quality metrics are stored for historical analysis:
- Raw metrics in JSON format
- Time-series tracking for trend analysis
- Alerting thresholds based on historical patterns

## 🔄 Running the Monitoring System

The monitoring system runs automatically as part of the pipeline, but can also be executed manually:

```bash
# Run validation with monitoring on raw data
python src/validate.py data/raw/products_2023-01-01.json

# Run validation with monitoring on silver data
python src/validate.py data/silver/products

# Start the data quality dashboard
streamlit run streamlit_app/dq_dashboard.py
```

## 📈 Continuous Improvement

The data quality monitoring system supports continuous improvement through:

1. Historical tracking of validation results
2. Adjustment of validation rules based on patterns
3. Extension points for adding new quality dimensions
4. Integration with observability platforms
