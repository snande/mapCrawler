"""Logging configuration and utilities.

This module sets up the logging configuration for the application and provides
a utility function to get loggers with consistent naming.
"""

import logging
import sys

from .config import get_settings


def configure_logging(level: str | None = None, format_string: str | None = None) -> None:
    """Configure logging for the application.

    This function configures the logging level and format. It prioritizes arguments
    passed to the function, then falls back to settings from configuration, and
    finally defaults to standard values.

    Args:
        level: Optional logging level (e.g., "DEBUG", "INFO").
        format_string: Optional logging format string.
    """
    settings = get_settings()

    log_level = level or settings.logging.level
    log_format = format_string or settings.logging.format

    # Set root logger configuration
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # Ensure configuration is applied even if basicConfig was called before
    )

    # Silence noisy loggers
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.info("Logging configured with level: %s", log_level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name.

    Args:
        name: The name of the logger.

    Returns:
        A logger instance.
    """
    return logging.getLogger(name)
