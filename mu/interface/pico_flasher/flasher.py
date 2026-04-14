"""
Pico drive detector and UF2 flasher.

Detects the RPI-RP2 / RP2350 BOOTSEL drive across macOS, Windows, and Linux,
then copies a .uf2 file onto it to flash the Pico.
"""
import ctypes
import logging
import os
import platform
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Volume names that indicate BOOTSEL mode
BOOTSEL_VOLUME_NAMES = ("RPI-RP2", "RP2350")


class PicoDriveDetector:
    """Finds the Pico BOOTSEL drive across different operating systems."""

    def find_drive(self) -> Optional[Path]:
        """
        Return the Path to the mounted Pico BOOTSEL drive, or None if not found.
        """
        system = platform.system()
        if system == "Darwin":
            return self._find_macos()
        elif system == "Windows":
            return self._find_windows()
        elif system == "Linux":
            return self._find_linux()
        else:
            logger.warning("Unsupported OS: %s", system)
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_macos(self) -> Optional[Path]:
        volumes_root = Path("/Volumes")
        for vol_name in BOOTSEL_VOLUME_NAMES:
            candidate = volumes_root / vol_name
            if candidate.is_dir():
                logger.info("Found Pico drive at: %s", candidate)
                return candidate
        return None

    def _find_windows(self) -> Optional[Path]:
        # Iterate drive letters and check volume name via Win32 API
        try:
            vol_name_buf = ctypes.create_unicode_buffer(1024)
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                drive = "{}:\\".format(letter)
                if not os.path.exists(drive):
                    continue
                ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(drive),
                    vol_name_buf,
                    ctypes.sizeof(vol_name_buf),
                    None, None, None, None, 0,
                )
                if vol_name_buf.value in BOOTSEL_VOLUME_NAMES:
                    result = Path(drive)
                    logger.info("Found Pico drive at: %s", result)
                    return result
        except Exception as exc:
            logger.error("Error scanning Windows drives: %s", exc)
        return None

    def _find_linux(self) -> Optional[Path]:
        # Common mount points on Linux / ChromeOS
        search_roots = [
            Path("/media"),
            Path("/mnt"),
            Path("/run/media"),
        ]
        for root in search_roots:
            if not root.is_dir():
                continue
            # /media/<user>/<VOL> or /media/<VOL>
            for candidate in root.rglob("*"):
                if candidate.name in BOOTSEL_VOLUME_NAMES and candidate.is_dir():
                    logger.info("Found Pico drive at: %s", candidate)
                    return candidate
        return None


class PicoFlasher:
    """Copies a .uf2 firmware file onto the Pico BOOTSEL drive."""

    def flash(self, uf2_path: str, drive_path: Path) -> None:
        """
        Copy *uf2_path* into *drive_path*.

        The Pico will automatically detect the file, flash it, and reboot.
        shutil.copy (not copy2) is used deliberately: copy2 tries to preserve
        file metadata which fails on FAT32 (Pico BOOTSEL drive) on macOS.

        :raises: OSError / shutil.Error on failure — let the caller report it.
        """
        dest = drive_path / os.path.basename(uf2_path)
        logger.info("Flashing %s → %s", uf2_path, dest)
        # shutil.copy: copies data + permissions but NOT timestamps.
        # This avoids the "Operation not supported" error on FAT32 volumes.
        shutil.copy(uf2_path, str(dest))
        logger.info("Flash copy complete.")
