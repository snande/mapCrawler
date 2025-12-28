"""Module for the Map Crawler service business logic.

This module provides the core service class `MapCrawlerService` which orchestrates
the interaction between the scraper, storage, and caching mechanisms.
"""

import logging
import time
import uuid
from collections.abc import Callable
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd

from map_crawler.backend.scraper import GoogleMapsScraper
from map_crawler.backend.storage import AzureStorage
from map_crawler.config import Settings

# Create a module-level logger
logger = logging.getLogger(__name__)

# Constants
RESULTS_PATH_PREFIX = "projects/mapCrawler/data/result"


class MapCrawlerService:
    """Core business logic for the Map Crawler service.

    This service orchestrates the search process by managing caching via
    Azure Blob Storage and scraping via GoogleMapsScraper. It attempts to
    serve requests from a persistent cache before falling back to live scraping.

    Attributes:
        settings (Settings): Application configuration settings.
        storage (AzureStorage): Interface for Azure Blob Storage operations.
        scraper (GoogleMapsScraper): Interface for scraping Google Maps.
        master_data (pd.DataFrame): In-memory cache of the master search index.
        delta_lat (float): Latitude delta for spatial cache matching.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the MapCrawlerService.

        Args:
            settings: Application configuration object containing database
                and scraper settings.
        """
        self.settings = settings
        self.storage = AzureStorage(settings.database)
        self.scraper = GoogleMapsScraper(settings.scraper)
        self.master_data = self.storage.load_master_search_data()

        # Grid matching threshold
        self.delta_lat = settings.scraper.delta_lat

    def search_places(
        self,
        term: str,
        lat: float,
        lng: float,
        force_refresh: bool = False,
        progress_callback: Callable[[float], Any] | None = None,
    ) -> tuple[pd.DataFrame, bool]:
        """Search for places matching the term at the given coordinates.

        The method first checks the persistent cache for existing results within
        the configured spatial delta. If found and valid, cached data is return.
        Otherwise, it triggers a live scrape.

        Args:
            term: The search term (e.g., "restaurants").
            lat: Latitude of the search center.
            lng: Longitude of the search center.
            force_refresh: If True, bypass cache and force a new scrape.
            progress_callback: Optional callback for progress updates.

        Returns:
            A tuple containing:
                - pd.DataFrame: The search results.
                - bool: True if data was served from cache, False otherwise.
        """
        search_query = term.strip().lower().replace(" ", "+")

        # 1. Attempt to retrieve from cache
        if not force_refresh:
            cached_key = self._find_cached_key(search_query, lat, lng)
            if cached_key:
                logger.info(f"Cache hit for query='{search_query}' at ({lat}, {lng})")
                try:
                    df = self._load_from_cache(cached_key)
                    if self._validate_dataframe(df):
                        return df, True
                    logger.warning(
                        f"Cached data for key '{cached_key}' is invalid/empty. Re-crawling."
                    )
                except Exception as exception:
                    logger.error(f"Failed to load cache for key '{cached_key}': {exception}")
                    # Fallback to scrape on cache failure

        # 2. Scrape live data
        logger.info(f"Scraping live data for query='{search_query}' at ({lat}, {lng})")
        df_results = self.scraper.scrape(
            term=search_query,
            lat=lat,
            lng=lng,
            progress_callback=progress_callback,
        )

        # 3. Save results and update master index
        if not df_results.empty:
            self._save_results_and_update_index(df_results, search_query, lat, lng)

        return df_results, False

    def _find_cached_key(self, search_query: str, lat: float, lng: float) -> str | None:
        """Find a matching cache key in the master data index.

        It searches for a previous query that matches the search term and is
        within the `delta_lat` and calculated `delta_long` distance.

        Args:
            search_query: The normalized search query string.
            lat: Latitude of the location.
            lng: Longitude of the location.

        Returns:
            The cache key string if found, otherwise None.
        """
        if self.master_data.empty:
            return None

        # Calculate longitude delta based on current latitude
        # delta_long approx = delta_lat / cos(latitude)
        # We must clamp cosine to avoid division by zero near poles.
        cos_lat = np.cos(np.radians(lat))
        delta_long = self.delta_lat / max(abs(cos_lat), 1e-6)

        # Vectorized filtering
        mask = (
            (self.master_data["Search"] == search_query)
            & ((self.master_data["Latitude"] - lat).abs() <= self.delta_lat)
            & ((self.master_data["Longitude"] - lng).abs() <= delta_long)
        )

        matches = self.master_data.loc[mask, "Key"]

        if not matches.empty:
            # Return the first match (most recent or arbitrary)
            return str(matches.values[0])

        return None

    def _load_from_cache(self, key: str) -> pd.DataFrame:
        """Load result dataframe from blob storage.

        Args:
            key: The unique key for the cached result file.

        Returns:
            pd.DataFrame: The loaded data.

        Raises:
            Exception: Propagates exceptions from storage or pandas if load fails.
        """
        result_file = f"{RESULTS_PATH_PREFIX}/{key}.json"
        data = self.storage.download_blob(result_file)
        return pd.read_json(BytesIO(data))

    def _validate_dataframe(self, df: pd.DataFrame) -> bool:
        """Validate that the dataframe has the required columns and is not empty.

        Args:
            df: The DataFrame to check.

        Returns:
            bool: True if valid, False otherwise.
        """
        if df.empty:
            return False

        required_cols = {"description", "latitude", "longitude", "rating", "raters"}
        return required_cols.issubset(df.columns)

    def _save_results_and_update_index(
        self, df: pd.DataFrame, search_query: str, lat: float, lng: float
    ) -> None:
        """Save results to storage and update the master search index.

        Args:
            df: The DataFrame containing scan results.
            search_query: The normalized search query used.
            lat: Latitude of the search.
            lng: Longitude of the search.
        """
        # Generate a unique key
        new_key = uuid.uuid4().hex
        result_file = f"{RESULTS_PATH_PREFIX}/{new_key}.json"

        try:
            # 1. Upload the result blob
            self.storage.upload_blob(result_file, df.to_json())
            logger.info(f"Uploaded result blob: {result_file}")

            # 2. Update in-memory master data
            new_entry = {
                "Search": search_query,
                "Latitude": float(lat),
                "Longitude": float(lng),
                "Time": time.time(),
                "Key": new_key,
            }

            # Use concat for better performance than append (deprecated)
            new_row_df = pd.DataFrame([new_entry])
            self.master_data = pd.concat([self.master_data, new_row_df], ignore_index=True)

            # 3. Persist updated master data to storage
            # We assume master_search_file_name acts as the registry
            master_file_name = self.settings.database.master_search_file_name
            self.storage.upload_blob(master_file_name, self.master_data.to_json())
            logger.info(f"Updated master index: {master_file_name}")

        except Exception as e:
            logger.error(f"Failed to save results or update index: {e}")
            # Consider if we should raise here or suppress. Suppressing to keep service alive.
