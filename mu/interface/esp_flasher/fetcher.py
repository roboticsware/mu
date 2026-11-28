"""
Firmware fetcher for the ESP Firmware Flasher.

Fetches MicroPython firmware information from Thonny's curated esptool
variants list, curated board lists, and optional custom JSON manifests or
GitHub Releases sources, and downloads .bin/.zip firmware files with
progress reporting.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile

import requests

logger = logging.getLogger(__name__)

# Thonny's curated list of MicroPython .bin variants for ESP boards
MICROPYTHON_VARIANTS_URL = (
    "https://raw.githubusercontent.com/thonny/thonny/master/data/micropython-variants-esptool.json"
)

# Optional built-in custom manifest URLs (e.g., TFLite-Micro / Edge Impulse builds)
CUSTOM_MANIFEST_URLS: list[str] = []

_GITHUB_WEB_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/releases(?:/.*)?)?/?$"
)
_GITHUB_API_RE = re.compile(
    r"^https?://api\.github\.com/repos/([^/]+)/([^/]+)/releases(?:/.*)?$"
)


def infer_chip_family(text: str, default: str = "esp32s3") -> str:
    """Infer an esptool chip family identifier from a filename, label, or URL."""
    raw_lower = (text or "").lower()
    compact = raw_lower.replace("-", "").replace("_", "")
    if "esp32s3" in compact or re.search(r"(^|[^a-z0-9])s3([^a-z0-9]|$)", raw_lower):
        return "esp32s3"
    if "esp32c6" in compact or re.search(r"(^|[^a-z0-9])c6([^a-z0-9]|$)", raw_lower):
        return "esp32c6"
    if "esp32c3" in compact or re.search(r"(^|[^a-z0-9])c3([^a-z0-9]|$)", raw_lower):
        return "esp32c3"
    if "esp32s2" in compact or re.search(r"(^|[^a-z0-9])s2([^a-z0-9]|$)", raw_lower):
        return "esp32s2"
    if "esp8266" in compact:
        return "esp8266"
    if "esp32" in compact:
        return "esp32"
    return default


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

# Curated camera-enabled MicroPython firmware list
# Sources: micropython-camera-API (v0.6.2 based on MicroPython v1.27.0)
CAMERA_BOARDS = [
    {
        "label": "ESP32-S3 Camera (OV2640 / Octal SPIRAM)",
        "family": "esp32s3",
        "version": "1.27.0 (cam)",
        "url": "https://github.com/cnadler86/micropython-camera-API/releases/download/v0.6.2/mpy_cam-v1.27.0-ESP32_GENERIC_S3-SPIRAM_OCT.zip",
    },
    {
        "label": "Freenove ESP32-S3 CAM (Camera)",
        "family": "esp32s3",
        "version": "1.27.0 (cam)",
        "url": "https://github.com/cnadler86/micropython-camera-API/releases/download/v0.6.2/mpy_cam-v1.27.0-FREENOVE_ESP32S3_CAM.zip",
    },
    {
        "label": "AI-Thinker ESP32-CAM (Camera)",
        "family": "esp32",
        "version": "1.27.0 (cam)",
        "url": "https://github.com/cnadler86/micropython-camera-API/releases/download/v0.6.2/mpy_cam-v1.27.0-AI_THINKER.zip",
    },
    {
        "label": "Seeed XIAO ESP32-S3 Sense (Camera)",
        "family": "esp32s3",
        "version": "1.27.0 (cam)",
        "url": "https://github.com/cnadler86/micropython-camera-API/releases/download/v0.6.2/mpy_cam-v1.27.0-XIAO_ESP32S3.zip",
    },
    {
        "label": "M5Stack Unit CAM (Camera)",
        "family": "esp32",
        "version": "1.27.0 (cam)",
        "url": "https://github.com/cnadler86/micropython-camera-API/releases/download/v0.6.2/mpy_cam-v1.27.0-M5STACK_UNITCAM.zip",
    },
]


class EspFirmwareRelease:
    """Represents a single downloadable .bin or .zip firmware asset."""

    def __init__(
        self,
        label: str,
        family: str,
        version: str,
        url: str,
        flash_offset: str = "",
    ):
        self.label = label              # human-readable board label
        self.family = family            # e.g. "esp32", "esp8266", "esp32s3"
        self.tag = version              # e.g. "1.28.0"
        self.url = url                  # direct .bin or .zip download URL
        self.flash_offset = flash_offset

    def __str__(self):
        return "{} — v{} ({})".format(
            self.label, self.tag, os.path.basename(self.url.split("?")[0])
        )


class EspFirmwareFetcher:
    """
    Fetches MicroPython firmware releases from Thonny's esptool data,
    custom JSON manifests, or GitHub Releases, and downloads .bin/.zip files.
    """

    def get_custom_releases(self, source_url: str) -> list[EspFirmwareRelease]:
        """
        Fetch custom firmware releases from a GitHub repo/releases URL or
        a custom JSON manifest URL.
        """
        url = (source_url or "").strip()
        if not url:
            return []

        web_match = _GITHUB_WEB_RE.match(url)
        api_match = _GITHUB_API_RE.match(url)
        if web_match or api_match:
            if web_match:
                owner, repo = web_match.groups()
                api_url = (
                    "https://api.github.com/repos/{}/{}/releases?per_page=10"
                ).format(owner, repo)
            else:
                owner, repo = api_match.groups()
                api_url = url
            resp = requests.get(
                api_url,
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict):
                payload = [payload]

            releases: list[EspFirmwareRelease] = []
            for rel in payload:
                tag = rel.get("tag_name") or rel.get("name") or "custom"
                for asset in rel.get("assets", []):
                    asset_name = asset.get("name", "")
                    download_url = asset.get("browser_download_url", "")
                    if not download_url:
                        continue
                    if not asset_name.lower().endswith((".bin", ".zip")):
                        continue
                    family = infer_chip_family(asset_name + " " + tag)
                    label = "{} ({}/{})".format(
                        family.upper(), owner, repo
                    )
                    releases.append(
                        EspFirmwareRelease(
                            label=label,
                            family=family,
                            version=tag,
                            url=download_url,
                        )
                    )
            return releases

        # Treat as JSON manifest URL
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("firmwares", []) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return []

        releases = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            item_url = (item.get("url") or "").strip()
            if not item_url:
                continue
            label = item.get("label") or item.get("name") or "Custom Firmware"
            version = str(item.get("version") or "custom")
            family = (
                item.get("family")
                or infer_chip_family(label + " " + item_url)
            )
            flash_offset = str(item.get("flash_offset") or "")
            releases.append(
                EspFirmwareRelease(
                    label=label,
                    family=family,
                    version=version,
                    url=item_url,
                    flash_offset=flash_offset,
                )
            )
        return releases

    def get_releases(self, custom_urls=None):
        """
        Query Thonny's esptool firmware metadata, curated boards, and any
        configured custom manifest URLs.

        :returns: List of EspFirmwareRelease objects.
        :raises: requests.RequestException on primary network error.
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

        # Add camera-enabled MicroPython firmware releases
        for cam in CAMERA_BOARDS:
            releases.append(
                EspFirmwareRelease(
                    label=cam["label"],
                    family=cam["family"],
                    version=cam["version"],
                    url=cam["url"],
                )
            )

        # Load configured custom manifests (failures here should not block official list)
        sources = list(CUSTOM_MANIFEST_URLS)
        env_url = os.environ.get("MU_ESP_CUSTOM_MANIFEST_URL", "").strip()
        if env_url:
            sources.append(env_url)
        if custom_urls:
            sources.extend(custom_urls)

        for src_url in sources:
            try:
                releases.extend(self.get_custom_releases(src_url))
            except Exception as exc:
                logger.warning("Failed to load custom manifest %s: %s", src_url, exc)

        logger.info("Found %d supported ESP firmware assets.", len(releases))
        return releases

    def download(self, url: str, progress_callback=None) -> str:
        """
        Download a .bin or .zip firmware file to a temporary path and return that path.
        .zip archives are kept intact so EspFlasher.write() can resolve single or
        multi-part images inside them.

        :param url: Direct download URL of the .bin or .zip file.
        :param progress_callback: Optional callable(downloaded_bytes, total_bytes).
        :returns: Absolute path to the downloaded temporary .bin or .zip file.
        :raises: requests.RequestException on network error.
        """
        logger.info("Downloading ESP firmware: %s", url)
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        is_zip = url.split("?")[0].lower().endswith(".zip")
        suffix = ".zip" if is_zip else ".bin"

        fd, dest_path = tempfile.mkstemp(suffix=suffix, prefix="mu_esp_fw_")
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
