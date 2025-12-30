"""Storage backend for the Map Crawler application.

This module provides the AzureStorage class which handles all interactions
with Azure Blob Storage, including uploading, downloading, and managing
search data.
"""

import logging
from io import BytesIO

import pandas as pd
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from map_crawler.config import DatabaseSettings

logger = logging.getLogger(__name__)


class AzureStorage:
    """Handles interactions with Azure Blob Storage.

    This class provides methods to upload and download blobs, as well as specific
    functionality to load the master search data.
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        """Initialize the storage client.

        Args:
            settings: DatabaseSettings configuration object containing
            Connection String and Container Name.
        """
        self.settings = settings
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                self.settings.connection_string
            )
            self.container_client = self.blob_service_client.get_container_client(
                container=self.settings.container_name
            )
        except Exception as exception:
            logger.error(f"Failed to initialize Azure Storage client: {exception}")
            raise

    def download_blob(self, blob_name: str) -> bytes:
        """Download a blob from the container.

        Args:
            blob_name: Name of the blob to download.

        Returns:
            The content of the blob as bytes.

        Raises:
            ResourceNotFoundError: If the blob does not exist.
        """
        try:
            return self.container_client.download_blob(blob_name).readall()
        except ResourceNotFoundError:
            logger.warning(f"Blob '{blob_name}' not found.")
            raise
        except Exception as exception:
            logger.error(f"Error downloading blob '{blob_name}': {exception}")
            raise

    def upload_blob(self, blob_name: str, data: str | bytes, overwrite: bool = True) -> None:
        """Upload data to a blob in the container.

        Args:
            blob_name: Name of the destination blob.
            data: Data to upload (can be string or bytes).
            overwrite: Whether to overwrite the existing blob if it exists. Defaults to True.
        """
        try:
            blob_client = self.container_client.get_blob_client(blob=blob_name)
            blob_client.upload_blob(data, overwrite=overwrite)
            logger.info(f"Successfully uploaded blob '{blob_name}'.")
        except Exception as exception:
            logger.error(f"Error uploading blob '{blob_name}': {exception}")
            raise

    def load_master_search_data(self) -> pd.DataFrame:
        """Load the master search file data into a pandas DataFrame.

        Returns:
            DataFrame containing search history with columns:
                - Search (str): The search term.
                - Latitude (float32): Latitude of the result.
                - Longitude (float32): Longitude of the result.
                - Time (float32): Timestamp of the search.
                - Key (str): Unique key for the search.
        """
        columns = ["Search", "Latitude", "Longitude", "Time", "Key"]
        try:
            data = self.download_blob(self.settings.master_search_file_name)
            return pd.read_json(
                BytesIO(data),
                dtype={
                    "Search": str,
                    "Latitude": "float32",
                    "Longitude": "float32",
                    "Time": "float32",
                    "Key": str,
                },
            )
        except ResourceNotFoundError:
            logger.warning(
                f"Master search file '{self.settings.master_search_file_name}' not found. \
                Returning empty DataFrame."
            )
            return pd.DataFrame(columns=columns)
        except Exception as exception:
            logger.error(f"Unexpected error loading master search data: {exception}")
            # Depending on business logic, we might want to raise this or return empty.
            # Returning empty allows the application to continue assuming a fresh start,
            # but logging the error is crucial.
            return pd.DataFrame(columns=columns)
