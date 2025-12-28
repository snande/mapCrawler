"""Pydantic models for the map_crawler package.

This module defines the data models used throughout the application to represent
places found on Google Maps and search history records. It uses Pydantic for
robust data validation and type checking.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Place(BaseModel):
    """Represents a single place found on Google Maps.

    This model encapsulates all the data extracted for a specific location,
    including its name, location, ratings, and various computed scores.

    Attributes:
        description: Name or description of the place.
        rating: Average rating of the place (0.0 to 5.0).
        raters: Number of people who rated the place.
        latitude: Latitude of the place (-90.0 to 90.0).
        longitude: Longitude of the place (-180.0 to 180.0).
        img_links: List of image URLs.
        price_val: Raw price value or estimate (aliased as 'price').
        price_level: Normalized price level (1-5 scale, 1=Cheap, 4=Expensive, can be None).
        review_url: URL to the reviews of the place.
        scaled_rating: Rating adjusted for number of raters (computed).
        dist: Distance from the search center (computed).
        scaled_dist_rating: Rating adjusted for distance (computed).
        vfm: Value for Money score (computed).
        composite: Composite score combining all factors (computed).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    description: str = Field(..., description="Name or description of the place.")
    rating: float = Field(..., ge=0.0, le=5.0, description="Average rating of the place (0-5).")
    raters: int = Field(
        ...,
        ge=0,
        description="Number of people who rated the place.",
    )
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude of the place.",
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude of the place.",
    )
    img_links: list[str] = Field(default_factory=list, description="List of image URLs.")
    price_val: float | None = Field(
        default=None, alias="price", description="Raw price value or estimate."
    )
    price_level: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Normalized price level (1-5 scale).",
    )
    review_url: str | None = Field(default=None, description="URL to the reviews of the place.")

    # Computed fields
    scaled_rating: float = Field(
        default=0.0, description="Rating adjusted for number of raters (0-1)."
    )
    dist: float = Field(default=0.0, description="Distance from the search center in km.")
    scaled_dist_rating: float = Field(
        default=0.0, description="Rating adjusted for distance (0-1)."
    )
    vfm: float = Field(default=0.0, description="Value for Money score (0-1).")
    composite: float = Field(
        default=0.0, description="Composite score combining all factors (0-1)."
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert the model to a dictionary using aliases.

        Returns:
            dict[str, Any]: A dictionary representation of the place.
        """
        return self.model_dump(by_alias=True)


class MasterSearchRecord(BaseModel):
    """Represents a record in the master search history.

    This model is used to track search queries and their locations to avoid
    redundant searches or to maintain a history of operations.

    Attributes:
        search_term: The search query used.
        latitude: Latitude of the search implementation.
        longitude: Longitude of the search implementation.
        timestamp: Time of the search (Unix timestamp).
        result_key: Key pointing to the stored result file.
    """

    search_term: str = Field(..., alias="Search", description="The search query used.")
    latitude: float = Field(
        ...,
        alias="Latitude",
        ge=-90.0,
        le=90.0,
        description="Latitude of the search center.",
    )
    longitude: float = Field(
        ...,
        alias="Longitude",
        ge=-180.0,
        le=180.0,
        description="Longitude of the search center.",
    )
    timestamp: float = Field(..., alias="Time", description="Time of the search (Unix timestamp).")
    result_key: str = Field(..., alias="Key", description="Key pointing to the stored result file.")
