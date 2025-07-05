-- models/dim_product.sql
{{
  config(
    materialized = 'table',
    schema = 'gold',
    unique_key = 'product_id',
    partition_by = {
      "field": "scrape_date",
      "data_type": "date",
      "granularity": "day"
    }
  )
}}

WITH product_data AS (
    SELECT
        product_id,
        name,
        brand,
        MAX(rating) AS rating,
        MAX(num_reviews) AS num_reviews,
        MAX(CASE WHEN in_stock THEN 1 ELSE 0 END) AS is_in_stock,
        MAX(price) AS latest_price,
        MIN(price) AS min_price,
        MAX(price) AS max_price,
        ARRAY_AGG(DISTINCT category) AS categories,
        MAX(scrape_timestamp) AS scrape_date
    FROM {{ source('silver', 'products') }}
    GROUP BY product_id, name, brand
),

price_stats AS (
    SELECT
        product_id,
        AVG(price) AS avg_price,
        STDDEV(price) AS price_stddev
    FROM {{ source('silver', 'products') }}
    GROUP BY product_id
)

SELECT
    p.product_id,
    p.name AS product_name,
    p.brand,
    p.rating,
    p.num_reviews,
    p.is_in_stock,
    p.latest_price,
    p.min_price,
    p.max_price,
    s.avg_price,
    s.price_stddev,
    p.categories,
    CASE
        WHEN p.rating >= 4.5 THEN 'Excellent'
        WHEN p.rating >= 4.0 THEN 'Very Good'
        WHEN p.rating >= 3.0 THEN 'Good'
        WHEN p.rating >= 2.0 THEN 'Fair'
        ELSE 'Poor'
    END AS rating_category,
    CASE
        WHEN p.latest_price < s.avg_price * 0.9 THEN 'Discount'
        WHEN p.latest_price > s.avg_price * 1.1 THEN 'Premium'
        ELSE 'Regular'
    END AS price_category,
    p.scrape_date
FROM product_data p
JOIN price_stats s ON p.product_id = s.product_id
