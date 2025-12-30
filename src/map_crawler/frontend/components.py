"""Frontend components for the Map Crawler application.

This module contains reusable UI components for the Streamlit interface,
including map displays and image processing utilities.
"""

from io import BytesIO
from typing import Any, cast

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from PIL import Image, ImageOps
from streamlit_folium import st_folium


def render_location_selector(df_cities: pd.DataFrame) -> tuple[float, float]:
    """Renders the Country -> State -> City selection sidebar widgets.

    Args:
        df_cities: DataFrame containing city data with columns 'country',
            'admin_name', 'city_ascii', 'lat', and 'lng'.

    Returns:
        A tuple containing (latitude, longitude) of the selected city.
    """
    # Country Selection
    country_list = sorted(df_cities["country"].unique())
    default_country = "India" if "India" in country_list else country_list[0]

    # Use session state to persist selection if needed, but simple selectbox is usually fine
    country = st.selectbox(
        "Country",
        country_list,
        index=country_list.index(default_country),
    )

    # State Selection
    # Filter by country
    states_in_country = df_cities[df_cities["country"] == country]
    state_list = sorted(states_in_country["admin_name"].unique())
    state = st.selectbox("State", state_list)

    # City Selection
    # Filter by country and state
    cities_in_state = states_in_country[states_in_country["admin_name"] == state]
    city_list = sorted(cities_in_state["city_ascii"].unique())
    city = st.selectbox("City", city_list)

    # Get coordinates
    # We can rely on the fact that the filtered dataframe won't be empty for the selected city
    # because the lists differ based on selection.
    selected_city_data = cities_in_state[cities_in_state["city_ascii"] == city].iloc[0]

    return float(selected_city_data["lat"]), float(selected_city_data["lng"])


def display_map(center_lat: float, center_lng: float, zoom_start: int = 6) -> dict[str, Any]:
    """Display a Folium map with Google Satellite tiles.

    Args:
        center_lat: Center latitude for the map initialization.
        center_lng: Center longitude for the map initialization.
        zoom_start: Initial zoom level. Defaults to 6.

    Returns:
        Data returned by st_folium, containing map interaction details like center and zoom.
    """
    folium_map = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=zoom_start,
        tiles=None,  # Disable default OpenStreetMap tiles
    )

    # Add Google Satellite tiles
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        overlay=False,
        control=True,
    ).add_to(folium_map)

    # Return the map component
    return cast(
        dict[str, Any], st_folium(folium_map, returned_objects=["center", "zoom"], height=400)
    )


def create_scatter_map(df: pd.DataFrame) -> Any:
    """Create a Plotly scatter mapbox figure.

    Expected DataFrame columns:
        - latitude: float
        - longitude: float
        - scaled_rating: numeric (used for color scale)
        - description: str (used for hover text)

    Args:
        df: DataFrame containing the place data.

    Returns:
        The created scatter map figure.
        Returns None if the DataFrame is empty or missing required columns.
    """
    required_cols = {"latitude", "longitude", "scaled_rating", "description"}
    if df.empty or not required_cols.issubset(df.columns):
        return None

    fig = px.scatter_mapbox(
        df,
        lat="latitude",
        lon="longitude",
        color="scaled_rating",
        color_continuous_scale="ylorbr",
        # Take first 3 words of description for label
        text=df["description"].str.split().str[:3].str.join(sep=" "),
        zoom=10,
        mapbox_style="carto-positron",
    )
    return fig


def fetch_and_resize_image(url: str, size: int = 150) -> Image.Image | None:
    """Fetch an image from a URL and resize it to a square thumbnail.

    Uses a robust method to center-crop and resize the image to avoid
    distortion while filling the specified size.

    Args:
        url: Image URL.
        size: Target size for width and height (square) in pixels.

    Returns:
        Resized PIL Image object, or None if fetch fails.
    """
    if not url:
        return None

    try:
        # Append sizing parameters if it looks like a Google user content URL
        # and doesn't already have them.
        target_url = url
        if "googleusercontent" in url and "=" not in url.split("/")[-1]:
            target_url = f"{url}=w{size}-h{size}-k-no"

        response = requests.get(target_url, timeout=5)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            # Use ImageOps.fit for a smart center crop to square, avoiding distortion
            resized_img: Image.Image = ImageOps.fit(
                img, (size, size), method=Image.Resampling.LANCZOS
            )
            return resized_img
    except Exception:
        # Silently fail on network/image errors as this is a UI helper
        return None

    return None
