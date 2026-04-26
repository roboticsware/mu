"""
Firmware fetcher for the ESP Firmware Flasher.

Fetches MicroPython firmware information from Thonny's curated esptool
variants list and downloads .bin firmware files with progress reporting.

Supported boards are filtered to a curated set of commonly-used boards.
Additional boards can be added to SUPPORTED_BOARDS as needed.
"""
import logging
import os
import tempfile

import requests

logger = logging.getLogger(__name__)

# Thonny's curated list of MicroPython .bin variants for ESP boards
MICROPYTHON_VARIANTS_URL = (
    "https://raw.githubusercontent.com/thonny/thonny/master/data/micropython-variants-esptool.json"
)

# Curated set of commonly-used boards.
# Key: (vendor, model) from Thonny JSON
# Value: human-readable label shown in the UI
SUPPORTED_BOARDS = {
    ("Espressif", "ESP8266"):       "ESP8266 (Generic)",
    ("Espressif", "ESP32 / WROOM"): "ESP32 / WROOM (Generic)",
    ("Espressif", "ESP32-S2"):      "ESP32-S2 (Generic)",
    ("Espressif", "ESP32-S3"):      "ESP32-S3 (Generic)",
    ("Espressif", "ESP32-C3"):      "ESP32-C3 (Generic)",
    ("Espressif", "ESP32-C6"):      "ESP32-C6 (Generic)",
    ("M5Stack",   "Atom"):          "M5Stack Atom (ESP32)",
    ("Wemos",     "C3 mini"):       "Wemos C3 Mini",
    ("Wemos",     "S2 mini"):       "Wemos S2 Mini",
}


class EspFirmwareRelease:
    """Represents a single downloadable .bin firmware asset."""

    def __init__(self, label: str, family: str, version: str, url: str):
        self.label = label    # human-readable board label
        self.family = family  # e.g. "esp32", "esp8266", "esp32s3"
        self.tag = version    # e.g. "1.28.0"
        self.url = url        # direct .bin download URL

    def __str__(self):
        return "{} — v{} ({})".format(self.label, self.tag, os.path.basename(self.url))


class EspFirmwareFetcher:
    """
    Fetches MicroPython firmware releases from Thonny's esptool data
    and downloads selected .bin files.
    """

    def get_releases(self):
        """
        Query Thonny's esptool firmware metadata and return a filtered list
        of EspFirmwareRelease objects for supported boards only.

        :returns: List of EspFirmwareRelease objects.
        :raises: requests.RequestException on network error.
        """
        logger.info("Fetching MicroPython esptool variants from Thonny data…")
        response = requests.get(MICROPYTHON_VARIANTS_URL, timeout=10)
        response.raise_for_status()

        data = response.json()
        releases = []

        for variant in data:
            vendor = variant.get("vendor", "")
            model = variant.get("model", "")
            family = variant.get("family", "")
            label = SUPPORTED_BOARDS.get((vendor, model))

            if label:
                for download in variant.get("downloads", []):
                    version = download.get("version")
                    url = download.get("url")
                    if version and url and url.endswith(".bin"):
                        releases.append(
                            EspFirmwareRelease(
                                label=label,
                                family=family,
                                version=version,
                                url=url,
                            )
                        )

        logger.info("Found %d supported ESP firmware assets.", len(releases))
        return releases

    def download(self, url: str, progress_callback=None) -> str:
        """
        Download a .bin firmware file to a temporary path and return that path.

        :param url: Direct download URL of the .bin file.
        :param progress_callback: Optional callable(downloaded_bytes, total_bytes).
        :returns: Absolute path to the downloaded temporary file.
        :raises: requests.RequestException on network error.
        """
        logger.info("Downloading ESP firmware: %s", url)
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        fd, dest_path = tempfile.mkstemp(suffix=".bin", prefix="mu_esp_fw_")
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)
        except Exception:
            try:
                os.unlink(dest_path)
            except OSError:
                pass
            raise

        logger.info(
            "ESP firmware downloaded to: %s (%d bytes)", dest_path, downloaded
        )
        return dest_path
