"""Utility functions for the map_crawler package."""


def generate_lat_long_grid(
    center_lat: float,
    center_lon: float,
    lat_step: float,
    lon_step: float,
    grid_radius: int = 3,
) -> list[tuple[float, float]]:
    """Generate a grid of latitude and longitude points around a center.

    This function creates a square grid of coordinates centered at the provided
    location. It is useful for generating search points to cover a specific area.

    Args:
        center_lat: The center latitude in degrees.
        center_lon: The center longitude in degrees.
        lat_step: The step size for latitude between grid points.
        lon_step: The step size for longitude between grid points.
        grid_radius: The number of steps to extend from the center in each
            direction. Defaults to 3, which creates a 7x7 grid (range -3 to +3).

    Returns:
        A list of (latitude, longitude) tuples representing the grid points.
    """
    # Range -grid_radius to +grid_radius inclusive
    return [
        (center_lat + i, center_lon + j)
        for i in [k * lat_step for k in range(-grid_radius, grid_radius + 1)]
        for j in [k * lon_step for k in range(-grid_radius, grid_radius + 1)]
    ]
