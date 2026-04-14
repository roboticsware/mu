"""
Firmware fetcher for the Pico Firmware Flasher.

Fetches MicroPython firmware information from Thonny's curated variants list
and downloads .uf2 firmware files with progress reporting.
"""
import logging
import os
import tempfile

import requests

logger = logging.getLogger(__name__)

# Thonny's curated list of MicroPython UF2 variants
# This is much more reliable than parsing GitHub releases directly.
MICROPYTHON_VARIANTS_URL = (
    "https://raw.githubusercontent.com/thonny/thonny/master/data/micropython-variants-uf2.json"
)

class FirmwareRelease:
    """Represents a single downloadable firmware asset."""

    def __init__(self, version: str, board: str, url: str, size: int):
        self.tag = version  # For compatibility with UI
        self.board = board  # e.g. "Pico W"
        self.url = url      # Direct .uf2 download URL
        self.size = size    # bytes

    def __str__(self):
        return "{} — {} ({})".format(self.tag, self.board, os.path.basename(self.url))


class FirmwareFetcher:
    """
    Fetches MicroPython firmware releases from Thonny's data and downloads
    selected .uf2 files.
    """

    def get_releases(self):
        """
        Query Thonny's firmware metadata and return a list of FirmwareRelease objects.

        :returns: List of FirmwareRelease objects.
        :raises: requests.RequestException on network error.
        """
        logger.info("Fetching MicroPython variants from Thonny data…")
        response = requests.get(MICROPYTHON_VARIANTS_URL, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        releases = []
        
        # We are interested in RP2 (Pico) family
        # Mapping Thonny's vendor/model to our labels
        target_models = {
            ("Raspberry Pi", "Pico"): "Pico",
            ("Raspberry Pi", "Pico W"): "Pico W",
            ("Raspberry Pi", "Pico 2"): "Pico 2",
        }

        for variant in data:
            vendor = variant.get("vendor")
            model = variant.get("model")
            label = target_models.get((vendor, model))
            
            if label:
                for download in variant.get("downloads", []):
                    version = download.get("version")
                    url = download.get("url")
                    size = download.get("size", 0)
                    if version and url and url.endswith(".uf2"):
                        releases.append(
                            FirmwareRelease(
                                version=version,
                                board=label,
                                url=url,
                                size=size
                            )
                        )
        
        # Sort by version (descending) is ideal, but let's keep Thonny's order 
        # which usually has latest versions first or consistent grouping.
        logger.info("Found %d Pico-related firmware assets.", len(releases))
        return releases

    def download(self, url: str, progress_callback=None) -> str:
        """
        Download a firmware file to a temporary path and return that path.

        :param url: Direct download URL of the .uf2 file.
        :param progress_callback: Optional callable(downloaded_bytes, total_bytes).
        :returns: Absolute path to the downloaded temporary file.
        :raises: requests.RequestException on network error.
        """
        logger.info("Downloading firmware: %s", url)
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        # Use a named temp file so we can pass its path to the flasher
        suffix = ".uf2"
        fd, dest_path = tempfile.mkstemp(suffix=suffix, prefix="mu_pico_fw_")
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)
        except Exception:
            # Clean up on failure
            try:
                os.unlink(dest_path)
            except OSError:
                pass
            raise

        logger.info("Firmware downloaded to: %s (%d bytes)", dest_path, downloaded)
        return dest_path
