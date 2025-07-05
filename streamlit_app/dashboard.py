import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import boto3
import os
import json
from io import StringIO, BytesIO
import pyarrow.parquet as pq

# Set page configuration
st.set_page_config(
    page_title="Product Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"
LOCAL_DATA_PATH = os.environ.get("LOCAL_DATA_PATH", "../data/gold")

# Helper functions
def load_data():
    """Load the product data from S3 or local storage."""
    if USE_S3:
        # Use boto3 to load data from S3
        s3_client = boto3.client('s3')
        response = s3_client.get_object(Bucket=S3_BUCKET, Key="gold/dim_product/dim_product.parquet")
        bytes_buffer = BytesIO(response['Body'].read())
        df = pq.read_table(bytes_buffer).to_pandas()
    else:
        # Load data from local storage
        file_path = os.path.join(LOCAL_DATA_PATH, "dim_product", "dim_product.parquet")
        if os.path.exists(file_path):
            df = pd.read_parquet(file_path)
        else:
            # If file doesn't exist, generate some mock data for development
            st.warning("No data file found. Using mock data for demonstration.")
            df = generate_mock_data()
    
    return df

def generate_mock_data():
    """Generate mock data for development purposes."""
    np.random.seed(42)
    brands = ['Apple', 'Samsung', 'Sony', 'LG', 'Bose', 'Dell', 'HP', 'Lenovo']
    categories = [['Electronics'], ['Computers'], ['Audio'], ['Home'], ['Phones'], ['Accessories']]
    
    return pd.DataFrame({
        'product_id': [f"P{i:04d}" for i in range(100)],
        'product_name': [f"Product {i}" for i in range(100)],
        'brand': np.random.choice(brands, 100),
        'rating': np.random.uniform(1, 5, 100).round(1),
        'num_reviews': np.random.randint(0, 1000, 100),
        'is_in_stock': np.random.choice([0, 1], 100),
        'latest_price': np.random.uniform(10, 1000, 100).round(2),
        'min_price': np.random.uniform(10, 800, 100).round(2),
        'max_price': np.random.uniform(200, 1200, 100).round(2),
        'avg_price': np.random.uniform(100, 900, 100).round(2),
        'price_stddev': np.random.uniform(1, 100, 100).round(2),
        'categories': np.random.choice(categories, 100),
        'rating_category': np.random.choice(['Excellent', 'Very Good', 'Good', 'Fair', 'Poor'], 100),
        'price_category': np.random.choice(['Discount', 'Regular', 'Premium'], 100),
        'scrape_date': pd.date_range(start='2023-01-01', periods=100)
    })

# App title and description
st.title("📊 Product Analytics Dashboard")
st.markdown("""
This dashboard provides insights from web-scraped product data that has been processed 
through our data pipeline with schema validation, quality checks, and transformations.
""")

# Load the data
with st.spinner("Loading data..."):
    df = load_data()

# Sidebar filters
st.sidebar.header("Filters")

# Brand filter
all_brands = sorted(df['brand'].unique())
selected_brands = st.sidebar.multiselect("Select Brands", all_brands, default=all_brands[:3])

# Rating filter
min_rating, max_rating = st.sidebar.slider("Rating Range", 1.0, 5.0, (3.0, 5.0), 0.1)

# Price filter
min_price = df['latest_price'].min()
max_price = df['latest_price'].max()
price_range = st.sidebar.slider("Price Range ($)", float(min_price), float(max_price), (float(min_price), float(max_price/2)))

# Apply filters
filtered_df = df[
    (df['brand'].isin(selected_brands)) &
    (df['rating'] >= min_rating) &
    (df['rating'] <= max_rating) &
    (df['latest_price'] >= price_range[0]) &
    (df['latest_price'] <= price_range[1])
]

# Display filtered data count
st.sidebar.info(f"Showing {len(filtered_df)} of {len(df)} products")

# Main dashboard content
col1, col2 = st.columns(2)

with col1:
    st.subheader("Price Analysis by Brand")
    
    brand_price_chart = alt.Chart(filtered_df).mark_boxplot().encode(
        x='brand:N',
        y=alt.Y('latest_price:Q', title='Price ($)'),
        color='brand:N'
    ).properties(
        height=300
    )
    
    st.altair_chart(brand_price_chart, use_container_width=True)
    
    st.subheader("Price Category Distribution")
    price_cat_chart = alt.Chart(filtered_df).mark_bar().encode(
        x='count():Q',
        y=alt.Y('price_category:N', sort='-x'),
        color='price_category:N'
    ).properties(
        height=200
    )
    
    st.altair_chart(price_cat_chart, use_container_width=True)

with col2:
    st.subheader("Rating Distribution")
    
    rating_hist = alt.Chart(filtered_df).mark_bar().encode(
        x=alt.X('rating:Q', bin=alt.Bin(step=0.5), title='Rating'),
        y='count():Q',
        color=alt.Color('rating:Q', scale=alt.Scale(scheme='greenblue'))
    ).properties(
        height=300
    )
    
    st.altair_chart(rating_hist, use_container_width=True)
    
    st.subheader("In-Stock Status by Brand")
    in_stock_chart = alt.Chart(filtered_df).mark_bar().encode(
        x='brand:N',
        y='count():Q',
        color='is_in_stock:N'
    ).properties(
        height=200
    )
    
    st.altair_chart(in_stock_chart, use_container_width=True)

# Product Details Section
st.subheader("Product Details")

# Add a search box
search_term = st.text_input("Search Products", "")

if search_term:
    search_results = df[df['product_name'].str.contains(search_term, case=False)]
    st.dataframe(search_results.sort_values('rating', ascending=False))
else:
    # Show top products by rating
    top_products = filtered_df.sort_values('rating', ascending=False).head(10)
    st.dataframe(top_products)

# Price Trends Section
st.subheader("Price Trends Over Time")

# For this demo, we'll create some synthetic price history data
if not filtered_df.empty:
    # Take the top 5 products by rating
    top_products = filtered_df.sort_values('rating', ascending=False).head(5)
    
    # Create synthetic price history
    dates = pd.date_range(end=pd.Timestamp.now(), periods=30)
    price_history = []
    
    for _, product in top_products.iterrows():
        base_price = product['avg_price']
        # Generate some random price fluctuations
        for date in dates:
            # Random fluctuation around the average price
            price = base_price * (1 + np.random.uniform(-0.1, 0.1))
            price_history.append({
                'product_id': product['product_id'],
                'product_name': product['product_name'],
                'date': date,
                'price': price
            })
    
    price_history_df = pd.DataFrame(price_history)
    
    # Create a line chart of price history
    price_chart = alt.Chart(price_history_df).mark_line().encode(
        x='date:T',
        y='price:Q',
        color='product_name:N',
        tooltip=['product_name', 'date', 'price']
    ).properties(
        height=400
    ).interactive()
    
    st.altair_chart(price_chart, use_container_width=True)
else:
    st.write("No data available for price trends after applying filters.")

# Footer
st.markdown("---")
st.markdown("""
**Data Pipeline Components**:
Web Scraper → S3 Raw Storage → Great Expectations Validation → 
PySpark ETL → Silver Layer → dbt Models → Gold Layer → Streamlit Dashboard
""")

if __name__ == "__main__":
    # This allows running the dashboard directly using: streamlit run dashboard.py
    pass
