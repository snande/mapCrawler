"""Main application module for Map Crawler."""

import asyncio
import concurrent.futures
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


@st.cache_resource
def install_playwright_browsers() -> None:
    """Installs Playwright browsers if they are missing."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        logger.info("Attempting to install Playwright browsers (chromium)...")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Playwright browsers installed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error installing Playwright browsers: {e.stderr}")
    except Exception as e:
        logger.error(f"Unexpected error installing Playwright browsers: {e}")


# Fix for Playwright on Windows: Force ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from map_crawler.backend.service import MapCrawlerService  # noqa: E402
from map_crawler.config import Settings, get_settings  # noqa: E402
from map_crawler.frontend.components import (  # noqa: E402
    create_scatter_map,
    display_map,
    fetch_and_resize_image,
    render_location_selector,
)
from map_crawler.logger import configure_logging  # noqa: E402

# --- Configuration Loading ---


def load_config() -> Settings:
    """Loads the application configuration.

    Returns:
        Settings: The application settings object.

    Raises:
        RuntimeError: If the configuration cannot be loaded.
    """
    try:
        return get_settings()
    except Exception as e:
        raise RuntimeError(f"Failed to load configuration: {e}") from e


@st.cache_resource
def get_service(_settings: Settings) -> MapCrawlerService:
    """Creates and caches the MapCrawlerService instance.

    Args:
        _settings: The application settings object. Using underscore to prevent
            Streamlit from hashing this object if it's not hashable, though
            Pydantic models usually are.

    Returns:
        MapCrawlerService: The initialized service.
    """
    return MapCrawlerService(_settings)


@st.cache_data(ttl=3600)
def load_cities_data() -> pd.DataFrame:
    """Loads and caches the worldcities.csv data.

    Attempts to locate the 'worldcities.csv' file in standard resource directories relative
    to the project root or the current working directory.

    Returns:
        pd.DataFrame: The cities data loaded from the CSV file.

    Raises:
        FileNotFoundError: If the CSV file cannot be found in any of the expected locations.
    """
    # 1. Try relative to this file (frontend/app.py) -> frontend/../../../resources
    #    This maps to src/map_crawler/frontend/../../../resources => project_root/resources
    base_path = Path(__file__).resolve().parent
    potential_paths = [
        # Ideally: project_root/resources/worldcities.csv
        base_path.parent.parent.parent / "resources" / "worldcities.csv",
        # Fallback: current working directory/resources (if running from root)
        Path.cwd() / "resources" / "worldcities.csv",
    ]

    for path in potential_paths:
        if path.exists():
            try:
                # Specify dtype to efficiently load data and avoid warnings if needed
                return pd.read_csv(path)
            except Exception as e:
                print(f"Error reading {path}: {e}")
                continue

    # If we reach here, no file was found
    raise FileNotFoundError("Could not find worldcities.csv in any expected location.")


# --- Main App Logic ---


def _fetch_result_images(results: pd.DataFrame, limit: int) -> dict[tuple[int, int], Any]:
    """Pre-fetches images for top results concurrently.

    Args:
        results: DataFrame containing the search results. Expected to have 'img_links'
            as a list of strings.
        limit: The number of results to process.

    Returns:
            dict[tuple[int, int], Any]: A dictionary mapping (row_index, img_index) to the
            fetched image object (PIL Image or bytes).
    """
    tasks: dict[tuple[int, int], str] = {}

    for item_num in range(limit):
        row = results.iloc[item_num]
        # We assume img_links is already normalized to a list by the caller
        img_links = row.get("img_links", [])

        # Queue up tasks for the first 4 images of this result
        for j, link in enumerate(img_links[:4]):
            if link:
                tasks[(item_num, j)] = link

    fetched_images: dict[tuple[int, int], Any] = {}

    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_key = {
                executor.submit(fetch_and_resize_image, url): key for key, url in tasks.items()
            }
            for future in concurrent.futures.as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    img = future.result()
                    if img:
                        fetched_images[key] = img
                except Exception:
                    # Ignore image fetching errors to prevent app crash
                    pass
    return fetched_images


def display_backend_results(df: pd.DataFrame, limit: int = 10) -> None:
    """Displays the list of results with details and images.

    This function limits the display to the top `limit` results. It fetches images
    concurrently for all places to improve performance.

    Args:
        df: A pandas DataFrame containing the search results. Expected columns include:
            - description: Name of the place.
            - rating: Actual rating.
            - raters: Number of ratings.
            - scaled_rating: Normalized rating.
            - scaled_dist_rating: Normalized distance rating.
            - dist: Displacement/distance.
            - price: Price estimate.
            - vfm: Value for Money score.
            - composite: Composite score.
            - img_links: Comma-separated string or list of image URLs.
        limit: Maximum number of results to display. Defaults to 10.
    """
    display_limit = min(limit, len(df))
    # Work on a copy to avoid SettingWithCopy warnings if we modify the slice
    results = df.iloc[:display_limit].copy()

    # --- Normalize Image Links ---
    # Ensure 'img_links' is always a list of strings
    def normalize_links(val: Any) -> list[str]:
        if isinstance(val, str):
            # Split by comma and filter empty strings
            return [link.strip() for link in val.split(",") if link.strip()]
        elif isinstance(val, list):
            return val
        return []

    results["img_links"] = results["img_links"].apply(normalize_links)

    # --- Pre-fetch Images Concurrently ---
    fetched_images = _fetch_result_images(results, display_limit)

    # --- Render Results ---
    for item_num in range(display_limit):
        row = results.iloc[item_num]
        name = row.get("description", "Unknown")

        # Use safe URL encoding
        safe_name = urllib.parse.quote_plus(str(name))
        link = f"https://www.google.co.in/maps/search/{safe_name}"

        st.markdown(f"#### {item_num + 1}. [{name}]({link})")

        # Improved layout: 2 equal columns
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Actual Rating**: {row.get('rating', 'N/A')}")
            st.markdown(f"**Raters**: {row.get('raters', 'N/A')}")
            st.markdown(f"**Scaled Rating**: {round(row.get('scaled_rating', 0), 2)}")
            st.markdown(f"**Distance Scaled Rating**: {round(row.get('scaled_dist_rating', 0), 2)}")

        with col2:
            st.markdown(f"**Displacement**: {round(row.get('dist', 0), 2)} km")
            st.markdown(f"**Price Estimate**: {row.get('price', 'N/A')}")
            st.markdown(f"**Value for Money**: {round(row.get('vfm', 0), 2)}")
            st.markdown(f"**Composite Rating**: {round(row.get('composite', 0), 2)}")

        # Display Images
        img_links = row.get("img_links", [])

        # Limit to 4
        display_links = img_links[:4]

        if display_links:
            cols = st.columns(len(display_links))
            for j, _ in enumerate(display_links):
                # Check if we successfully fetched this image
                img = fetched_images.get((item_num, j))
                if img:
                    cols[j].image(img, use_container_width=True)

        st.divider()


def display_data_tabs(df: pd.DataFrame) -> None:
    """Display the analysis tabs for the search results.

    Args:
        df: The pandas DataFrame containing the search results.
    """
    tabs = st.tabs(
        [
            "Map View",
            "Best Places by Rating",
            "Best Places by Distance",
            "Best Places by Value for Money",
            "Best Places by Composite Rating",
            "Raw Data",
        ]
    )

    # --- Tab 0: Map View ---
    with tabs[0]:
        fig = create_scatter_map(df)
        try:
            # Attempt to use modern parameters if supported
            # using width="stretch" as recommended by newer Streamlit versions for full width
            st.plotly_chart(
                fig,
                key="map",
                on_select="ignore",
                selection_mode="points",
                use_container_width=True,
            )
        except TypeError:
            # Fallback for older Streamlit versions
            st.plotly_chart(fig, use_container_width=True)

    # --- Tabs 1-4: Ranked Lists ---
    # Define mapping of tab index to sort column
    # Tab 1: Rating, Tab 2: Distance, Tab 3: VFM, Tab 4: Composite
    sort_metrics = [
        (1, "scaled_rating"),
        (2, "scaled_dist_rating"),
        (3, "vfm"),
        (4, "composite"),
    ]

    for tab_idx, sort_col in sort_metrics:
        with tabs[tab_idx]:
            # Sort dataframe by the metric and display
            sorted_df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
            display_backend_results(sorted_df)

    # --- Tab 5: Raw Data ---
    with tabs[5]:
        st.dataframe(df)


def _init_session_state() -> None:
    """Initialize session state variables with default values.

    Ensures that necessary session state keys exist, such as 'refresh', 'lat',
    'lng', and 'zoom'.
    """
    if "refresh" not in st.session_state:
        st.session_state.refresh = False

    # Defaults: Lat/Lng for user ease (e.g., India center)
    if "lat" not in st.session_state:
        st.session_state["lat"] = 22.59
        st.session_state["lng"] = 79.75
        st.session_state["zoom"] = 4


def _resolve_coordinates(
    inp_mode: str,
    text_input: str,
    city_lat: float,
    city_lng: float,
    map_data: dict[str, Any] | None,
) -> tuple[float, float] | None:
    """Resolves the latitude and longitude based on the input mode.

    Args:
        inp_mode: The selected input mode ("Text", "List", "Map").
        text_input: The text input for "Near" search.
        city_lat: The latitude of the selected city.
        city_lng: The longitude of the selected city.
        map_data: The data returned from the map component.

    Returns:
        tuple[float, float] | None: The resolved (lat, lng) tuple, or None if validation fails.
    """
    if inp_mode == "Text":
        return _parse_coordinates(text_input)
    elif inp_mode == "List":
        return city_lat, city_lng
    elif inp_mode == "Map":
        if map_data and "center" in map_data:
            return map_data["center"]["lat"], map_data["center"]["lng"]
        st.warning("Map center not available. Please pan the map.")
        return None
    return None


def _parse_coordinates(input_str: str) -> tuple[float, float] | None:
    """Parses a string input "lat, lng" into a tuple of floats.

    Args:
        input_str: A string containing comma-separated latitude and longitude.

    Returns:
        tuple[float, float] | None: A tuple (lat, lng) if parsing is successful,
        None otherwise. Displays an error in Streamlit if parsing fails.
    """
    try:
        parts = input_str.split(",")
        if len(parts) != 2:
            raise ValueError("Exactly two comma-separated values required.")
        lat = float(parts[0].strip())
        lng = float(parts[1].strip())
        return lat, lng
    except (ValueError, IndexError):
        st.error("Invalid coordinates format. Please provide 'lat, lng'.")
        return None


def main() -> None:
    """Entry point for the application.

    Checks if running within Streamlit and relaunches if necessary.
    """
    if st.runtime.exists():
        _main_app_logic()
    else:
        import sys

        from streamlit.web import cli as stcli

        sys.argv = ["streamlit", "run", __file__] + sys.argv[1:]
        sys.exit(stcli.main())


def _main_app_logic() -> None:
    """Core logic for the Streamlit application."""
    st.set_page_config(layout="wide", page_title="Map Crawler")
    configure_logging()
    install_playwright_browsers()
    st.title("Map Crawler Refactored")

    # --- Initialization ---
    try:
        settings = load_config()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    service = get_service(settings)
    _init_session_state()

    try:
        df_cities = load_cities_data()
    except FileNotFoundError:
        st.error("Could not find 'worldcities.csv' in resources.")
        st.stop()

    # --- UI Layout ---
    col1, col2 = st.columns([1, 3])

    # Left Column: Inputs
    with col1:
        search_for = st.text_input("Search For:", "Restaurant")
        city_lat, city_lng = render_location_selector(df_cities)
        search_near = st.text_input("Near (Text search)")
        st.write("Get Coordinates from:")
        inp_mode = st.radio("Select Coordinates Input Mode", ["Text", "List", "Map"])

    # Right Column: Map and Results
    with col2:
        map_data = display_map(st.session_state["lat"], st.session_state["lng"])
        if st.button("Center map over city"):
            st.session_state["lat"] = city_lat
            st.session_state["lng"] = city_lng
            st.rerun()

    # Resolve Coordinates
    lat_lng = _resolve_coordinates(inp_mode, search_near, city_lat, city_lng, map_data)

    if lat_lng:
        lat_search, lng_search = lat_lng
        # Show what we are searching near
        if search_for:
            st.divider()
            st.subheader(f"Searching for '{search_for}' near ({lat_search:.3f}, {lng_search:.3f})")

    # --- Search Execution ---
    if lat_lng and search_for:
        clicked = st.button("Search")

        if clicked or st.session_state.refresh:
            force_refresh = st.session_state.refresh
            if force_refresh:
                st.info("Refreshing data...")
            st.session_state.refresh = False

            progress_bar = st.progress(0)

            lat_search, lng_search = lat_lng

            df_results, is_cached = service.search_places(
                term=search_for,
                lat=lat_search,
                lng=lng_search,
                force_refresh=force_refresh,
                progress_callback=lambda x: progress_bar.progress(x),
            )

            progress_bar.empty()

            if df_results.empty:
                st.warning("No results found.")
            else:
                display_data_tabs(df_results)
                if st.button("Refresh Data"):
                    st.session_state.refresh = True
                    st.rerun()


if __name__ == "__main__":
    main()
