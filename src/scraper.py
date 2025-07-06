#!/usr/bin/env python3
"""
Product Web Scraper using Whoogle Search

This script uses Whoogle Search to find product data from e-commerce websites and
stores the results as JSON files in the raw data layer.
"""

import os
import json
import logging
import datetime
import re
import requests
import subprocess
from bs4 import BeautifulSoup
import boto3
from botocore.exceptions import ClientError
import time
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
WHOOGLE_HOST = os.environ.get("WHOOGLE_HOST", "127.0.0.1")
WHOOGLE_PORT = os.environ.get("WHOOGLE_PORT", "5000")
WHOOGLE_URL = f"http://{WHOOGLE_HOST}:{WHOOGLE_PORT}"
PRODUCT_SEARCH_TERMS = [
    "best laptops 2024",
    "top rated smartphones",
    "wireless headphones reviews",
    "gaming monitors 2024",
    "best smart home devices"
]
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "../data/raw")
S3_BUCKET = os.environ.get("S3_BUCKET", "web-scraped-data-pipeline")
USE_S3 = os.environ.get("USE_S3", "False").lower() == "true"

def start_whoogle_server():
    """Start the Whoogle Search server as a subprocess."""
    logger.info("Starting Whoogle Search server...")
    
    try:
        # Check if Whoogle is already running
        response = requests.get(f"{WHOOGLE_URL}", timeout=2)
        if response.status_code == 200:
            logger.info("Whoogle server is already running")
            return True
    except requests.exceptions.ConnectionError:
        logger.info("Whoogle server not running, starting it now")
        
    try:
        # Start Whoogle server as a background process
        process = subprocess.Popen(
            ["whoogle-search", f"--port={WHOOGLE_PORT}", f"--host={WHOOGLE_HOST}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        time.sleep(5)
        
        # Check if server started successfully
        try:
            response = requests.get(f"{WHOOGLE_URL}", timeout=5)
            if response.status_code == 200:
                logger.info("Whoogle server started successfully")
                return True
            else:
                logger.error(f"Whoogle server returned status code {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to Whoogle server after starting")
            return False
    except Exception as e:
        logger.error(f"Error starting Whoogle server: {e}")
        return False

def search_products(search_term):
    """Use Whoogle to search for products based on the search term."""
    logger.info(f"Searching for: {search_term}")
    
    search_url = f"{WHOOGLE_URL}/search?q={search_term.replace(' ', '+')}"
    
    try:
        response = requests.get(search_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract search results
        search_results = []
        result_elements = soup.select('.g')
        
        for element in result_elements:
            # Extract title and URL
            title_element = element.select_one('.r > a')
            
            if not title_element:
                continue
                
            title = title_element.text.strip()
            url = title_element.get('href')
            
            # Extract description
            description_element = element.select_one('.st')
            description = description_element.text.strip() if description_element else ""
            
            search_results.append({
                "title": title,
                "url": url,
                "description": description,
                "search_term": search_term
            })
        
        logger.info(f"Found {len(search_results)} results for '{search_term}'")
        return search_results
    
    except Exception as e:
        logger.error(f"Error searching for '{search_term}': {e}")
        return []

def scrape_product_details(search_result):
    """Scrape details from a product page."""
    url = search_result["url"]
    logger.info(f"Scraping product details from {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Initialize product with search result data
        product = {
            "url": url,
            "scrape_date": datetime.datetime.now().isoformat(),
            "title": search_result["title"],
            "search_term": search_result["search_term"],
            "description": search_result["description"],
        }
        
        # Extract product ID if available
        product_id = None
        
        # Try different methods to extract product ID
        # Method 1: From URL
        product_id_match = re.search(r'product[/_-]id[/_-]?=?([A-Za-z0-9]+)', url, re.IGNORECASE)
        if product_id_match:
            product_id = product_id_match.group(1)
        
        # Method 2: From page content
        if not product_id:
            product_id_elem = soup.select_one('[data-product-id], [id*=product-id], [class*=product-id]')
            if product_id_elem:
                product_id = product_id_elem.get('data-product-id') or product_id_elem.text.strip()
        
        # Method 3: Generate from URL
        if not product_id:
            product_id = url.split('/')[-1].split('?')[0]
            if not product_id or len(product_id) > 50:
                product_id = f"p{hash(url) % 100000:05d}"
        
        product["product_id"] = product_id
        
        # Extract common product information using various selectors that might be present
        # Price
        price_elem = soup.select_one('.price, .product-price, [data-price], [itemprop="price"], .offer-price')
        if price_elem:
            price_text = price_elem.text.strip()
            # Extract digits and decimal point
            price_match = re.search(r'[\d,]+\.\d+|\d+', price_text)
            if price_match:
                price_str = price_match.group(0).replace(',', '')
                try:
                    product["price"] = float(price_str)
                except ValueError:
                    product["price"] = None
        
        # Brand
        brand_elem = soup.select_one('[itemprop="brand"], .brand, .product-brand')
        product["brand"] = brand_elem.text.strip() if brand_elem else "Unknown"
        
        # Rating
        rating_elem = soup.select_one('[itemprop="ratingValue"], .rating, .product-rating, [data-rating]')
        if rating_elem:
            rating_text = rating_elem.text.strip() if rating_elem.text else rating_elem.get('data-rating', '')
            rating_match = re.search(r'([\d.]+)', rating_text)
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                    # Normalize to 5-star scale if needed
                    if rating > 5 and rating <= 10:
                        rating = rating / 2
                    elif rating > 10 and rating <= 100:
                        rating = rating / 20
                    product["rating"] = min(5.0, rating)  # Cap at 5.0
                except ValueError:
                    product["rating"] = None
        
        # Number of reviews
        reviews_elem = soup.select_one('[itemprop="reviewCount"], .review-count, .product-reviews-count')
        if reviews_elem:
            reviews_text = reviews_elem.text.strip()
            reviews_match = re.search(r'(\d+)', reviews_text)
            if reviews_match:
                try:
                    product["num_reviews"] = int(reviews_match.group(1))
                except ValueError:
                    product["num_reviews"] = 0
        else:
            product["num_reviews"] = 0
        
        # In stock status
        stock_elem = soup.select_one('.stock, .availability, [itemprop="availability"]')
        if stock_elem:
            product["in_stock"] = "in stock" in stock_elem.text.lower() or "available" in stock_elem.text.lower()
        else:
            # Check for common out-of-stock indicators
            out_of_stock_indicators = [
                '.out-of-stock', 
                '[data-availability="out-of-stock"]',
                '.sold-out'
            ]
            product["in_stock"] = not any(soup.select_one(selector) for selector in out_of_stock_indicators)
        
        # Categories
        categories = []
        breadcrumb = soup.select_one('.breadcrumb, .breadcrumbs, [itemtype*="BreadcrumbList"]')
        if breadcrumb:
            category_elems = breadcrumb.select('li, [itemprop="itemListElement"]')
            categories = [elem.text.strip() for elem in category_elems if elem.text.strip()]
        
        # If no categories from breadcrumb, look for category tags
        if not categories:
            category_elems = soup.select('.category, [itemprop="category"], .product-category')
            categories = [elem.text.strip() for elem in category_elems if elem.text.strip()]
        
        # If still no categories, use the search term as a category
        if not categories:
            search_term_parts = search_result["search_term"].split()
            if len(search_term_parts) > 1:
                categories = [search_term_parts[0]]
        
        product["categories"] = categories if categories else ["Uncategorized"]
        
        # Image URLs
        image_elems = soup.select('[itemprop="image"], .product-image img, .product-img img, .product-photo img')
        image_urls = []
        for img in image_elems:
            src = img.get('src') or img.get('data-src')
            if src:
                # Convert relative URLs to absolute
                if src.startswith('/'):
                    parsed_url = requests.utils.urlparse(url)
                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    src = base_url + src
                image_urls.append(src)
        
        product["image_urls"] = image_urls
        
        return product
    
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return None

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
    logger.info("Starting web scraping process with Whoogle Search")
    
    # Start Whoogle server
    if not start_whoogle_server():
        logger.error("Failed to start Whoogle server. Exiting.")
        return 0
    
    # Generate timestamp for filenames
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"products_{timestamp}.json"
    s3_key = f"raw/{filename}"
    
    all_products = []
    
    # Process each search term
    for search_term in PRODUCT_SEARCH_TERMS:
        logger.info(f"Processing search term: {search_term}")
        
        # Search for products
        search_results = search_products(search_term)
        
        # Limit to top 5 results per search term to avoid too many requests
        top_results = search_results[:5]
        
        # Scrape each product
        for result in top_results:
            # Add a small delay to avoid overwhelming the target site
            time.sleep(random.uniform(1.0, 3.0))
            
            try:
                product = scrape_product_details(result)
                if product:
                    all_products.append(product)
            except Exception as e:
                logger.error(f"Error processing {result['url']}: {e}")
    
    # Save data locally
    file_path = save_to_local(all_products, filename)
    
    # Upload to S3 if enabled
    if USE_S3:
        upload_to_s3(file_path, s3_key)
    
    logger.info(f"Scraped {len(all_products)} products successfully")
    return len(all_products)

if __name__ == "__main__":
    main()
