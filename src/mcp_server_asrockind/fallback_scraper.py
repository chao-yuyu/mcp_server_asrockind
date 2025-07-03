"""Lightweight fallback scraper using requests instead of Selenium."""

import logging
import random
import time
import urllib.parse
from typing import Dict, List, Any, Optional

import requests
from bs4 import BeautifulSoup
from .config import get_config, get_scraping_config


logger = logging.getLogger(__name__)
config = get_config()
scraping_config = get_scraping_config()


class FallbackScraper:
    """Lightweight scraper using requests for better performance."""
    
    def __init__(self):
        self.base_url = config.base_url
        self.session = requests.Session()
        self._setup_session()
    
    def _setup_session(self):
        """Setup requests session with headers and timeout."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session.headers.update(headers)
        self.session.timeout = scraping_config.page_load_timeout
    
    def search_products(self, query: str) -> List[Dict[str, Any]]:
        """Search for products using requests."""
        search_url = f"{self.base_url}/en-gb/product/search?search={urllib.parse.quote(query)}"
        logger.info(f"Fallback search: {search_url}")
        
        try:
            # Get search page
            response = self.session.get(search_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check for no results
            if soup.select_one('div.no-result'):
                logger.info("No results found (fallback)")
                return []
            
            # Find product links
            product_links = soup.select('a.whole-link.d-block')[:scraping_config.max_products_per_search]
            logger.info(f"Found {len(product_links)} products (fallback)")
            
            products = []
            for i, link in enumerate(product_links):
                try:
                    product = self._scrape_single_product_fallback(link, i + 1)
                    if product:
                        products.append(product)
                        logger.info(f"Scraped product {i+1}: {product['name']} (fallback)")
                    
                    # Small delay between requests
                    if i < len(product_links) - 1:
                        time.sleep(random.uniform(0.5, 1.0))
                        
                except Exception as e:
                    logger.error(f"Error scraping product {i+1} (fallback): {e}")
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []
    
    def _scrape_single_product_fallback(self, link_element, product_num: int) -> Optional[Dict[str, Any]]:
        """Scrape single product using requests."""
        try:
            # Get product URL and name
            product_url = urllib.parse.urljoin(self.base_url, link_element['href'])
            
            name_element = link_element.select_one('div.product-title')
            if name_element:
                product_name = name_element.get_text(separator=' ', strip=True)
                product_name = ' '.join(product_name.split())
            else:
                product_name = product_url.split('/')[-1]
            
            # Get product details page
            response = self.session.get(product_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract basic specifications
            specs = self._extract_specifications_simple(soup)
            
            return {
                "name": product_name,
                "url": product_url,
                "specifications": specs
            }
            
        except Exception as e:
            logger.error(f"Error scraping product details (fallback): {e}")
            return None
    
    def _extract_specifications_simple(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract specifications with simpler approach."""
        specs = {}
        
        try:
            # Try to find specification tables
            spec_tables = soup.select('table.table-spec, table[class*="spec"]')
            
            for table in spec_tables:
                # Get category from nearby headings
                category = ""
                for heading in ['h3', 'h2', 'h4']:
                    prev_heading = table.find_previous(heading)
                    if prev_heading:
                        category = prev_heading.get_text(strip=True)
                        break
                
                # Extract table data
                for row in table.select('tr'):
                    cells = row.select('td, th')
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        if key and value and key.lower() not in ['specification', 'feature']:
                            full_key = f"{category} - {key}" if category else key
                            specs[full_key] = value
            
            # If no specs found, try to get basic product info
            if not specs:
                # Try to find product description or features
                desc_elements = soup.select('.product-desc, .overview, .description')
                for desc in desc_elements:
                    text = desc.get_text(strip=True)
                    if text and len(text) > 10:
                        specs['Description'] = text[:500] + '...' if len(text) > 500 else text
                        break
                        
        except Exception as e:
            logger.error(f"Error extracting specifications (fallback): {e}")
        
        return specs
    
    def close(self):
        """Close the session."""
        self.session.close() 