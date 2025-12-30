# Map Crawler

A structured Streamlit application for scraping and visualizing map data.

## Overview

This project refactors a legacy map scraper into a clean, modular Python application. It allows users to search for places on Google Maps, scrape details like ratings and estimated prices, and visualize them on an interactive map.

## Features

- **Search**: Scrape data from Google Maps for specific categories (e.g., Restaurants) using Playwright.
- **Visualization**: Interactive map with markers and heatmap using Plotly and Folium.
- **Filtering**: Sort results by rating, distance, price estimate, and composite scores.
- **Storage**: Caches results in Azure Blob Storage with spatial-based cache matching.
- **Concurrency**: Fast image pre-fetching using thread pools for better UX.

## Project Structure

- `src/map_crawler/frontend/`: Streamlit UI and components.
- `src/map_crawler/backend/`: Scraper, storage, and service logic.
- `src/map_crawler/models.py`: Data models using Pydantic.
- `src/map_crawler/config.py`: Environment-based configuration.
- `resources/`: Static data like `worldcities.csv`.

## Setup

1.  **Install dependencies**:
    ```bash
    poetry install
    ```

2.  **Configuration**:
    Create a `.env` file with the following mandatory variables:
    ```env
    # Database Settings
    DATABASE__CONNECTION_STRING="your_azure_connection_string"
    DATABASE__CONTAINER_NAME="your_container_name"
    DATABASE__MASTER_SEARCH_FILE_NAME="master_search.json"

    # Scraper Settings (Optional, defaults provided in config.py)
    SCRAPER__MAX_SCROLLS=3
    SCRAPER__TIMEOUT=10
    ```

3.  **Install Playwright Browsers**:
    ```bash
    poetry run playwright install chromium
    ```

4.  **Run the app**:
    ```bash
    poetry run streamlit run src/map_crawler/frontend/app.py
    ```

## Development

- **Linting**: `poetry run ruff check .`
- **Typing**: `poetry run mypy .`
- **Testing**: `poetry run pytest`
