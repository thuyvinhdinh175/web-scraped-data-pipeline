#!/usr/bin/env python3
"""
Product Web Scraper

This script scrapes product data from a target e-commerce website and
stores the results as JSON files in the raw data layer.
"""

import os
import json
import logging
import datetime
import requests
from bs4 import BeautifulSoup
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
TARGET_URL = "https://example-ecommerce-site.com/products"
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "../data/raw")
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"

def get_product_urls():
    """Scrape the main product listing page to get individual product URLs."""
    logger.info(f"Scraping product URLs from {TARGET_URL}")
    
    response = requests.get(TARGET_URL)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    product_links = soup.select('.product-item a')
    
    product_urls = [link['href'] for link in product_links]
    logger.info(f"Found {len(product_urls)} product URLs")
    
    return product_urls

def scrape_product_details(product_url):
    """Scrape details from a single product page."""
    logger.info(f"Scraping product details from {product_url}")
    
    response = requests.get(product_url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract product details
    product = {
        "url": product_url,
        "scrape_date": datetime.datetime.now().isoformat(),
        "product_id": product_url.split('/')[-1],
        "name": soup.select_one('.product-name').text.strip(),
        "price": float(soup.select_one('.product-price').text.strip().replace('$', '')),
        "description": soup.select_one('.product-description').text.strip(),
        "rating": float(soup.select_one('.product-rating').get('data-rating', 0)),
        "num_reviews": int(soup.select_one('.product-reviews-count').text.strip().split()[0]),
        "in_stock": "In Stock" in soup.select_one('.product-availability').text,
        "brand": soup.select_one('.product-brand').text.strip(),
        "categories": [cat.text.strip() for cat in soup.select('.product-category')],
        "image_urls": [img['src'] for img in soup.select('.product-image img')]
    }
    
    return product

def save_to_local(data, filename):
    """Save the scraped data to a local JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, filename)
    
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"Saved scraped data to {file_path}")
    return file_path

def upload_to_s3(file_path, s3_key):
    """Upload the JSON file to S3."""
    s3_client = boto3.client('s3')
    try:
        s3_client.upload_file(file_path, S3_BUCKET, s3_key)
        logger.info(f"Uploaded {file_path} to s3://{S3_BUCKET}/{s3_key}")
        return True
    except ClientError as e:
        logger.error(f"Error uploading to S3: {e}")
        return False

def main():
    """Main function to orchestrate the scraping process."""
    logger.info("Starting web scraping process")
    
    # Generate timestamp for filenames
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"products_{timestamp}.json"
    s3_key = f"raw/{filename}"
    
    # Get product URLs
    product_urls = get_product_urls()
    
    # Scrape each product
    products = []
    for url in product_urls:
        try:
            product = scrape_product_details(url)
            products.append(product)
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
    
    # Save data locally
    file_path = save_to_local(products, filename)
    
    # Upload to S3 if enabled
    if USE_S3:
        upload_to_s3(file_path, s3_key)
    
    logger.info(f"Scraped {len(products)} products successfully")
    return len(products)

if __name__ == "__main__":
    main()
