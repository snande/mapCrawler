"""Tests for utility functions in map_crawler."""

from map_crawler.utils import generate_lat_long_grid


def test_generate_lat_long_grid() -> None:
    """Test generating a grid of coordinates around a center point."""
    grid = generate_lat_long_grid(0, 0, 1, 1)
    # Range -3 to 3 inclusive is 7 points. 7x7 = 49 points.
    assert len(grid) == 49
    assert (0, 0) in grid
