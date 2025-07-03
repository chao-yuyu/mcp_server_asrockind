"""Configuration settings for ASRock Industrial MCP Server."""

import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ScrapingConfig:
    """Configuration for web scraping behavior."""
    
    # Timeout settings (in seconds)
    page_load_timeout: int = 15
    element_wait_timeout: int = 10
    implicit_wait: int = 3
    
    # Retry settings
    max_retries: int = 2
    retry_delay_min: float = 2.0
    retry_delay_max: float = 4.0
    
    # Product limits
    max_products_per_search: int = 3
    
    # Delay settings (in seconds)
    search_delay_min: float = 1.0
    search_delay_max: float = 2.0
    product_delay_min: float = 1.0
    product_delay_max: float = 2.0
    
    # Chrome options
    chrome_options: List[str] = None
    
    def __post_init__(self):
        if self.chrome_options is None:
            self.chrome_options = [
                '--headless',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-images',
                '--disable-javascript',
                '--disable-plugins',
                '--disable-extensions',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-popup-blocking',
                '--disable-infobars',
                '--disable-notifications',
                '--window-size=1920,1080',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            ]


@dataclass
class ServerConfig:
    """Configuration for MCP server behavior."""
    
    # Server identification
    server_name: str = "mcp-asrockind"
    
    # Base URL for ASRock Industrial
    base_url: str = "https://www.asrockind.com"
    
    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Debug settings
    save_debug_html: bool = False
    debug_html_path: str = "debug_pages"


# Global configuration instance
config = ServerConfig()
scraping_config = ScrapingConfig()


def get_config() -> ServerConfig:
    """Get the global server configuration."""
    return config


def get_scraping_config() -> ScrapingConfig:
    """Get the global scraping configuration."""
    return scraping_config


def update_config_from_env():
    """Update configuration from environment variables."""
    global config, scraping_config
    
    # Server config from environment
    config.server_name = os.getenv("MCP_SERVER_NAME", config.server_name)
    config.base_url = os.getenv("ASROCK_BASE_URL", config.base_url)
    config.log_level = os.getenv("LOG_LEVEL", config.log_level)
    config.save_debug_html = os.getenv("SAVE_DEBUG_HTML", "false").lower() == "true"
    
    # Scraping config from environment
    scraping_config.page_load_timeout = int(os.getenv("PAGE_LOAD_TIMEOUT", scraping_config.page_load_timeout))
    scraping_config.max_retries = int(os.getenv("MAX_RETRIES", scraping_config.max_retries))
    scraping_config.max_products_per_search = int(os.getenv("MAX_PRODUCTS", scraping_config.max_products_per_search))


# Initialize configuration from environment
update_config_from_env() 