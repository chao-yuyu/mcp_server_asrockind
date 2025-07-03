import asyncio
import json
import logging
import random
import time
import urllib.parse
from enum import Enum
from typing import Sequence, Optional, Dict, List, Any

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from .config import get_config, get_scraping_config
from .fallback_scraper import FallbackScraper


# Configure logging
config = get_config()
scraping_config = get_scraping_config()

logging.basicConfig(
    level=getattr(logging, config.log_level),
    format=config.log_format
)
logger = logging.getLogger(__name__)


class AsrockindTools(str, Enum):
    SEARCH_PRODUCTS = "asrock_industrial_product_search"


class ProductInfo(BaseModel):
    name: str
    url: str
    specifications: Dict[str, str] = {}


class ProductSearchResult(BaseModel):
    products: List[ProductInfo]
    total_results: int


class WebDriverManager:
    """Manages WebDriver lifecycle and configuration."""
    
    def __init__(self):
        self.driver = None
        self.base_url = config.base_url
        self._initialization_failed = False
        
    def setup_driver(self) -> bool:
        """Setup Chrome WebDriver with optimized options."""
        if self._initialization_failed:
            logger.warning("Skipping WebDriver setup due to previous failure")
            return False
            
        try:
            if self.driver:
                self.cleanup_driver()
            
            options = self._get_chrome_options()
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            
            # Set timeouts from config
            self.driver.set_page_load_timeout(scraping_config.page_load_timeout)
            self.driver.implicitly_wait(scraping_config.implicit_wait)
            
            # Anti-detection measures
            self._setup_anti_detection()
            
            logger.info("WebDriver setup successful")
            return True
            
        except Exception as e:
            logger.error(f"WebDriver setup failed: {e}")
            self._initialization_failed = True
            return False
    
    def _get_chrome_options(self) -> Options:
        """Get optimized Chrome options from config."""
        options = Options()
        
        # Add all options from config
        for option in scraping_config.chrome_options:
            options.add_argument(option)
        
        # Page load strategy
        options.page_load_strategy = 'eager'
        
        # Experimental options
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        return options
    
    def _setup_anti_detection(self):
        """Setup anti-detection measures."""
        try:
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e:
            logger.warning(f"Anti-detection setup failed: {e}")
    
    def is_driver_alive(self) -> bool:
        """Check if driver is still alive."""
        if self._initialization_failed or not self.driver:
            return False
        try:
            self.driver.current_url
            return True
        except:
            return False
    
    def ensure_driver(self) -> bool:
        """Ensure driver is ready for use."""
        if not self.driver or not self.is_driver_alive():
            logger.info("Reinitializing WebDriver...")
            return self.setup_driver()
        return True
    
    def safe_get(self, url: str) -> bool:
        """Safely navigate to URL with retries."""
        if self._initialization_failed:
            return False
            
        for attempt in range(scraping_config.max_retries):
            try:
                if not self.ensure_driver():
                    logger.error("Failed to initialize WebDriver")
                    return False
                
                self.driver.get(url)
                return True
                 
            except Exception as e:
                logger.warning(f"Navigation failed (attempt {attempt + 1}): {e}")
                if attempt < scraping_config.max_retries - 1:
                    time.sleep(random.uniform(
                        scraping_config.retry_delay_min, 
                        scraping_config.retry_delay_max
                    ))
                    continue
                return False
        return False
    
    def cleanup_driver(self):
        """Clean up WebDriver resources."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def __del__(self):
        self.cleanup_driver()


class ProductScraper:
    """Handles product scraping logic."""
    
    def __init__(self, driver_manager: WebDriverManager):
        self.driver_manager = driver_manager
        self.base_url = driver_manager.base_url
    
    def scrape_search_results(self, query: str) -> List[Dict[str, Any]]:
        """Scrape product search results."""
        search_url = f"{self.base_url}/en-gb/product/search?search={urllib.parse.quote(query)}"
        logger.info(f"Searching: {search_url}")
        
        if not self.driver_manager.safe_get(search_url):
            logger.error("Failed to load search page")
            return []
        
        # Wait for results with timeout from config
        try:
            wait = WebDriverWait(self.driver_manager.driver, scraping_config.element_wait_timeout)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.whole-link.d-block, div.no-result")))
        except Exception as e:
            logger.warning(f"Timeout waiting for search results: {e}")
            return []
        
        # Get page source and parse
        page_source = self.driver_manager.driver.page_source
        
        # Save debug HTML if enabled
        if config.save_debug_html:
            self._save_debug_html(page_source, "search_results.html")
        
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Check for no results
        if soup.select_one('div.no-result'):
            logger.info("No results found")
            return []
        
        # Find product links (limit by config)
        product_links = soup.select('a.whole-link.d-block')[:scraping_config.max_products_per_search]
        logger.info(f"Found {len(product_links)} product links")
        
        products = []
        for i, link in enumerate(product_links):
            try:
                product = self._scrape_single_product(link, i + 1)
                if product:
                    products.append(product)
                    logger.info(f"Scraped product {i+1}: {product['name']}")
                
                # Delay between products (from config)
                if i < len(product_links) - 1:
                    time.sleep(random.uniform(
                        scraping_config.product_delay_min,
                        scraping_config.product_delay_max
                    ))
                     
            except Exception as e:
                logger.error(f"Error scraping product {i+1}: {e}")
                continue
        
        return products
    
    def _scrape_single_product(self, link_element, product_num: int) -> Optional[Dict[str, Any]]:
        """Scrape a single product's details."""
        try:
            # Get product URL and name
            product_url = urllib.parse.urljoin(self.base_url, link_element['href'])
            
            name_element = link_element.select_one('div.product-title')
            if name_element:
                product_name = name_element.get_text(separator=' ', strip=True)
                product_name = ' '.join(product_name.split())
            else:
                product_name = product_url.split('/')[-1]
            
            # Get product details
            if not self.driver_manager.safe_get(product_url):
                logger.warning(f"Failed to load product page: {product_url}")
                return None
            
            # Wait for product info with timeout from config
            try:
                wait = WebDriverWait(self.driver_manager.driver, scraping_config.element_wait_timeout)
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-info")))
            except Exception as e:
                logger.warning(f"Timeout waiting for product details: {e}")
                # Continue anyway, might still get some data
            
            # Parse specifications
            page_source = self.driver_manager.driver.page_source
            
            # Save debug HTML if enabled
            if config.save_debug_html:
                self._save_debug_html(page_source, f"product_{product_num}.html")
            
            soup = BeautifulSoup(page_source, 'html.parser')
            specs = self._extract_specifications(soup)
            
            return {
                "name": product_name,
                "url": product_url,
                "specifications": specs
            }
            
        except Exception as e:
            logger.error(f"Error scraping product details: {e}")
            return None
    
    def _extract_specifications(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract product specifications from soup."""
        specs = {}
        
        try:
            spec_tables = soup.select('table.table-spec')
            for table in spec_tables:
                # Get category from previous h3
                category = ""
                prev_h3 = table.find_previous('h3', class_='title-sub')
                if prev_h3:
                    category = prev_h3.text.strip()
                
                # Extract table rows
                for row in table.select('tr'):
                    cells = row.select('td, th')
                    if len(cells) >= 2:
                        key = cells[0].text.strip()
                        value = cells[1].text.strip()
                        if key and value:
                            full_key = f"{category} - {key}" if category else key
                            specs[full_key] = value
                            
        except Exception as e:
            logger.error(f"Error extracting specifications: {e}")
        
        return specs
    
    def _save_debug_html(self, html_content: str, filename: str):
        """Save HTML content for debugging."""
        try:
            import os
            debug_dir = config.debug_html_path
            os.makedirs(debug_dir, exist_ok=True)
            
            filepath = os.path.join(debug_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.debug(f"Saved debug HTML: {filepath}")
        except Exception as e:
            logger.warning(f"Failed to save debug HTML: {e}")


class AsrockindServer:
    """Main server class for ASRock Industrial MCP server."""
    
    def __init__(self):
        self.driver_manager = WebDriverManager()
        self.scraper = ProductScraper(self.driver_manager)
        self.fallback_scraper = FallbackScraper()
        
        # Try to initialize driver, but don't fail if it doesn't work
        driver_ready = self.driver_manager.setup_driver()
        if not driver_ready:
            logger.warning("WebDriver initialization failed, will use fallback scraper only")
    
    async def search_products(self, query: str) -> List[Dict[str, Any]]:
        """Search for products with the given query."""
        for attempt in range(scraping_config.max_retries):
            try:
                logger.info(f"Search attempt {attempt + 1} for query: {query}")
                
                # Add delay from config
                await asyncio.sleep(random.uniform(
                    scraping_config.search_delay_min,
                    scraping_config.search_delay_max
                ))
                
                # Try Selenium first if available
                products = []
                if not self.driver_manager._initialization_failed:
                    try:
                        products = self.scraper.scrape_search_results(query)
                        if products:
                            logger.info(f"Successfully found {len(products)} products using Selenium")
                            return products
                    except Exception as e:
                        logger.warning(f"Selenium scraping failed: {e}")
                
                # Fallback to requests-based scraper
                logger.info("Trying fallback scraper...")
                products = self.fallback_scraper.search_products(query)
                if products:
                    logger.info(f"Successfully found {len(products)} products using fallback scraper")
                    return products
                
                logger.warning(f"No products found on attempt {attempt + 1}")
                
            except Exception as e:
                logger.error(f"Search attempt {attempt + 1} failed: {e}")
                
                if attempt < scraping_config.max_retries - 1:
                    await asyncio.sleep(random.uniform(
                        scraping_config.retry_delay_min * 2,
                        scraping_config.retry_delay_max * 2
                    ))
                    continue
        
        logger.error("All search attempts failed")
        return []
    
    def cleanup(self):
        """Clean up resources."""
        self.driver_manager.cleanup_driver()
        self.fallback_scraper.close()


async def serve() -> None:
    """Main server entry point."""
    server = Server(config.server_name)
    asrockind_server = AsrockindServer()
    
    try:
        @server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available ASRock Industrial tools."""
            return [
                Tool(
                    name=AsrockindTools.SEARCH_PRODUCTS.value,
                    description="Search for ASRock Industrial products by keyword. Returns product name, URL, and detailed specifications. Uses optimized scraping with fallback for reliability.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for products (e.g., 'SBC-230', 'motherboard', 'embedded system', 'IMB')",
                            }
                        },
                        "required": ["query"],
                    },
                ),
            ]

        @server.call_tool()
        async def call_tool(
            name: str, arguments: dict
        ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
            """Handle tool calls for ASRock Industrial product queries."""
            try:
                if name == AsrockindTools.SEARCH_PRODUCTS.value:
                    query = arguments.get("query")
                    if not query:
                        raise ValueError("Missing required argument: query")
                    
                    # Validate query
                    query = query.strip()
                    if len(query) < 2:
                        raise ValueError("Search query must be at least 2 characters long")
                    
                    result = await asrockind_server.search_products(query)
                    
                    # Format response
                    response_data = {
                        "query": query,
                        "total_results": len(result),
                        "products": result,
                        "search_info": {
                            "source": "ASRock Industrial website",
                            "max_products_per_search": scraping_config.max_products_per_search,
                            "search_method": "Selenium + Fallback (requests)" if not asrockind_server.driver_manager._initialization_failed else "Fallback only (requests)"
                        }
                    }
                    
                    return [TextContent(type="text", text=json.dumps(response_data, indent=2, ensure_ascii=False))]
                else:
                    raise ValueError(f"Unknown tool: {name}")

            except Exception as e:
                logger.error(f"Tool call error: {e}")
                raise McpError(f"Error processing request: {str(e)}")

        # Run server
        logger.info(f"Starting {config.server_name} server...")
        logger.info(f"Configuration: max_products={scraping_config.max_products_per_search}, timeout={scraping_config.page_load_timeout}s")
        options = server.create_initialization_options()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)
            
    finally:
        # Cleanup resources
        logger.info("Shutting down server...")
        asrockind_server.cleanup()


if __name__ == "__main__":
    asyncio.run(serve())

