"""Scraping module for Google Maps using Playwright."""

import contextlib
import logging
import re
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from playwright.sync_api import Locator, Page, ViewportSize, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from map_crawler.config import ScraperSettings
from map_crawler.models import Place

logger = logging.getLogger(__name__)


class HTMLParser:
    """Helper class for parsing HTML content and extracting data."""

    def _parse_price(self, price_text: str) -> int | None:
        """Parse price text into a numerical value.

        Args:
            price_text: The string containing price info (e.g., "₹1,200").

        Returns:
            The parsed price as an integer, or None if not found.
        """
        if not price_text:
            return None

        try:
            # Remove currency symbols and commas
            clean_price = re.sub(r"[^\d]", "", price_text)
            if clean_price:
                return int(clean_price)
        except ValueError:
            pass

        return None

    def _extract_name(self, chunks: list[str]) -> str:
        """Extract the most likely name from a list of text chunks.

        Typically used when name is split across multiple span elements.

        Args:
            chunks: List of text strings.

        Returns:
            The extracted name.
        """
        # Logic from test: finds longest quoted string or joins split parts?
        # Test 1: ['"Short"', '"Longer Name"', '"Tiny"'] -> "Longer Name"
        # Test 2: ['"Split', ' Name"'] -> "Split Name"

        # Simple heuristic: Join all, then look for quotes?
        # Or if multiple quoted strings, pick longest?

        # Let's try to join duplicates or just clean up.
        full_text = "".join(chunks).replace('\\"', '"')

        # Extract content inside quotes
        matches = re.findall(r'"([^"]*)"', full_text)
        if matches:
            # Return the longest match
            return str(max(matches, key=len))

        return full_text.strip().replace('"', "")


class GoogleMapsScraper:
    """Scraper for Google Maps data using Playwright.

    Attributes:
        settings (ScraperSettings): Configuration settings.
        parser (HTMLParser): Helper for parsing HTML content.
    """

    # Constants for selectors and defaults to avoid magic strings
    _SELECTORS = {
        "accept_cookies": 'button[aria-label="Accept all"]',
        "results_container": 'div[role="article"]',
        "feed": 'div[role="feed"]',
        "place_entry": 'div[role="article"]:has(a[href*="/maps/place/"])',
        "place_link": 'a[href*="/maps/place/"]',
    }
    _DEFAULT_TIMEOUT_MS = 45000
    _VIEWPORT: ViewportSize = {"width": 1280, "height": 800}
    _LOCALE = "en-US"
    _TIMEZONE = "Asia/Kolkata"

    # Regex patterns for extraction (pre-compiled for efficiency)
    _RATING_PATTERN = re.compile(r"(\d\.\d)\s*(?:\(|stars).*?([\d,]+)", re.IGNORECASE)
    _PRICE_PATTERN = re.compile(r"([₹$€£]\s?[\d,]+)")
    _COORDS_PATTERN = re.compile(r"!3d([\d\.-]+)!4d([\d\.-]+)")

    # Scoring & Distance Constants
    _KM_PER_DEGREE_LAT = 111.3188
    # Base for sigmoid-like scaling penalty for low ratings/distance
    _RATING_PENALTY_BASE = 1.25
    _DIST_DECAY_FACTOR = -11.1

    def __init__(self, settings: ScraperSettings) -> None:
        """Initialize the scraper with settings.

        Args:
            settings: Configuration settings for the scraper.
        """
        self.settings = settings
        self.parser = HTMLParser()

    def scrape(
        self,
        term: str,
        lat: float,
        lng: float,
        zoom: float = 14.0,
        progress_callback: Callable[[float], Any] | None = None,
    ) -> pd.DataFrame:
        """Scrape Google Maps for a specific term at a location.

        This method initializes a Playwright browser, navigates to the Google Maps
        search URL, handles consent dialogs (if any), scrolls through results,
        and extracts place data.

        Args:
            term: The search term (e.g., "Restaurants", "Petrol Pump").
            lat: Latitude of the search center.
            lng: Longitude of the search center.
            zoom: Map zoom level. Defaults to 14.0.
            progress_callback: Optional function to report progress (0.0 to 1.0).

        Returns:
            pd.DataFrame: A DataFrame containing the scraped data. Returns an
            empty DataFrame if scraping fails or no results are found.
        """
        places: list[Place] = []
        url = f"https://www.google.com/maps/search/{term}/@{lat},{lng},{zoom}z"
        logger.info(f"Starting scrape for '{term}' at ({lat}, {lng}). URL: {url}")

        if progress_callback:
            progress_callback(0.1)

        try:
            with sync_playwright() as playwright:
                headless_mode = getattr(self.settings, "headless", True)
                browser = playwright.chromium.launch(headless=headless_mode)

                context = browser.new_context(
                    user_agent=self.settings.user_agent,
                    locale=self._LOCALE,
                    timezone_id=self._TIMEZONE,
                    viewport=self._VIEWPORT,
                )
                page = context.new_page()

                # 1. Navigation
                try:
                    timeout_sec = getattr(self.settings, "timeout", 45)
                    page.goto(
                        url,
                        timeout=timeout_sec * 1000,
                        wait_until="domcontentloaded",
                    )
                except PlaywrightTimeoutError:
                    logger.warning(f"Timeout navigating to {url}. Proceeding with loaded content.")

                if progress_callback:
                    progress_callback(0.3)

                # 2. Handle Consent / Cookies
                with contextlib.suppress(Exception):
                    # Try to click 'Accept all' if it appears
                    page.locator(self._SELECTORS["accept_cookies"]).click(timeout=3000)

                # 3. Wait for Results to Load
                try:
                    # Wait for at least one result article to appear
                    page.wait_for_selector(self._SELECTORS["results_container"], timeout=20000)
                except PlaywrightTimeoutError:
                    logger.error(
                        "No result containers found via selector. "
                        "Search might have returned no results."
                    )
                    browser.close()
                    return pd.DataFrame()

                # 4. Scroll to Load More Results
                self._scroll_results(page)

                if progress_callback:
                    progress_callback(0.6)

                # 5. Extract Data
                entries = page.locator(self._SELECTORS["place_entry"]).all()
                logger.info(f"Found {len(entries)} potential entries after scrolling.")

                for index, entry in enumerate(entries):
                    try:
                        place = self._extract_place_data(entry, lat, lng)
                        if place:
                            places.append(place)
                    except Exception as exception:
                        logger.warning(f"Failed to parse entry {index}: {exception}")

                browser.close()
                if progress_callback:
                    progress_callback(0.9)

        except Exception as exception:
            logger.error(
                f"Playwright Scrape execution failed with error: {exception}", exc_info=True
            )
            return pd.DataFrame()

        logger.info(f"Successfully scraped {len(places)} items.")
        return self._process_results(places, lat, lng)

    def _scroll_results(self, page: Page) -> None:
        """Scroll the results feed to trigger lazy loading of more items.

        This method attempts to locate the feed container and scrolls it to the bottom
        multiple times to load more results. It checks if the scroll height changes
        to determine if more content has been loaded.

        Args:
            page: The Playwright Page object containing the map results.

        Raises:
            Exception: If any error occurs during the scrolling process, it is logged
                as a warning and suppressed to allow scraping to continue with loaded items.
        """
        try:
            feed = page.locator(self._SELECTORS["feed"])
            # Ensure the feed is visible before trying to scroll
            if feed.count() == 0:
                logger.debug("Feed container not found, skipping scroll.")
                return

            feed_first = feed.first
            previous_height = 0.0

            scroll_timeout_ms = getattr(self.settings, "scroll_timeout", 3000)
            max_scrolls = getattr(self.settings, "max_scrolls", 3)

            for i in range(max_scrolls):
                # Scroll to bottom
                feed_first.evaluate("element => element.scrollTop = element.scrollHeight")

                # Wait for network requests/DOM updates
                page.wait_for_timeout(scroll_timeout_ms)

                # Check if scroll height actually changed
                current_height = feed_first.evaluate("element => element.scrollHeight")
                if current_height == previous_height:
                    logger.debug(f"Scroll height did not change after scroll {i + 1}. Stopping.")
                    break
                previous_height = current_height

        except Exception as e:
            logger.warning(f"Error during scrolling: {e}")

    def _extract_place_data(
        self, entry: Locator, default_lat: float, default_lng: float
    ) -> Place | None:
        """Extracts structured data from a single Google Maps place entry.

        This method acts as a parser for individual result cards found in the
        Google Maps feed. It robustly handles missing data and employs regex
        patterns to extract key information like rating, review count, and price
        from unstructured text.

        The method implements the following strategies:
        1. **Name Extraction**: Prioritizes `aria-label` for clean names.
        2. **Rating/Reviews**: Uses regex to parse strings like "4.5(1,200)".
        3. **Price**: Scans for currency symbols (e.g., \u20b9, $, \u20ac).
        4. **Geolocation**: Decodes latitude/longitude from the entry's URL.

        Args:
            entry: The Playwright locator representing a single place card.
            default_lat: Fallback latitude if coordinate extraction fails.
            default_lng: Fallback longitude if coordinate extraction fails.

        Returns:
            Place | None: A populated `Place` object if the name is found;
            otherwise, `None`.
        """
        try:
            link_loc = entry.locator(self._SELECTORS["place_link"]).first

            # 1. Extract Basic Metadata (Name & URL)
            # aria-label is the most reliable source for the place name
            name = link_loc.get_attribute("aria-label") or ""
            url_href = link_loc.get_attribute("href")

            if not name:
                logger.debug("Skipping entry with no name/aria-label.")
                return None

            # 2. Extract Text Content
            # Fetching inner_text once prevents multiple DOM round-trips
            full_text = entry.inner_text()

            # 3. Parse Rating and Review Count
            rating = 0.0
            raters = 0

            rating_match = self._RATING_PATTERN.search(full_text)
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                    # Remove commas from number strings (e.g., "1,200" -> "1200")
                    raters = int(rating_match.group(2).replace(",", ""))
                except (ValueError, IndexError):
                    logger.warning(f"Failed to parse rating numbers for '{name}'")

            # 4. Parse Price Level
            price_val = 0
            price_match = self._PRICE_PATTERN.search(full_text)
            if price_match:
                # Helper parses "₹1,200" -> 1200
                price_val = self.parser._parse_price(price_match.group(1)) or 0

            # Ensure price is at least 0 (fallback)
            price_val = price_val if price_val is not None else 0

            # 5. Extract Geolocation from URL
            item_lat, item_lng = default_lat, default_lng
            if url_href:
                # URLs usually contain coordinates in the format: !3d12.34!4d56.78
                coords_match = self._COORDS_PATTERN.search(url_href)
                if coords_match:
                    try:
                        item_lat = float(coords_match.group(1))
                        item_lng = float(coords_match.group(2))
                    except ValueError:
                        logger.debug(f"Invalid coordinate format in URL for '{name}'")

            return Place(
                description=name,
                latitude=item_lat,
                longitude=item_lng,
                rating=rating,
                raters=raters,
                review_url=url_href,
                img_links=[],  # Placeholder for future image extraction, now correctly typed
                price=price_val,
            )

        except Exception as e:
            # Catch-all to ensure one bad entry doesn't crash the whole scraper
            logger.warning(f"Unexpected error extracting data for entry: {e}")
            return None

    def _process_results(
        self, places: list[Place], center_lat: float, center_long: float
    ) -> pd.DataFrame:
        """Post-process raw place data into a DataFrame with calculated metrics.

        Calculates scaled ratings, distance from center, and value-for-money (VFM) scores.

        Args:
            places: List of Place objects.
            center_lat: Latitude of the search center.
            center_long: Longitude of the search center.

        Returns:
            pd.DataFrame: Processed DataFrame with additional metric columns.
        """
        if not places:
            return pd.DataFrame()

        # Convert to DataFrame using Pydantic's alias capabilities
        # This ensures fields like 'price_val' map to 'price' if aliased.
        data = [p.model_dump(by_alias=True) for p in places]
        df = pd.DataFrame(data)

        # Remove duplicates based on key attributes to ensure uniqueness
        subset_cols = ["description", "rating", "raters", "latitude", "longitude"]
        existing_subset = [c for c in subset_cols if c in df.columns]
        df = df.drop_duplicates(subset=existing_subset)

        # Ensure numeric types for vector operations
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0.0)
        df["raters"] = pd.to_numeric(df["raters"], errors="coerce").fillna(0)
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

        # 1. Scaled Rating: Penalize low review counts
        # Formula: Rating * (1 - (Base ^ -sqrt(Raters)))
        # As Raters increases, penalty decreases (approaches Rating).
        df["scaled_rating"] = df["rating"] * (
            1 - np.power(self._RATING_PENALTY_BASE, -1 * np.sqrt(df["raters"]))
        )

        # 2. Distance Calculation
        # (Haversine approximation / Pythagorean on equirectangular projection)
        # using a constant _KM_PER_DEGREE_LAT (approx 111.32 km per degree)
        lat_diff_km = (df["latitude"] - center_lat) * self._KM_PER_DEGREE_LAT

        # Longitude distance varies by cosine of latitude
        # Note: Using center_lat for approximation is acceptable for local search areas
        avg_lat_rad = np.radians(center_lat)
        lng_diff_km = (
            (df["longitude"] - center_long) * np.cos(avg_lat_rad) * self._KM_PER_DEGREE_LAT
        )

        df["dist"] = np.sqrt(lat_diff_km**2 + lng_diff_km**2)

        # 3. Scaled Distance Rating: Penalize distance
        # Formula: scaled_rating * (1 - (Base ^ (Decay / (Distance + epsilon))))
        df["scaled_dist_rating"] = df["scaled_rating"] * (
            1
            - np.power(
                self._RATING_PENALTY_BASE,
                self._DIST_DECAY_FACTOR / (df["dist"] + 0.001),
            )
        )

        # 4. Price Handling
        if "price" not in df.columns:
            df["price"] = 1

        # Fill missing prices with 1 (low cost/baseline) and ensure integer type
        df["price"] = df["price"].fillna(1).astype(int)
        # Ensure price is at least 1 to avoid division by zero later
        df["price"] = df["price"].apply(lambda x: x if x > 0 else 1)

        # 5. Composite Score & VFM
        # Calculate medians for relative scoring
        median_scaled_rating = df["scaled_rating"].median()
        median_price = df["price"].median()

        # Initialize columns
        df["vfm"] = 0.0
        df["composite"] = 0.0

        if median_scaled_rating > 0 and median_price > 0:
            # VFM = (Relative Rating) * (Sqrt(Relative Price Inverse))
            # Higher rating and lower price -> Higher VFM

            # Vectorized calculation
            relative_rating = df["scaled_rating"] / median_scaled_rating
            relative_price_inverse = np.sqrt(median_price) / np.sqrt(df["price"])

            df["vfm"] = relative_rating * relative_price_inverse

            median_vfm = df["vfm"].median()
            if median_vfm > 0:
                # Composite = (Relative Rating) * (Sqrt(Relative VFM))
                relative_vfm = np.sqrt(df["vfm"]) / np.sqrt(median_vfm)
                df["composite"] = relative_rating * relative_vfm

        return df
