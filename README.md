# Map Crawler

A structured Streamlit application for scraping and visualizing map data.

## Overview

This project refactors a legacy map scraper into a clean, modular Python application. It allows users to search for places on Google Maps, scrape details like ratings and estimated prices, and visualize them on an interactive map.

## Features

- **Search**: Scrape data from Google Maps for specific categories (e.g., Restaurants).
- **Visualization**: Interactive map with markers colored by rating.
- **Filtering**: Sort results by rating, distance, value for money, etc.
- **Storage**: Caches results in Azure Blob Storage.

## Setup

1.  **Install dependencies**:
    ```bash
    poetry install
    ```

2.  **Configuration**:
    Create a `.env` file with the following variables:
    ```env
    DATABASE__CONNECTION_STRING="your_connection_string"
    DATABASE__CONTAINER_NAME="your_container_name"
    DATABASE__MASTER_SEARCH_FILE_NAME="master_search.json"
    ```

3.  **Run the app**:
    ```bash
    poetry run streamlit run src/map_crawler/app.py
    ```

## Development

- **Linting**: `poetry run ruff check .`
- **Testing**: `poetry run pytest`
