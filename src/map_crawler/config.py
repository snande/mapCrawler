"""Configuration settings for the MapCrawler application.

This module defines the configuration settings for the MapCrawler application, including
database connection details and scraper settings. It uses Pydantic's BaseSettings for
environment variable management.
"""

from functools import lru_cache

from pydantic import BaseModel, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Azure Blob Storage connection details.

    Attributes:
        connection_string: The connection string for the Azure Blob Storage account.
        container_name: The name of the container where data will be stored.
        master_search_file_name: The name of the file containing master search results.
    """

    connection_string: str = Field(..., description="Azure Blob Storage connection string")
    container_name: str = Field(..., description="Container name")
    master_search_file_name: str = Field(
        "master_search.json", description="Master search file name"
    )


class ScraperSettings(BaseModel):
    """Settings for the Google Maps scraper.

    Attributes:
        timeout: Request timeout in seconds.
        retries: Number of retries for failed requests.
        delta_lat: Latitude step for grid generation.
        max_scrolls: Maximum number of scrolls to load results.
        scroll_timeout: Timeout in milliseconds to wait after scrolling.
        user_agent: User-Agent string to use for requests.
    """

    timeout: int = Field(10, description="Request timeout in seconds")
    retries: int = Field(3, description="Number of retries for failed requests")
    # delta_lat of 0.022 is approximately 2.5km, suitable for local search grids.
    delta_lat: float = Field(0.022, description="Latitude step for grid generation")
    max_scrolls: int = Field(3, description="Maximum number of scrolls to load results")
    scroll_timeout: int = Field(3000, description="Timeout in milliseconds to wait after scrolling")

    # Headers
    user_agent: str = Field(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        description="User-Agent string",
    )

    @computed_field
    def headers(self) -> dict[str, str]:
        """Return the headers dictionary.

        Returns:
            A dictionary containing the HTTP headers to be used in scraper requests.
        """
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en,en-IN;q=0.9,en-US;q=0.8,hi;q=0.7",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
            ),
            "DNT": "1",
            "Connection": "close",
            "Upgrade-Insecure-Requests": "1",
        }


class LoggingSettings(BaseModel):
    """Logging configuration settings.

    Attributes:
        level: The logging level (e.g., INFO, DEBUG).
        format: The log message format string.
    """

    level: str = Field("INFO", description="Logging level")
    format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format",
    )


class Settings(BaseSettings):
    """Global application settings.

    This class loads settings from environment variables and provides a structured
    access to them.

    Attributes:
        database: Database configuration settings.
        scraper: Scraper configuration settings.
        logging: Logging configuration settings.
    """

    database: DatabaseSettings
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of the settings.

    This function returns a singleton instance of the Settings class, cached
    using lru_cache to avoid reloading environment variables on every call.

    Returns:
        The global Settings instance.
    """
    return Settings()
