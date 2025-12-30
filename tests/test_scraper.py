"""Tests for the Google Maps scraper and HTML parser."""

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest
from playwright.sync_api import Locator

from map_crawler.backend.scraper import GoogleMapsScraper, HTMLParser
from map_crawler.config import ScraperSettings
from map_crawler.models import Place

# Configure logging for live and debug tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def settings() -> ScraperSettings:
    """Fixture for scraper settings."""
    return ScraperSettings()


@pytest.fixture
def scraper(settings: ScraperSettings) -> GoogleMapsScraper:
    """Fixture for GoogleMapsScraper."""
    return GoogleMapsScraper(settings)


@pytest.fixture
def parser() -> HTMLParser:
    """Fixture for HTMLParser."""
    return HTMLParser()


class TestScraperInitialization:
    """Tests for scraper initialization and settings."""

    def test_map_scraper_initialization(self, settings: ScraperSettings) -> None:
        """Test that the scraper initializes with correct settings."""
        scraper = GoogleMapsScraper(settings)
        assert scraper.settings.timeout == 10

    def test_scraper_scroll_settings(self, settings: ScraperSettings) -> None:
        """Test that scraper settings are correctly applied."""
        assert settings.max_scrolls == 3
        assert settings.scroll_timeout == 3000

        custom_settings = ScraperSettings(max_scrolls=5, scroll_timeout=5000)
        assert custom_settings.max_scrolls == 5
        assert custom_settings.scroll_timeout == 5000


class TestHTMLParser:
    """Tests for HTMLParser's internal parsing logic."""

    def test_parse_price(self, parser: HTMLParser) -> None:
        """Test parsing price strings into integers."""
        # Accessing private method for testing existing logic is preserved
        p1 = parser._parse_price("₹1,200")
        assert p1 == 1200

        p1 = parser._parse_price("")
        assert p1 is None

    def test_extract_name_simple(self, parser: HTMLParser) -> None:
        """Test extracting place names from HTML chunks."""
        # Test finding the longest quoted string
        chunks = ['\\"Short\\"', '\\"Longer Name\\"', '\\"Tiny\\"']
        assert parser._extract_name(chunks) == "Longer Name"

        # Test reassembling split string
        chunks_split = ['\\"Split', ' Name\\"']
        assert parser._extract_name(chunks_split) == "Split Name"


class TestPlaceExtraction:
    """Tests for extracting place data from Playwright locators."""

    def test_extract_place_data_full(self, scraper: GoogleMapsScraper) -> None:
        """Test extracting full place data from a mock locator."""
        # Mock Entry Locator
        mock_entry = MagicMock(spec=Locator)

        # Mock Link Locator (name and href)
        mock_link = MagicMock(spec=Locator)
        mock_link.get_attribute.side_effect = lambda attr: {
            "aria-label": "Test Place",
            "href": "https://www.google.com/maps/place/Test+Place/@12.9716,77.5946,14z/data=!3d12.9716!4d77.5946",
        }.get(attr)

        # entry.locator(...).first returns mock_link
        mock_entry.locator.return_value.first = mock_link

        # Mock inner_text for rating, reviews, price
        mock_entry.inner_text.return_value = "4.5(1,200) • ₹1,500 for two"

        place = scraper._extract_place_data(mock_entry, 10.0, 10.0)

        assert place is not None
        assert place.description == "Test Place"
        assert place.latitude == 12.9716
        assert place.longitude == 77.5946
        assert place.rating == 4.5
        assert place.raters == 1200
        assert place.price_val == 1500

    def test_extract_place_data_stars_format(self, scraper: GoogleMapsScraper) -> None:
        """Test extracting place data when ratings are in 'stars' format."""
        mock_entry = MagicMock(spec=Locator)
        mock_link = MagicMock(spec=Locator)
        mock_link.get_attribute.side_effect = lambda attr: {
            "aria-label": "Star Place",
            "href": "",
        }.get(attr)
        mock_entry.locator.return_value.first = mock_link

        # "4.2 stars 500 Reviews" format
        mock_entry.inner_text.return_value = "4.2 stars 500 Reviews"

        place = scraper._extract_place_data(mock_entry, 10.0, 10.0)

        assert place is not None
        assert place.rating == 4.2
        assert place.raters == 500
        # Should fall back to defaults for lat/lng
        assert place.latitude == 10.0
        assert place.longitude == 10.0

    def test_extract_place_data_no_name(self, scraper: GoogleMapsScraper) -> None:
        """Test extraction failure when no name is found."""
        mock_entry = MagicMock(spec=Locator)
        mock_link = MagicMock(spec=Locator)
        # No aria-label
        mock_link.get_attribute.return_value = None
        mock_entry.locator.return_value.first = mock_link

        place = scraper._extract_place_data(mock_entry, 0.0, 0.0)
        assert place is None


class TestResultProcessing:
    """Tests for processing and scoring scraped results."""

    def test_process_results_empty(self, scraper: GoogleMapsScraper) -> None:
        """Test that processing an empty list returns an empty DataFrame."""
        df = scraper._process_results([], 0.0, 0.0)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_process_results_basic_fields(self, scraper: GoogleMapsScraper) -> None:
        """Test that basic fields are calculated correctly."""
        places = [
            Place(
                description="Place A",
                rating=5.0,
                raters=100,
                latitude=10.0,
                longitude=10.0,
                price=2,
            )
        ]
        df = scraper._process_results(places, 10.0, 10.0)

        assert not df.empty
        assert len(df) == 1

        expected_cols = ["scaled_rating", "dist", "scaled_dist_rating", "vfm", "composite"]
        for col in expected_cols:
            assert col in df.columns

    def test_deduplication(self, scraper: GoogleMapsScraper) -> None:
        """Test that duplicates are removed based on key attributes."""
        place1 = Place(
            description="Duplicate", rating=4.5, raters=50, latitude=12.0, longitude=77.0, price=1
        )
        # Create identical place
        place2 = Place(
            description="Duplicate", rating=4.5, raters=50, latitude=12.0, longitude=77.0, price=1
        )

        df = scraper._process_results([place1, place2], 12.0, 77.0)
        assert len(df) == 1

    def test_distance_calculation(self, scraper: GoogleMapsScraper) -> None:
        """Test distance calculation logic."""
        # Place at (0, 0), Center at (0, 1)
        # 1 degree longitude at equator is approx 111.32 km
        p1 = Place(
            description="Equator Point", rating=5.0, raters=10, latitude=0.0, longitude=0.0, price=1
        )

        df = scraper._process_results([p1], 0.0, 1.0)
        distance = df.iloc[0]["dist"]

        # Allow some margin for floating point / constant minor diffs
        assert 111.0 < distance < 112.0

    def test_vfm_and_composite_scores(self, scraper: GoogleMapsScraper) -> None:
        """Test relative scoring logic."""
        places = [
            # High rating, low price -> High VFM
            Place(
                description="Best Value", rating=5.0, raters=100, latitude=0, longitude=0, price=1
            ),
            # Low rating, high price -> Low VFM
            Place(
                description="Worst Value", rating=3.0, raters=100, latitude=0, longitude=0, price=4
            ),
            # Median baseline
            Place(description="Average", rating=4.0, raters=100, latitude=0, longitude=0, price=2),
        ]

        df = scraper._process_results(places, 0, 0)

        # Sort by VFM descending
        df_sorted = df.sort_values("vfm", ascending=False)

        assert df_sorted.iloc[0]["description"] == "Best Value"
        assert df_sorted.iloc[-1]["description"] == "Worst Value"

        # Check composite score follows a similar trend (since distance is same for all)
        df_comp_sorted = df.sort_values("composite", ascending=False)
        assert df_comp_sorted.iloc[0]["description"] == "Best Value"

    def test_division_by_zero_guards(self, scraper: GoogleMapsScraper) -> None:
        """Test that the code handles all-zero or missing values gracefully."""
        places = [
            Place(
                description="Zero Raters", rating=5.0, raters=0, latitude=0, longitude=0, price=0
            ),
        ]

        df = scraper._process_results(places, 0, 0)
        # Should not crash, and values should be handled (likely 0 or fallback)
        assert not df.empty
        assert df.iloc[0]["vfm"] >= 0
        assert df.iloc[0]["composite"] >= 0


@pytest.mark.live
def test_live_scrape_new_delhi(scraper: GoogleMapsScraper) -> None:
    """Test scraping 'Restaurant' in New Delhi.

    Verify:
    1. Headers bypass bot detection (server returns data).
    2. JSON parser correctly extracts places.
    """
    # New Delhi Coordinates
    lat = 28.6139
    lng = 77.2090
    term = "Restaurant"

    logger.info(f"Starting live scrape for '{term}' at ({lat}, {lng})...")
    df_results = scraper.scrape(term, lat, lng)

    logger.info(f"Scrape completed. Found {len(df_results)} results.")

    if not df_results.empty:
        print("\n--- First 5 Results ---")
        print(df_results[["description", "rating", "raters"]].head(5))

    assert not df_results.empty, "Scraper returned empty results for guaranteed query."
    assert "description" in df_results.columns, "Missing 'description' column"
    assert "rating" in df_results.columns, "Missing 'rating' column"
