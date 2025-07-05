import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import json
import os
import glob
import datetime
from datetime import timedelta
import boto3

# Set page configuration
st.set_page_config(
    page_title="Data Quality Monitoring Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"
METRICS_DIR = os.environ.get("METRICS_DIR", "../data/metrics")

def load_metrics_from_local(metrics_type, days=7):
    """Load metrics files from local filesystem."""
    metrics_path = os.path.join(METRICS_DIR, metrics_type)
    if not os.path.exists(metrics_path):
        return pd.DataFrame()
    
    all_data = []
    cutoff_date = datetime.datetime.now() - timedelta(days=days)
    
    for file_path in glob.glob(f"{metrics_path}/*.json"):
        try:
            # Check if file is recent enough
            file_timestamp = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_timestamp < cutoff_date:
                continue
                
            with open(file_path, 'r') as f:
                data = json.load(f)
                # Add filename as source
                data['source_file'] = os.path.basename(file_path)
                all_data.append(data)
        except Exception as e:
            st.error(f"Error loading metrics from {file_path}: {e}")
    
    if not all_data:
        return pd.DataFrame()
    
    # Normalize and convert to DataFrame
    return pd.json_normalize(all_data)

def load_metrics_from_s3(metrics_type, days=7):
    """Load metrics files from S3."""
    s3_client = boto3.client('s3')
    metrics_prefix = f"metrics/{metrics_type}/"
    
    all_data = []
    cutoff_date = datetime.datetime.now() - timedelta(days=days)
    
    try:
        # List objects in the metrics prefix
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=metrics_prefix
        )
        
        if 'Contents' not in response:
            return pd.DataFrame()
        
        for obj in response['Contents']:
            # Check if file is recent enough
            if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                continue
                
            # Get the object content
            obj_response = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=obj['Key']
            )
            
            # Load JSON data
            data = json.loads(obj_response['Body'].read().decode('utf-8'))
            # Add S3 key as source
            data['source_file'] = obj['Key']
            all_data.append(data)
    except Exception as e:
        st.error(f"Error loading metrics from S3: {e}")
    
    if not all_data:
        return pd.DataFrame()
    
    # Normalize and convert to DataFrame
    return pd.json_normalize(all_data)

def load_metrics(metrics_type, days=7):
    """Load metrics from either local or S3 based on configuration."""
    if USE_S3:
        return load_metrics_from_s3(metrics_type, days)
    else:
        return load_metrics_from_local(metrics_type, days)

def format_timestamp(timestamp_str):
    """Format timestamp string to readable date/time."""
    try:
        if '_' in timestamp_str:
            dt = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        else:
            dt = datetime.datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp_str

# App title and header
st.title("🔍 Data Quality Monitoring Dashboard")
st.markdown("""
This dashboard provides insights into data quality metrics tracked across the pipeline.
It helps identify issues, trends, and anomalies in the data processing flow.
""")

# Sidebar for date range selection
st.sidebar.header("Settings")
days_to_show = st.sidebar.slider("Days to show", 1, 30, 7)

# Load validation metrics
validation_df = load_metrics("validation_failure", days_to_show)
schema_drift_df = load_metrics("schema_drift", days_to_show)
record_count_df = load_metrics("record_count", days_to_show)
null_counts_df = load_metrics("null_counts", days_to_show)
data_arrival_df = load_metrics("data_arrival", days_to_show)

# Main dashboard content - split into tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📉 Schema Validation", 
    "🧪 Null Counts", 
    "🔁 Schema Drift", 
    "⏱ Data Arrival", 
    "📊 Record Counts"
])

with tab1:
    st.header("Schema Validation Results")
    
    if validation_df.empty:
        st.info("No validation metrics available for the selected time period.")
    else:
        # Prepare data for charts
        validation_df['timestamp'] = validation_df['metadata.timestamp'].apply(format_timestamp)
        validation_df['data_path'] = validation_df['metadata.data_path'].apply(lambda x: os.path.basename(x))
        
        # Validation success rate over time
        st.subheader("Validation Success Rate Over Time")
        success_df = validation_df[['timestamp', 'validation_success', 'failure_rate', 'data_path']]
        
        success_chart = alt.Chart(success_df).mark_line(point=True).encode(
            x='timestamp:T',
            y=alt.Y('failure_rate:Q', scale=alt.Scale(domain=[0, 1]), title='Failure Rate'),
            color=alt.Color('data_path:N', title='Data Path'),
            tooltip=['timestamp', 'failure_rate', 'data_path']
        ).properties(height=300)
        
        st.altair_chart(success_chart, use_container_width=True)
        
        # Failed expectations table
        st.subheader("Recent Validation Failures")
        if 'failed_expectations' in validation_df.columns:
            # Explode the failed_expectations array into separate rows
            failures = []
            for idx, row in validation_df.iterrows():
                if isinstance(row.get('failed_expectations'), list):
                    for exp in row['failed_expectations']:
                        failures.append({
                            'timestamp': row['timestamp'],
                            'data_path': row['data_path'],
                            'expectation_type': exp.get('expectation_type', 'unknown'),
                            'details': str(exp.get('kwargs', {}))
                        })
            
            if failures:
                failures_df = pd.DataFrame(failures)
                st.dataframe(failures_df.sort_values('timestamp', ascending=False))
            else:
                st.success("No validation failures! 🎉")
        else:
            st.info("No detailed failure information available.")

with tab2:
    st.header("Null Counts in Critical Fields")
    
    if null_counts_df.empty:
        st.info("No null count metrics available for the selected time period.")
    else:
        # Prepare data for charts
        null_counts_df['timestamp'] = null_counts_df['metadata.timestamp'].apply(format_timestamp)
        
        # Check if we have column-specific null counts
        if any(col.startswith('null_counts.') for col in null_counts_df.columns):
            # Melt the DataFrame to get column names and null counts
            null_columns = [col for col in null_counts_df.columns if col.startswith('null_counts.')]
            melted_df = pd.melt(
                null_counts_df,
                id_vars=['timestamp', 'metadata.data_path'],
                value_vars=null_columns,
                var_name='column',
                value_name='null_count'
            )
            
            # Clean up column names
            melted_df['column'] = melted_df['column'].str.replace('null_counts.', '')
            melted_df['data_path'] = melted_df['metadata.data_path'].apply(lambda x: os.path.basename(x))
            
            # Create chart
            st.subheader("Null Counts by Column")
            null_chart = alt.Chart(melted_df).mark_line(point=True).encode(
                x='timestamp:T',
                y=alt.Y('null_count:Q', title='Number of Nulls'),
                color='column:N',
                tooltip=['timestamp', 'column', 'null_count', 'data_path']
            ).properties(height=300)
            
            st.altair_chart(null_chart, use_container_width=True)
            
            # Table of most recent null counts
            st.subheader("Most Recent Null Counts")
            latest_timestamp = melted_df['timestamp'].max()
            latest_nulls = melted_df[melted_df['timestamp'] == latest_timestamp]
            
            if not latest_nulls.empty:
                st.dataframe(latest_nulls[['column', 'null_count', 'data_path']])
            else:
                st.info("No recent null count data available.")
        else:
            st.info("No column-specific null count data available.")

with tab3:
    st.header("Schema Drift Detection")
    
    if schema_drift_df.empty:
        st.info("No schema drift metrics available for the selected time period.")
    else:
        # Prepare data for charts
        schema_drift_df['timestamp'] = schema_drift_df['metadata.timestamp'].apply(format_timestamp)
        schema_drift_df['data_path'] = schema_drift_df['metadata.data_path'].apply(lambda x: os.path.basename(x))
        
        # Schema drift over time
        st.subheader("Schema Changes Over Time")
        
        # Check if we have the necessary columns
        if all(col in schema_drift_df.columns for col in ['has_drift', 'added_columns', 'removed_columns', 'modified_columns']):
            # Create a summary of changes
            changes = []
            for idx, row in schema_drift_df.iterrows():
                added = len(row['added_columns']) if isinstance(row['added_columns'], list) else 0
                removed = len(row['removed_columns']) if isinstance(row['removed_columns'], list) else 0
                modified = len(row['modified_columns']) if isinstance(row['modified_columns'], dict) else 0
                
                changes.append({
                    'timestamp': row['timestamp'],
                    'data_path': row['data_path'],
                    'added': added,
                    'removed': removed,
                    'modified': modified,
                    'has_drift': row['has_drift']
                })
            
            if changes:
                changes_df = pd.DataFrame(changes)
                
                # Melt the DataFrame for stacked bar chart
                melted_changes = pd.melt(
                    changes_df,
                    id_vars=['timestamp', 'data_path', 'has_drift'],
                    value_vars=['added', 'removed', 'modified'],
                    var_name='change_type',
                    value_name='count'
                )
                
                # Create chart
                drift_chart = alt.Chart(melted_changes).mark_bar().encode(
                    x='timestamp:T',
                    y='count:Q',
                    color='change_type:N',
                    tooltip=['timestamp', 'data_path', 'change_type', 'count']
                ).properties(height=300)
                
                st.altair_chart(drift_chart, use_container_width=True)
                
                # Table of recent schema changes
                st.subheader("Recent Schema Changes")
                st.dataframe(changes_df.sort_values('timestamp', ascending=False))
                
                # Detail view for latest change
                if changes_df['has_drift'].any():
                    st.subheader("Latest Schema Drift Details")
                    latest_drift = schema_drift_df[schema_drift_df['has_drift'] == True].sort_values('timestamp', ascending=False).iloc[0]
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write("Added Columns")
                        added = latest_drift.get('added_columns', [])
                        if added:
                            for col in added:
                                st.write(f"- {col}")
                        else:
                            st.write("None")
                    
                    with col2:
                        st.write("Removed Columns")
                        removed = latest_drift.get('removed_columns', [])
                        if removed:
                            for col in removed:
                                st.write(f"- {col}")
                        else:
                            st.write("None")
                    
                    with col3:
                        st.write("Modified Columns")
                        modified = latest_drift.get('modified_columns', {})
                        if modified:
                            for col, change in modified.items():
                                st.write(f"- {col}: {change.get('from_type', 'unknown')} → {change.get('to_type', 'unknown')}")
                        else:
                            st.write("None")
            else:
                st.info("No schema changes detected in the selected time period.")
        else:
            st.info("Schema drift data does not contain expected fields.")

with tab4:
    st.header("Data Arrival Monitoring")
    
    if data_arrival_df.empty:
        st.info("No data arrival metrics available for the selected time period.")
    else:
        # Prepare data for charts
        data_arrival_df['timestamp'] = data_arrival_df['metadata.timestamp'].apply(format_timestamp)
        data_arrival_df['file_path'] = data_arrival_df['file_path'].apply(lambda x: os.path.basename(x))
        
        # Check if we have the necessary columns
        if all(col in data_arrival_df.columns for col in ['hours_since_update', 'is_delayed', 'last_modified']):
            # Data arrival delays
            st.subheader("File Update Delays")
            
            # Format the last_modified timestamps
            data_arrival_df['last_modified_formatted'] = data_arrival_df['last_modified'].apply(format_timestamp)
            
            # Create chart
            delay_chart = alt.Chart(data_arrival_df).mark_bar().encode(
                x='file_path:N',
                y=alt.Y('hours_since_update:Q', title='Hours Since Last Update'),
                color=alt.condition(
                    alt.datum.is_delayed,
                    alt.value('red'),
                    alt.value('green')
                ),
                tooltip=['file_path', 'last_modified_formatted', 'hours_since_update', 'is_delayed']
            ).properties(height=300)
            
            st.altair_chart(delay_chart, use_container_width=True)
            
            # Table of current delays
            st.subheader("Current Data Arrival Status")
            
            # Get the most recent status for each file
            latest_status = data_arrival_df.sort_values('timestamp', ascending=False).drop_duplicates('file_path')
            
            if not latest_status.empty:
                status_df = latest_status[['file_path', 'last_modified_formatted', 'hours_since_update', 'is_delayed']]
                status_df.columns = ['File', 'Last Modified', 'Hours Since Update', 'Is Delayed']
                
                # Apply color highlighting for delayed files
                def highlight_delayed(row):
                    return ['background-color: #ffcccc' if row['Is Delayed'] else '' for _ in row]
                
                st.dataframe(status_df.style.apply(highlight_delayed, axis=1))
            else:
                st.info("No recent data arrival status available.")
        else:
            st.info("Data arrival metrics do not contain expected fields.")

with tab5:
    st.header("Record Count Anomalies")
    
    if record_count_df.empty:
        st.info("No record count metrics available for the selected time period.")
    else:
        # Prepare data for charts
        record_count_df['timestamp'] = record_count_df['metadata.timestamp'].apply(format_timestamp)
        record_count_df['data_path'] = record_count_df['metadata.data_path'].apply(lambda x: os.path.basename(x))
        
        # Check if we have the necessary columns
        if all(col in record_count_df.columns for col in ['current_count', 'is_anomaly', 'percent_change']):
            # Record count over time
            st.subheader("Record Counts Over Time")
            
            # Create chart
            count_chart = alt.Chart(record_count_df).mark_line(point=True).encode(
                x='timestamp:T',
                y=alt.Y('current_count:Q', title='Record Count'),
                color='data_path:N',
                tooltip=['timestamp', 'data_path', 'current_count', 'percent_change', 'is_anomaly']
            ).properties(height=300)
            
            # Add markers for anomalies
            anomaly_markers = alt.Chart(record_count_df[record_count_df['is_anomaly']]).mark_circle(
                size=100,
                color='red'
            ).encode(
                x='timestamp:T',
                y='current_count:Q',
                tooltip=['timestamp', 'data_path', 'current_count', 'percent_change']
            )
            
            st.altair_chart(count_chart + anomaly_markers, use_container_width=True)
            
            # Percent change chart
            st.subheader("Record Count Percentage Change")
            
            percent_chart = alt.Chart(record_count_df).mark_bar().encode(
                x='timestamp:T',
                y=alt.Y('percent_change:Q', title='% Change from Historical Average'),
                color=alt.condition(
                    alt.datum.is_anomaly,
                    alt.value('red'),
                    alt.value('steelblue')
                ),
                tooltip=['timestamp', 'data_path', 'current_count', 'percent_change']
            ).properties(height=300)
            
            st.altair_chart(percent_chart, use_container_width=True)
            
            # Table of recent anomalies
            st.subheader("Recent Record Count Anomalies")
            anomalies = record_count_df[record_count_df['is_anomaly']].sort_values('timestamp', ascending=False)
            
            if not anomalies.empty:
                anomaly_df = anomalies[['timestamp', 'data_path', 'current_count', 'avg_historical_count', 'percent_change']]
                anomaly_df.columns = ['Timestamp', 'Data Path', 'Current Count', 'Historical Average', '% Change']
                st.dataframe(anomaly_df)
            else:
                st.success("No record count anomalies detected in the selected time period! 🎉")
        else:
            st.info("Record count metrics do not contain expected fields.")

# Footer with summary metrics
st.markdown("---")

# Create summary cards
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Validation failures
    total_validations = len(validation_df) if not validation_df.empty else 0
    failed_validations = validation_df['validation_success'].value_counts().get(False, 0) if not validation_df.empty else 0
    
    st.metric(
        label="Validation Success Rate",
        value=f"{(1 - failed_validations/total_validations)*100:.1f}%" if total_validations > 0 else "N/A",
        delta=None
    )

with col2:
    # Schema drift
    total_drift_checks = len(schema_drift_df) if not schema_drift_df.empty else 0
    drift_detected = schema_drift_df['has_drift'].sum() if not schema_drift_df.empty and 'has_drift' in schema_drift_df.columns else 0
    
    st.metric(
        label="Schema Stability",
        value=f"{(1 - drift_detected/total_drift_checks)*100:.1f}%" if total_drift_checks > 0 else "N/A",
        delta=None
    )

with col3:
    # Data delays
    total_files = len(data_arrival_df.drop_duplicates('file_path')) if not data_arrival_df.empty else 0
    delayed_files = data_arrival_df[data_arrival_df['is_delayed']].drop_duplicates('file_path').shape[0] if not data_arrival_df.empty else 0
    
    st.metric(
        label="Files On Schedule",
        value=f"{(1 - delayed_files/total_files)*100:.1f}%" if total_files > 0 else "N/A",
        delta=None
    )

with col4:
    # Record count anomalies
    total_counts = len(record_count_df) if not record_count_df.empty else 0
    anomalies = record_count_df['is_anomaly'].sum() if not record_count_df.empty else 0
    
    st.metric(
        label="Record Count Stability",
        value=f"{(1 - anomalies/total_counts)*100:.1f}%" if total_counts > 0 else "N/A",
        delta=None
    )

# Data quality info
st.markdown("""
### Data Quality Metrics Tracked

This dashboard monitors these key data quality dimensions:

1. **Schema Validation**: Percentage of rows that fail schema checks
2. **Null Counts**: Number of nulls in critical fields
3. **Schema Drift**: Detection of new, removed, or modified columns
4. **Data Arrival**: Monitoring for data freshness and delays
5. **Record Counts**: Anomaly detection for unexpected changes in volume

For more details on data quality implementation, check the monitoring code and Great Expectations configuration.
""")
